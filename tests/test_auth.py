import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import auth
from app import dashboard as dashboard_module


class AuthTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.auth_path = Path(self.temp_dir.name) / "auth.json"
        patcher = patch("app.auth.AUTH_PATH", self.auth_path)
        patcher.start()
        self.addCleanup(patcher.stop)
        dashboard_module._login_throttle.clear()


class PasswordTests(AuthTestCase):
    def test_no_password_set_initially(self):
        self.assertFalse(auth.is_password_set())
        self.assertFalse(auth.verify_password("anything"))

    def test_set_and_verify_password(self):
        auth.set_password("correct horse")

        self.assertTrue(auth.is_password_set())
        self.assertTrue(auth.verify_password("correct horse"))
        self.assertFalse(auth.verify_password("wrong horse"))

    def test_password_is_not_stored_in_plain_text(self):
        auth.set_password("correct horse")

        self.assertNotIn("correct horse", self.auth_path.read_text(encoding="utf-8"))

    def test_short_password_is_rejected(self):
        with self.assertRaises(ValueError):
            auth.set_password("short")
        self.assertFalse(auth.is_password_set())


class SessionTokenTests(AuthTestCase):
    def setUp(self):
        super().setUp()
        auth.set_password("correct horse")

    def test_valid_token_verifies(self):
        self.assertTrue(auth.verify_session_token(auth.create_session_token()))

    def test_tampered_token_is_rejected(self):
        expires, fingerprint, signature = auth.create_session_token().split(".")
        forged = f"{int(expires) + 999999}.{fingerprint}.{signature}"

        self.assertFalse(auth.verify_session_token(forged))
        self.assertFalse(auth.verify_session_token("garbage"))
        self.assertFalse(auth.verify_session_token(None))

    def test_expired_token_is_rejected(self):
        token = auth.create_session_token(now=1000)

        self.assertFalse(auth.verify_session_token(token, now=1000 + auth.SESSION_MAX_AGE_SECONDS + 1))

    def test_changing_password_invalidates_existing_tokens(self):
        token = auth.create_session_token()

        auth.set_password("battery staple")

        self.assertFalse(auth.verify_session_token(token))


class LoginThrottleTests(unittest.TestCase):
    def test_locks_out_after_max_failures_then_recovers(self):
        throttle = auth.LoginThrottle()
        for _ in range(throttle.MAX_FAILURES):
            self.assertEqual(throttle.retry_after("1.2.3.4", now=100), 0)
            throttle.record_failure("1.2.3.4", now=100)

        self.assertGreater(throttle.retry_after("1.2.3.4", now=101), 0)
        self.assertEqual(throttle.retry_after("5.6.7.8", now=101), 0)
        self.assertEqual(throttle.retry_after("1.2.3.4", now=100 + throttle.LOCKOUT_SECONDS + 1), 0)


class DashboardAuthTests(AuthTestCase):
    def local_client(self):
        return TestClient(dashboard_module.app, client=("127.0.0.1", 50000))

    def remote_client(self):
        return TestClient(dashboard_module.app, client=("192.0.2.10", 50000))

    def test_pages_redirect_to_login_when_signed_out(self):
        auth.set_password("correct horse")
        client = self.local_client()

        for path in ("/", "/settings"):
            response = client.get(path, follow_redirects=False)
            self.assertEqual(response.status_code, 303)
            self.assertEqual(response.headers["location"], "/login")

    def test_api_returns_401_when_signed_out(self):
        auth.set_password("correct horse")
        client = self.local_client()

        self.assertEqual(client.get("/api/devices").status_code, 401)
        self.assertEqual(client.get("/api/settings").status_code, 401)
        self.assertEqual(client.put("/api/settings", json={"values": {}}).status_code, 401)

    def test_login_page_is_public(self):
        response = self.local_client().get("/login")

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="password"', response.text)

    def test_status_offers_setup_only_to_local_clients(self):
        self.assertTrue(self.local_client().get("/api/auth/status").json()["setup_allowed"])
        self.assertFalse(self.remote_client().get("/api/auth/status").json()["setup_allowed"])

    def test_first_run_setup_from_local_client_signs_in(self):
        client = self.local_client()

        response = client.post("/api/auth/setup", json={"password": "correct horse"})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(auth.verify_password("correct horse"))
        self.assertEqual(client.get("/api/settings").status_code, 200)

    def test_setup_rejected_from_remote_client(self):
        response = self.remote_client().post("/api/auth/setup", json={"password": "correct horse"})

        self.assertEqual(response.status_code, 403)
        self.assertFalse(auth.is_password_set())

    def test_setup_rejected_once_password_exists(self):
        auth.set_password("correct horse")

        response = self.local_client().post("/api/auth/setup", json={"password": "attacker pw"})

        self.assertEqual(response.status_code, 409)
        self.assertTrue(auth.verify_password("correct horse"))

    def test_setup_rejects_short_password(self):
        response = self.local_client().post("/api/auth/setup", json={"password": "short"})

        self.assertEqual(response.status_code, 422)

    def test_login_logout_flow(self):
        auth.set_password("correct horse")
        client = self.remote_client()

        self.assertEqual(client.post("/api/auth/login", json={"password": "nope"}).status_code, 401)
        login = client.post("/api/auth/login", json={"password": "correct horse"})
        self.assertEqual(login.status_code, 200)
        cookie_header = login.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie_header)
        self.assertIn("samesite=strict", cookie_header)
        self.assertEqual(client.get("/api/devices").status_code, 200)

        self.assertEqual(client.post("/api/auth/logout").status_code, 200)
        self.assertEqual(client.get("/api/devices").status_code, 401)

    def test_repeated_failed_logins_are_throttled(self):
        auth.set_password("correct horse")
        client = self.remote_client()
        for _ in range(auth.LoginThrottle.MAX_FAILURES):
            client.post("/api/auth/login", json={"password": "nope"})

        response = client.post("/api/auth/login", json={"password": "correct horse"})

        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response.headers)

    def test_change_password_requires_current_password(self):
        auth.set_password("correct horse")
        client = self.local_client()
        client.post("/api/auth/login", json={"password": "correct horse"})

        wrong = client.post("/api/auth/password", json={"current_password": "nope", "new_password": "battery staple"})
        self.assertEqual(wrong.status_code, 403)

        ok = client.post("/api/auth/password", json={"current_password": "correct horse", "new_password": "battery staple"})
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(auth.verify_password("battery staple"))
        # The changing browser gets a fresh session and stays signed in.
        self.assertEqual(client.get("/api/devices").status_code, 200)

    def test_changing_password_signs_out_other_sessions(self):
        auth.set_password("correct horse")
        other = self.remote_client()
        other.post("/api/auth/login", json={"password": "correct horse"})

        auth.set_password("battery staple")

        self.assertEqual(other.get("/api/devices").status_code, 401)


if __name__ == "__main__":
    unittest.main()
