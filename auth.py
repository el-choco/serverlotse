"""Signed browser sessions. The environment token is never sent to the browser."""
import hashlib
import hmac
from http.cookies import SimpleCookie, CookieError
import os
import secrets
import threading
import time

COOKIE = "serverlotse_session"
GUARD = threading.Lock()
REVOKED = {}
ATTEMPTS = {}
MAX_AGE = 30 * 86400


def sign(payload, token):
    return hmac.new(token.encode(), ("session:" + payload).encode(), hashlib.sha256).hexdigest()


def issue(token, remember=True):
    lifetime = MAX_AGE if remember else 12 * 3600
    payload = f"{int(time.time()) + lifetime}.{secrets.token_hex(24)}"
    return payload + "." + sign(payload, token), lifetime


def from_header(header):
    try:
        cookies = SimpleCookie()
        cookies.load(header or "")
        return cookies[COOKIE].value if COOKIE in cookies else ""
    except CookieError:
        return ""


def valid(value, token):
    if not token or not value or len(value) > 200:
        return False
    try:
        expiry, nonce, signature = value.split(".")
        expires = int(expiry)
        if expires <= time.time() or expires > time.time() + MAX_AGE + 5 or len(nonce) != 48:
            return False
        if not hmac.compare_digest(signature, sign(expiry + "." + nonce, token)):
            return False
        with GUARD:
            return value not in REVOKED
    except (ValueError, TypeError):
        return False


def cookie(value, lifetime=None):
    result = f"{COOKIE}={value}; Path=/; HttpOnly; SameSite=Strict"
    if lifetime is not None:
        result += f"; Max-Age={lifetime}"
    if os.getenv("SESSION_COOKIE_SECURE", "1") == "1":
        result += "; Secure"
    return result


def revoke(value):
    if not value:
        return
    with GUARD:
        for item, expires in list(REVOKED.items()):
            if expires <= time.time():
                del REVOKED[item]
        if len(REVOKED) >= 2000:
            raise ValueError("Zu viele abgemeldete Sitzungen. Bitte später erneut versuchen.")
        try:
            REVOKED[value] = int(value.split(".")[0])
        except ValueError:
            return


def allow_attempt(peer):
    now = time.time()
    with GUARD:
        for address, times in list(ATTEMPTS.items()):
            times[:] = [stamp for stamp in times if now - stamp < 60]
            if not times:
                del ATTEMPTS[address]
        if len(ATTEMPTS) >= 500 and peer not in ATTEMPTS:
            return False
        times = ATTEMPTS.setdefault(peer, [])
        if len(times) >= 10:
            return False
        times.append(now)
        return True
