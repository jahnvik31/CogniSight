"""Issue #8 software flow with synthetic data and real application components.

No camera, audio device, receiver, TLS handshake or phone is exercised here.
The Flask client models already-terminated HTTPS at the local proxy boundary.
"""

import importlib.util
import json
import re
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from cognisight.navigation.service import NavigationService
from cognisight.recognition.runtime import Runtime
from cognisight.recognition.store import Store

HAS_WEB = all(importlib.util.find_spec(name) is not None for name in ("flask", "flask_wtf"))


@unittest.skipUnless(HAS_WEB, "Flask/Flask-WTF unavailable; full module-to-web flow not run")
class AvailableModuleIntegrationTests(unittest.TestCase):
    def setUp(self):
        from werkzeug.security import generate_password_hash
        from cognisight.caregiver import create_dashboard_app

        self.temp = tempfile.TemporaryDirectory()
        self.state = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.state / "synthetic.sqlite3")
        self.addCleanup(self.store.close)
        self.person = self.store.enroll(
            "Synthetic Person", "Synthetic relation", "Synthetic context", "",
            [[1.0, 0.0]] * 10, "synthetic-model",
        )
        self.now = 100.0
        self.navigation = NavigationService({}, clock=lambda: self.now)
        self.runtime = Runtime(
            self.store,
            {"model_version": "synthetic-model", "threshold": 0.8,
             "margin": 0.1, "calibrated": True},
            clock=lambda: self.now, navigation=self.navigation,
        )
        self.runtime.on_health("camera", "ready")
        (self.state / "password.hash").write_text(
            generate_password_hash("synthetic-test-password")
        )
        self.app = create_dashboard_app(
            self.runtime.dashboard_snapshot, self.state, ["cognisight.local"]
        )
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        self.navigation.accept_line(b'{"class":"VERSION","proto_major":3}')

    def get(self, path):
        return self.client.get(
            path, base_url="https://cognisight.local",
            environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
        )

    def post(self, path, data):
        return self.client.post(
            path, data=data, base_url="https://cognisight.local",
            environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
            headers={"Origin": "https://cognisight.local",
                     "Referer": "https://cognisight.local" + path},
        )

    def token(self, path="/login"):
        page = self.get(path)
        return re.search(r'name="csrf_token"[^>]*value="([^"]+)"',
                         page.get_data(as_text=True)).group(1)

    def login(self):
        response = self.post("/login", {"csrf_token": self.token(),
                                         "password": "synthetic-test-password"})
        self.assertEqual(response.status_code, 302)
        return response

    def confirm(self):
        start = self.now
        # Use actual stored gallery matching, tracker and event producer.
        for offset in (0.0, 0.2, 0.4):
            self.now = start + offset
            match = self.runtime.gallery.match([1.0, 0.0])
            self.runtime.observe([((0, 0, 100, 100), match)], self.now, None)

    def fix(self, **changes):
        report = {"class": "TPV", "mode": 3, "lat": 0.0, "lon": 0.0,
                  "time": "2026-11-12T12:00:00Z", "speed": 0.0}
        report.update(changes)
        self.navigation.accept_line(json.dumps(report, allow_nan=False).encode())

    def state_json(self):
        response = self.get("/dashboard/state")
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response.headers["Cache-Control"])
        return response.get_json()

    def test_confirmation_event_and_verified_context_reach_authenticated_consumer(self):
        subscriber = self.runtime.subscribe()
        self.confirm()
        self.fix()
        event = subscriber.get_nowait()
        self.assertEqual(event["kind"], "confirmed")
        self.assertEqual(event["person_id"], self.person)
        self.assertEqual(event["model_version"], "synthetic-model")
        self.assertTrue(event["event_id"])
        self.assertTrue(subscriber.empty())
        self.login()
        state = self.state_json()
        self.assertEqual(state["recognition"]["status"], "live")
        self.assertEqual(state["recognition"]["people"], [{
            "person_id": self.person, "name": "Synthetic Person",
            "relationship": "Synthetic relation", "note": "Synthetic context",
        }])
        self.assertEqual(state["outdoor"]["status"], "live")
        self.assertEqual((state["outdoor"]["latitude"], state["outdoor"]["longitude"]), (0, 0))
        self.assertEqual(state["indoor"]["status"], "unavailable")
        self.assertEqual(state["indoor"]["reason"], "not_integrated")
        self.assertIsNone(state["recognition"]["observed_at"])
        encoded = json.dumps(state, allow_nan=False)
        for private_field in ("embeddings", "audio_int16", "synthetic-model", "created", "pronunciation"):
            self.assertNotIn(private_field, encoded)
        self.runtime.unsubscribe(subscriber)

    def test_unauthenticated_response_cannot_expose_known_person_or_position(self):
        self.confirm()
        self.fix()
        response = self.get("/dashboard/state")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json(), {"error": "authentication_required"})
        self.assertNotIn("Synthetic Person", response.get_data(as_text=True))
        self.assertNotIn("latitude", response.get_data(as_text=True))
        self.assertEqual(self.get("/enroll").status_code, 404)

    def test_successful_polls_never_renew_independent_source_evidence(self):
        self.confirm()
        self.fix()
        self.login()
        self.now += 1.0
        state = self.state_json()
        self.assertEqual(state["recognition"]["status"], "stale")
        self.assertEqual(state["recognition"]["people"], [])
        self.assertEqual(state["outdoor"]["status"], "live")
        self.now += 9.0
        state = self.state_json()
        self.assertEqual(state["outdoor"]["status"], "stale")
        self.assertIsNone(state["outdoor"]["latitude"])
        self.assertEqual(state["outdoor"]["last_known"]["latitude"], 0.0)
        self.assertEqual(state["outdoor"]["last_known"]["label"], "Last known location")
        self.assertEqual(state["outdoor"]["last_known"]["age_seconds"], 10.0)
        self.assertEqual(self.state_json()["outdoor"]["status"], "stale")

    def test_invalid_gps_then_no_fix_do_not_hide_recognition_or_reuse_current_coordinates(self):
        self.confirm()
        self.fix()
        self.login()
        for report, expected in (({"mode": 3, "lat": 91, "lon": 0}, "invalid"),
                                 ({"mode": 1}, "no_fix")):
            self.fix(**report)
            state = self.state_json()
            self.assertEqual(state["recognition"]["status"], "live")
            self.assertEqual(state["recognition"]["people"][0]["name"], "Synthetic Person")
            self.assertEqual(state["outdoor"]["status"], expected)
            self.assertIsNone(state["outdoor"]["latitude"])
            self.assertEqual(state["outdoor"]["last_known"]["latitude"], 0.0)

    def test_recognition_failure_keeps_valid_outdoor_data_and_can_recover(self):
        self.confirm()
        self.fix()
        self.login()
        for component in ("camera", "storage"):
            self.runtime.on_health(component, "unavailable")
            state = self.state_json()
            self.assertEqual(state["recognition"]["status"], "unavailable")
            self.assertEqual(state["recognition"]["people"], [])
            self.assertEqual(state["outdoor"]["status"], "live")
            self.runtime.on_health(component, "ready")
        self.assertEqual(self.state_json()["recognition"]["status"], "live")

    def test_profile_edit_invalidates_http_cache_until_new_evidence(self):
        self.confirm()
        self.fix()
        self.login()
        self.store.update(self.person, "Synthetic Updated", "New synthetic relation",
                          "New synthetic context", "", True)
        self.assertEqual(self.state_json()["recognition"]["people"], [])
        self.now += 0.1
        match = self.runtime.gallery.match([1.0, 0.0])
        self.runtime.observe([((0, 0, 100, 100), match)], self.now, None)
        people = self.state_json()["recognition"]["people"]
        self.assertEqual(people[0]["name"], "Synthetic Updated")
        self.assertEqual(people[0]["note"], "New synthetic context")

    def test_blocked_recognition_producer_still_serves_outdoor_through_http(self):
        self.confirm()
        self.fix()
        self.login()
        held, release = threading.Event(), threading.Event()

        def hold_runtime():
            with self.runtime.lock:
                held.set()
                release.wait(2)

        worker = threading.Thread(target=hold_runtime)
        worker.start()
        self.assertTrue(held.wait(1))
        try:
            state = self.state_json()
            self.assertEqual(state["recognition"]["status"], "unavailable")
            self.assertEqual(state["outdoor"]["status"], "live")
        finally:
            release.set()
            worker.join(2)
        self.assertFalse(worker.is_alive())

    def test_logout_and_fixed_session_expiry_remove_access_to_available_data(self):
        self.confirm()
        self.fix()
        self.login()
        self.assertEqual(self.state_json()["recognition"]["status"], "live")
        response = self.post("/logout", {"csrf_token": self.token("/dashboard")})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.get("/dashboard/state").status_code, 401)
        with patch("itsdangerous.timed.TimestampSigner.get_timestamp", return_value=1000000):
            self.login()
        with patch("itsdangerous.timed.TimestampSigner.get_timestamp", return_value=1000901):
            response = self.get("/dashboard/state")
            self.assertEqual(response.status_code, 401)
            self.assertNotIn("Synthetic Person", response.get_data(as_text=True))
