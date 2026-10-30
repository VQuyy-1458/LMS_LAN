"""Saved exam configurations; the existing file-exam engine runs one release at a time."""
import copy
import json
import re
import uuid

from . import learning, code_runner
from .storage import read_json, write_json, utc_now, audit, atomic_transaction

CURRENT = "current"
FILE_KEYS = ("exam_duration_minutes", "submission_policy", "max_submissions", "overwrite_previous", "accepted_submission_extensions")


def listing():
    rows = copy.deepcopy(read_json("exam_catalog.json", []))
    settings = read_json("settings.json")
    active_id = settings.get("exam_catalog_id") or CURRENT
    active = next((r for r in rows if r["id"] == active_id), None)
    if active is None:
        active = {"id": active_id, "type": "file", "scheduled_at": None, "created_at": "", "description": ""}
        rows.insert(0, active)
    active.update({"title": settings.get("exam_title") or "Kỳ thi nộp file của lớp", "course_id": settings.get("exam_course_id"), "state": settings.get("exam_state", "idle"), "duration_minutes": settings.get("exam_duration_minutes", 90), "participants": settings.get("exam_participants", []), "started_at": settings.get("exam_started_at"), "active": True, "file_settings": {k: settings.get(k) for k in FILE_KEYS}})
    active["scheduled_at"] = settings.get("exam_scheduled_at") or active.get("scheduled_at")
    for row in rows:
        row.setdefault("active", False)
        row.setdefault("state", "idle")
        row.setdefault("assessment_type", settings.get("exam_assessment_type", "test") if row["id"] == active_id else "test")
        if row["id"] == active_id:
            row["release_id"] = settings.get("exam_release_id")
            from .deadlines import exam_end
            end=exam_end(settings.get("exam_started_at"),settings.get("exam_duration_minutes"),settings.get("exam_ends_at")) if settings.get("exam_state") in {"started","ended"} else None
            row["ends_at"]=end.isoformat() if end else None
    from .exam_timing import waiting
    from .exam_schedule import describe
    for row in rows:
        row.update(describe(row))
        row["waiting"] = waiting(row["state"], row.get("started_at")) or row["auto_start_ready"]
        if row["auto_start_ready"]:
            row["ends_at"] = row["planned_end"]
    return rows


def validate_assessment(assessment_type, course_id, exam_id, rows):
    if assessment_type not in {"test", "midterm", "final"}:
        raise learning.LearningError(400, "Chọn loại kỳ thi: Test, Giữa kỳ hoặc Cuối kỳ.")
    if assessment_type != "test" and not course_id:
        raise learning.LearningError(400, "Kỳ thi tính điểm phải thuộc một khóa học.")
    if assessment_type == "final" and any(r["id"] != exam_id and r.get("course_id") == course_id and r.get("assessment_type") == "final" for r in rows):
        raise learning.LearningError(409, "Mỗi khóa học chỉ có một kỳ thi cuối kỳ, kể cả thi nộp file và thi lập trình.")


def integer(value, label, low, high):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise learning.LearningError(400, f"{label} không hợp lệ.")
    if not low <= number <= high:
        raise learning.LearningError(400, f"{label} phải từ {low} đến {high}.")
    return number


def prepare_programming_participants(raw, course_id):
    """Validate the roster before creating accounts; caller holds an atomic transaction."""
    ids = [value.strip() for value in raw.replace(",", "\n").splitlines() if value.strip()]
    if not ids:
        raise learning.LearningError(400, "Hãy chọn hoặc nhập ít nhất một MSSV.")
    if len(ids) > 10000 or any(len(sid) > 80 or not sid.isalnum() for sid in ids):
        raise learning.LearningError(400, "Danh sách MSSV không hợp lệ (tối đa 10.000 MSSV, mỗi MSSV tối đa 80 chữ hoặc số).")
    ids = list(dict.fromkeys(ids))
    from .admin_workspace import course_members
    course, _ = course_members(course_id)
    if course and course["status"] == "completed":
        raise learning.LearningError(409, "Khóa học đã tổng kết, không thể thay đổi danh sách dự thi.")
    if course and course.get("student_ids") is not None and not set(ids).issubset(course["student_ids"]):
        raise learning.LearningError(400, "Danh sách dự thi có MSSV không thuộc khóa học. Hãy thêm sinh viên vào khóa học trước.")
    students = read_json("students.json")
    if any(sid in students and not students[sid].get("active", True) for sid in ids):
        raise learning.LearningError(400, "Danh sách có tài khoản đang bị khóa. Hãy mở tài khoản hoặc bỏ chọn sinh viên đó.")
    from .security import hash_password
    created = []
    for sid in ids:
        if sid not in students:
            students[sid] = {"student_id": sid, "full_name": "Chưa cập nhật", "password_hash": hash_password(sid), "active": True, "created_at": utc_now(), "last_ip": None, "last_seen": None, "must_change_password": True}
            created.append(sid)
    if created:
        write_json("students.json", students)
    return ids, created


