"""Small JSON/JSONL persistence layer with atomic replacement and a process lock."""
from __future__ import annotations
import json
import copy
import logging
import functools
import tempfile
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from .config import DATA_DIR, LOG_DIR

_LOCK = threading.RLock()
_LOCAL = threading.local()
_CACHE = {}
logger = logging.getLogger(__name__)


def _journal_path():
    return DATA_DIR / ".transaction.json"


def _recover():
    """Undo an interrupted commit before exposing any JSON documents."""
    path = _journal_path()
    if not path.exists():
        return
    journal = json.loads(path.read_text(encoding="utf-8"))
    if journal.get("state") == "prepared":
        for name, previous in journal["before"].items():
            if Path(name).name != name or not name.endswith(".json"):
                raise RuntimeError("Invalid transaction journal document")
            if previous["exists"]:
                atomic_write(_path(name), previous["value"])
            else:
                _path(name).unlink(missing_ok=True)
        audit_path = _path("audit.jsonl")
        if audit_path.exists():
            with audit_path.open("r+b") as output:
                output.truncate(journal["audit_offset"])
                output.flush()
                os.fsync(output.fileno())
    elif journal.get("state") != "committed":
        raise RuntimeError("Invalid transaction journal state")
    _CACHE.clear()
    path.unlink()


def on_rollback(callback):
    batch = getattr(_LOCAL, "batch", None)
    if batch is not None:
        batch["rollback"].append(callback)


def after_commit(callback):
    batch = getattr(_LOCAL, "batch", None)
    if batch is None:
        callback()
    else:
        batch["commit"].append(callback)


