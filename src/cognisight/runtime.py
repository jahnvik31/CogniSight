"""The running device: camera, recognition, speech, and what happened.

Three background threads share this object:

* camera: reads frames as fast as the camera gives them and keeps the newest
  one, plus a JPEG with boxes drawn on it for the dashboard stream;
* recognition: takes the newest frame, names the faces in it, and tells the
  announcer;
* signs: reads printed sign markers in the newest frame and moves the
  navigator (where the wearer is, and any trip in progress);
* voice: loads speech (and optionally listening) without blocking start-up.

Nothing here raises when the camera, DeepFace, or audio is missing. Each part
reports its error in ``status()`` and keeps retrying where that makes sense.
"""

from collections import deque
import itertools
import socket
import threading
import time

from cognisight.camera import open_camera
from cognisight.faces import DETECTOR, MODEL
from cognisight.signs import MarkerDetector, Navigator, the
from cognisight.voice import Announcer, Listener, NullSpeaker, load_speaker, parse_command

SEEN_GAP_SECONDS = 30
KNOWN_COLOR = (79, 107, 47)  # BGR moss
UNKNOWN_COLOR = (22, 138, 201)  # BGR marigold
SIGN_COLOR = (138, 95, 47)  # BGR of the dashboard's route blue, #2F5F8A
SIGN_INTERVAL = 0.25


class CameraUnavailable(RuntimeError):
    pass


