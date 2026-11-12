"""Optional service configuration and lifecycle contracts without native dependencies."""

import json
import importlib.util
import io
import sys
from contextlib import ExitStack, redirect_stdout
from types import SimpleNamespace
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from cognisight.recognition.config import validate_config
from cognisight.recognition.cli import (
    run_services,
    validate_service_ports,
    create_http_server,
    _run_service_command,
)


def base_config():
    return {
        "threshold": 0.6,
        "margin": 0.08,
        "input_device": "USB headset",
        "output_device": "USB headset",
        "model_version": "sface:test",
    }


class OptionalConfigTests(unittest.TestCase):
    def test_old_recognition_configs_keep_both_services_disabled(self):
        value = validate_config(base_config())
        self.assertFalse(value["navigation"]["enabled"])
        self.assertFalse(value["caregiver"]["enabled"])
        self.assertEqual(value["navigation"]["gpsd_host"], "127.0.0.1")
        self.assertEqual(value["navigation"]["gpsd_port"], 2947)
        self.assertEqual(value["navigation"]["fix_max_age"], 10)
        self.assertEqual(value["caregiver"]["backend_port"], 8766)

    def test_explicit_hosts_and_canonical_navigation_settings_preserved(self):
        config = base_config()
        config["navigation"] = {
            "enabled": True,
            "gpsd_host": "::1",
            "gpsd_port": 3000,
            "fix_max_age": 15,
        }
        config["caregiver"] = {
            "enabled": True,
            "allowed_hosts": ["Pi.Example", "192.168.1.10"],
            "backend_port": 9000,
        }
        value = validate_config(config)
        self.assertEqual(value["navigation"]["gpsd_port"], 3000)
        self.assertEqual(
            value["caregiver"]["allowed_hosts"], ["pi.example", "192.168.1.10"]
        )
        self.assertEqual(config["caregiver"]["allowed_hosts"][0], "Pi.Example")

    def test_enabled_caregiver_requires_exact_nonempty_hosts(self):
        invalid = (
            [],
            ["*"],
            ["*.example.com"],
            ["http://pi.local"],
            ["pi.local:443"],
            ["pi.local/path"],
            ["a@pi.local"],
            ["pi local"],
            ["-pi.local"],
            ["pi..local"],
        )
        for hosts in invalid:
            with self.subTest(hosts=hosts):
                config = base_config()
                config["caregiver"] = {"enabled": True, "allowed_hosts": hosts}
                with self.assertRaises(ValueError):
                    validate_config(config)

    def test_invalid_option_shapes_ranges_and_remote_gpsd_rejected(self):
        options = (
            ("navigation", []),
            ("caregiver", "enabled"),
            ("navigation", {"enabled": 1}),
            ("caregiver", {"enabled": "yes"}),
            ("navigation", {"gpsd_host": "192.168.1.20"}),
            ("navigation", {"gpsd_port": True}),
            ("navigation", {"gpsd_port": 65536}),
            ("navigation", {"fix_max_age": float("nan")}),
            ("navigation", {"fix_max_age": 0}),
            ("caregiver", {"backend_port": True}),
            ("caregiver", {"backend_port": 1023}),
            ("caregiver", {"allowed_hosts": "pi.local"}),
        )
        for key, value in options:
            with self.subTest(key=key, value=value):
                config = base_config()
                config[key] = value
                with self.assertRaises(ValueError):
                    validate_config(config)

    def test_dashboard_port_cannot_collide_with_enrollment(self):
        config = validate_config(
            {
                **base_config(),
                "caregiver": {
                    "enabled": True,
                    "allowed_hosts": ["pi.local"],
                    "backend_port": 8766,
                },
            }
        )
        validate_service_ports(config, 8765)
        with self.assertRaises(ValueError):
            validate_service_ports(config, 8766)
        for port in (True, 1, 65536):
            with self.assertRaises(ValueError):
                validate_service_ports(config, port)


