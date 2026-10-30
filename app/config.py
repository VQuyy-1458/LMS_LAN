from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent
RUNTIME_DIR = Path(os.getenv("CSS_DATA_ROOT", str(BASE_DIR))).resolve()
DATA_DIR = RUNTIME_DIR / "data"
LOG_DIR = RUNTIME_DIR / "logs"
EXAM_DIR = RUNTIME_DIR / "de-thi"
UPLOAD_DIR = RUNTIME_DIR / "submissions"
STATIC_DIR = BASE_DIR / "static"
TEMPLATE_DIR = BASE_DIR / "templates"
HOST = os.getenv("CSS_HOST", "0.0.0.0")
PORT = int(os.getenv("CSS_PORT", "8080"))
MAX_REQUEST_SIZE = 50 * 1024 * 1024

def _request_timeout(name, default):
    value = float(os.getenv(name, default))
    if not 0 < value < float("inf"):
        raise ValueError(f"{name} must be a positive, finite number of seconds")
    return value

REQUEST_IDLE_TIMEOUT_SECONDS = _request_timeout("CSS_REQUEST_IDLE_TIMEOUT", "30")
REQUEST_BODY_TIMEOUT_SECONDS = _request_timeout("CSS_REQUEST_BODY_TIMEOUT", "300")
MAX_ZIP_ENTRIES = 3000
MAX_UNCOMPRESSED_SIZE = 250 * 1024 * 1024
SESSION_COOKIE = "css_session"
SESSION_TTL_SECONDS = 12 * 60 * 60
LOCKOUT_SECONDS = 15 * 60
MAX_FAILED_LOGINS = 3
ALLOWED_EXAM_EXTENSIONS = {".pdf", ".txt", ".png", ".jpg", ".jpeg", ".gif", ".webp"}
