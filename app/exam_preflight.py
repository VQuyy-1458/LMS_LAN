"""Admin-only review and isolated reference judging before opening an exam."""
import copy
import hashlib
import json
import threading
import uuid

from . import learning, exam_catalog, code_runner, exams
from .storage import read_json, write_json, utc_now, atomic_transaction, audit

_gate = threading.BoundedSemaphore(1)
_jobs_lock = threading.Lock()
_jobs = {}


def _snapshot(exam_id, row=None, include_fingerprint=True):
    row = row if row is not None else next((e for e in exam_catalog.listing() if e["id"] == exam_id), None)
    if row is None:
        raise learning.LearningError(404, "Không tìm thấy kỳ thi.")
    from .admin_workspace import course_members
    course, members = course_members(row.get("course_id"))
    students = read_json("students.json")
    checks = []
    def check(label, ok, detail):
        checks.append({"label": label, "ok": bool(ok), "detail": detail})
    check("Khóa học", not course or course["status"] != "completed", course["name"] if course else "Kỳ thi chung")
    code = row["type"] == "programming"
    check("Trạng thái kỳ thi", row["state"] == ("idle" if code else "distributed") and (code or row.get("active")),
          "Chỉ mở bản nháp thi code hoặc kỳ thi file đang được chọn và đã phát đề.")
    participants = list(row.get("participants") or [])
    files = []
    if code:
        if not row.get("participants_configured"):
            participants = sorted(s for s in members if students[s].get("active", True))
    else:
        settings = read_json("settings.json")
        release = settings.get("exam_release_id")
        assignments = read_json("assignments.json")
        assigned = {sid: a for sid, a in assignments.items() if release and a.get("release_id") == release}
        configured = set(row.get("participants") or [])
        check("Danh sách và đề đã phát", not configured or configured == set(assigned), "Nếu thay đổi danh sách sau khi phát đề, cần phân phối đề lại trước khi mở thi.")
        participants = sorted(assigned)
        available = {f["name"] for f in exams.list_exam_files()}
        for name in sorted({a.get("exam_file") for a in assigned.values() if a.get("exam_file")}):
            path = exams.EXAM_DIR / name
            stat = path.stat() if name in available else None
            files.append({"name": name, "exists": stat is not None, "size": stat.st_size if stat else 0, "modified_ns": stat.st_mtime_ns if stat else None})
        check("File đề đã phát", bool(files) and all(f["exists"] for f in files) and all(a.get("exam_file") for a in assigned.values()), "Kiểm tra các file đề đã gán còn tồn tại.")
    check("Danh sách dự thi", bool(participants), f"{len(participants)} sinh viên")
    invalid = [sid for sid in participants if sid not in members or sid not in students or not students[sid].get("active", True)]
    check("Quyền dự thi", not invalid, "Cần cập nhật danh sách: " + ", ".join(invalid) if invalid else "Thí sinh thuộc phạm vi khóa học và tài khoản đang mở.")
    problems = row.get("programming", {}).get("problems", []) if code else []
    languages = row.get("programming", {}).get("languages", []) if code else []
    if code:
        check("Bài toán và test case", bool(problems) and all(p.get("tests") and code_runner.budget_valid(p) for p in problems), "Mỗi bài cần có test và nằm trong ngân sách chấm.")
        check("Ngôn ngữ", bool(languages) and all(l in code_runner.LANGUAGES for l in languages), ", ".join(languages))
    from .exam_timing import window
    from datetime import datetime, timezone
    begins, ends = window(row.get("scheduled_at"), row["duration_minutes"])
    check("Lịch bắt đầu và kết thúc", ends > datetime.now(timezone.utc), "Theo giờ Việt Nam; mở trước lịch sẽ chờ đến giờ bắt đầu." if ends > datetime.now(timezone.utc) else "Lịch đã hết thời gian, cần chỉnh lại trước khi mở.")
    canonical = {"id": row["id"], "type": row["type"], "title": row["title"], "course_id": row.get("course_id"), "course_status": course.get("status") if course else None,
                 "state": row["state"], "duration_minutes": row["duration_minutes"], "assessment_type": row.get("assessment_type"), "scheduled_at":row.get("scheduled_at"), "description":row.get("description"),
                 "participants": participants, "invalid": invalid, "programming": row.get("programming") if code else None,
                 "file_settings": row.get("file_settings") if not code else None, "release_id": row.get("release_id"), "files": files}
    fingerprint = hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest() if include_fingerprint else None
    return row, {"exam_id": row["id"], "title": row["title"], "type": row["type"], "course_name": course["name"] if course else "Kỳ thi chung",
                 "assessment_type": row.get("assessment_type", "test"), "duration_minutes": row["duration_minutes"], "languages": languages,
                 "participants": [{"student_id": sid, "full_name": students.get(sid, {}).get("full_name", sid)} for sid in participants],
                 "problems": [{"index": i, "title": p["title"], "points": p["points"], "tests": len(p["tests"])} for i, p in enumerate(problems)],
                 "total_points": sum(p["points"] for p in problems), "scheduled_at": row.get("scheduled_at"), "planned_end": ends.isoformat() if row.get("scheduled_at") else None, "files": files, "checks": checks, "fingerprint": fingerprint}


