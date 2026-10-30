"""Personal notification feed and persistent read receipts."""
import hashlib
import threading

from . import learning
from .storage import read_json, write_json, utc_now

LOCK = threading.RLock()


def feed(student_id, workspace=None):
    workspace = workspace if workspace is not None else learning.snapshot({"role": "student", "user_id": student_id})
    receipts = read_json("notification_reads.json", {}).get(student_id, {})
    rows = []
    for item in read_json("notifications.json", []):
        if item.get("student_id") not in (None, student_id):
            continue
        fallback = hashlib.sha256((item.get("created_at", "") + item.get("message", "")).encode()).hexdigest()[:20]
        key = "notice:" + str(item.get("id") or fallback)
        message = item.get("message", "")
        rows.append({"id": key, "sender": item.get("created_by") or "Giảng viên", "title": item.get("title") or message.split("\n", 1)[0][:160] or "Thông báo từ giảng viên", "description": message, "created_at": item.get("created_at"), "scope": "personal" if item.get("student_id") else "general", "course_name": "", "read": key in receipts})
    courses = {c["id"]: c["name"] for c in workspace["courses"]}
    for item in workspace["events"]:
        if item.get("kind") != "announcement":
            continue
        key = "course:" + item["id"]
        rows.append({"id": key, "sender": item.get("created_by") or "Giảng viên", "title": item["title"], "description": item.get("description", ""), "created_at": item.get("starts_at") or item.get("created_at"), "scope": "course", "course_name": courses.get(item["course_id"], ""), "read": key in receipts})
    return sorted(rows, key=lambda row: row.get("created_at") or "", reverse=True)


def mark_read(student_id, ids=None, all_visible=False):
    with LOCK:
        visible = {item["id"] for item in feed(student_id)}
        selected = visible if all_visible else set(ids or [])
        if not selected.issubset(visible):
            raise learning.LearningError(404, "Không tìm thấy thông báo thuộc tài khoản của bạn.")
        receipts = read_json("notification_reads.json", {})
        own = receipts.setdefault(student_id, {})
        own.update({key: utc_now() for key in selected})
        receipts[student_id] = {key: value for key, value in own.items() if key in visible}
        write_json("notification_reads.json", receipts)
        return {"ok": True, "ids": sorted(selected)}
