"""Synthetic protocol fixtures only; no real locations or receiver claims."""

import json
import math
import socket
import threading
import time
import unittest

from cognisight.navigation.service import NavigationService


def fix(**changes):
    data = {
        "class": "TPV",
        "mode": 3,
        "lat": 0.0,
        "lon": 0.0,
        "time": "2026-11-12T12:00:00Z",
        "speed": 1.0,
    }
    data.update(changes)
    return data


class NavigationStateTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.service = NavigationService({}, clock=lambda: self.now)

    def test_initial_disconnected_and_valid_origin_fix(self):
        self.assertEqual(self.service.snapshot()["status"], "disconnected")
        self.service.accept_report(fix())
        value = self.service.snapshot()
        self.assertEqual(value["status"], "live")
        self.assertEqual(value["latitude"], 0.0)
        self.assertEqual(value["longitude"], 0.0)
        self.assertEqual(value["observed_at"], "2026-11-12T12:00:00+00:00")
        self.assertEqual(value["age_seconds"], 0.0)
        json.dumps(value, allow_nan=False)

    def test_silence_expires_and_last_known_is_separate(self):
        self.service.accept_report(fix())
        self.now = 110.0
        value = self.service.snapshot()
        self.assertEqual(value["status"], "stale")
        self.assertIsNone(value["latitude"])
        self.assertEqual(value["last_known"]["latitude"], 0.0)
        self.assertEqual(value["last_known"]["age_seconds"], 10.0)

    def test_no_fix_and_invalid_never_reuse_coordinates(self):
        self.service.accept_report(fix())
        for invalid in (
            fix(mode=1),
            fix(lat=math.nan),
            fix(lon=181),
            fix(lat=-91),
            fix(speed=-1),
            fix(mode=True),
        ):
            self.service.accept_report(invalid)
            value = self.service.snapshot()
            self.assertNotEqual(value["status"], "live")
            self.assertIsNone(value["latitude"])
            self.assertEqual(value["last_known"]["latitude"], 0.0)

    def test_optional_utc_remains_unknown_and_bad_supplied_time_is_rejected(self):
        report = fix()
        del report["time"]
        self.service.accept_report(report)
        self.assertIsNone(self.service.snapshot()["observed_at"])
        for bad in ("garbage", "2026-11-12T12:00:00", "1970-01-01T00:00:00Z"):
            self.service.accept_report(fix(time=bad))
            self.assertEqual(self.service.snapshot()["status"], "invalid")

    def test_partial_messages_do_not_refresh_old_fix(self):
        self.service.accept_report(fix())
        self.now = 109
        self.service.accept_report({"class": "TPV", "mode": 3, "speed": 1})
        self.now = 111
        self.assertEqual(self.service.snapshot()["status"], "stale")

    def test_sky_does_not_fake_position_and_callback_cannot_break_state(self):
        service = NavigationService({}, on_update=lambda value: 1 / 0, clock=lambda: self.now)
        service.accept_report({"class": "SKY", "satellites": [{}]})
        self.assertNotEqual(service.snapshot()["status"], "live")
        service.accept_report(fix())
        self.assertEqual(service.snapshot()["status"], "live")

    def test_config_rejects_remote_host_and_invalid_timing(self):
        for config in (
            {"gpsd_host": "example.com"},
            {"gpsd_port": True},
            {"fix_max_age": 0},
            {"fix_max_age": math.nan},
        ):
            with self.assertRaises(ValueError):
                NavigationService(config)


