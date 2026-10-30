"""Authentication helpers using only Python's standard library."""
from __future__ import annotations
import hashlib
import hmac
import ipaddress
import os
import secrets
import time
import threading
import math
from datetime import datetime
from urllib.parse import urlsplit
from .config import SESSION_TTL_SECONDS, SESSION_COOKIE, LOCKOUT_SECONDS, MAX_FAILED_LOGINS
from .storage import read_json, write_json, utc_now, audit, transaction
_HASH_SLOTS = threading.BoundedSemaphore(4)

class SecurityError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail

def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    if not _HASH_SLOTS.acquire(timeout=2):
        raise SecurityError(429, "Đang có nhiều yêu cầu xác thực. Vui lòng thử lại sau ít giây.")
    try:
        digest = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt), n=2**14, r=8, p=1, dklen=32).hex()
    finally:
        _HASH_SLOTS.release()
    return f"scrypt${salt}${digest}"

def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        algorithm, salt, digest = encoded.split("$", 2)
        if algorithm != "scrypt":
            return False
        candidate = hash_password(password, salt).split("$", 2)[2]
        return hmac.compare_digest(candidate, digest)
    except (ValueError, TypeError):
        return False

@transaction()
def new_session(user_id: str, role: str, ip: str, user_agent: str) -> str:
    token = secrets.token_urlsafe(32)
    sessions = read_json("sessions.json")
    sessions = {key:value for key,value in sessions.items() if value.get("expires_at", 0) >= time.time()}
    token_key = hashlib.sha256(token.encode("utf-8")).hexdigest()
    sessions[token_key] = {"user_id": user_id, "role": role, "created_at": utc_now(), "expires_at": time.time() + SESSION_TTL_SECONDS, "ip": ip, "user_agent": user_agent[:300], "last_seen": utc_now()}
    write_json("sessions.json", sessions)
    return token

@transaction()
def get_session(request, touch=True) -> dict | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    sessions = read_json("sessions.json")
    token_key = hashlib.sha256(token.encode("utf-8")).hexdigest()
    item = sessions.get(token_key)
    if not item or item.get("expires_at", 0) < time.time():
        if item:
            sessions.pop(token_key, None)
            write_json("sessions.json", sessions)
        return None
    try:
        elapsed = time.time() - datetime.fromisoformat(item.get("last_seen", "")).timestamp()
    except (TypeError, ValueError):
        elapsed = float("inf")
    ip = request.client.host if getattr(request, "client", None) else item.get("ip")
    if touch and (elapsed >= 10 or ip != item.get("ip")):
        item["last_seen"] = utc_now()
        item["ip"] = ip
        write_json("sessions.json", sessions)
    return {**item, "token": token, "token_key": token_key}

def require_user(request, role: str | None = None, touch=True) -> dict:
    session = get_session(request, touch=touch)
    if not session:
        raise SecurityError(401, "Vui lòng đăng nhập.")
    if role and session["role"] != role:
        raise SecurityError(403, "Bạn không có quyền thực hiện thao tác này.")
    return session

def client_ip(request) -> str:
    return request.client.host if getattr(request, "client", None) else "unknown"

def login_allowed(key: str) -> tuple[bool, int]:
    attempts = read_json("login_attempts.json")
    item = attempts.get(key, {})
    remaining = float(item.get("locked_until", 0)) - time.time()
    return remaining <= 0, max(0, math.ceil(remaining))


def login_state(key, attempts):
    until=float(attempts.get(key.casefold(),{}).get("locked_until",0))
    seconds=max(0,math.ceil(until-time.time()))
    return {"login_locked":seconds>0,"login_retry_after_seconds":seconds,"login_locked_until":until if seconds else None}

@transaction()
def record_login_failure(key: str) -> int:
    attempts = read_json("login_attempts.json")
    now = time.time()
    attempts = {name:row for name,row in attempts.items() if row.get("locked_until", 0) > now or now-row.get("window_start", 0) < LOCKOUT_SECONDS}
    if key not in attempts and len(attempts) >= 8192:
        oldest = min(attempts, key=lambda name:attempts[name].get("window_start", 0))
        attempts.pop(oldest)
    item = attempts.get(key, {"failures": 0, "window_start": time.time()})
    now = time.time()
    if now - item.get("window_start", now) > LOCKOUT_SECONDS:
        item = {"failures": 0, "window_start": now}
    item["failures"] = int(item.get("failures", 0)) + 1
    if item["failures"] >= MAX_FAILED_LOGINS:
        item["locked_until"] = now + LOCKOUT_SECONDS
        item["failures"] = 0
        item["window_start"] = now
    attempts[key] = item
    write_json("login_attempts.json", attempts)
    return max(0, int(item.get("locked_until", 0) - now))


