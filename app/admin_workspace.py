"""Bridge course learning data and the existing file-exam workflow."""
from . import learning
from .storage import read_json, write_json, utc_now, audit


def course_members(course_id):
    students = read_json("students.json")
    if not course_id:
        return None, set(students)
    course = learning.find(learning.load(), "courses", course_id)
    return course, {sid for sid in students if course.get("student_ids") is None or sid in course["student_ids"]}


def scope_monitor(rows, course_id):
    if not course_id:
        return rows
    _, members = course_members(course_id)
    assignments = read_json("assignments.json")
    records = read_json("submissions.json")
    result = []
    for original in rows:
        if original["student_id"] not in members:
            continue
        row = dict(original)
        assignment = assignments.get(row["student_id"], {})
        if assignment.get("course_id") != course_id:
            row.update({"exam_file": None, "exam_status": "not_assigned", "started_at": None, "ends_at": None, "remaining_seconds": None})
        own = [r for r in records.get(row["student_id"], []) if r.get("course_id") == course_id]
        row.update({"submission_count": len(own), "latest_submission": own[-1] if own else None})
        result.append(row)
    return result


def overview(session, course_id=""):
    data = learning.snapshot(session)
    course_members(course_id)
    students = read_json("students.json")
    settings = read_json("settings.json")
    for course in data["courses"]:
        _, members = course_members(course["id"])
        submissions = [r for r in data["submissions"] if r["course_id"] == course["id"]]
        latest = {}
        for row in submissions:
            latest[(row["assignment_id"], row["student_id"])] = row
        course["student_count"] = len(members)
        course["pending_count"] = sum(r.get("score") is None for r in latest.values())
        course["lessons"] = [r for r in data["events"] if r["course_id"] == course["id"] and r["kind"] == "lesson"]
        course["assignment_count"] = sum(r["course_id"] == course["id"] for r in data["assignments"])
    data["stats"] = {"courses": len(data["courses"]), "students": len(students), "pending": sum(c["pending_count"] for c in data["courses"]), "running_exams": int(settings.get("exam_state") == "started")}
    data["exam"] = {"title": settings.get("exam_title") or "Kỳ thi nộp file của lớp", "course_id": settings.get("exam_course_id"), "state": settings.get("exam_state", "idle"), "duration_minutes": settings.get("exam_duration_minutes", 90), "participants": settings.get("exam_participants", []), "started_at": settings.get("exam_started_at"), "release_id": settings.get("exam_release_id")}
    data["server_time"] = utc_now()
    from .exam_catalog import listing
    data["exams"] = listing()
    data["stats"]["running_exams"] += sum(e["type"] == "programming" and e["state"] == "started" for e in data["exams"])
    return data


def set_exam_context(session, form, ip):
    with learning.LOCK:
        settings = read_json("settings.json")
        if settings.get("exam_state") in {"distributed", "started"} or settings.get("exam_released"):
            raise learning.LearningError(409, "Kỳ thi đã phát đề. Hãy kết thúc lượt thi trước khi thay đổi khóa học hoặc tên kỳ thi.")
        course_id = form.get("course_id", "").strip()
        from .exam_catalog import listing, validate_assessment
        validate_assessment(settings.get("exam_assessment_type", "test"), course_id, settings.get("exam_catalog_id") or "current", listing())
        course, members = course_members(course_id)
        if course and course["status"] == "completed":
            raise learning.LearningError(409, "Khóa học đã tổng kết, không thể mở kỳ thi mới.")
        title = learning.text(form, "title")
        students = read_json("students.json")
        settings.update({"exam_course_id": course_id or None, "exam_title": title, "exam_state": "idle", "exam_started_at": None, "exam_participants": sorted(sid for sid in members if students[sid].get("active", True))})
        write_json("settings.json", settings)
        audit("admin.exam_context_updated", session["user_id"], ip, {"course_id": course_id or None, "title": title})
        return {"ok": True}
