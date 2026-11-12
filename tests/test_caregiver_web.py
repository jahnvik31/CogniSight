import importlib.util
import re
import tempfile
import unittest
from pathlib import Path

HAS_WEB = all(importlib.util.find_spec(name) is not None for name in ("flask", "flask_wtf"))


@unittest.skipUnless(HAS_WEB, "Flask/Flask-WTF unavailable; HTTPS caregiver integration not run")
class CaregiverWebTests(unittest.TestCase):
    def setUp(self):
        from werkzeug.security import generate_password_hash
        from cognisight.caregiver import create_dashboard_app

        self.temp = tempfile.TemporaryDirectory()
        self.state = Path(self.temp.name)
        (self.state / "password.hash").write_text(generate_password_hash("long-test-password"))
        self.app = create_dashboard_app(
            lambda: {"schema_version": 1}, self.state, ["cognisight.local"]
        )
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    def get(self, url, **kwargs):
        return self.client.get(
            url,
            base_url="https://cognisight.local",
            environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
            **kwargs,
        )

    def post(self, url, **kwargs):
        # Model a browser honoring Referrer-Policy: same-origin for HTTPS forms.
        headers = dict(kwargs.pop("headers", {}))
        headers.setdefault("Origin", "https://cognisight.local")
        headers.setdefault("Referer", "https://cognisight.local/login")
        return self.client.post(
            url,
            base_url="https://cognisight.local",
            environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
            headers=headers,
            **kwargs,
        )

    def token(self, path="/login"):
        return re.search(
            r'name="csrf_token"[^>]*value="([^"]+)"', self.get(path).get_data(as_text=True)
        ).group(1)

    def login(self):
        return self.post(
            "/login", data={"csrf_token": self.token(), "password": "long-test-password"}
        )

    def test_login_secure_cookie_state_and_no_enrollment_routes(self):
        self.assertEqual(self.get("/dashboard/state").status_code, 401)
        self.assertEqual(
            self.post("/login", data={"password": "long-test-password"}).status_code, 400
        )
        response = self.login()
        self.assertEqual(response.status_code, 302)
        cookie = response.headers["Set-Cookie"]
        for flag in ("Secure", "HttpOnly", "SameSite=Strict", "cognisight_caregiver="):
            self.assertIn(flag, cookie)
        self.assertEqual(self.get("/dashboard").status_code, 200)
        response = self.get("/dashboard/state")
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual(response.json["recognition"]["status"], "unavailable")
        self.assertEqual(self.get("/enroll").status_code, 404)
        self.assertEqual(self.get("/people").status_code, 404)

    def test_host_origin_tls_and_proxy_peer_rejected(self):
        self.assertEqual(
            self.client.get(
                "/login",
                base_url="http://cognisight.local",
                environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.get("/login", headers={"Origin": "https://evil.test"}).status_code, 403
        )
        self.assertEqual(
            self.client.get(
                "/login",
                base_url="https://evil.test",
                environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                "/login",
                base_url="http://cognisight.local",
                headers={"X-Forwarded-Proto": "https", "X-Forwarded-For": "192.168.1.10"},
                environ_overrides={"REMOTE_ADDR": "192.168.1.20"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                "/login",
                base_url="http://cognisight.local",
                headers={"X-Forwarded-Proto": "https", "X-Forwarded-For": "192.168.1.10"},
                environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
            ).status_code,
            200,
        )

    def test_logout_csrf_and_separate_signing_key(self):
        from cognisight.recognition.web import private_secret

        self.assertNotEqual(self.app.secret_key, private_secret(self.state))
        self.login()
        self.assertEqual(self.post("/logout").status_code, 400)
        self.assertEqual(
            self.post("/logout", data={"csrf_token": self.token("/dashboard")}).status_code, 302
        )
        self.assertEqual(self.get("/dashboard/state").status_code, 401)

    def test_provider_failure_leaks_no_exception(self):
        from cognisight.caregiver import create_dashboard_app

        def broken():
            raise ValueError("secret face data")

        app = create_dashboard_app(broken, self.state, ["cognisight.local"])
        client = app.test_client()
        with client.session_transaction(base_url="https://cognisight.local") as session:
            session["authenticated"] = True
        response = client.get(
            "/dashboard/state",
            base_url="https://cognisight.local",
            environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
        )
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("secret", response.get_data(as_text=True))

    def test_polling_does_not_extend_fifteen_minute_session(self):
        from unittest.mock import patch

        with patch("itsdangerous.timed.TimestampSigner.get_timestamp", return_value=1000000):
            self.login()
        with patch("itsdangerous.timed.TimestampSigner.get_timestamp", return_value=1000300):
            response = self.get("/dashboard/state")
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("Set-Cookie", response.headers)
        with patch("itsdangerous.timed.TimestampSigner.get_timestamp", return_value=1000901):
            self.assertEqual(self.get("/dashboard/state").status_code, 401)

    def test_browser_policy_preserves_referrer_for_https_login(self):
        page = self.get("/login")
        token = re.search(
            r'name="csrf_token"[^>]*value="([^"]+)"', page.get_data(as_text=True)
        ).group(1)
        headers = {"Origin": "https://cognisight.local"}
        # no-referrer suppresses this header in browsers and breaks strict HTTPS CSRF.
        if page.headers.get("Referrer-Policy") != "no-referrer":
            headers["Referer"] = "https://cognisight.local/login"
        response = self.client.post(
            "/login",
            base_url="https://cognisight.local",
            environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
            headers=headers,
            data={"csrf_token": token, "password": "long-test-password"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(page.headers["Referrer-Policy"], "same-origin")

    def test_valid_csrf_token_does_not_bypass_https_referrer_check(self):
        for headers in (
            {"Origin": "https://cognisight.local"},
            {"Origin": "https://cognisight.local", "Referer": "https://evil.test/login"},
        ):
            with self.subTest(headers=headers):
                response = self.client.post(
                    "/login",
                    base_url="https://cognisight.local",
                    environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
                    headers=headers,
                    data={"csrf_token": self.token(), "password": "long-test-password"},
                )
                self.assertEqual(response.status_code, 400)