def save_programming_participants(session, form, ip):
    with learning.LOCK, atomic_transaction():
        catalog = read_json("exam_catalog.json", [])
        row = next((r for r in catalog if r["id"] == form.get("exam_id") and r["type"] == "programming"), None)
        if not row:
            raise learning.LearningError(404, "Không tìm thấy kỳ thi lập trình.")
        if row.get("state", "idle") != "idle":
            raise learning.LearningError(409, "Không thể thay đổi danh sách dự thi khi kỳ thi đã mở hoặc kết thúc.")
        if "course_id" in form and (form["course_id"] or None) != row.get("course_id"):
            raise learning.LearningError(409, "Khóa học của kỳ thi đã thay đổi. Hãy tải lại danh sách dự thi.")
        ids, created = prepare_programming_participants(form.get("student_ids", ""), row.get("course_id"))
        row.update(participants=ids, participants_configured=True, updated_at=utc_now())
        write_json("exam_catalog.json", catalog)
        audit("admin.programming_participants_updated", session["user_id"], ip, {"exam_id": row["id"], "count": len(ids), "created": len(created)})
        return {"ok": True, "exam_id": row["id"], "student_ids": ids, "created": created, "count": len(ids)}


def save(session, form, ip):
    with learning.LOCK, atomic_transaction():
        rows = listing()
        exam_id = form.get("id", "")
        old = next((r for r in rows if r["id"] == exam_id), None)
        if exam_id and not old:
            raise learning.LearningError(404, "Không tìm thấy kỳ thi.")
        if old and old["state"] in {"distributed", "scheduled", "started", "ended"}:
            raise learning.LearningError(409, "Kỳ thi đã phát đề. Không thể thay đổi cấu hình của lượt thi này.")
        kind = form.get("type", "file")
        if kind not in {"file", "programming"} or old and old["type"] != kind:
            raise learning.LearningError(400, "Loại kỳ thi không hợp lệ hoặc đã được cố định.")
        course_id = learning.text(form, "course_id", required=False) or None
        assessment_type = form.get("assessment_type", old.get("assessment_type", "test") if old else "test")
        validate_assessment(assessment_type, course_id, exam_id, rows)
        from .admin_workspace import course_members
        course, members = course_members(course_id)
        if course and course["status"] == "completed":
            raise learning.LearningError(409, "Khóa học đã tổng kết, không thể thay đổi kỳ thi.")
        scheduled = form.get("scheduled_at", "").strip()
        if scheduled:
            scheduled = learning.date_value(scheduled).isoformat()
        students = read_json("students.json")
        metadata_only = bool(old and old["active"] and kind == "file" and form.get("metadata_only") == "true")
        row = {"id": exam_id or uuid.uuid4().hex, "type": kind, "course_id": course_id, "title": learning.text(form, "title"), "description": learning.text(form, "description", required=False, limit=10000), "duration_minutes": old["duration_minutes"] if metadata_only else integer(form.get("duration_minutes", "90"), "Thời lượng", 1, 1440), "scheduled_at": scheduled or None, "state": old.get("state", "idle") if old else "idle", "participants": sorted(s for s in members if students[s].get("active", True)), "created_at": old.get("created_at") if old else utc_now(), "updated_at": utc_now()}
        row["assessment_type"] = assessment_type
        if old:
            for key in ("release_id", "started_at", "ended_at"):
                if old.get(key): row[key] = old[key]
        if old and old["active"] and old["course_id"] == course_id:
            row["participants"] = old["participants"]
        if kind == "programming" and old and old.get("participants_configured") and old["course_id"] == course_id:
            row["participants"] = old["participants"]
            row["participants_configured"] = True
        if kind == "programming":
            languages = list(dict.fromkeys(form.get("languages", "").split(",")))
            if not languages or any(x not in {"c", "cpp", "java", "python"} for x in languages):
                raise learning.LearningError(400, "Chọn ít nhất một ngôn ngữ lập trình hợp lệ.")
            try:
                problems = json.loads(form.get("problems", "[]"))
            except (TypeError, ValueError):
                raise learning.LearningError(400, "Danh sách bài toán không hợp lệ.")
            if not isinstance(problems, list) or len(problems) > 30:
                raise learning.LearningError(400, "Mỗi kỳ thi có tối đa 30 bài toán.")
            cleaned = []
            for problem in problems:
                if not isinstance(problem, dict):
                    raise learning.LearningError(400, "Bài toán không hợp lệ.")
                if not isinstance(problem.get("title", ""), str) or not isinstance(problem.get("statement", ""), str):
                    raise learning.LearningError(400, "Tên và đề bài phải là văn bản.")
                tests = problem.get("tests", [])
                if not isinstance(tests, list) or len(tests) > 100:
                    raise learning.LearningError(400, "Mỗi bài toán có tối đa 100 test case.")
                cases = []
                for test in tests:
                    if not isinstance(test, dict) or not isinstance(test.get("input", ""), str) or not isinstance(test.get("output", ""), str) or len(test.get("input", "")) > 100000 or len(test.get("output", "")) > 100000:
                        raise learning.LearningError(400, "Dữ liệu test case không hợp lệ hoặc quá lớn.")
                    cases.append({"input": test.get("input", ""), "output": test.get("output", ""), "sample": test.get("sample") is True})
                checker = problem.get("checker", "tokens")
                if checker not in {"exact", "tokens"}:
                    raise learning.LearningError(400, "Cách so khớp kết quả không hợp lệ.")
                cleaned.append({"title": learning.text(problem, "title"), "statement": learning.text(problem, "statement", required=False, limit=20000), "points": integer(problem.get("points", 100), "Điểm bài toán", 1, 1000), "time_limit_ms": integer(problem.get("time_limit_ms", 1000), "Giới hạn thời gian (ms)", 100, 30000), "memory_limit_mb": integer(problem.get("memory_limit_mb", 256), "Bộ nhớ (MB)", 16, 2048), "checker": checker, "tests": cases})
            row["programming"] = {"languages": languages, "problems": cleaned}
            if any(not code_runner.budget_valid(problem) for problem in cleaned):
                raise learning.LearningError(400, "Số test và thời gian mỗi test vượt ngân sách chấm. Hãy giảm số test hoặc giới hạn thời gian.")
            if "participant_ids" in form:
                row["participants"], _ = prepare_programming_participants(form["participant_ids"], course_id)
                row["participants_configured"] = True
        elif metadata_only:
            row["file_settings"] = old["file_settings"]
        else:
            policy = form.get("submission_policy", "once")
            if policy not in {"once", "configurable"}:
                raise learning.LearningError(400, "Chính sách nộp không hợp lệ.")
            extensions = sorted(set(form.get("accepted_submission_extensions", ".zip").replace(",", " ").lower().split()))
            if not extensions or any(not re.fullmatch(r"\.[a-z0-9]{1,9}", x) for x in extensions):
                raise learning.LearningError(400, "Định dạng file không hợp lệ. Ví dụ: .zip .pdf")
            row["file_settings"] = {"exam_duration_minutes": row["duration_minutes"], "submission_policy": policy, "max_submissions": integer(form.get("max_submissions", "1"), "Số lần nộp", 1, 20), "overwrite_previous": form.get("overwrite_previous") == "true", "accepted_submission_extensions": extensions}
        if old and old["active"]:
            settings = read_json("settings.json")
            settings.update(row["file_settings"])
            settings.update({"exam_title": row["title"], "exam_course_id": course_id, "exam_participants": row["participants"], "exam_catalog_id": row["id"], "exam_assessment_type": assessment_type})
            settings["exam_scheduled_at"] = row.get("scheduled_at")
            write_json("settings.json", settings)
        # Active fields are overlaid from the running engine when read.
        saved = [r for r in rows if r["id"] != row["id"]]
        saved.append(row)
        for r in saved:
            r.pop("active", None)
        write_json("exam_catalog.json", saved)
        audit("admin.exam_configuration_saved", session["user_id"], ip, {"id": row["id"], "type": kind})
        return {"ok": True, "id": row["id"]}