class FakeStore:
    def __init__(self, events):
        self.events = events

    def close(self):
        self.events.append("store.close")


class FakeRuntime:
    def __init__(self, events, fail=False):
        self.events = events
        self.closed = threading.Event()
        self.fail = fail

    def run(self):
        self.events.append("runtime.run")
        if self.fail:
            raise RuntimeError("private runtime failure must not escape")
        self.closed.wait(2)

    def close(self):
        self.events.append("runtime.close")
        self.closed.set()


class FakeServer:
    def __init__(self, events, name, fail=False):
        self.events, self.name, self.fail = events, name, fail
        self.closed = threading.Event()

    def run(self):
        self.events.append(self.name + ".run")
        if self.fail:
            raise RuntimeError("private server failure must not escape")
        self.closed.wait(2)

    def close(self):
        self.events.append(self.name + ".close")
        self.closed.set()


class LifecycleTests(unittest.TestCase):
    def test_shutdown_closes_both_servers_runtime_then_store(self):
        events, stop = [], threading.Event()
        runtime = FakeRuntime(events)
        servers = [FakeServer(events, "enrollment"), FakeServer(events, "dashboard")]
        timer = threading.Timer(0.03, stop.set)
        timer.start()
        try:
            run_services(
                runtime,
                servers,
                stop,
                FakeStore(events),
                poll_interval=0.005,
                join_timeout=0.5,
            )
        finally:
            timer.cancel()
        for event in (
            "runtime.run",
            "enrollment.run",
            "dashboard.run",
            "runtime.close",
            "enrollment.close",
            "dashboard.close",
            "store.close",
        ):
            self.assertIn(event, events)
        self.assertGreater(events.index("store.close"), events.index("runtime.close"))

    def test_worker_failure_stops_other_services_and_closes_store(self):
        for kind in ("runtime", "dashboard"):
            with self.subTest(kind=kind):
                events = []
                runtime = FakeRuntime(events, fail=kind == "runtime")
                servers = [
                    FakeServer(events, "enrollment"),
                    FakeServer(events, "dashboard", fail=kind == "dashboard"),
                ]
                with self.assertRaisesRegex(RuntimeError, "Service worker terminated"):
                    run_services(
                        runtime,
                        servers,
                        threading.Event(),
                        FakeStore(events),
                        poll_interval=0.005,
                        join_timeout=0.5,
                    )
                self.assertIn("store.close", events)
                self.assertIn("enrollment.close", events)
                self.assertIn("dashboard.close", events)


class HttpServerBoundaryTests(unittest.TestCase):
    def test_only_dashboard_server_accepts_forwarded_proto_from_loopback(self):
        def factory(app, **options):
            return options

        enrollment = create_http_server(factory, object(), 8765)
        dashboard = create_http_server(factory, object(), 8766, caregiver=True)
        self.assertEqual(enrollment["host"], "127.0.0.1")
        self.assertNotIn("trusted_proxy", enrollment)
        self.assertEqual(dashboard["host"], "127.0.0.1")
        self.assertEqual(dashboard["trusted_proxy"], "127.0.0.1")
        self.assertEqual(dashboard["trusted_proxy_headers"], {"x-forwarded-proto"})
        self.assertTrue(dashboard["clear_untrusted_proxy_headers"])

    @unittest.skipUnless(
        importlib.util.find_spec("waitress"),
        "Waitress unavailable; proxy middleware boundary not run",
    )
    def test_actual_waitress_middleware_preserves_only_trusted_https_scheme(self):
        from waitress.proxy_headers import proxy_headers_middleware

        seen = []

        def app(environ, start_response):
            seen.append(dict(environ))
            start_response("200 OK", [("Content-Type", "text/plain")])
            return [b"ok"]

        def factory(application, **options):
            return proxy_headers_middleware(
                application,
                trusted_proxy=options.get("trusted_proxy"),
                trusted_proxy_headers=options.get("trusted_proxy_headers", set()),
                trusted_proxy_count=1,
                clear_untrusted=options.get("clear_untrusted_proxy_headers", True),
            )

        wrapped = create_http_server(factory, app, 8766, caregiver=True)
        for peer, expected_scheme in (("127.0.0.1", "https"), ("192.0.2.8", "http")):
            environ = {
                "REMOTE_ADDR": peer,
                "HTTP_HOST": "pi.local",
                "wsgi.url_scheme": "http",
                "HTTP_X_FORWARDED_PROTO": "https",
                "HTTP_X_FORWARDED_FOR": "192.0.2.99",
                "HTTP_X_FORWARDED_HOST": "evil.example",
                "SERVER_NAME": "pi.local",
                "SERVER_PORT": "8766",
            }
            list(wrapped(environ, lambda status, headers: None))
            self.assertEqual(seen[-1]["wsgi.url_scheme"], expected_scheme)
            self.assertEqual(seen[-1]["REMOTE_ADDR"], peer)
            self.assertEqual(seen[-1]["HTTP_HOST"], "pi.local")
            self.assertNotIn("HTTP_X_FORWARDED_FOR", seen[-1])
            self.assertNotIn("HTTP_X_FORWARDED_HOST", seen[-1])