def review(exam_id):
    with learning.LOCK:
        row, report = _snapshot(exam_id)
        saved = read_json("exam_preflight.json", {}).get(exam_id, {})
    runner = code_runner.status() if row["type"] == "programming" else {"ready": True, "detail": "Thi nộp file không cần bộ chấm Docker."}
    report["runner"] = runner
    with _jobs_lock:
        report["jobs"] = [copy.deepcopy(j) for j in _jobs.values() if j["exam_id"] == exam_id and j["fingerprint"] == report["fingerprint"]]
    for p in report["problems"]:
        result = saved.get(str(p["index"]), {})
        p["verified"] = (result.get("fingerprint") == report["fingerprint"] and result.get("image_id") == runner.get("image_id") and
                         result.get("result", {}).get("verdict") == "AC" and result["result"].get("passed") == p["tests"])
        p["verification"] = result if result.get("fingerprint") == report["fingerprint"] else None
    report["can_open"] = all(c["ok"] for c in report["checks"]) and runner["ready"]
    return report


def verify_reference(session, form, ip):
    exam_id = form.get("exam_id", "")
    source, language = form.get("source", ""), form.get("language", "")
    if not source.strip() or len(source.encode("utf-8")) > 100000:
        raise learning.LearningError(400, "Lời giải chuẩn phải từ 1 đến 100.000 byte.")
    runner = code_runner.status()
    if not runner["ready"]:
        raise learning.LearningError(409, runner["detail"])
    with learning.LOCK:
        row, report = _snapshot(exam_id)
        if row["type"] != "programming" or not all(c["ok"] for c in report["checks"]):
            raise learning.LearningError(409, "Cần hoàn tất cấu hình và danh sách dự thi trước khi chấm thử.")
        if report["fingerprint"] != form.get("fingerprint"):
            raise learning.LearningError(409, "Cấu hình đã thay đổi. Hãy mở lại bước kiểm tra.")
        index = learning.integer(form, "problem_index", -1, 0, len(row["programming"]["problems"])-1)
        if language not in report["languages"]:
            raise learning.LearningError(400, "Ngôn ngữ lời giải chuẩn không được phép trong kỳ thi.")
        problem = copy.deepcopy(row["programming"]["problems"][index])
    if not _gate.acquire(blocking=False):
        raise learning.LearningError(429, "Đang chấm một lời giải chuẩn. Chờ hoàn tất rồi thử bài tiếp theo.")
    job_id = uuid.uuid4().hex
    job = {"id": job_id, "exam_id": exam_id, "problem_index": index, "fingerprint": report["fingerprint"], "state": "running", "stage": "preparing", "completed_tests": 0, "total_tests": len(problem["tests"])}
    with _jobs_lock:
        # Only the most recent job for each problem is needed by the review UI.
        for key in list(_jobs):
            if _jobs[key]["state"] != "running" and (_jobs[key]["exam_id"] == exam_id and _jobs[key]["problem_index"] == index or len(_jobs) > 50):
                del _jobs[key]
        _jobs[job_id] = job
    def work():
        try:
            def progress(stage, completed, total):
                with _jobs_lock:
                    job.update(stage=stage, completed_tests=completed, total_tests=total)
            result = code_runner.judge(source.encode("utf-8"), language, problem, progress=progress, image=runner["image_id"])
            receipt = {"fingerprint": report["fingerprint"], "image_id": runner["image_id"], "language": language, "source_sha256": hashlib.sha256(source.encode()).hexdigest(), "result": result, "verified_at": utc_now(), "verified_by": session["user_id"]}
            with learning.LOCK, atomic_transaction():
                _, current = _snapshot(exam_id)
                if current["fingerprint"] != report["fingerprint"]:
                    raise RuntimeError("Cấu hình đã thay đổi trong lúc chấm; kết quả thử không còn hiệu lực.")
                records = read_json("exam_preflight.json", {})
                records.setdefault(exam_id, {})[str(index)] = receipt
                write_json("exam_preflight.json", records)
                audit("exam.reference_verified", session["user_id"], ip, {"exam_id": exam_id, "problem_index": index, "verdict": result["verdict"]})
            with _jobs_lock:
                job.update(state="done", result=result)
        except Exception as error:
            with _jobs_lock:
                job.update(state="error", error=str(error))
        finally:
            _gate.release()
    try:
        thread = threading.Thread(target=work, daemon=True, name="exam-reference-judge")
        thread.start()
    except BaseException:
        with _jobs_lock:
            _jobs.pop(job_id, None)
        _gate.release()
        raise
    return {"ok": True, "job_id": job_id}


def open_checked(session, form, ip, runner=None):
    # Caller checks Docker before entering the shared metadata transaction.
    exam_id = form.get("exam_id", "")
    with learning.LOCK, atomic_transaction():
        row, report = _snapshot(exam_id)
        if report["fingerprint"] != form.get("fingerprint"):
            raise learning.LearningError(409, "Cấu hình hoặc danh sách dự thi đã thay đổi. Hãy kiểm tra lại trước khi mở.")
        if not all(c["ok"] for c in report["checks"]):
            raise learning.LearningError(409, "Chưa đủ điều kiện mở kỳ thi. Hãy kiểm tra các mục chưa đạt.")
        if row["type"] == "programming":
            if not runner or not runner["ready"]:
                raise learning.LearningError(409, "Bộ chấm chưa sẵn sàng.")
            from . import programming
            result = programming.control(session, {"exam_id": exam_id, "action": "start"}, ip, runner_ready=True)
        else:
            try:
                exams.start_exam_session()
            except ValueError as error:
                raise learning.LearningError(409, str(error))
            result = {"ok": True}
        audit("exam.opened_after_review", session["user_id"], ip, {"exam_id": exam_id, "fingerprint": report["fingerprint"]})
        return result
