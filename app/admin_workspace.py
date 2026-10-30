"""Bridge course learning data and the existing file-exam workflow."""
from datetime import datetime, timezone

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


def exam_monitor(rows, exam_id, course_id=""):
    """Project presence onto one exam; never mix another exam's attempts or files."""
    from .exam_catalog import listing
    exam = next((e for e in listing() if e["id"] == exam_id), None)
    if not exam:
        raise learning.LearningError(404, "Không tìm thấy kỳ thi cần giám sát.")
    if course_id and exam.get("course_id") != course_id:
        raise learning.LearningError(403, "Kỳ thi không thuộc khóa học đang chọn.")
    now = datetime.now(timezone.utc)
    end = learning.date_value(exam["ends_at"]) if exam.get("ends_at") else None
    live = bool(exam["state"] == "started" and not exam.get("waiting") and end and end > now)
    members = set(exam.get("participants", []))
    attempts = read_json("programming_attempts.json", {}) if exam["type"] == "programming" else {}
    code_records = read_json("programming_submissions.json", []) if exam["type"] == "programming" else []
    code_by_student = {}
    for record in code_records:
        if record["exam_id"] == exam_id:
            code_by_student.setdefault(record["student_id"], []).append(record)
    problem_count = len(exam.get("programming", {}).get("problems", []))
    file_records = read_json("submissions.json") if exam["type"] == "file" else {}
    assignments = read_json("assignments.json") if exam["type"] == "file" else {}
    result = []
    for original in rows:
        sid = original["student_id"]
        if sid not in members:
            continue
        row = dict(original)
        if exam["type"] == "programming":
            attempt = attempts.get(exam_id + ":" + sid, {})
            records = sorted(code_by_student.get(sid, []), key=lambda r: r.get("submitted_at", ""))
            latest = records[-1] if records else None
            solved = set()
            for record in records:
                grades = [h.get("result") for h in record.get("grading_history", [])] + [record.get("result")]
                grade = next((g for g in reversed(grades) if g and g.get("score") is not None), None)
                index = record.get("problem_index")
                if grade and grade.get("verdict") == "AC" and isinstance(index, int) and 0 <= index < problem_count:
                    solved.add(index)
            row.update(exam_file=exam["title"], exam_status="submitted" if records else "in_progress" if attempt else "assigned",
                       started_at=attempt.get("started_at"), ends_at=attempt.get("ends_at") or exam.get("ends_at"),
                       latest_verdict=(latest.get("result") or {}).get("verdict") or latest.get("state") if latest else None,
                       accepted_problems=len(solved), total_problems=problem_count, can_force=False, can_adjust=False)
        else:
            attempt = assignments.get(sid, {})
            if not exam.get("release_id") or attempt.get("release_id") != exam["release_id"]:
                attempt = {}
            records = [r for r in file_records.get(sid, []) if exam.get("release_id") and r.get("release_id") == exam["release_id"]]
            row.update(exam_file=attempt.get("exam_file"), exam_status=attempt.get("status", "not_assigned"),
                       started_at=attempt.get("started_at"), ends_at=attempt.get("ends_at"), latest_verdict=None,
                       can_force=live and bool(exam.get("active")) and attempt.get("status") in {"assigned", "in_progress"},
                       can_adjust=live and bool(exam.get("active")) and bool(attempt.get("ends_at")))
        row_end = learning.date_value(row["ends_at"]) if row.get("ends_at") else None
        row.update(submission_count=len(records), latest_submission=records[-1] if records else None,
                   remaining_seconds=max(0, int((row_end-now).total_seconds())) if row_end and row.get("started_at") else None)
        if exam["type"] == "programming" and records:
            # The monitor only needs summary metadata, not every private test output.
            row["latest_submission"] = {k: records[-1].get(k) for k in ("id", "exam_id", "student_id", "problem_index", "problem_title", "submitted_at", "state")}
        result.append(row)
    context = {k: exam.get(k) for k in ("id", "title", "course_id", "type", "state", "waiting", "started_at", "ends_at")}
    if exam.get("auto_start_ready"):
        context["started_at"] = exam["scheduled_at"]
    context["live"] = live
    context["activity_id"] = ("code:" + exam_id) if exam["type"] == "programming" else "file:" + str(exam.get("release_id") or "")
    return result, context


def validate_file_monitor_target(exam_id, student_id):
    """A stale/code monitor link must never mutate the current file assignment."""
    if not exam_id:
        return
    from .exam_catalog import listing
    exam = next((e for e in listing() if e["id"] == exam_id), None)
    assignment = read_json("assignments.json").get(student_id, {})
    if not exam or exam["type"] != "file" or not exam.get("active") or not exam.get("release_id") or assignment.get("release_id") != exam["release_id"] or student_id not in exam.get("participants", []):
        raise learning.LearningError(409, "Thao tác không áp dụng cho kỳ thi đang giám sát.")


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