class GPSDTransportTests(unittest.TestCase):
    def test_actual_loopback_stream_handshake_split_lines_and_shutdown(self):
        server = socket.socket()
        try:
            server.bind(("127.0.0.1", 0))
            server.listen(1)
        except PermissionError:
            server.close()
            self.skipTest("Sandbox blocks loopback socket binding; run on target Pi")
        watched = []
        done = threading.Event()

        def receiver():
            client, _ = server.accept()
            with client:
                client.sendall(b'{"class":"VERSION","proto_major":3}\n')
                watched.append(client.recv(4096))
                payload = (json.dumps(fix()) + "\n").encode()
                client.sendall(payload[:10])
                client.sendall(payload[10:])
                done.wait(2)
            server.close()

        thread = threading.Thread(target=receiver, daemon=True)
        thread.start()
        service = NavigationService({"gpsd_port": server.getsockname()[1]})
        service.start()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and service.snapshot()["status"] != "live":
            time.sleep(0.01)
        self.assertEqual(service.snapshot()["status"], "live")
        self.assertIn(b"WATCH", watched[0])
        started = time.monotonic()
        service.close()
        done.set()
        thread.join(2)
        self.assertLess(time.monotonic() - started, 1.5)

    def test_oversized_or_wrong_protocol_fails_closed(self):
        service = NavigationService({})
        for line in (
            b"x" * 10241,
            b'{"class":"VERSION","proto_major":99}',
            b'{"class":"TPV","mode":NaN}',
        ):
            with self.assertRaises(ValueError):
                service.accept_line(line)
        self.assertNotEqual(service.snapshot()["status"], "live")


class SimulatedSocketTests(unittest.TestCase):
    def test_adapter_parses_stream_and_invalidates_fix_on_disconnect(self):
        from unittest.mock import patch

        updates = []
        released = threading.Event()

        class Stream:
            def __init__(self):
                self.parts = [
                    b'{"class":"VERSION","proto_major":3}\n',
                    json.dumps(fix()).encode() + b"\n",
                ]

            def settimeout(self, value):
                pass

            def sendall(self, value):
                if not value.startswith(b"?WATCH="):
                    raise AssertionError("Missing WATCH")

            def recv(self, size):
                if self.parts:
                    return self.parts.pop(0)
                released.wait(0.1)
                return b""

            def shutdown(self, mode):
                released.set()

            def close(self):
                released.set()

        stream = Stream()
        service = NavigationService({}, on_update=lambda snapshot: updates.append(snapshot))
        with patch("socket.create_connection", return_value=stream):
            service.start()
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline and not any(s["status"] == "live" for s in updates):
                time.sleep(0.01)
            self.assertTrue(any(s["status"] == "live" for s in updates))
            released.set()
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline and service.snapshot()["status"] != "disconnected":
                time.sleep(0.01)
            snapshot = service.snapshot()
            self.assertEqual(snapshot["status"], "disconnected")
            self.assertIsNone(snapshot["latitude"])
            self.assertEqual(snapshot["last_known"]["latitude"], 0.0)
            service.close()


class EpochTests(unittest.TestCase):
    def test_repeated_receiver_epoch_does_not_keep_old_fix_fresh(self):
        now = [100.0]
        service = NavigationService({}, clock=lambda: now[0])
        service.accept_report(fix())
        now[0] = 109.0
        service.accept_report(fix())
        now[0] = 111.0
        self.assertEqual(service.snapshot()["status"], "stale")

    def test_out_of_order_receiver_epoch_is_not_live(self):
        service = NavigationService({})
        service.accept_report(fix())
        service.accept_report(fix(time="2026-11-12T11:59:59Z"))
        self.assertEqual(service.snapshot()["status"], "invalid")
        self.assertIsNone(service.snapshot()["latitude"])


class FreshnessContractTests(unittest.TestCase):
    def test_configured_expiry_is_shared_with_snapshot_consumers(self):
        now = [10.0]
        service = NavigationService({"fix_max_age": 2}, clock=lambda: now[0])
        service.accept_report(fix())
        now[0] = 11.5
        value = service.snapshot()
        self.assertEqual(value["status"], "live")
        self.assertEqual(value["max_age_seconds"], 2)
        now[0] = 12.0
        self.assertEqual(service.snapshot()["status"], "stale")
