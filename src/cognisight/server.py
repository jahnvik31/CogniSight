"""The caregiver dashboard's API, the camera stream, and the built Solid app.

The routes are described in docs/API.md.
"""

from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

from cognisight.faces import PHOTO_TYPES, NoFaceError, person_name
from cognisight.runtime import CameraUnavailable

MAX_UPLOAD_BYTES = 15 * 1024 * 1024


def create_app(gallery, runtime, locator=None, static_dir=None):
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

    def person_json(person):
        return {
            "name": person.name,
            "relationship": person.relationship,
            "note": person.note,
            "photos": person.photos,
            "last_seen": runtime.last_seen(person.name),
        }

    def error(message, status):
        return jsonify(error=message), status

    def photo_bytes():
        """(bytes, suffix) from an upload, or from the camera when none was sent."""
        upload = request.files.get("photo")
        if upload is not None and upload.filename:
            suffix = Path(upload.filename).suffix.lower()
            if suffix not in PHOTO_TYPES:
                raise ValueError("Use a JPG, PNG, or WebP photo.")
            data = upload.read()
            if not data:
                raise ValueError("That photo is empty.")
            return data, suffix, "photo"
        return runtime.capture(), ".jpg", "capture"

    @app.errorhandler(413)
    def too_large(_):
        return error("That photo is larger than 15 MB. Use a smaller one.", 413)

    # ------------------------------------------------------------ live

    @app.get("/api/live")
    def live():
        return jsonify(runtime.live())

    @app.get("/api/events")
    def events():
        try:
            limit = int(request.args.get("limit", 50))
        except ValueError:
            limit = 50
        return jsonify(events=runtime.events(limit))

    @app.get("/stream.mjpg")
    def stream():
        if runtime.snapshot() is None:
            return error("The camera is not running.", 503)

        def generate():
            for jpeg in runtime.frames():
                yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n"

        response = Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/snapshot.jpg")
    def snapshot():
        jpeg = runtime.snapshot()
        if jpeg is None:
            return error("The camera is not running.", 503)
        return Response(jpeg, mimetype="image/jpeg", headers={"Cache-Control": "no-store"})

    # ------------------------------------------------------------ device

    @app.get("/api/status")
    def status():
        return jsonify(runtime.status())

    @app.post("/api/speech")
    def speech():
        body = request.get_json(silent=True) or {}
        return jsonify(runtime.set_speech(bool(body.get("enabled"))))

    @app.post("/api/speech/test")
    def speech_test():
        body = request.get_json(silent=True) or {}
        text = body.get("text") if isinstance(body.get("text"), str) else None
        ok = runtime.test_speech(text[:200] if text else None)
        if not ok:
            return error(runtime.speech_status()["error"] or "Speech did not play.", 503)
        return jsonify(ok=True)

    @app.post("/api/listening")
    def listening():
        body = request.get_json(silent=True) or {}
        return jsonify(runtime.set_listening(bool(body.get("enabled"))))

    # ------------------------------------------------------------ people

    @app.get("/api/people")
    def people():
        return jsonify(people=[person_json(p) for p in gallery.people()])

    @app.post("/api/people")
    def create_person():
        try:
            name = person_name(request.form.get("name", ""))
        except ValueError as exc:
            return error(str(exc), 400)
        try:
            data, suffix, stem = photo_bytes()
        except ValueError as exc:
            return error(str(exc), 400)
        except CameraUnavailable as exc:
            return error("Could not take a photo: {}".format(exc), 503)
        try:
            gallery.create(name, request.form.get("relationship", ""), request.form.get("note", ""))
        except FileExistsError as exc:
            return error(str(exc), 409)
        try:
            gallery.add_photo(name, data, suffix, stem)
        except Exception as exc:
            gallery.delete(name)
            if isinstance(exc, NoFaceError):
                return error(str(exc), 400)
            return error("Could not read that photo: {}".format(exc), 400)
        return jsonify(person_json(gallery.get(name))), 201

    @app.get("/api/people/<name>")
    def get_person(name):
        try:
            return jsonify(person_json(gallery.get(name)))
        except (KeyError, ValueError):
            return error("That person is not saved.", 404)

    @app.patch("/api/people/<name>")
    def update_person(name):
        body = request.get_json(silent=True) or {}
        try:
            person = gallery.update(
                name,
                relationship=body.get("relationship") if isinstance(body.get("relationship"), str) else None,
                note=body.get("note") if isinstance(body.get("note"), str) else None,
            )
        except (KeyError, ValueError):
            return error("That person is not saved.", 404)
        return jsonify(person_json(person))

    @app.delete("/api/people/<name>")
    def delete_person(name):
        try:
            gallery.delete(name)
        except (KeyError, ValueError):
            return error("That person is not saved.", 404)
        return "", 204

    @app.post("/api/people/<name>/photos")
    def add_photo(name):
        try:
            gallery.get(name)
        except (KeyError, ValueError):
            return error("That person is not saved.", 404)
        try:
            data, suffix, stem = photo_bytes()
            gallery.add_photo(name, data, suffix, stem)
        except CameraUnavailable as exc:
            return error("Could not take a photo: {}".format(exc), 503)
        except NoFaceError as exc:
            return error(str(exc), 400)
        except ValueError as exc:
            return error(str(exc), 400)
        except Exception as exc:
            return error("Could not read that photo: {}".format(exc), 400)
        return jsonify(person_json(gallery.get(name))), 201

    @app.get("/api/people/<name>/photos/<filename>")
    def photo(name, filename):
        try:
            path = gallery.photo_path(name, filename)
        except (KeyError, ValueError):
            return error("That photo is not saved.", 404)
        return send_from_directory(path.parent, path.name, max_age=3600)

    @app.delete("/api/people/<name>/photos/<filename>")
    def delete_photo(name, filename):
        try:
            gallery.delete_photo(name, filename)
        except (KeyError, ValueError):
            return error("That photo is not saved.", 404)
        return "", 204

    # ------------------------------------------------------------ location

    @app.get("/api/location")
    def location():
        if locator is None:
            return error("Location is not available.", 503)
        return jsonify(locator.current())

    @app.post("/api/location/refresh")
    def location_refresh():
        if locator is None:
            return error("Location is not available.", 503)
        return jsonify(locator.current(force=True))

    @app.route("/api/<path:_>", methods=["GET", "POST", "PATCH", "DELETE"])
    def unknown_api(_):
        return error("No such API route.", 404)

    # ------------------------------------------------------------ dashboard

    if static_dir is not None:
        assets = Path(static_dir)

        @app.get("/", defaults={"path": ""})
        @app.get("/<path:path>")
        def frontend(path):
            candidate = (assets / path).resolve()
            if path and candidate.is_file() and assets.resolve() in candidate.parents:
                return send_from_directory(assets, path)
            response = send_from_directory(assets, "index.html")
            response.headers["Cache-Control"] = "no-cache"
            return response

    return app


def serve(app, host, port):
    from werkzeug.serving import make_server

    server = make_server(host, port, app, threaded=True)
    server.serve_forever()
