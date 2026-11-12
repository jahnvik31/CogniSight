"""Local entry points. Credentials and model downloads are never implicit."""

import argparse
from contextlib import ExitStack
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


def validate_service_ports(config, enrollment_port):
    if type(enrollment_port) is not int or not 1024 <= enrollment_port <= 65535:
        raise ValueError("Use an enrollment port between 1024 and 65535")
    caregiver = config.get("caregiver", {})
    if (
        caregiver.get("enabled", False)
        and caregiver.get("backend_port", 8766) == enrollment_port
    ):
        raise ValueError("Enrollment and caregiver backend ports must be different")


def create_http_server(factory, app, port, caregiver=False):
    options = {
        "host": "127.0.0.1", "port": port, "threads": 2,
        "connection_limit": 32, "backlog": 32,
        "channel_timeout": 30, "cleanup_interval": 5,
        "max_request_body_size": 16384, "max_request_header_size": 16384,
    }
    if caregiver:
        # Trust only TLS scheme from the same-host reverse proxy. In particular,
        # preserve the real loopback peer for the dashboard's proxy guard and
        # never accept forwarded host/client-IP overrides at this boundary.
        options.update(
            trusted_proxy="127.0.0.1",
            trusted_proxy_headers={"x-forwarded-proto"},
            clear_untrusted_proxy_headers=True,
        )
    return factory(app, **options)


def _close_server(server, timeout=10):
    failed = False
    try:
        server.close()
    except Exception:
        failed = True
    dispatcher = getattr(server, "task_dispatcher", None)
    if dispatcher is not None:
        try:
            dispatcher.shutdown(timeout=timeout)
            # Waitress shutdown's return value describes pending cancellation,
            # not whether every active request has exited. Inspect its workers.
            if getattr(dispatcher, "threads", ()):
                failed = True
        except Exception:
            failed = True
    # BaseWSGIServer.close removes the listener/trigger but leaves HTTP keepalive
    # channels in its own private asyncore map. Closing only owned channels lets
    # server.run terminate without touching any other application's global map.
    socket_map = getattr(server, "_map", None)
    if socket_map is None:
        socket_map = getattr(server, "map", None)
    if socket_map is not None:
        for channel in list(socket_map.values()):
            try:
                channel.close()
            except Exception:
                failed = True
    if failed:
        raise RuntimeError("Local HTTP cleanup failed")


def run_services(
    runtime, servers, stop_event, store, poll_interval=0.2, join_timeout=10
):
    """Own service lifecycles; a failed worker tears down the whole service group.

    All listening servers must already have been created successfully. Only the
    runtime owns device workers. Waitress servers stay loopback-bound; HTTPS for
    the caregiver dashboard is terminated by the separately configured proxy.
    """
    failed = threading.Event()
    started = []

    def guarded(callback):
        try:
            callback()
        except BaseException:
            # Native/library exceptions may contain private data; do not retain
            # exception messages or print tracebacks from background threads.
            failed.set()

    runtime_thread = threading.Thread(
        target=guarded, args=(runtime.run,), name="recognition-runtime", daemon=True
    )
    workers = [runtime_thread] + [
        threading.Thread(
            target=guarded,
            args=(server.run,),
            name="local-http-" + str(index),
            daemon=True,
        )
        for index, server in enumerate(servers)
    ]
    try:
        for thread in workers:
            thread.start()
            started.append(thread)
        while not stop_event.wait(poll_interval):
            if failed.is_set() or any(not thread.is_alive() for thread in started):
                raise RuntimeError("Service worker terminated")
    finally:
        cleanup_failed = False
        try:
            runtime.close()
        except Exception:
            cleanup_failed = True
            logging.getLogger("cognisight").error("Runtime shutdown failed")
        for server in servers:
            try:
                _close_server(server, join_timeout)
            except Exception:
                cleanup_failed = True
                logging.getLogger("cognisight").error("Local HTTP shutdown failed")
        for thread in started:
            thread.join(timeout=join_timeout)
        if any(thread.is_alive() for thread in started):
            # A still-running request/runtime may use the database. Do not close
            # it underneath that worker; supervisor/process exit owns cleanup.
            logging.getLogger("cognisight").error("Service shutdown exceeded timeout")
            raise RuntimeError("Service shutdown exceeded timeout")
        if cleanup_failed or getattr(runtime, "cleanup_failed", False):
            # In particular, a stalled Waitress request may still use SQLite.
            # Leave its handle open for process/supervisor cleanup on failure.
            raise RuntimeError("Service cleanup failed")
        store.close()
        if failed.is_set():
            raise RuntimeError("Service worker terminated")


