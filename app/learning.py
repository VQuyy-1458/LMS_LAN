"""Course learning workflows, using the project's JSON storage and session auth."""
from __future__ import annotations

import copy
from contextlib import ExitStack
import hashlib
import math
import secrets
import threading
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import BASE_DIR, RUNTIME_DIR
from .storage import read_json, write_json, utc_now, audit, atomic_transaction, save_payload
from .submissions import validate_zip
from . import submission_rate, enrollments

FILES = RUNTIME_DIR / "learning-files"
LOCK = threading.RLock()
EXTENSIONS = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".txt", ".zip", ".c", ".cpp", ".java", ".py", ".png", ".jpg", ".jpeg"}
EMPTY = {"courses": [], "materials": [], "events": [], "assignments": [], "submissions": [], "attendance": [], "grades": []}
WEIGHTS = {"attendance": 10, "homework": 10, "midterm": 10, "final": 70}


class LearningError(Exception):
    def __init__(self, status, detail):
        super().__init__(detail)
        self.status, self.detail = status, detail


def load():
    data = read_json("learning.json", copy.deepcopy(EMPTY))
    for key in EMPTY:
        data.setdefault(key, [])
    return data


def initialize_enrollments():
    """Baseline existing membership without guessing or changing historical marks."""
    with LOCK, atomic_transaction():
        data, students, at = load(), read_json("students.json"), utc_now()
        changed = sum(enrollments.initialize(c, students, at, legacy=True) for c in data["courses"])
        if changed:
            write_json("learning.json", data)
            audit("learning.enrollment_baseline", "system", "127.0.0.1", {"courses": changed})
        return changed


def gradebook(data, course, student_ids):
    now = datetime.now(timezone.utc)
    weights = course.get("weights", WEIGHTS)
    tasks = [a for a in data["assignments"] if a["course_id"] == course["id"]]
    closed = [a for a in data["attendance"] if a["course_id"] == course["id"] and (a["closed"] or date_value(a["expires_at"]) <= now)]
    students = read_json("students.json")
    from .course_grades import exam_marks
    exam_results = exam_marks(course["id"], student_ids)
    latest_submissions = {(s["assignment_id"],s["student_id"]):s for s in data["submissions"]}
    overrides_by_student = {}
    for override in data["grades"]:
        if override["course_id"] == course["id"]:
            overrides_by_student.setdefault(override["student_id"],[]).append(override)
    task_due = {task["id"]:date_value(task["due_at"]) <= now for task in tasks}
    rows = []
    for sid in student_ids:
        absent = sum(a["records"].get(sid, {}).get("status") not in {"present", "late"}
                     for a in closed if enrollments.applies(course, sid, a, "attendance", students))
        values = {"attendance": max(0, 10 - absent), "homework": None, "midterm": None, "final": None}
        homework = []
        for task in tasks:
            if not enrollments.applies(course, sid, task, "assignment", students):
                continue
            latest = latest_submissions.get((task["id"],sid))
            score = latest.get("score") if latest else (0 if task_due[task["id"]] else None)
            if task_due[task["id"]] or score is not None:
                homework.append(score)
        if homework and all(score is not None for score in homework):
            values["homework"] = round(sum(homework) / len(homework), 2)
        for component in ("midterm", "final"):
            marks = [r["score"] for r in exam_results[sid] if r["assessment_type"] == component]
            if marks and all(v is not None for v in marks):
                values[component] = round(sum(marks) / len(marks), 2)
        automatic = dict(values)
        overrides = {}
        for row in overrides_by_student.get(sid,[]):
            values[row["component"]] = row["score"]
            overrides[row["component"]] = row["score"]
        complete = all(values[k] is not None for k, w in weights.items() if w > 0)
        total = round(sum((values[k] or 0) * w / 100 for k, w in weights.items()), 2) if complete else None
        rows.append({"student_id": sid, "full_name": students.get(sid, {}).get("full_name", sid), **values, "total": total, "automatic": automatic, "overrides": overrides, "exam_results": exam_results[sid], "enrollment": enrollments.info(course, sid, students), "excluded_assignments": sum(not enrollments.applies(course, sid, a, "assignment", students) for a in tasks), "excluded_attendance": sum(not enrollments.applies(course, sid, a, "attendance", students) for a in closed)})
    return {"course_id": course["id"], "weights": weights, "items": rows}


