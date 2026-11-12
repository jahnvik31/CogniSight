"""Local setup UI security and integration behavior; never claims camera success."""

import importlib.util
import re
import tempfile
import unittest
from pathlib import Path

from cognisight.recognition.web import LoginLimiter, local_request_allowed, private_secret


class SecurityTests(unittest.TestCase):
    def test_exact_loopback_host_and_origin_required(self):
        self.assertTrue(local_request_allowed("localhost:8765", None))
        self.assertTrue(local_request_allowed("127.0.0.1:8765", "http://127.0.0.1:8765"))
        for host, origin in [
            ("localhost.evil.test", None),
            ("evil.test", None),
            ("127.0.0.1:8765", "http://evil.test"),
            ("localhost:8765", "null"),
            ("localhost:8765", "http://localhost:9999"),
            ("localhost:8765", "http://user@localhost:8765"),
        ]:
            self.assertFalse(local_request_allowed(host, origin), (host, origin))

    def test_rate_limit_expires_and_success_resets(self):
        limiter = LoginLimiter(limit=3, window=60)
        for now in (0, 1, 2):
            self.assertTrue(limiter.allowed(now))
            limiter.failure(now)
        self.assertFalse(limiter.allowed(3))
        self.assertTrue(limiter.allowed(61))
        limiter.success()
        self.assertTrue(limiter.allowed(62))

    def test_session_secret_persists_with_private_permissions(self):
        with tempfile.TemporaryDirectory() as path:
            first = private_secret(Path(path))
            self.assertEqual(first, private_secret(Path(path)))
            self.assertGreaterEqual(len(first), 32)
            self.assertEqual((Path(path) / "session.key").stat().st_mode & 0o777, 0o600)


HAS_WEB = all(importlib.util.find_spec(name) is not None for name in ("flask", "flask_wtf"))


class Control:
    def __init__(self):
        self.count = 0
        self.enrolling = False
        self.target = None

    def status(self):
        return {"camera": "unverified", "enrollment": self.enrolling, "calibrated": False}

    def begin_enrollment(self, person_id=None):
        self.target = person_id
        self.enrolling = True
        self.count = 0

    def capture_sample(self):
        self.count += 1
        return {"accepted": True, "count": self.count, "reason": "test double"}

    def cancel_enrollment(self):
        self.enrolling = False
        self.count = 0

    def finish_enrollment(self, name, relationship, note, pronunciation):
        if self.count < 10:
            raise ValueError("Ten usable samples are required.")
        return "person-id"

    def clear_history(self):
        pass


@unittest.skipUnless(HAS_WEB, "Flask/Flask-WTF unavailable; run after installing web dependencies")
class WebTests(unittest.TestCase):
    def test_csrf_tokens_expire_after_fifteen_minutes(self):
        from flask_wtf.csrf import generate_csrf, validate_csrf
        from wtforms import ValidationError
        from unittest.mock import patch
        import time

        with self.app.test_request_context("/login"):
            token = generate_csrf()
            validate_csrf(token)
            later = int(time.time()) + 901
            with patch("itsdangerous.timed.TimestampSigner.get_timestamp", return_value=later):
                with self.assertRaises(ValidationError):
                    validate_csrf(token)

    def setUp(self):
        from werkzeug.security import generate_password_hash
        from cognisight.recognition.store import Store
        from cognisight.recognition.web import create_app

        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.store = Store(self.path / "db.sqlite3")
        (self.path / "password.hash").write_text(generate_password_hash("long-test-password"))
        self.control = Control()
        self.app = create_app(self.store, self.control, self.path)
        self.app.config.update(TESTING=True)
        self.client = self.app.test_client()

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def token(self, url="/login"):
        response = self.client.get(url)
        return re.search(
            r'name="csrf_token"[^>]*value="([^"]+)"', response.get_data(as_text=True)
        ).group(1)

    def login(self):
        return self.client.post(
            "/login", data={"csrf_token": self.token(), "password": "long-test-password"}
        )

    def test_auth_csrf_local_host_and_no_cache(self):
        self.assertEqual(self.client.get("/").status_code, 302)
        self.assertEqual(
            self.client.post("/login", data={"password": "long-test-password"}).status_code, 400
        )
        self.assertEqual(self.client.get("/login", headers={"Host": "evil.test"}).status_code, 403)
        self.assertEqual(self.login().status_code, 302)
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual(self.client.post("/history/clear").status_code, 400)

    def test_untrusted_origin_and_cross_site_fetch_rejected(self):
        token = self.token()
        self.assertEqual(
            self.client.post(
                "/login",
                data={"csrf_token": token, "password": "long-test-password"},
                headers={"Origin": "https://evil.test"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get("/login", headers={"Sec-Fetch-Site": "cross-site"}).status_code, 403
        )

    def test_login_throttling_and_password_setup_required(self):
        for _ in range(5):
            token = self.token()
            self.client.post("/login", data={"csrf_token": token, "password": "wrong"})
        self.assertEqual(
            self.client.post(
                "/login", data={"csrf_token": self.token(), "password": "wrong"}
            ).status_code,
            429,
        )
        (self.path / "password.hash").unlink()
        self.assertEqual(self.client.get("/login").status_code, 503)

    def test_profile_output_is_escaped_and_delete_requires_post(self):
        person_id = self.store.enroll(
            "<script>alert(1)</script>", "relative", "", "", [[1, 0]] * 10, "v1"
        )
        self.login()
        response = self.client.get("/")
        self.assertIn("&lt;script&gt;", response.get_data(as_text=True))
        self.assertNotIn("<script>alert(1)</script>", response.get_data(as_text=True))
        self.assertEqual(self.client.get("/people/" + person_id + "/delete").status_code, 405)

    def test_insufficient_capture_cannot_finish_and_cancel_releases_camera(self):
        self.login()
        self.client.post("/enroll/begin", data={"csrf_token": self.token("/")})
        response = self.client.post(
            "/enroll/finish",
            data={"csrf_token": self.token("/enroll"), "name": "A", "confirmed": "y"},
        )
        self.assertEqual(response.status_code, 400)
        self.client.post("/enroll/cancel", data={"csrf_token": self.token("/enroll")})
        self.assertFalse(self.control.enrolling)

    def test_additional_samples_use_existing_identity_and_preserve_profile(self):
        person_id = self.store.enroll(
            "Ananya", "your daughter", "Verified note", "", [[1, 0]] * 10, "v1"
        )
        self.login()
        response = self.client.post(
            "/people/" + person_id + "/samples", data={"csrf_token": self.token("/")}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.control.target, person_id)
        page = self.client.get("/enroll").get_data(as_text=True)
        self.assertIn("Additional samples for Ananya", page)
        self.assertEqual(self.store.person(person_id)["note"], "Verified note")