def _run_service_command(args, config):
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
    import fcntl

    with ExitStack() as cleanup:
        lock = cleanup.enter_context((state / "service.lock").open("a"))
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Another recognition service is running") from None
        handler = RotatingFileHandler(
            state / "module.log", maxBytes=1024 * 1024, backupCount=3
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger = logging.getLogger("cognisight")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        cleanup.callback(handler.close)
        cleanup.callback(logger.removeHandler, handler)
        store = Store(state / "state.sqlite3")
        runtime, navigation, servers = None, None, []
        services_own_resources = False
        try:
            if config["navigation"]["enabled"]:
                from cognisight.navigation.service import NavigationService

                navigation = NavigationService(config["navigation"])
            runtime = Runtime(
                store, config, vision=Vision(config), navigation=navigation
            )
            runtime.audio = AudioEngine(config, runtime.command, runtime.on_health)
            app = create_app(store, runtime, state)
            servers.append(create_http_server(create_server, app, args.port))
            caregiver = config["caregiver"]
            if caregiver["enabled"]:
                from cognisight.caregiver import create_dashboard_app

                dashboard = create_dashboard_app(
                    runtime.dashboard_snapshot, state, caregiver["allowed_hosts"]
                )
                servers.append(
                    create_http_server(
                        create_server,
                        dashboard,
                        caregiver["backend_port"],
                        caregiver=True,
                    )
                )
            # Every socket is bound before starting camera/GPSD/audio threads.
            stop_event = threading.Event()
            previous_term = signal.getsignal(signal.SIGTERM)
            signal.signal(signal.SIGTERM, lambda signum, frame: stop_event.set())
            cleanup.callback(signal.signal, signal.SIGTERM, previous_term)
            print("Local enrollment: http://127.0.0.1:" + str(args.port), flush=True)
            if caregiver["enabled"]:
                print(
                    "Caregiver backend: loopback only; use the configured HTTPS reverse proxy.",
                    flush=True,
                )
            services_own_resources = True
            try:
                run_services(runtime, servers, stop_event, store)
            except KeyboardInterrupt:
                pass
        finally:
            if not services_own_resources:
                # App/server creation can fail before any worker starts. Clean
                # all previously acquired resources and release the camera lock.
                for server in servers:
                    try:
                        _close_server(server)
                    except Exception:
                        logger.error("Local HTTP startup cleanup failed")
                try:
                    if runtime is not None:
                        runtime.close()
                    elif navigation is not None:
                        navigation.close()
                finally:
                    store.close()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Offline contextual recognition and local caregiver enrollment"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    doctor_parser = sub.add_parser("doctor", help="Report environment; does not certify hardware")
    doctor_parser.add_argument("--native", action="store_true", help="Explicit isolated native imports; no devices are opened")
    sub.add_parser("devices", help="List audio devices without selecting defaults")
    password = sub.add_parser(
        "password", help="Set local caregiver password interactively"
    )
    password.add_argument("--state-dir", type=Path, default=default_state())
    run = sub.add_parser(
        "run",
        help="Run recognition, configured GPSD monitoring, and local web services",
        description="Local enrollment stays on loopback. Optional GPSD navigation monitoring and HTTPS-proxied caregiver access are enabled only in config.json.",
    )
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--state-dir", type=Path, default=default_state())
    run.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Loopback enrollment port; caregiver backend port is configured separately",
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            if args.native:
                from .diagnostics import native_report

                report = native_report()
                print(json.dumps(report, indent=2))
                return 0 if all(item["state"] == "passed" for item in report["dependencies"].values()) else 1
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

            secret = getpass.getpass(
                "New caregiver password (at least 12 characters): "
            )
            if len(secret) < 12 or secret != getpass.getpass("Confirm password: "):
                raise ValueError(
                    "Passwords must match and contain at least 12 characters"
                )
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
            print(
                "Password set. Restart the running service to invalidate existing sessions."
            )
            return 0
        from .config import load_config

        config = load_config(args.config)
        validate_service_ports(config, args.port)
        return _run_service_command(args, config)
    except (
        OSError,
        ValueError,
        RuntimeError,
        ImportError,
        KeyError,
        json.JSONDecodeError,
    ) as exc:
        # No raw exception messages: library errors may include private paths/data.
        print(
            "Unable to complete command ("
            + type(exc).__name__
            + "). Check setup/configuration and doctor output."
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
