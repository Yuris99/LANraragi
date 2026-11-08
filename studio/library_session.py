"""Hub login for the whole Library.

The browser signs in once at /login. The Studio issues a signed, HttpOnly cookie;
the gateway asks /api/auth/check (auth_request) before every other section.
Signing key = HMAC(server secret, STUDIO_PASSWORD), so changing the password or
rotating the secret file signs every browser out.
"""
import base64
import hashlib
import hmac
import os
import secrets
import threading
import time
from pathlib import Path

COOKIE = 'library_session'
LIFETIME = 30 * 24 * 3600


def _b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()


class Sessions:
    def __init__(self, secret_path=None, password=None, lifetime=LIFETIME):
        self.password = password if password is not None else os.environ.get('STUDIO_PASSWORD', '')
        self.lifetime = lifetime
        self.secret_path = Path(secret_path) if secret_path else None
        self._secret = self._load_secret()
        self._failures = {}
        self._lock = threading.Lock()

    def _load_secret(self):
        env = os.environ.get('STUDIO_SESSION_SECRET', '')
        if env:
            return env.encode()
        if self.secret_path:
            try:
                return self.secret_path.read_bytes().strip()
            except FileNotFoundError:
                value = secrets.token_hex(32).encode()
                self.secret_path.parent.mkdir(parents=True, exist_ok=True)
                fd = os.open(self.secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, 'wb') as handle:
                    handle.write(value)
                return value
        return secrets.token_hex(32).encode()

    def _key(self):
        return hmac.new(self._secret, self.password.encode(), hashlib.sha256).digest()

    def _sign(self, payload):
        return _b64(hmac.new(self._key(), payload.encode(), hashlib.sha256).digest())

    def issue(self, now=None):
        expires = int((time.time() if now is None else now) + self.lifetime)
        payload = f'{expires}.{secrets.token_hex(8)}'
        return f'{payload}.{self._sign(payload)}'

    def valid(self, token, now=None):
        if not self.password or not token or len(token) > 200:
            return False
        parts = token.split('.')
        if len(parts) != 3 or not parts[0].isdigit():
            return False
        payload = parts[0] + '.' + parts[1]
        if not hmac.compare_digest(parts[2], self._sign(payload)):
            return False
        return int(parts[0]) > (time.time() if now is None else now)

    def check_password(self, candidate, client):
        """Constant-time compare with a per-client backoff after repeated failures."""
        now = time.time()
        with self._lock:
            count, until = self._failures.get(client, (0, 0))
            if until > now:
                return None  # locked out for a moment
        ok = bool(self.password) and hmac.compare_digest(str(candidate).encode(), self.password.encode())
        with self._lock:
            if ok:
                self._failures.pop(client, None)
            else:
                count += 1
                self._failures[client] = (count, now + min(60, 2 ** max(0, count - 3)) if count >= 4 else 0)
                if len(self._failures) > 1000:
                    self._failures.clear()
        return ok

    @staticmethod
    def cookie_from(header):
        for part in (header or '').split(';'):
            name, _, value = part.strip().partition('=')
            if name == COOKIE:
                return value
        return ''

    def set_cookie(self, token, secure):
        return (f'{COOKIE}={token}; Path=/; Max-Age={self.lifetime}; HttpOnly; SameSite=Lax'
                + ('; Secure' if secure else ''))

    @staticmethod
    def clear_cookie(secure):
        return f'{COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax' + ('; Secure' if secure else '')