@transaction()
def check_login_source(ip):
    now = time.time()
    rows = {key:[at for at in values if at > now-60] for key,values in read_json("auth_throttle.json", {}).items()}
    rows = {key:values for key,values in rows.items() if values}
    recent = rows.setdefault(ip, [])
    if len(recent) >= 120:
        raise SecurityError(429, "Có quá nhiều yêu cầu đăng nhập từ máy này. Vui lòng thử lại sau một phút.")
    if len(rows) > 4096:
        oldest = min((key for key in rows if key != ip), key=lambda key:rows[key][-1])
        rows.pop(oldest)
    recent.append(now)
    write_json("auth_throttle.json", rows)

@transaction()
def clear_login_failures(key: str) -> None:
    attempts = read_json("login_attempts.json")
    attempts.pop(key, None)
    write_json("login_attempts.json", attempts)

@transaction()
def revoke_student_sessions(student_id: str) -> int:
    sessions = read_json("sessions.json")
    revoked = [key for key, value in sessions.items() if value.get("role") == "student" and value.get("user_id") == student_id]
    for key in revoked: sessions.pop(key)
    if revoked: write_json("sessions.json", sessions)
    return len(revoked)


@transaction()
def logout_session(token: str) -> None:
    sessions = read_json("sessions.json")
    sessions.pop(hashlib.sha256(token.encode("utf-8")).hexdigest(), None)
    write_json("sessions.json", sessions)

def check_origin(request) -> None:
    """Validate a browser Origin against the request Host without brittle string matching.

    Browsers can normalize host casing and omit default ports. Compare parsed
    hostnames and effective ports instead of requiring the Origin string to be
    byte-for-byte equal to ``scheme://Host``. Requests without Origin are kept
    compatible with non-browser clients; cookie-authenticated browser forms are
    protected by checking any Origin that is supplied.
    """
    origin = (request.headers.get("Origin") or "").strip()
    if not origin:
        return
    host_header = (request.headers.get("Host") or "").strip()
    allowed_origins = {
        item.strip().rstrip("/")
        for item in os.getenv("CSS_ALLOWED_ORIGINS", "").split(",")
        if item.strip()
    }
    if allowed_origins and origin.rstrip("/") in allowed_origins:
        return
    if origin.lower() == "null" and _is_verified_loopback_request(request, host_header):
        return
    try:
        parsed_origin = urlsplit(origin)
        parsed_host = urlsplit("//" + host_header)
        request_scheme = getattr(request, "scheme", None)
        if (
            parsed_origin.scheme.lower() not in ("http", "https")
            or not parsed_origin.hostname
            or parsed_origin.username is not None
            or parsed_origin.password is not None
            or parsed_origin.path not in ("", "/")
            or parsed_origin.query
            or parsed_origin.fragment
            or not parsed_host.hostname
            or parsed_host.username is not None
            or parsed_host.password is not None
            or parsed_host.path
            or parsed_host.query
            or parsed_host.fragment
            or (request_scheme and parsed_origin.scheme.lower() != request_scheme.lower())
        ):
            raise ValueError("Malformed Origin or Host")

        origin_scheme = parsed_origin.scheme.lower()
        origin_port = parsed_origin.port or (443 if origin_scheme == "https" else 80)
        host_port = parsed_host.port or (443 if origin_scheme == "https" else 80)
        same_host = _normalize_hostname(parsed_origin.hostname) == _normalize_hostname(parsed_host.hostname)
        if not same_host or origin_port != host_port:
            raise ValueError("Origin does not match Host")
    except (ValueError, UnicodeError) as exc:
        raise SecurityError(
            403,
            "Origin không hợp lệ. "
            f"Origin={origin or '(trống)'}, Host={host_header or '(trống)'}. "
            "Hãy mở trang bằng đúng URL server in ra, không mở file HTML trực tiếp.",
        ) from exc


def _normalize_hostname(hostname: str) -> str:
    """Normalize DNS names and IP literals without changing their identity."""
    value = hostname.rstrip(".").lower()
    try:
        return ipaddress.ip_address(value).compressed
    except ValueError:
        return value


def _is_verified_loopback_request(request, host_header: str) -> bool:
    """Accept privacy-mode ``Origin: null`` only for browser same-origin requests.

    Browsers can send ``null`` for a same-origin form in privacy/WebView modes.
    A file:// page normally sends ``Sec-Fetch-Site: none`` or ``cross-site`` and
    therefore does not pass this check.
    """
    try:
        host = urlsplit("//" + host_header)
        if not host.hostname or not ipaddress.ip_address(host.hostname).is_loopback:
            return False
        fetch_site = (request.headers.get("Sec-Fetch-Site") or "").strip().lower()
        if fetch_site == "same-origin":
            return True
        referer = (request.headers.get("Referer") or "").strip()
        if not referer:
            return False
        parsed_referer = urlsplit(referer)
        return (
            parsed_referer.scheme in ("http", "https")
            and _normalize_hostname(parsed_referer.hostname or "") == _normalize_hostname(host.hostname)
            and (parsed_referer.port or (443 if parsed_referer.scheme == "https" else 80))
            == (host.port or (443 if parsed_referer.scheme == "https" else 80))
        )
    except (ValueError, UnicodeError):
        return False
