"""Close expired submission windows independently of students keeping a page open."""
import threading
import traceback
import time
from datetime import datetime, timedelta, timezone

from . import learning
from .storage import read_json, write_json, audit, atomic_transaction
from . import storage

_last_refresh = None


def maybe_refresh():
    """Coalesce polling while noticing changed deadline documents."""
    global _last_refresh
    names = ("learning.json", "settings.json", "assignments.json", "exam_catalog.json", "programming_attempts.json")
    def signature():
        result = []
        for name in names:
            try:
                stat = (storage.DATA_DIR / name).stat()
                result.append((stat.st_mtime_ns, stat.st_size, stat.st_ino))
            except FileNotFoundError:
                result.append(None)
        return (str(storage.DATA_DIR.resolve()), tuple(result))
    stamp = signature()
    last = _last_refresh
    if last and last[0] == stamp and time.monotonic()-last[1] < .5:
        return
    with learning.LOCK:
        last = _last_refresh
        if last and last[0] == stamp and time.monotonic()-last[1] < .5:
            return
        refresh()
        _last_refresh = (signature(), time.monotonic())


def exam_end(started_at, duration_minutes, ends_at=None):
    if ends_at:
        return learning.date_value(ends_at)
    if started_at:
        return learning.date_value(started_at) + timedelta(minutes=int(duration_minutes or 90))
    return None


def refresh(now=None):
    now = now or datetime.now(timezone.utc)
    with learning.LOCK, atomic_transaction():
        from . import exam_schedule
        exam_schedule.refresh(now)
        data = learning.load()
        changed = False
        for task in data["assignments"]:
            if not task.get("closed_at") and learning.date_value(task["due_at"]) <= now:
                task["closed_at"] = task["due_at"]
                changed = True
                audit("learning.assignment_expired", "system", None, {"id": task["id"]})
        if changed:
            write_json("learning.json", data)

        settings = read_json("settings.json")
        assignments = read_json("assignments.json")
        base_end = exam_end(settings.get("exam_started_at"), settings.get("exam_duration_minutes"), settings.get("exam_ends_at")) if settings.get("exam_state") == "started" else None
        changed = False
        for sid, item in assignments.items():
            if item.get("release_id") != settings.get("exam_release_id") or not item.get("started_at") or not item.get("ends_at"):
                continue
            if base_end and item.get("deadline_mode") != "global":
                old_default = learning.date_value(item["started_at"]) + timedelta(minutes=int(settings.get("exam_duration_minutes", 90)))
                extra = (learning.date_value(item["ends_at"]) - old_default).total_seconds()
                item.update({"ends_at": (base_end + timedelta(seconds=extra)).isoformat(), "deadline_mode": "global", "extra_time_seconds": extra})
                changed = True
            expired = learning.date_value(item["ends_at"]) <= now
            if expired and not item.get("closed_at"):
                item["closed_at"] = item["ends_at"]
                if item.get("status") not in {"submitted", "ended"}:
                    item["status"] = "expired"
                changed = True
                audit("exam.student_expired", sid, None, {"release_id": item.get("release_id")})
            elif not expired and item.get("closed_at") and not item.get("forced_submit") and settings.get("exam_state") == "started":
                # A teacher may extend an individual student's existing deadline.
                item.pop("closed_at", None)
                if item.get("status") == "expired": item["status"] = "in_progress"
                changed = True
        if changed:
            write_json("assignments.json", assignments)

        if base_end:
            effective_end = max([base_end] + [learning.date_value(a["ends_at"]) for a in assignments.values() if a.get("release_id") == settings.get("exam_release_id") and a.get("started_at") and a.get("ends_at") and not a.get("forced_submit")])
            if effective_end <= now:
                settings.update({"exam_state": "ended", "exam_released": False, "exam_ends_at": base_end.isoformat(), "exam_ended_at": effective_end.isoformat(), "exam_closed_automatically": True})
                for item in assignments.values():
                    if item.get("release_id") == settings.get("exam_release_id"):
                        item.setdefault("closed_at", effective_end.isoformat())
                        if item.get("status") not in {"submitted", "ended"}: item["status"] = "expired"
                write_json("assignments.json", assignments)
                write_json("settings.json", settings)
                audit("exam.auto_ended", "system", None, {"release_id": settings.get("exam_release_id")})

        attempts = read_json("programming_attempts.json", {})
        catalog = read_json("exam_catalog.json", [])
        catalog_changed = False
        changed = False
        for exam in catalog:
            if exam.get("type") != "programming" or exam.get("state") != "started": continue
            end = exam_end(exam.get("started_at"), exam.get("duration_minutes"), exam.get("ends_at"))
            if not end: continue
            for key, attempt in attempts.items():
                if not key.startswith(exam["id"]+":"): continue
                if learning.date_value(attempt["ends_at"]) > end:
                    attempt["ends_at"] = end.isoformat()
                    changed = True
            if end <= now:
                exam.update({"state": "ended", "ends_at": end.isoformat(), "ended_at": end.isoformat(), "closed_automatically": True})
                catalog_changed = True
                audit("programming.exam_auto_ended", "system", None, {"exam_id": exam["id"]})
        for key, attempt in attempts.items():
            if not attempt.get("closed_at") and learning.date_value(attempt["ends_at"]) <= now:
                attempt.update({"closed_at": attempt["ends_at"], "status": "expired"})
                changed = True
                audit("programming.student_expired", "system", None, {"attempt": key})
        if changed:
            write_json("programming_attempts.json", attempts)
        if catalog_changed:
            write_json("exam_catalog.json", catalog)


def start_worker():
    stop = threading.Event()
    def run():
        last_resume = 0
        while not stop.is_set():
            try: refresh()
            except Exception: traceback.print_exc()
            if time.monotonic()-last_resume >= 10:
                try:
                    from . import programming
                    programming.resume()
                except Exception:
                    traceback.print_exc()
                last_resume = time.monotonic()
            stop.wait(1)
    thread = threading.Thread(target=run, name="submission-deadlines", daemon=True)
    thread.start()
    return stop, thread