def save_payload(path: Path, content: bytes):
    """Create a new payload, flush it before metadata, and clean it on rollback."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        on_rollback(lambda: path.unlink(missing_ok=True))
        output.write(content)
        output.flush()
        os.fsync(output.fileno())


def _commit(batch):
    writes, records = batch["writes"], batch["audit"]
    if not writes and not records:
        return
    before = {}
    for name in writes:
        path = _path(name)
        before[name] = {"exists":path.exists(), "value":json.loads(path.read_text(encoding="utf-8")) if path.exists() else None}
    audit_path = _path("audit.jsonl")
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    journal = {"state":"prepared", "before":before, "audit_offset":audit_path.stat().st_size if audit_path.exists() else 0}
    atomic_write(_journal_path(), journal)
    try:
        for name, value in writes.items():
            atomic_write(_path(name), value)
        if records:
            with audit_path.open("a", encoding="utf-8", newline="\n") as output:
                for record in records:
                    output.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
                output.flush()
                os.fsync(output.fileno())
        journal["state"] = "committed"
        atomic_write(_journal_path(), journal)
    except BaseException:
        try:
            _recover()
        except Exception:
            logger.exception("Transaction recovery deferred until storage becomes writable")
        raise
    _CACHE.clear()
    try:
        _journal_path().unlink()
    except OSError:
        logger.warning("Committed journal will be cleaned on the next storage access", exc_info=True)


@contextmanager
def atomic_transaction():
    """Stage JSON/audit changes, commit together, and recover interrupted writes.

    Callers using the learning lock must acquire it before entering this scope.
    Nested scopes share the outer operation; a nested failure poisons that batch.
    """
    callbacks = []
    with _LOCK:
        existing = getattr(_LOCAL, "batch", None)
        if existing is not None:
            try:
                yield
            except BaseException:
                existing["failed"] = True
                raise
            return
        _recover()
        batch = {"writes":{}, "audit":[], "rollback":[], "commit":[], "failed":False}
        _LOCAL.batch = batch
        try:
            yield
            if batch["failed"]:
                raise RuntimeError("A nested storage operation failed")
            _commit(batch)
            callbacks = batch["commit"]
        except BaseException:
            for callback in reversed(batch["rollback"]):
                try:
                    callback()
                except Exception:
                    logger.exception("Could not clean a newly staged file")
            raise
        finally:
            del _LOCAL.batch
    for callback in callbacks:
        try:
            callback()
        except Exception:
            logger.exception("Post-commit task failed; persisted work can be resumed")


def mutation(function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        from .learning import LOCK
        with LOCK, atomic_transaction():
            return function(*args, **kwargs)
    return wrapped


@contextmanager
def transaction():
    """Keep a read/modify/write operation atomic across request threads."""
    with _LOCK:
        yield


DEFAULTS = {
    "students.json": {},
    "admins.json": {},
    "settings.json": {
        "exam_duration_minutes": 90,
        "submission_policy": "configurable",
        "max_submissions": 1,
        "accepted_submission_extensions": [".zip"],
        "overwrite_previous": True,
        "exam_password_enabled": False,
        "exam_password_hash": None,
        "distribution_mode": "random",
        "distribution_config": {},
        "exam_released": False,
        "exam_state": "idle",
        "exam_release_id": None,
        "exam_release_at": None,
        "exam_participants": [],
        "max_upload_bytes": 52428800,
        "allow_late_submission": False
    },
    "assignments.json": {},
    "submissions.json": {},
    "sessions.json": {},
    "login_attempts.json": {},
    "machines.json": {}
    ,"notifications.json": []
}

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")

def _path(name: str) -> Path:
    if name.endswith(".jsonl"):
        return LOG_DIR / name
    return DATA_DIR / name

def initialize() -> None:
    with _LOCK:
        DATA_DIR.mkdir(parents=True,exist_ok=True)
        LOG_DIR.mkdir(parents=True,exist_ok=True)
        _recover()
        for name, default in DEFAULTS.items():
            p = _path(name)
            if not p.exists():
                atomic_write(p, default)
            elif name == "settings.json":
                with p.open("r", encoding="utf-8") as f:
                    current = json.load(f)
                missing = {key: value for key, value in default.items() if key not in current}
                if "exam_state" not in current:
                    current["exam_state"] = "started" if current.get("exam_released") else "idle"
                    missing.pop("exam_state", None)
                if missing:
                    current.update(missing)
                    atomic_write(p, current)
        (LOG_DIR / "audit.jsonl").touch(exist_ok=True)

def atomic_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2)
    handle, name = tempfile.mkstemp(prefix=path.name+".",suffix=".tmp",dir=path.parent)
    tmp = Path(name)
    try:
        with os.fdopen(handle,"w",encoding="utf-8",newline="\n") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp,path)
        if os.name != "nt":
            directory=os.open(path.parent,os.O_RDONLY)
            try:os.fsync(directory)
            finally:os.close(directory)
    finally:
        tmp.unlink(missing_ok=True)

def read_json(name: str, default: Any = None) -> Any:
    with _LOCK:
        batch = getattr(_LOCAL, "batch", None)
        if batch is not None and name in batch["writes"]:
            return copy.deepcopy(batch["writes"][name])
        if batch is None:
            _recover()
        p = _path(name)
        if not p.exists():
            if default is not None:
                return copy.deepcopy(default)
            return copy.deepcopy(DEFAULTS.get(name, {}))
        try:
            stat = p.stat()
            key = str(p.resolve())
            stamp = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
            cached = _CACHE.get(key)
            if cached is None or cached[0] != stamp:
                with p.open("r", encoding="utf-8") as f:
                    value = json.load(f)
                _CACHE[key] = (stamp, value)
            else:
                value = cached[1]
            return copy.deepcopy(value)
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(f"Không thể đọc {p.name}; không tự ghi đè dữ liệu lỗi: {exc}") from exc

def write_json(name: str, value: Any) -> None:
    with _LOCK:
        batch = getattr(_LOCAL, "batch", None)
        if batch is not None:
            batch["writes"][name] = copy.deepcopy(value)
            return
        _recover()
        atomic_write(_path(name), value)
        _CACHE.pop(str(_path(name).resolve()), None)

def update_json(name: str, mutator):
    with _LOCK:
        value = read_json(name)
        result = mutator(value)
        write_json(name, value)
        return result

def audit(event: str, actor: str | None, ip: str | None, details: dict | None = None) -> None:
    record = {"occurred_at": utc_now(), "event": event, "actor": actor, "ip": ip, "details": details or {}}
    p = _path("audit.jsonl")
    with _LOCK:
        batch = getattr(_LOCAL, "batch", None)
        if batch is not None:
            batch["audit"].append(record)
            return
        _recover()
        p.parent.mkdir(parents=True,exist_ok=True)
        with p.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            f.flush()
            os.fsync(f.fileno())
