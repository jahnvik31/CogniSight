"""cognisight start | camera | enroll | identify | download"""

import argparse
import os
from pathlib import Path
import sys

from cognisight.faces import DETECTOR, REPO_ROOT, THRESHOLD, DeepFaceEmbedder, Gallery

DEFAULT_GALLERY = REPO_ROOT / "data" / "faces"
WEB_DIST = REPO_ROOT / "web" / "dist"


def load_env(path=REPO_ROOT / ".env"):
    """Read KEY=value lines into the environment without overriding it."""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def main(argv=None):
    parser = argparse.ArgumentParser(prog="cognisight", description="CogniSight on the Raspberry Pi")
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--gallery", type=Path, default=DEFAULT_GALLERY, help="Folder of people (default: data/faces)")
    shared.add_argument("--threshold", type=float, default=THRESHOLD, help="Cosine distance cutoff (default: 0.30)")
    shared.add_argument("--detector", default=DETECTOR, help="DeepFace face detector (default: opencv)")
    commands = parser.add_subparsers(dest="command", required=True)

    start = commands.add_parser("start", parents=[shared], help="Run the camera, recognition, speech, and dashboard")
    start.add_argument("--host", default="0.0.0.0")
    start.add_argument("--port", type=int, default=8765)
    start.add_argument("--camera", type=int, default=0, help="USB camera number, used only when no Pi camera is present")
    start.add_argument("--flip", action="store_true", help="Rotate the camera picture 180 degrees")
    start.add_argument("--swap-colors", action="store_true", help="Swap red and blue if faces look blue")
    start.add_argument("--interval", type=float, default=0.5, help="Seconds between recognition checks")
    start.add_argument("--no-speech", action="store_true", help="Start with speech off")
    start.add_argument("--no-listen", action="store_true", help="Do not listen for voice commands")
    start.add_argument("--listen-model", choices=["tiny", "small", "medium"], default="tiny")

    check = commands.add_parser("camera", help="Save one frame from the camera")
    check.add_argument("--output", type=Path, default=Path("camera-check.jpg"))
    check.add_argument("--camera", type=int, default=0)
    check.add_argument("--flip", action="store_true")

    enroll = commands.add_parser("enroll", parents=[shared], help="Add a photo of a person")
    enroll.add_argument("name")
    enroll.add_argument("image", type=Path)
    enroll.add_argument("--relationship", default="")
    enroll.add_argument("--note", default="")

    identify = commands.add_parser("identify", parents=[shared], help="Name the people in one photo")
    identify.add_argument("image", type=Path)

    download = commands.add_parser("download", help="Download every model so the demo runs offline")
    download.add_argument("--no-voice", action="store_true")

    args = parser.parse_args(argv)
    load_env()

    if args.command == "camera":
        from cognisight.camera import save_snapshot

        try:
            kind, label, width, height, path = save_snapshot(args.output, args.camera, args.flip)
        except Exception as exc:
            print("Camera check failed: {}".format(exc), file=sys.stderr)
            return 1
        print("{} ({}) {}x{} -> {}".format(kind, label, width, height, path))
        return 0

    if args.command == "download":
        return _download(not args.no_voice)

    gallery = Gallery(args.gallery, DeepFaceEmbedder(args.detector), threshold=args.threshold)

    if args.command == "enroll":
        if not args.image.is_file():
            print("No photo at {}".format(args.image), file=sys.stderr)
            return 1
        try:
            gallery.get(args.name)
        except KeyError:
            gallery.create(args.name, args.relationship, args.note)
        try:
            saved = gallery.add_photo(args.name, args.image.read_bytes(), args.image.suffix)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 1
        print(saved)
        return 0

    if args.command == "identify":
        faces = gallery.identify(str(args.image))
        if not faces:
            print("no face found")
            return 1
        for face in faces:
            print(face.name or "unknown", "" if face.distance is None else "({:.3f})".format(face.distance))
        return 0 if any(face.name for face in faces) else 1

    return _start(args, gallery)


def _start(args, gallery):
    from functools import partial

    from cognisight.camera import open_camera
    from cognisight.location import Locator
    from cognisight.runtime import Runtime
    from cognisight.server import create_app, serve

    args.gallery.mkdir(parents=True, exist_ok=True)
    runtime = Runtime(
        gallery,
        camera_factory=partial(open_camera, args.camera, args.flip, args.swap_colors),
        interval=args.interval,
        port=args.port,
        speech=not args.no_speech,
        listen=not args.no_listen,
        listen_model=args.listen_model,
    ).start()
    static = WEB_DIST if (WEB_DIST / "index.html").is_file() else None
    if static is None:
        print("The dashboard is not built (web/dist is missing). The API still runs.", file=sys.stderr)
    app = create_app(gallery, runtime, Locator(), static)
    print("CogniSight is running.")
    for url in ["http://localhost:{}".format(args.port)] + _urls(args.port):
        print("  Dashboard: {}".format(url))
    print("Press Ctrl+C to stop.")
    try:
        serve(app, args.host, args.port)
    except KeyboardInterrupt:
        pass
    finally:
        runtime.close()
    return 0


def _urls(port):
    from cognisight.runtime import device_urls

    return device_urls(port)


def _download(voice):
    print("Downloading the face recognition model (about 95 MB)…")
    embedder = DeepFaceEmbedder()
    embedder.load()
    import numpy as np

    embedder.embed(np.zeros((160, 160, 3), dtype=np.uint8))  # loads the face detector too
    print("Face recognition ready.")
    if voice:
        print("Downloading speech models…")
        try:
            from cognisight.voice import download_voice_models

            download_voice_models()
            print("Speech ready.")
        except Exception as exc:
            print("Speech models could not be downloaded: {}".format(exc), file=sys.stderr)
            print("CogniSight will still run; speech will use espeak-ng or stay off.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