def text(form, key, limit=200, required=True):
    value = form.get(key, "").strip()
    if (required and not value) or len(value) > limit:
        raise LearningError(400, f"Thông tin {key} không hợp lệ (tối đa {limit} ký tự).")
    return value


def integer(form, key, default, minimum, maximum):
    try:
        value = int(form.get(key, str(default)))
    except ValueError:
        raise LearningError(400, f"Thông tin {key} phải là số nguyên.")
    if not minimum <= value <= maximum:
        raise LearningError(400, f"Thông tin {key} phải từ {minimum} đến {maximum}.")
    return value


def date_value(value):
    try:
        result = datetime.fromisoformat(value)
        if result.tzinfo is None:
            raise ValueError()
        return result.astimezone(timezone.utc)
    except (ValueError, TypeError):
        raise LearningError(400, "Thời gian không hợp lệ hoặc thiếu múi giờ.")


def find(data, collection, item_id):
    item = next((r for r in data[collection] if r["id"] == item_id), None)
    if not item:
        raise LearningError(404, "Không tìm thấy nội dung.")
    return item


def course_access(data, course_id, session, write=False):
    course = find(data, "courses", course_id)
    if session["role"] != "admin" and course.get("student_ids") is not None and session["user_id"] not in course["student_ids"]:
        raise LearningError(403, "Bạn không thuộc khóa học này.")
    if write and course["status"] == "completed":
        raise LearningError(409, "Khóa học đã tổng kết, chỉ được xem dữ liệu.")
    return course


def own_submission(data, submission_id, session):
    row = find(data, "submissions", submission_id)
    course_access(data, row["course_id"], session)
    if session["role"] != "admin" and row["student_id"] != session["user_id"]:
        raise LearningError(403, "Bạn chỉ được xem bài nộp của mình.")
    return row


def snapshot(session):
    """Return only enrolled course data, personal results, and public file metadata."""
    with LOCK:
        data = load()
        admin = session["role"] == "admin"
        sid = session["user_id"]
        courses = [c for c in data["courses"] if admin or c.get("student_ids") is None or sid in c["student_ids"]]
        ids = {c["id"] for c in courses}
        students = read_json("students.json")
        course_by_id = {c["id"]: c for c in courses}
        result = {"courses": copy.deepcopy(courses)}
        for course in result["courses"]:
            if admin:
                course["enrollments"] = {k: enrollments.info(course, k, students) for k in enrollments.member_ids(course, students)}
            else:
                course["enrollment"] = enrollments.info(course, sid, students)
                course.pop("student_ids", None)
                course.pop("enrollments", None)
                course.pop("enrollment_tracking_since", None)
        for key in ("materials", "events", "assignments", "submissions", "attendance"):
            result[key] = [copy.deepcopy(r) for r in data[key] if r["course_id"] in ids and (key != "submissions" or admin or r["student_id"] == sid)]
        for key in ("materials", "assignments", "submissions"):
            for row in result[key]:
                row.pop("stored_name", None)
        if not admin:
            for kind, key in (("assignment", "assignments"), ("attendance", "attendance")):
                for row in result[key]:
                    row["grading_applicable"] = enrollments.applies(course_by_id[row["course_id"]], sid, row, kind, students)
        now = datetime.now(timezone.utc)
        for row in result["attendance"]:
            row["open"] = not row.get("closed") and date_value(row["expires_at"]) > now
            row["session_status"] = "closed" if row.get("closed") else "expired" if not row["open"] else "open"
            row["lesson_at"] = row.get("lesson_at") or row["created_at"]
            if not admin:
                row.pop("code", None)
                row["record"] = row.pop("records", {}).get(sid)
            else:
                c = course_by_id[row["course_id"]]
                row["excluded_student_ids"] = [k for k in enrollments.member_ids(c, students) if not enrollments.applies(c, k, row, "attendance", students)]
        if admin:
            result["students"] = [{"student_id": k, "full_name": v.get("full_name", ""), "active": v.get("active", True)} for k, v in read_json("students.json").items()]
        students = read_json("students.json")
        result["gradebooks"] = [gradebook(data, c, [sid] if not admin else [k for k in students if c.get("student_ids") is None or k in c["student_ids"]]) for c in courses]
        return result


