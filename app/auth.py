"""Single admin password for the dashboard, plus signed session cookies.

The password is stored as a salted scrypt hash in auth.json in the per-user
config directory (next to .env), never in plain text. Sessions are stateless
HMAC-signed cookies: the signing key lives in the same file, and every token
embeds a fingerprint of the current password hash, so changing the password
invalidates every existing session without having to track them.

Standard library only — no extra dependency to bundle into the installers.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from app.paths import user_data_dir

AUTH_PATH = user_data_dir() / "auth.json"

SESSION_COOKIE = "noa_session"
SESSION_MAX_AGE_SECONDS = 12 * 60 * 60
MIN_PASSWORD_LENGTH = 8

# scrypt cost parameters (~16 MB of memory per hash).
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1


def _b64(raw):
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _load():
    try:
        return json.loads(AUTH_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(data):
    tmp_path = AUTH_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    if os.name != "nt":
        os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, AUTH_PATH)


def _hash_password(password, salt, n, r, p):
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p,
        maxmem=128 * r * (n + p + 2) * 2, dklen=32,
    )


def is_password_set():
    return "password_hash" in _load()


def validate_new_password(password):
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")


def set_password(password):
    """Set (or replace) the admin password. Invalidates all existing sessions."""
    validate_new_password(password)
    data = _load()
    salt = secrets.token_bytes(16)
    data.update({
        "password_salt": _b64(salt),
        "password_hash": _b64(_hash_password(password, salt, _SCRYPT_N, _SCRYPT_R, _SCRYPT_P)),
        "scrypt": {"n": _SCRYPT_N, "r": _SCRYPT_R, "p": _SCRYPT_P},
    })
    data.setdefault("session_key", _b64(secrets.token_bytes(32)))
    _save(data)


def verify_password(password):
    data = _load()
    if "password_hash" not in data:
        return False
    params = data.get("scrypt", {})
    candidate = _hash_password(
        password or "",
        _unb64(data["password_salt"]),
        params.get("n", _SCRYPT_N),
        params.get("r", _SCRYPT_R),
        params.get("p", _SCRYPT_P),
    )
    return hmac.compare_digest(candidate, _unb64(data["password_hash"]))


def _sign(data, payload):
    key = _unb64(data["session_key"])
    return _b64(hmac.new(key, payload.encode("ascii"), hashlib.sha256).digest())


def _password_fingerprint(data):
    return hashlib.sha256(data["password_hash"].encode("ascii")).hexdigest()[:16]


def create_session_token(now=None):
    data = _load()
    expires = int((now or time.time()) + SESSION_MAX_AGE_SECONDS)
    payload = f"{expires}.{_password_fingerprint(data)}"
    return f"{payload}.{_sign(data, payload)}"


def verify_session_token(token, now=None):
    data = _load()
    if not token or "password_hash" not in data or "session_key" not in data:
        return False
    try:
        expires, fingerprint, signature = token.split(".")
        expires = int(expires)
    except ValueError:
        return False

    payload = f"{expires}.{fingerprint}"
    if not hmac.compare_digest(signature, _sign(data, payload)):
        return False
    if fingerprint != _password_fingerprint(data):
        return False
    return (now or time.time()) < expires


class LoginThrottle:
    """Slows down password guessing: after MAX_FAILURES failed logins from one
    client, further attempts are refused until LOCKOUT_SECONDS have passed."""

    MAX_FAILURES = 5
    LOCKOUT_SECONDS = 60

    def __init__(self):
        self._failures = {}

    def retry_after(self, client, now=None):
        count, last = self._failures.get(client, (0, 0.0))
        if count < self.MAX_FAILURES:
            return 0
        remaining = self.LOCKOUT_SECONDS - ((now or time.time()) - last)
        if remaining <= 0:
            self._failures.pop(client, None)
            return 0
        return int(remaining) + 1

    def record_failure(self, client, now=None):
        count, _ = self._failures.get(client, (0, 0.0))
        self._failures[client] = (count + 1, now or time.time())

    def reset(self, client):
        self._failures.pop(client, None)

    def clear(self):
        self._failures.clear()
