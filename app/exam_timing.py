"""Scheduled shared exam windows and audited live time changes."""
from datetime import datetime, timedelta, timezone

from . import learning
from .storage import read_json, write_json, utc_now, audit, atomic_transaction


def window(scheduled_at, duration_minutes, now=None):
    now = now or datetime.now(timezone.utc)
    start = learning.date_value(scheduled_at) if scheduled_at else now
    return start, start + timedelta(minutes=int(duration_minutes))


def waiting(state, started_at, now=None):
    return state == "started" and bool(started_at) and learning.date_value(started_at) > (now or datetime.now(timezone.utc))


def update(session, form, ip):
    from . import exam_catalog
    with learning.LOCK, atomic_transaction():
        exam_id = learning.text(form, "exam_id", 80)
        row = next((e for e in exam_catalog.listing() if e["id"] == exam_id), None)
        if not row:
            raise learning.LearningError(404, "Không tìm thấy kỳ thi.")
        if row["state"] == "ended":
            raise learning.LearningError(409, "Kỳ thi đã kết thúc; không sửa thời gian của lịch sử thi.")
        if row.get("course_id"):
            learning.course_access(learning.load(), row["course_id"], session, write=True)
        if row["type"] == "file" and not row.get("active"):
            raise learning.LearningError(409, "Hãy chọn kỳ thi file này để cấu hình phát đề trước.")
        now = datetime.now(timezone.utc)
        running = row["state"] == "started" and not row.get("waiting")
        scheduled = form.get("scheduled_at", "").strip()
        requested_start = learning.date_value(scheduled) if scheduled else None
        original_start = learning.date_value(row["started_at"]) if row.get("started_at") else None
        if running and requested_start and requested_start.replace(microsecond=0) != original_start.replace(microsecond=0):
            raise learning.LearningError(409, "Kỳ thi đang diễn ra: giữ giờ bắt đầu thực tế, chỉ điều chỉnh thời lượng hoặc giờ kết thúc.")
        start = original_start if running else requested_start
        duration = learning.integer(form, "duration_minutes", row["duration_minutes"], 1, 1440)
        mode = form.get("mode", "duration")
        if mode not in {"duration", "end"}:
            raise learning.LearningError(400, "Cách điều chỉnh thời gian không hợp lệ.")
        if mode == "end":
            if not start:
                raise learning.LearningError(400, "Cần đặt giờ bắt đầu trước khi chọn giờ kết thúc cụ thể.")
            end = learning.date_value(form.get("ends_at"))
            minutes = (end-start).total_seconds()/60
            if not 1 <= minutes <= 1440:
                raise learning.LearningError(400, "Giờ kết thúc phải sau giờ bắt đầu từ 1 phút đến 24 giờ.")
            import math
            duration = math.ceil(minutes)
        else:
            end = (start or now) + timedelta(minutes=duration)
        if end <= now:
            raise learning.LearningError(400, "Giờ kết thúc phải ở tương lai. Dùng nút Kết thúc kỳ thi nếu muốn đóng ngay.")
        if row.get("waiting") and start is None:
            raise learning.LearningError(400, "Kỳ thi đang chờ cần có giờ bắt đầu.")
        published = row["state"] in {"scheduled", "started"}
        updates = {"scheduled_at": start.isoformat() if start else None, "duration_minutes": duration, "updated_at": utc_now()}
        if published:
            updates.update(started_at=start.isoformat(), ends_at=end.isoformat())
        rows = read_json("exam_catalog.json", [])
        stored = next((e for e in rows if e["id"] == exam_id), None)
        if stored:
            stored.update(updates)
            write_json("exam_catalog.json", rows)
        if row["type"] == "file":
            settings = read_json("settings.json")
            settings.update(exam_scheduled_at=updates["scheduled_at"], exam_duration_minutes=duration)
            if published:
                settings.update(exam_started_at=start.isoformat(), exam_ends_at=end.isoformat())
                assignments = read_json("assignments.json")
                for a in assignments.values():
                    if a.get("release_id") == settings.get("exam_release_id") and a.get("started_at"):
                        a["ends_at"] = (end+timedelta(seconds=a.get("extra_time_seconds", 0))).isoformat()
                        a["deadline_mode"] = "global"
                        if not a.get("forced_submit") and learning.date_value(a["ends_at"]) > now:
                            a.pop("closed_at", None)
                            if a.get("status") == "expired": a["status"] = "in_progress"
                write_json("assignments.json", assignments)
            write_json("settings.json", settings)
        elif published:
            attempts = read_json("programming_attempts.json", {})
            for key, attempt in attempts.items():
                if key.startswith(exam_id+":"):
                    attempt["ends_at"] = end.isoformat()
                    attempt.pop("closed_at", None)
                    if attempt.get("status") == "expired": attempt["status"] = "in_progress"
            write_json("programming_attempts.json", attempts)
        audit("exam.timing_updated", session["user_id"], ip, {"exam_id": exam_id, "previous_start":row.get("started_at") or row.get("scheduled_at"), "previous_end":row.get("ends_at"), "start":updates["scheduled_at"], "end":end.isoformat(), "duration_minutes":duration})
        return {"ok": True, "starts_at":updates["scheduled_at"], "ends_at":end.isoformat(), "duration_minutes":duration}