class StartupTests(unittest.TestCase):
    def fixture(self, state, fail_dashboard=False):
        events, servers, runtimes, navigation = [], [], [], []

        class Store:
            def __init__(self, path):
                events.append("store.create")

            def close(self):
                events.append("store.close")

        class Nav:
            def __init__(self, config):
                navigation.append(config)

            def close(self):
                events.append("navigation.close")

        class Runtime:
            def __init__(self, store, config, vision=None, navigation=None):
                self.navigation = navigation
                runtimes.append(self)

            def run(self):
                events.append("runtime.run")

            def close(self):
                events.append("runtime.close")
                if self.navigation:
                    self.navigation.close()

            def command(self, command):
                pass

            def on_health(self, component, state):
                pass

            def dashboard_snapshot(self):
                return {"data_source": "unavailable"}

        def factory(app, **options):
            if len(servers) == 1 and fail_dashboard:
                raise OSError("cannot bind second socket")
            server = FakeServer(events, "server-" + str(len(servers)))
            server.options = options
            servers.append(server)
            events.append("server.create")
            return server

        def serve(runtime, bound, stop, store):
            events.append("workers.start")
            self.assertEqual(len(bound), len(servers))
            runtime.close()
            for server in bound:
                server.close()
            store.close()

        # Import dependency modules before snapshotting sys.modules so each
        # patch targets the same module object imported by the lazy CLI path.
        for module in ("store", "runtime", "vision", "audio", "web"):
            importlib.import_module("cognisight.recognition." + module)
        importlib.import_module("cognisight.navigation.service")
        stack = ExitStack()
        stack.enter_context(
            patch.dict(
                sys.modules,
                {
                    "waitress": SimpleNamespace(create_server=factory),
                    "cognisight.caregiver": SimpleNamespace(
                        create_dashboard_app=lambda *args: object()
                    ),
                },
            )
        )
        stack.enter_context(patch("cognisight.recognition.store.Store", Store))
        stack.enter_context(patch("cognisight.recognition.runtime.Runtime", Runtime))
        stack.enter_context(
            patch("cognisight.recognition.vision.Vision", lambda config: object())
        )
        stack.enter_context(
            patch("cognisight.recognition.audio.AudioEngine", lambda *args: object())
        )
        stack.enter_context(
            patch("cognisight.recognition.web.create_app", lambda *args: object())
        )
        stack.enter_context(
            patch("cognisight.navigation.service.NavigationService", Nav)
        )
        stack.enter_context(
            patch("cognisight.recognition.cli.run_services", side_effect=serve)
        )
        stack.enter_context(redirect_stdout(io.StringIO()))
        self.addCleanup(stack.close)
        args = SimpleNamespace(state_dir=state, port=8765)
        return args, events, servers, navigation

    def test_second_bind_failure_cleans_up_without_starting_workers(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            (state / "password.hash").write_text("test-hash")
            args, events, servers, navigation = self.fixture(state, fail_dashboard=True)
            config = validate_config(
                {
                    **base_config(),
                    "navigation": {"enabled": True},
                    "caregiver": {"enabled": True, "allowed_hosts": ["pi.local"]},
                }
            )
            with self.assertRaises(OSError):
                _run_service_command(args, config)
            self.assertEqual(len(servers), 1)
            self.assertIn("server-0.close", events)
            self.assertIn("runtime.close", events)
            self.assertIn("navigation.close", events)
            self.assertIn("store.close", events)
            self.assertNotIn("workers.start", events)

    def test_optional_services_bind_before_worker_start_and_defaults_stay_off(self):
        for enabled in (False, True):
            with (
                self.subTest(enabled=enabled),
                tempfile.TemporaryDirectory() as directory,
            ):
                state = Path(directory)
                (state / "password.hash").write_text("test-hash")
                args, events, servers, navigation = self.fixture(state)
                config = validate_config(
                    {
                        **base_config(),
                        "navigation": {"enabled": enabled},
                        "caregiver": {
                            "enabled": enabled,
                            "allowed_hosts": ["pi.local"],
                        },
                    }
                )
                self.assertEqual(_run_service_command(args, config), 0)
                self.assertEqual(len(servers), 2 if enabled else 1)
                self.assertEqual(len(navigation), 1 if enabled else 0)
                self.assertLess(
                    max(
                        i for i, event in enumerate(events) if event == "server.create"
                    ),
                    events.index("workers.start"),
                )
                self.assertIn("store.close", events)


class KeepAliveShutdownTests(unittest.TestCase):
    def test_shutdown_closes_server_owned_keepalive_channels(self):
        events, stop = [], threading.Event()

        class KeepAliveServer(FakeServer):
            def __init__(self):
                super().__init__(events, "enrollment")
                server = self

                class Channel:
                    def close(self):
                        events.append("channel.close")
                        server._map.clear()
                        server.closed.set()

                self._map = {1: Channel()}

            def close(self):
                # Waitress BaseWSGIServer closes only listener and trigger.
                events.append("enrollment.close")

        server = KeepAliveServer()
        timer = threading.Timer(0.02, stop.set)
        timer.start()
        try:
            with patch("cognisight.recognition.cli.logging.getLogger"):
                run_services(
                    FakeRuntime(events),
                    [server],
                    stop,
                    FakeStore(events),
                    poll_interval=0.005,
                    join_timeout=0.05,
                )
        finally:
            timer.cancel()
            server.closed.set()
        self.assertIn("channel.close", events)
        self.assertIn("store.close", events)
        self.assertLess(events.index("channel.close"), events.index("store.close"))

    def test_stuck_waitress_request_prevents_database_close(self):
        events, stop = [], threading.Event()

        class Dispatcher:
            threads = {1}

            def shutdown(self, timeout):
                events.append("dispatcher.shutdown")

        server = FakeServer(events, "enrollment")
        server.task_dispatcher = Dispatcher()
        timer = threading.Timer(0.02, stop.set)
        timer.start()
        try:
            with patch("cognisight.recognition.cli.logging.getLogger"):
                with self.assertRaisesRegex(RuntimeError, "Service cleanup failed"):
                    run_services(
                        FakeRuntime(events),
                        [server],
                        stop,
                        FakeStore(events),
                        poll_interval=0.005,
                        join_timeout=0.05,
                    )
        finally:
            timer.cancel()
            server.closed.set()
        self.assertNotIn("store.close", events)