def save_file(file):
    if not file or not file.get("filename") or not file.get("data"):
        raise LearningError(400, "Hãy chọn file có nội dung.")
    name = Path(file["filename"].replace("\\", "/")).name[:180]
    extension = Path(name).suffix.lower()
    if extension not in EXTENSIONS:
        raise LearningError(400, "Loại file không được hỗ trợ.")
    if len(file["data"]) > 20 * 1024 * 1024:
        raise LearningError(413, "File vượt giới hạn 20 MiB.")
    if extension == ".zip":
        valid, message = validate_zip(file["data"])
        if not valid:
            raise LearningError(400, message)
    FILES.mkdir(parents=True, exist_ok=True)
    stored = secrets.token_hex(24) + extension
    save_payload(FILES / stored, file["data"])
    return {"original_filename": name, "stored_name": stored, "size_bytes": len(file["data"]), "sha256": hashlib.sha256(file["data"]).hexdigest()}


def file_for(kind, item_id, session):
    with LOCK:
        data = load()
        if kind == "submissions":
            row = own_submission(data, item_id, session)
        elif kind in {"materials", "assignments"}:
            row = find(data, kind, item_id)
            course_access(data, row["course_id"], session)
        else:
            raise LearningError(404, "Không tìm thấy file.")
        if not row.get("stored_name"):
            raise LearningError(404, "Nội dung này không có file đính kèm.")
        path = (FILES / row["stored_name"]).resolve()
        if path.parent != FILES.resolve() or not path.is_file():
            raise LearningError(404, "File không còn tồn tại.")
        return path, row["original_filename"]


def preview_file(kind, item_id, session):
    path, name = file_for(kind, item_id, session)
    return preview_path(path, name, f"/api/learning/view/{kind}/{item_id}")


def preview_path(path, name, pdf_url):
    extension = Path(name).suffix.lower()
    limit = 2 * 1024 * 1024
    if extension == ".pdf":
        return {"kind": "pdf", "name": name, "url": pdf_url}
    if extension in {".txt", ".c", ".cpp", ".java", ".py"}:
        with path.open("rb") as source:
            raw = source.read(limit + 1)
        return {"kind": "text", "name": name, "text": raw[:limit].decode("utf-8", "replace"), "truncated": len(raw) > limit}
    if extension in {".zip", ".docx", ".pptx"}:
        try:
            with zipfile.ZipFile(path) as archive:
                if extension == ".zip":
                    infos = archive.infolist()
                    return {"kind": "text", "name": name, "text": "Nội dung file ZIP (không giải nén hoặc chạy mã):\n\n" + "\n".join(f"{i.filename}  ({i.file_size} bytes)" for i in infos[:1000]), "truncated": len(infos) > 1000}
                names = [n for n in archive.namelist() if n == "word/document.xml" or (n.startswith("ppt/slides/slide") and n.endswith(".xml"))]
                result = []
                total = 0
                for entry in names[:100]:
                    total += archive.getinfo(entry).file_size
                    if total > limit:
                        raise LearningError(413, "Nội dung quá lớn để xem trực tiếp. Hãy tải file.")
                    document = ET.fromstring(archive.read(entry))
                    result.append("\n".join(e.text for e in document.iter() if e.tag.rsplit("}", 1)[-1] == "t" and e.text))
                return {"kind": "text", "name": name, "text": "\n\n".join(result) or "Không có nội dung văn bản để xem.", "truncated": len(names) > 100}
        except (zipfile.BadZipFile, ET.ParseError, KeyError):
            raise LearningError(400, "Không đọc được nội dung tài liệu. Hãy tải file để kiểm tra.")
    return {"kind": "unsupported", "name": name, "text": "Định dạng này cần tải về để xem."}