def activate(session, form, ip):
    with learning.LOCK, atomic_transaction():
        rows = listing()
        row = next((r for r in rows if r["id"] == form.get("id")), None)
        if not row:
            raise learning.LearningError(404, "Không tìm thấy kỳ thi.")
        if row["type"] != "file":
            raise learning.LearningError(409, "Thi lập trình được mở trong phần Vận hành & chấm thi lập trình, không dùng quy trình phát đề file.")
        if row["active"]:
            return {"ok": True}
        settings = read_json("settings.json")
        if settings.get("exam_state") in {"distributed", "started"}:
            raise learning.LearningError(409, "Đang có lượt thi đã phát đề. Hãy kết thúc lượt thi đó trước.")
        from .admin_workspace import course_members
        course, members = course_members(row["course_id"])
        if course and course["status"] == "completed":
            raise learning.LearningError(409, "Khóa học đã tổng kết.")
        students = read_json("students.json")
        settings.update(row["file_settings"])
        settings["exam_assessment_type"] = row["assessment_type"]
        settings["exam_scheduled_at"] = row.get("scheduled_at")
        settings.update({"exam_catalog_id": row["id"], "exam_course_id": row["course_id"], "exam_title": row["title"], "exam_participants": sorted(s for s in members if students[s].get("active", True)), "exam_state": "idle", "exam_released": False, "exam_started_at": None, "exam_release_id": None, "exam_release_at": None, "exam_password_enabled": False, "exam_password_hash": None})
        for r in rows:
            r.pop("active", None)
        row["state"] = "idle"
        write_json("exam_catalog.json", rows)
        write_json("settings.json", settings)
        audit("admin.exam_configuration_activated", session["user_id"], ip, {"id": row["id"]})
        return {"ok": True}