class Runtime:
    def __init__(
        self,
        gallery,
        signs=None,
        camera_factory=open_camera,
        speaker_factory=load_speaker,
        listener_factory=Listener,
        interval=0.5,
        port=8765,
        speech=True,
        listen=True,
        listen_model="tiny",
    ):
        self.gallery = gallery
        self.signs = signs
        self.port = port
        self.interval = interval
        self._camera_factory = camera_factory
        self._speaker_factory = speaker_factory
        self._listener_factory = listener_factory
        self._listen_model = listen_model
        self._want_speech = speech
        self._want_listen = listen

        self._started = time.time()
        self._stop = threading.Event()
        self._recognition_loaded = threading.Event()
        self._lock = threading.Lock()
        self._frame_ready = threading.Condition(self._lock)
        self._frame = None
        self._jpeg = None
        self._frame_number = 0
        self._camera = None
        self._camera_error = "Starting the camera…"

        self._faces = []
        self._updated = None
        self._recognition_error = "Loading face recognition…"
        self._recognition_ok = False
        self._seconds_per_check = None

        self._events = deque(maxlen=300)
        self._event_ids = itertools.count(1)
        self._last_seen = {}
        self._last_unknown = 0.0
        self._said = None
        self._heard = None

        self.announcer = Announcer(NullSpeaker("Loading speech…"), on_said=self._record_said)
        self.announcer.enabled = speech
        self._listener = None
        self._listen_error = "Loading listening…" if listen else "Listening is off."
        self._listening = False

        self._markers = []
        self._signs_error = None
        self.navigator = None
        if signs is not None:
            self.navigator = Navigator(
                signs, say=self.announcer.say, event=self.event, can_speak=self.announcer.can_speak
            )

    # ------------------------------------------------------------ lifecycle

    def start(self):
        # numpy and OpenCV break when two threads import them at the same
        # time, so load them here before any thread starts.
        for module in ("numpy", "cv2"):
            try:
                __import__(module)
            except ImportError:
                pass
        for target in (self._camera_loop, self._recognition_loop, self._sign_loop, self._voice_setup):
            threading.Thread(target=target, daemon=True, name=target.__name__).start()
        self.event("system", None, "CogniSight started")
        return self

    def close(self):
        self._stop.set()
        if self._listener:
            try:
                self._listener.close()
            except Exception:
                pass
        with self._lock:
            camera, self._camera = self._camera, None
        if camera:
            try:
                camera.close()
            except Exception:
                pass

    # ------------------------------------------------------------ camera

    def _camera_loop(self):
        while not self._stop.is_set():
            if self._camera is None:
                try:
                    camera = self._camera_factory()
                except Exception as exc:
                    self._camera_error = "Camera not found: {}".format(exc)
                    self._stop.wait(5)
                    continue
                with self._lock:
                    self._camera = camera
                    self._camera_error = None
                self.event("system", None, "Camera ready ({})".format(getattr(camera, "label", "camera")))
            try:
                frame = self._camera.read()
            except Exception as exc:
                self._camera_error = "Camera stopped: {}".format(exc)
                self.event("system", None, "Camera stopped. Retrying.")
                with self._lock:
                    camera, self._camera = self._camera, None
                try:
                    camera.close()
                except Exception:
                    pass
                self._stop.wait(2)
                continue
            jpeg = self._annotate(frame)
            with self._frame_ready:
                self._frame = frame
                self._jpeg = jpeg
                self._frame_number += 1
                self._frame_ready.notify_all()

    def _annotate(self, frame):
        try:
            import cv2
        except ImportError:
            return None
        image = frame.copy()
        with self._lock:
            faces = list(self._faces)
            markers = list(self._markers)
        for marker in markers:
            points = [(int(x), int(y)) for x, y in marker["corners"]]
            for i in range(4):
                cv2.line(image, points[i], points[(i + 1) % 4], SIGN_COLOR, 3)
            label = marker["name"]
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
            x = min(p[0] for p in points)
            y = max(p[1] for p in points) + 6
            cv2.rectangle(image, (x - 2, y), (x + tw + 14, y + th + 14), SIGN_COLOR, -1)
            cv2.putText(image, label, (x + 6, y + th + 6), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
        for face in faces:
            x, y, w, h = face.box
            color = KNOWN_COLOR if face.name else UNKNOWN_COLOR
            label = face.name or "Unknown"
            cv2.rectangle(image, (x, y), (x + w, y + h), color, 3)
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
            top = max(y - th - 14, 0)
            cv2.rectangle(image, (x - 2, top), (x + tw + 14, top + th + 14), color, -1)
            cv2.putText(image, label, (x + 6, top + th + 6), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
        ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return encoded.tobytes() if ok else None

    def frames(self):
        """Yield annotated JPEGs as they arrive, for the MJPEG stream."""
        last = -1
        while not self._stop.is_set():
            with self._frame_ready:
                self._frame_ready.wait_for(lambda: self._frame_number != last or self._stop.is_set(), timeout=5)
                if self._jpeg is None or self._camera is None:
                    return
                last = self._frame_number
                jpeg = self._jpeg
            yield jpeg

    def snapshot(self):
        with self._lock:
            return self._jpeg if self._camera is not None else None

    def capture(self):
        """A clean JPEG of the current frame, for enrolling a person."""
        try:
            import cv2
        except ImportError as exc:
            raise CameraUnavailable("OpenCV is not installed.") from exc
        with self._lock:
            frame = None if self._camera is None or self._frame is None else self._frame.copy()
        if frame is None:
            raise CameraUnavailable(self._camera_error or "The camera is not running.")
        ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
        if not ok:
            raise CameraUnavailable("Could not encode the camera frame.")
        return encoded.tobytes()

    # ------------------------------------------------------------ recognition

    def _recognition_loop(self):
        try:
            self.gallery.embedder.load()
            self.gallery.refresh()
            self._recognition_ok = True
            self._recognition_error = None
            self.event("system", None, "Face recognition ready")
        except Exception as exc:
            self._recognition_error = str(exc)
            self.event("system", None, "Face recognition could not start: {}".format(exc))
            return
        finally:
            self._recognition_loaded.set()
        last = -1
        while not self._stop.is_set():
            with self._frame_ready:
                self._frame_ready.wait_for(lambda: self._frame_number != last or self._stop.is_set(), timeout=2)
                frame = self._frame
                last = self._frame_number
            if frame is None:
                continue
            started = time.monotonic()
            try:
                faces = self.gallery.identify(frame)
                self._recognition_error = None
            except Exception as exc:
                self._recognition_error = "Recognition failed: {}".format(exc)
                faces = []
            elapsed = time.monotonic() - started
            self._seconds_per_check = round(elapsed, 2)
            with self._lock:
                self._faces = faces
                self._updated = time.time()
            self._after_recognition(faces)
            self._stop.wait(max(self.interval - elapsed, 0.05))

    def _after_recognition(self, faces):
        now = time.time()
        people = {}
        if any(face.name for face in faces):
            people = {person.name: person for person in self.gallery.people()}
        for face in faces:
            if face.name:
                person = people.get(face.name)
                previous = self._last_seen.get(face.name, 0)
                self._last_seen[face.name] = now
                if now - previous > SEEN_GAP_SECONDS:
                    self.event("seen", face.name, "{} is in view".format(face.name))
                self.announcer.seen(face.name, person.relationship if person else "")
            elif now - self._last_unknown > SEEN_GAP_SECONDS:
                self.event("unknown", None, "Someone they don't know is in view")
            if not face.name:
                self._last_unknown = now

    def in_view(self):
        with self._lock:
            names = {face.name for face in self._faces if face.name}
        return [person for person in self.gallery.people() if person.name in names]

    # ------------------------------------------------------------ signs

    def _sign_loop(self):
        if self.navigator is None:
            return
        try:
            detector = MarkerDetector()
        except Exception as exc:
            self._signs_error = "Signs need OpenCV with the ArUco module: {}".format(exc)
            self.event("system", None, self._signs_error)
            return
        last = -1
        while not self._stop.is_set():
            with self._frame_ready:
                self._frame_ready.wait_for(lambda: self._frame_number != last or self._stop.is_set(), timeout=2)
                frame = self._frame
                last = self._frame_number
            if frame is None:
                continue
            try:
                found = detector.detect(frame)
                self._signs_error = None
            except Exception as exc:
                self._signs_error = "Reading signs failed: {}".format(exc)
                found = []
            markers = []
            for sign_id, corners in found:
                sign = self.signs.get(sign_id)
                if sign is not None:
                    markers.append({"id": sign_id, "name": sign["name"], "corners": corners})
            with self._lock:
                self._markers = markers
            self.navigator.seen([marker["id"] for marker in markers])
            self._stop.wait(SIGN_INTERVAL)

    def markers(self):
        with self._lock:
            return list(self._markers)

    # ------------------------------------------------------------ voice

    def _voice_setup(self):
        # Load speech after TensorFlow has finished importing; two large
        # libraries importing at once on the Pi is slow and fragile.
        self._recognition_loaded.wait(timeout=180)
        speaker = self._speaker_factory()
        self.announcer.speaker = speaker
        if speaker.available:
            self.event("system", None, "Speech ready")
        else:
            self.event("system", None, "Speech unavailable: {}".format(speaker.error))
        if self._want_listen:
            self.set_listening(True)

    def _record_said(self, text):
        self._said = {"text": text, "at": time.time()}
        self.event("said", None, text)

    def _on_heard(self, text):
        command = parse_command(text)
        # Over a loudspeaker the microphone hears the device itself ("Let's go
        # to the bathroom" sounds like a request). While it is talking, only
        # "stop" counts.
        talking = getattr(self.announcer.speaker, "is_talking", lambda: False)
        try:
            busy = bool(talking())
        except Exception:
            busy = False
        if busy and command != "stop":
            return
        if command == "go" or (command is None and "where am i" in text.lower()):
            self._navigate_by_voice(text)
            command = command or "where"
        elif command == "stop":
            self.announcer.handle(text, [])
            if self.navigator is not None and self.navigator.guide is not None:
                self.navigator.stop("Stopped guiding when asked")
        else:
            command = self.announcer.handle(text, self.in_view())
        if command:
            self._heard = {"text": text.strip(), "at": time.time()}
            self.event("heard", None, "Heard “{}”".format(text.strip()))

    def _navigate_by_voice(self, text):
        if self.navigator is None:
            return
        if "where am i" in text.lower():
            room = self.navigator.state()["room"]
            if room and time.time() - room["seen_at"] <= 300:
                self.announcer.say("You're in {}.".format(the(room["name"])))
            else:
                self.announcer.say("I'm not sure. Look around for a sign on the wall.")
            return
        sign = self.signs.find_destination(text)
        if sign is None:
            names = ", ".join(s["name"] for s in self.signs.signs()[:6])
            self.announcer.say(
                "I don't know that room. I know {}.".format(names) if names else "I don't know any rooms yet."
            )
            return
        self.navigator.start(sign["id"])

    def set_speech(self, enabled):
        self.announcer.enabled = bool(enabled)
        if not enabled:
            self.announcer.stop()
        self.event("system", None, "Speech turned {}".format("on" if enabled else "off"))
        return self.speech_status()

    def test_speech(self, text=None):
        was = self.announcer.enabled
        self.announcer.enabled = True
        try:
            self.announcer.say(text or "Hello. CogniSight speech is working.")
        finally:
            self.announcer.enabled = was
        return bool(self.announcer.speaker.available) and self.announcer.error is None

    def set_listening(self, enabled):
        if enabled and not self._listening:
            try:
                if self._listener is None:
                    self._listener = self._listener_factory(self._on_heard, model=self._listen_model)
                self._listener.start()
                self._listening = True
                self._listen_error = None
                self.event("system", None, "Listening for “stop” and “who is this”")
            except Exception as exc:
                self._listener = None
                self._listen_error = "Listening unavailable: {}".format(exc)
        elif not enabled and self._listening:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listening = False
            self._listen_error = None
        return self.listening_status()

    # ------------------------------------------------------------ reporting

    def event(self, kind, name, text):
        with self._lock:
            self._events.appendleft(
                {"id": next(self._event_ids), "kind": kind, "name": name, "text": text, "at": time.time()}
            )

    def events(self, limit=50):
        with self._lock:
            return list(itertools.islice(self._events, max(1, min(int(limit), 300))))

    def last_seen(self, name):
        return self._last_seen.get(name)

    def live(self):
        with self._lock:
            faces = list(self._faces)
            frame = self._frame
            camera = self._camera is not None
            updated = self._updated
        relationships = {}
        if any(face.name for face in faces):
            relationships = {p.name: p.relationship for p in self.gallery.people()}
        height, width = (frame.shape[:2] if frame is not None else (None, None))
        return {
            "camera": camera,
            "frame": {"width": width, "height": height},
            "faces": [
                {
                    "name": face.name,
                    "relationship": relationships.get(face.name) if face.name else None,
                    "distance": face.distance,
                    "box": list(face.box),
                }
                for face in faces
            ],
            "updated": updated,
            "said": self._said,
            **self.home_state(),
            "markers": [{"id": m["id"], "name": m["name"], "corners": m["corners"]} for m in self.markers()],
        }

    def home_state(self):
        if self.navigator is None:
            return {"room": None, "guide": None}
        return self.navigator.state()

    def speech_status(self):
        speaker = self.announcer.speaker
        return {
            "available": bool(speaker.available),
            "enabled": self.announcer.enabled,
            "error": self.announcer.error or speaker.error,
        }

    def listening_status(self):
        return {
            "available": self._listener is not None,
            "enabled": self._listening,
            "error": self._listen_error,
            "heard": self._heard,
        }

    def status(self):
        camera = self._camera
        return {
            "hostname": socket.gethostname(),
            "urls": device_urls(self.port),
            "uptime": round(time.time() - self._started, 1),
            "camera": {
                "ok": camera is not None,
                "label": getattr(camera, "label", None),
                "kind": getattr(camera, "kind", None),
                "error": None if camera is not None else self._camera_error,
            },
            "recognition": {
                "ok": self._recognition_ok and self._recognition_error is None,
                "model": MODEL,
                "detector": getattr(self.gallery.embedder, "detector", DETECTOR),
                "threshold": self.gallery.threshold,
                "seconds_per_check": self._seconds_per_check,
                "error": self._recognition_error,
            },
            "speech": self.speech_status(),
            "listening": self.listening_status(),
            "people": len(self.gallery.people()),
            "signs": {
                "ok": self.navigator is not None and self._signs_error is None,
                "count": len(self.signs.signs()) if self.signs is not None else 0,
                "error": self._signs_error,
            },
        }


def device_urls(port):
    urls = []
    hostname = socket.gethostname()
    if hostname and hostname != "localhost":
        urls.append("http://{}.local:{}".format(hostname, port))
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("10.255.255.255", 1))  # no packet is sent
            address = probe.getsockname()[0]
        finally:
            probe.close()
        if address and not address.startswith("127."):
            urls.append("http://{}:{}".format(address, port))
    except OSError:
        pass
    return urls
