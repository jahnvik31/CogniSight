"""Local entry points. Credentials and model downloads are never implicit."""

import argparse
import getpass
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import platform
import signal
import sys
import threading


def default_state():
    return Path.home() / ".local/share/cognisight"


def validate_state_dir(path):
    state = Path(path).expanduser().resolve()
    repo = Path(__file__).resolve().parents[3]
    if state == repo or repo in state.parents:
        raise ValueError("Private state must be outside the repository")
    return state


def doctor():
    from importlib.util import find_spec

    return {
        "architecture": platform.machine(),
        "system": platform.system(),
        "python": platform.python_version(),
        "qualification": "unverified: run actual Pi qualification",
        "dependencies": {
            name: find_spec(name) is not None
            for name in (
                "picamera2",
                "cv2",
                "numpy",
                "vosk",
                "piper",
                "sounddevice",
                "flask",
                "flask_wtf",
                "waitress",
            )
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Offline contextual recognition and local caregiver enrollment"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Report environment; does not certify hardware")
    sub.add_parser("devices", help="List audio devices without selecting defaults")
    password = sub.add_parser("password", help="Set local caregiver password interactively")
    password.add_argument("--state-dir", type=Path, default=default_state())
    run = sub.add_parser("run", help="Run camera/audio service and loopback enrollment tool")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--state-dir", type=Path, default=default_state())
    run.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            print(json.dumps(doctor(), indent=2))
            return 0
        if args.command == "devices":
            import sounddevice as sd

            print(sd.query_devices())
            return 0
        if args.command == "password":
            args.state_dir = validate_state_dir(args.state_dir)
            from werkzeug.security import generate_password_hash
            from .web import private_secret

            secret = getpass.getpass("New caregiver password (at least 12 characters): ")
            if len(secret) < 12 or secret != getpass.getpass("Confirm password: "):
                raise ValueError("Passwords must match and contain at least 12 characters")
            args.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            path = args.state_dir / "password.hash"
            if path.is_symlink():
                raise ValueError("Password path cannot be a symlink")
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as stream:
                stream.write(generate_password_hash(secret))
            os.chmod(path, 0o600)
            # Password rotation invalidates existing signed browser sessions.
            session_key = args.state_dir / "session.key"
            if session_key.exists():
                session_key.unlink()
            private_secret(args.state_dir)
            print("Password set. Restart the running service to invalidate existing sessions.")
            return 0
        from .config import load_config

        config = load_config(args.config)
        if not 1024 <= args.port <= 65535:
            raise ValueError("Use a port between 1024 and 65535")
        from waitress import create_server
        from .store import Store
        from .runtime import Runtime
        from .vision import Vision
        from .audio import AudioEngine
        from .web import create_app

        state = validate_state_dir(args.state_dir)
        state.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(state, 0o700)
        if not (state / "password.hash").is_file():
            raise ValueError("Run cognisight password with this state directory first")
        # An advisory lock prevents a second process from taking the CSI camera.
        import fcntl

        lock = (state / "service.lock").open("a")
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Another recognition service is running")
        handler = RotatingFileHandler(state / "module.log", maxBytes=1024 * 1024, backupCount=3)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logging.getLogger("cognisight").addHandler(handler)
        logging.getLogger("cognisight").setLevel(logging.INFO)
        store = Store(state / "state.sqlite3")
        runtime = Runtime(store, config, vision=Vision(config))
        runtime.audio = AudioEngine(config, runtime.command, runtime.on_health)
        app = create_app(store, runtime, state)
        server = create_server(app, host="127.0.0.1", port=args.port, threads=2)
        thread = threading.Thread(target=runtime.run, name="recognition-runtime", daemon=True)
        thread.start()

        def stop(signum=None, frame=None):
            runtime.close()
            # waitress does not install signal handling in this embedding.
            server.close()
            raise KeyboardInterrupt

        signal.signal(signal.SIGTERM, stop)
        print("Local enrollment: http://127.0.0.1:" + str(args.port), flush=True)
        try:
            server.run()
        except KeyboardInterrupt:
            pass
        finally:
            runtime.close()
            thread.join(timeout=10)
            if thread.is_alive():
                logging.getLogger("cognisight").error("Runtime shutdown exceeded timeout")
            else:
                store.close()
            server.close()
            lock.close()
        return 0
    except (OSError, ValueError, RuntimeError, ImportError, KeyError, json.JSONDecodeError) as exc:
        # No raw exception messages: library errors may include private paths/data.
        print(
            "Unable to complete command ("
            + type(exc).__name__
            + "). Check setup/configuration and doctor output."
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