def mutate(session, action, form, files, ip):
    with LOCK, atomic_transaction(), ExitStack() as guards:
        data = load()
        admin = session["role"] == "admin"
        sid = session["user_id"]
        if action != "submit" and action != "check-in" and not admin:
            raise LearningError(403, "Chỉ giảng viên được quản lý nội dung học tập.")
        row = {"id": secrets.token_hex(10), "created_at": utc_now()}
        if action == "course":
            members = form.get("student_ids", "").replace(",", " ").split()
            if any(k not in read_json("students.json") for k in members):
                raise LearningError(400, "Danh sách có MSSV chưa tồn tại.")
            row.update({"name": text(form, "name"), "code": text(form, "code", 80), "group": text(form, "group", 80, False), "semester": text(form, "semester", 80), "description": text(form, "description", 10000, False), "student_ids": list(dict.fromkeys(members)) if members or form.get("enrollment")=="selected" else None, "status": "active"})
            enrollments.initialize(row, read_json("students.json"), row["created_at"])
            data["courses"].append(row)
        elif action == "course-update":
            row = course_access(data, text(form, "course_id", 80), session, write=True)
            row.update({"name": text(form, "name"), "code": text(form, "code", 80), "group": text(form, "group", 80, False), "semester": text(form, "semester", 80), "description": text(form, "description", 10000, False)})
        elif action == "course-members":
            row = course_access(data, text(form, "course_id", 80), session, write=True)
            members = list(dict.fromkeys(form.get("student_ids", "").replace(",", " ").split()))
            if len(members)>10000 or any(sid not in read_json("students.json") for sid in members):
                raise LearningError(400, "Danh sách có MSSV chưa tồn tại hoặc quá nhiều sinh viên.")
            policy = form.get("include_previous", "false")
            if policy not in {"false", "true"}:
                raise LearningError(400, "Quy tắc tính nội dung trước khi tham gia không hợp lệ.")
            enrollments.update_members(row, read_json("students.json"), members, utc_now(), policy == "true")
        elif action in {"material", "event", "assignment", "attendance"}:
            course_id = text(form, "course_id", 80)
            course_access(data, course_id, session, write=True)
            lesson = None
            if action == "attendance":
                lesson = find(data, "events", text(form, "event_id", 80))
                if lesson["course_id"] != course_id or lesson["kind"] != "lesson":
                    raise LearningError(400, "Chỉ mở điểm danh từ buổi học trong lịch của khóa học.")
                existing = next((s for s in data["attendance"] if s.get("event_id") == lesson["id"]), None)
                if existing:
                    return {"ok": True, "id": existing["id"]}
            row.update({"course_id": course_id, "title": lesson["title"] if lesson else text(form, "title"), "topic": text(form, "topic", 200, False), "description": text(form, "description", 10000, False)})
            if action == "material":
                row.update(save_file(files.get("file")))
                data["materials"].append(row)
            elif action == "event":
                starts = date_value(form.get("starts_at"))
                row.update({"starts_at": starts.isoformat(), "location": text(form, "location", 200, False), "kind": form.get("kind", "lesson")})
                if row["kind"] not in {"lesson", "announcement", "exam"}:
                    raise LearningError(400, "Loại lịch không hợp lệ.")
                data["events"].append(row)
            elif action == "assignment":
                due = date_value(form.get("due_at"))
                if due <= datetime.now(timezone.utc):
                    raise LearningError(400, "Hạn nộp bài phải ở tương lai.")
                row.update({"due_at": due.isoformat(), "max_attempts": integer(form, "max_attempts", 3, 1, 20)})
                if files.get("file") and files["file"].get("filename"):
                    row.update(save_file(files["file"]))
                data["assignments"].append(row)
            else:
                expires = date_value(form["expires_at"]) if form.get("expires_at") else datetime.now(timezone.utc) + timedelta(minutes=integer(form, "duration_minutes", 15, 1, 240))
                if expires <= datetime.now(timezone.utc):
                    raise LearningError(400, "Thời hạn điểm danh phải ở tương lai.")
                row.update({"event_id": lesson["id"], "lesson_at": lesson["starts_at"], "expires_at": expires.isoformat(), "code": secrets.token_hex(4).upper(), "closed": False, "records": {}})
                data["attendance"].append(row)
        elif action == "submit":
            if admin:
                raise LearningError(403, "Chỉ tài khoản sinh viên được nộp bài.")
            assignment = find(data, "assignments", text(form, "assignment_id", 80))
            course_access(data, assignment["course_id"], session, write=True)
            if assignment.get("closed_at") or date_value(assignment["due_at"]) <= datetime.now(timezone.utc):
                raise LearningError(409, "Đã hết hạn nộp bài.")
            prior = [r for r in data["submissions"] if r["assignment_id"] == assignment["id"] and r["student_id"] == sid]
            key = text(form, "request_id", 80)
            digest = hashlib.sha256((files.get("file") or {}).get("data", b"")).hexdigest()
            duplicate = next((r for r in prior if r.get("request_id") == key), None)
            if duplicate:
                if duplicate["sha256"] != digest:
                    raise LearningError(409, "Yêu cầu gửi lại có nội dung khác.")
                return {"ok": True, "id": duplicate["id"]}
            if len(prior) >= assignment["max_attempts"]:
                raise LearningError(409, "Bạn đã dùng hết số lần nộp bài.")
            guards.enter_context(submission_rate.guard(sid))
            row.update(save_file(files.get("file")))
            row.update({"course_id": assignment["course_id"], "assignment_id": assignment["id"], "assignment_title": assignment["title"], "student_id": sid, "ip": ip, "request_id": key, "score": None, "feedback": "", "attempt": len(prior) + 1, "grading_history": []})
            row["assignment_snapshot"] = {k: assignment.get(k) for k in ("title","description","due_at","max_attempts")}
            row["full_name"] = read_json("students.json").get(sid,{}).get("full_name",sid)
            row["course_name"] = find(data,"courses",assignment["course_id"])["name"]
            data["submissions"].append(row)
        elif action == "grade":
            row = own_submission(data, text(form, "submission_id", 80), session)
            course_access(data, row["course_id"], session, write=True)
            try:
                score = float(form.get("score", ""))
            except ValueError:
                raise LearningError(400, "Điểm phải là số từ 0 đến 10.")
            if not math.isfinite(score) or not 0 <= score <= 10:
                raise LearningError(400, "Điểm phải từ 0 đến 10.")
            history = row.setdefault("grading_history", [])
            if not history and row.get("score") is not None:
                history.append({"id": "legacy", "score": row["score"], "feedback": row.get("feedback", ""), "graded_at": row.get("graded_at"), "graded_by": row.get("graded_by", "Trước khi lưu lịch sử")})
            feedback, graded_at = text(form, "feedback", 4000, False), utc_now()
            history.append({"id": secrets.token_hex(16), "score": round(score, 2), "feedback": feedback, "graded_at": graded_at, "graded_by": sid})
            row.update({"score": round(score, 2), "feedback": feedback, "graded_at": graded_at, "graded_by": sid})
        elif action == "check-in":
            if admin:
                raise LearningError(403, "Chỉ sinh viên được tự điểm danh.")
            row = find(data, "attendance", text(form, "session_id", 80))
            course_access(data, row["course_id"], session, write=True)
            if not secrets.compare_digest(form.get("code", "").strip().upper(), row["code"]):
                raise LearningError(400, "Mã điểm danh không đúng.")
            previous = row["records"].get(sid)
            if previous and previous["status"] == "absent":
                raise LearningError(409, "Giảng viên đã ghi nhận bạn vắng. Hãy liên hệ giảng viên để điều chỉnh.")
            if not previous and (row["closed"] or date_value(row["expires_at"]) <= datetime.now(timezone.utc)):
                raise LearningError(409, "Phiên điểm danh đã kết thúc.")
            if not previous:
                row["records"][sid] = {"status": "present", "checked_in_at": utc_now(), "ip": ip}
                write_json("learning.json", data)
                audit("learning.check-in", sid, ip, {"id":row["id"],"course_id":row["course_id"]})
            return {"ok":True,"id":row["id"],"session_id":row["id"],"course_id":row["course_id"],"course_name":find(data,"courses",row["course_id"])["name"],"title":row["title"],"record":copy.deepcopy(row["records"][sid]),"already_checked_in":bool(previous)}
        elif action == "attendance-record":
            row = find(data, "attendance", text(form, "session_id", 80))
            course = course_access(data, row["course_id"], session, write=True)
            if row["closed"] or date_value(row["expires_at"]) <= datetime.now(timezone.utc):
                raise LearningError(409, "Phiên đã kết thúc, không thể sửa điểm danh.")
            student_id = text(form, "student_id", 80)
            if student_id not in read_json("students.json") or (course["student_ids"] is not None and student_id not in course["student_ids"]):
                raise LearningError(400, "Sinh viên không thuộc khóa học.")
            status = form.get("status")
            if status not in {"present", "late", "absent"}:
                raise LearningError(400, "Trạng thái điểm danh không hợp lệ.")
            row["records"][student_id] = {"status": status, "checked_in_at": utc_now(), "reason": text(form, "reason", 1000)}
        elif action == "close-attendance":
            row = find(data, "attendance", text(form, "session_id", 80))
            course_access(data, row["course_id"], session, write=True)
            row["closed"] = True
        elif action == "complete-course":
            row = course_access(data, text(form, "course_id", 80), session, write=True)
            exam = read_json("settings.json")
            if exam.get("exam_course_id") == row["id"] and exam.get("exam_state") in {"distributed", "started"}:
                raise LearningError(409, "Hãy kết thúc kỳ thi của khóa học trước khi tổng kết.")
            if any(e.get("course_id") == row["id"] and e.get("type") == "programming" and e.get("state") == "started" for e in read_json("exam_catalog.json", [])):
                raise LearningError(409, "Hãy kết thúc kỳ thi lập trình của khóa học trước khi tổng kết.")
            members = [sid for sid in read_json("students.json") if row.get("student_ids") is None or sid in row["student_ids"]]
            if any(r["total"] is None for r in gradebook(data, row, members)["items"]):
                raise LearningError(409, "Chưa đủ điểm thành phần để tổng kết. Hãy hoàn thành bảng điểm hoặc điều chỉnh trọng số.")
            row["status"] = "completed"
        elif action == "course-weights":
            row = course_access(data, text(form, "course_id", 80), session, write=True)
            weights = {key: integer(form, key, 0, 0, 100) for key in WEIGHTS}
            if sum(weights.values()) != 100:
                raise LearningError(400, "Tổng trọng số phải bằng 100%.")
            row["weights"] = weights
        elif action == "gradebook-save":
            import json
            course_id = text(form, "course_id", 80)
            course = course_access(data, course_id, session, write=True)
            try:
                changes = json.loads(form.get("items", "[]"))
            except (TypeError, ValueError):
                raise LearningError(400, "Danh sách điểm không hợp lệ.")
            if not isinstance(changes, list) or len(changes) > 40000:
                raise LearningError(400, "Danh sách điểm không hợp lệ.")
            students = read_json("students.json")
            updates = {}
            for change in changes:
                if not isinstance(change, dict):
                    raise LearningError(400, "Dữ liệu điểm không hợp lệ.")
                student_id, component = change.get("student_id"), change.get("component")
                if not isinstance(student_id, str) or student_id not in students or (course.get("student_ids") is not None and student_id not in course["student_ids"]):
                    raise LearningError(400, "Sinh viên không thuộc khóa học.")
                if not isinstance(component, str) or component not in WEIGHTS:
                    raise LearningError(400, "Thành phần điểm không hợp lệ.")
                raw = change.get("score")
                score = None
                if raw is not None and raw != "":
                    try:
                        score = float(raw)
                    except (ValueError, TypeError):
                        raise LearningError(400, "Điểm phải từ 0 đến 10.")
                    if isinstance(raw, bool) or not math.isfinite(score) or not 0 <= score <= 10:
                        raise LearningError(400, "Điểm phải từ 0 đến 10.")
                    score = round(score, 2)
                updates[(student_id, component)] = score
            data["grades"] = [g for g in data["grades"] if g["course_id"] != course_id or (g["student_id"], g["component"]) not in updates]
            for (student_id, component), score in updates.items():
                if score is not None:
                    data["grades"].append({"id": secrets.token_hex(10), "created_at": utc_now(), "course_id": course_id, "student_id": student_id, "component": component, "score": score})
        elif action == "grade-component":
            course_id = text(form, "course_id", 80)
            course = course_access(data, course_id, session, write=True)
            student_id = text(form, "student_id", 80)
            if student_id not in read_json("students.json") or (course.get("student_ids") is not None and student_id not in course["student_ids"]):
                raise LearningError(400, "Sinh viên không thuộc khóa học.")
            component = form.get("component")
            if component not in WEIGHTS:
                raise LearningError(400, "Thành phần điểm không hợp lệ.")
            raw = form.get("score", "").strip()
            score = None
            if raw:
                try:
                    score = float(raw)
                except ValueError:
                    raise LearningError(400, "Điểm phải là số từ 0 đến 10.")
                if not math.isfinite(score) or not 0 <= score <= 10:
                    raise LearningError(400, "Điểm phải từ 0 đến 10.")
            data["grades"] = [r for r in data["grades"] if not (r["course_id"] == course_id and r["student_id"] == student_id and r["component"] == component)]
            if score is not None:
                row.update({"course_id": course_id, "student_id": student_id, "component": component, "score": round(score, 2)})
                data["grades"].append(row)
        else:
            raise LearningError(404, "Không tìm thấy thao tác học tập.")
        write_json("learning.json", data)
        audit("learning." + action, sid, ip, {"id": row["id"]})
        return {"ok": True, "id": row["id"]}
