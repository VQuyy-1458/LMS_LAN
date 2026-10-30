"""Transfer course teaching content without accounts, grades or submissions."""
import base64
import json
import secrets

from . import learning
from .storage import write_json, utc_now, audit, atomic_transaction

FORMAT = "classroom-course-v1"
LIMIT = 15 * 1024 * 1024


def export_course(course_id, session):
    if session["role"] != "admin":
        raise learning.LearningError(403, "Chỉ giảng viên được xuất khóa học.")
    with learning.LOCK, atomic_transaction():
        data = learning.load()
        course = learning.course_access(data, course_id, session)
        package = {"format": FORMAT, "course": {**{k: course.get(k, "") for k in ("name", "code", "group", "semester", "description")}, "weights": course.get("weights", learning.WEIGHTS)}, "materials": [], "assignments": [], "events": []}
        total = 0
        for row in data["materials"]:
            if row["course_id"] != course_id:
                continue
            path, filename = learning.file_for("materials", row["id"], session)
            total += path.stat().st_size
            if total > LIMIT:
                raise learning.LearningError(413, "Tổng học liệu vượt 15 MiB cho một gói chuyển khóa.")
            package["materials"].append({**{k: row.get(k, "") for k in ("title", "topic", "description")}, "filename": filename, "data_base64": base64.b64encode(path.read_bytes()).decode("ascii")})
        for key, fields in (("assignments", ("title", "description", "topic", "due_at", "max_attempts")), ("events", ("title", "description", "kind", "starts_at", "location"))):
            package[key] = [{k: row.get(k, "") for k in fields} for row in data[key] if row["course_id"] == course_id]
        for source, exported in zip([r for r in data["assignments"] if r["course_id"] == course_id], package["assignments"]):
            if source.get("stored_name"):
                path, filename = learning.file_for("assignments", source["id"], session)
                total += path.stat().st_size
                if total > LIMIT:
                    raise learning.LearningError(413, "Tổng tài liệu và đề bài vượt 15 MiB cho một gói chuyển khóa.")
                exported.update({"filename": filename, "data_base64": base64.b64encode(path.read_bytes()).decode("ascii")})
        return package


def field(row, name, maximum=200, required=True):
    value = row.get(name, "")
    if not isinstance(value, str):
        raise learning.LearningError(400, "Gói khóa học có trường văn bản không hợp lệ.")
    return learning.text({name: value}, name, maximum, required)


def import_course(file, session, ip):
    if session["role"] != "admin":
        raise learning.LearningError(403, "Chỉ giảng viên được nhập khóa học.")
    if not file or not file.get("data"):
        raise learning.LearningError(400, "Hãy chọn gói khóa học JSON.")
    if len(file["data"]) > 24 * 1024 * 1024:
        raise learning.LearningError(413, "Gói khóa học vượt giới hạn 24 MiB.")
    try:
        package = json.loads(file["data"].decode("utf-8-sig"))
    except (ValueError, UnicodeError):
        raise learning.LearningError(400, "File không phải gói khóa học JSON hợp lệ.")
    if not isinstance(package, dict) or package.get("format") != FORMAT or not isinstance(package.get("course"), dict):
        raise learning.LearningError(400, "Định dạng gói khóa học không được hỗ trợ.")
    for key, limit in (("materials", 100), ("assignments", 200), ("events", 1000)):
        if not isinstance(package.get(key, []), list) or len(package.get(key, [])) > limit or any(not isinstance(r, dict) for r in package.get(key, [])):
            raise learning.LearningError(400, "Gói có danh sách nội dung không hợp lệ hoặc quá lớn.")
    now, cid = utc_now(), secrets.token_hex(10)
    source = package["course"]
    weights = source.get("weights", learning.WEIGHTS)
    if not isinstance(weights,dict) or set(weights)!=set(learning.WEIGHTS) or any(not isinstance(w,int) or isinstance(w,bool) or not 0<=w<=100 for w in weights.values()) or sum(weights.values())!=100:
        raise learning.LearningError(400, "Trọng số điểm trong gói không hợp lệ.")
    course = {"id": cid, "created_at": now, "created_by": session["user_id"], "name": field(source, "name"), "code": field(source, "code", 80), "group": field(source, "group", 80, False), "semester": field(source, "semester", 80), "description": field(source, "description", 10000, False), "student_ids": [], "status": "active"}
    course["weights"] = dict(weights)
    learning.enrollments.initialize(course, {}, now)
    staged = {"materials": [], "events": [], "assignments": []}
    total = 0
    for row in package.get("materials", []):
        encoded = row.get("data_base64")
        if not isinstance(encoded, str):
            raise learning.LearningError(400, "Học liệu thiếu dữ liệu file.")
        try:
            payload = base64.b64decode(encoded, validate=True)
        except ValueError:
            raise learning.LearningError(400, "Dữ liệu file trong gói không hợp lệ.")
        total += len(payload)
        if total > LIMIT:
            raise learning.LearningError(413, "Tổng học liệu trong gói vượt 15 MiB.")
        staged["materials"].append({"id": secrets.token_hex(10), "created_at": now, "course_id": cid, "title": field(row, "title"), "topic": field(row, "topic", 200, False), "description": field(row, "description", 10000, False), "file": {"filename": field(row, "filename", 180), "data": payload}})
    for row in package.get("assignments", []):
        attempts = row.get("max_attempts", 3)
        if not isinstance(attempts, int) or isinstance(attempts, bool) or not 1 <= attempts <= 20:
            raise learning.LearningError(400, "Số lần nộp trong gói không hợp lệ.")
        staged["assignments"].append({"id": secrets.token_hex(10), "created_at": now, "course_id": cid, "title": field(row, "title"), "description": field(row, "description", 10000, False), "topic": field(row, "topic", 200, False), "due_at": learning.date_value(row.get("due_at")).isoformat(), "max_attempts": attempts})
        if "data_base64" in row:
            if not isinstance(row["data_base64"], str):
                raise learning.LearningError(400, "Dữ liệu đề bài trong gói không hợp lệ.")
            try:
                payload = base64.b64decode(row["data_base64"], validate=True)
            except ValueError:
                raise learning.LearningError(400, "Dữ liệu đề bài trong gói không hợp lệ.")
            total += len(payload)
            if total > LIMIT:
                raise learning.LearningError(413, "Tổng tài liệu và đề bài trong gói vượt 15 MiB.")
            staged["assignments"][-1]["file"] = {"filename": field(row, "filename", 180), "data": payload}
    for row in package.get("events", []):
        if row.get("kind") not in {"lesson", "announcement", "exam"}:
            raise learning.LearningError(400, "Loại lịch trong gói không hợp lệ.")
        staged["events"].append({"id": secrets.token_hex(10), "created_at": now, "course_id": cid, "title": field(row, "title"), "description": field(row, "description", 10000, False), "kind": row["kind"], "starts_at": learning.date_value(row.get("starts_at")).isoformat(), "location": field(row, "location", 200, False)})
    written = []
    with learning.LOCK:
        data = learning.load()
        try:
            for row in staged["materials"] + staged["assignments"]:
                if "file" not in row:
                    continue
                row.update(learning.save_file(row.pop("file")))
                written.append(learning.FILES / row["stored_name"])
            data["courses"].append(course)
            for key in staged:
                data[key].extend(staged[key])
            write_json("learning.json", data)
        except Exception:
            for path in written:
                if path.resolve().parent == learning.FILES.resolve():
                    path.unlink(missing_ok=True)
            raise
        audit("learning.course_imported", session["user_id"], ip, {"id": cid})
    return {"ok": True, "id": cid}
