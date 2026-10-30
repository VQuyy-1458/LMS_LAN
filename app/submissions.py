from __future__ import annotations
import io
import re
import uuid
import zipfile
from pathlib import Path
from datetime import datetime, timezone
from .config import UPLOAD_DIR, MAX_REQUEST_SIZE, MAX_ZIP_ENTRIES, MAX_UNCOMPRESSED_SIZE
from .storage import read_json, write_json, utc_now, audit, atomic_transaction, save_payload
from . import submission_rate


def validate_zip(data: bytes) -> tuple[bool, str]:
    if not data:
        return False, "File ZIP rỗng."
    if len(data) > MAX_REQUEST_SIZE:
        return False, "File vượt quá giới hạn 50 MiB."
    if not data.startswith(b"PK\x03\x04") and not data.startswith(b"PK\x05\x06") and not data.startswith(b"PK\x07\x08"):
        return False, "Nội dung không có chữ ký ZIP hợp lệ."
    try:
        with zipfile.ZipFile(io.BytesIO(data), "r") as archive:
            infos = archive.infolist()
            if not infos:
                return False, "ZIP không chứa tệp nào."
            if len(infos) > MAX_ZIP_ENTRIES:
                return False, f"ZIP có quá nhiều mục (tối đa {MAX_ZIP_ENTRIES})."
            total = sum(info.file_size for info in infos)
            if total > MAX_UNCOMPRESSED_SIZE:
                return False, "Tổng dung lượng giải nén vượt giới hạn an toàn."
            bad = archive.testzip()
            if bad:
                return False, f"ZIP bị lỗi CRC tại mục {Path(bad).name}."
            for info in infos:
                p = Path(info.filename)
                if p.is_absolute() or ".." in p.parts or "\\" in info.filename:
                    return False, "ZIP chứa đường dẫn không an toàn."
        return True, "ZIP hợp lệ."
    except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
        return False, f"Không thể đọc ZIP: {exc}"

def accept_submission(student_id: str, original_name: str, data: bytes, ip: str, request_id=None) -> dict:
    from .learning import LOCK, LearningError
    if request_id and (len(request_id) > 80 or not re.fullmatch(r"[A-Za-z0-9._:-]+", request_id)):
        raise LearningError(400, "Mã yêu cầu nộp bài không hợp lệ.")
    with LOCK, atomic_transaction():
        if request_id:
            previous = next((r for r in read_json("submissions.json").get(student_id, []) if r.get("request_id") == request_id), None)
            if previous:
                if previous["sha256"] != __import__("hashlib").sha256(data).hexdigest():
                    raise LearningError(409, "Yêu cầu gửi lại có nội dung khác. Hãy tạo lần nộp mới.")
                return previous
        with submission_rate.guard(student_id):
            return _accept_submission(student_id, original_name, data, ip, request_id)


def _accept_submission(student_id: str, original_name: str, data: bytes, ip: str, request_id=None) -> dict:
    if not data:
        raise ValueError("File bài làm không được rỗng.")
    if len(data) > MAX_REQUEST_SIZE:
        raise ValueError("File vượt quá giới hạn 50 MiB.")
    settings = read_json("settings.json")
    extension = Path(original_name).suffix.lower()
    accepted = {
        str(item).lower() if str(item).startswith(".") else f".{str(item).lower()}"
        for item in settings.get("accepted_submission_extensions", [".zip"])
    }
    if extension not in accepted:
        raise ValueError(f"Loại file không được chấp nhận. Cho phép: {', '.join(sorted(accepted))}.")
    if extension == ".zip":
        ok, message = validate_zip(data)
        if not ok:
            raise ValueError(message)
    assignments = read_json("assignments.json")
    assignment = assignments.get(student_id)
    if not settings.get("exam_released") or not assignment or assignment.get("release_id") != settings.get("exam_release_id"):
        raise ValueError("Lượt thi đã kết thúc hoặc bạn chưa được giao đề.")
    if not assignment.get("started_at"):
        raise ValueError("Bạn chưa bắt đầu làm bài.")
    if assignment.get("forced_submit") or settings.get("exam_state") != "started":
        raise ValueError("Kỳ thi đã kết thúc hoặc giảng viên đã thu bài.")
    if assignment.get("status") in {"submitted", "expired"} and settings.get("submission_policy") != "configurable":
        raise ValueError("Trạng thái bài thi không cho phép nộp bài.")
    if assignment.get("ends_at"):
        end = datetime.fromisoformat(assignment["ends_at"])
        if datetime.now(timezone.utc) >= end:
            assignment["status"] = "expired"
            assignments[student_id] = assignment
            write_json("assignments.json", assignments)
            audit("submission.rejected_expired", student_id, ip, {})
            raise ValueError("Đã hết giờ. Server từ chối bài nộp muộn.")
    records = read_json("submissions.json")
    all_records = records.get(student_id, [])
    existing = [item for item in all_records if item.get("release_id") == assignment.get("release_id")]
    max_submissions = max(1, int(settings.get("max_submissions", 1)))
    if settings.get("submission_policy") == "once" and existing:
        raise ValueError("Bạn đã nộp bài; kỳ thi chỉ cho phép nộp một lần.")
    if settings.get("submission_policy") == "configurable" and len(existing) >= max_submissions:
        raise ValueError("Bạn đã sử dụng hết số lần nộp được phép.")
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", student_id)[:30]
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    saved_name = f"{safe_id}_{timestamp}{extension}"
    destination = UPLOAD_DIR / saved_name
    save_payload(destination, data)
    record = {"id": uuid.uuid4().hex, "attempt": len(existing)+1, "filename": saved_name, "original_filename": Path(original_name).name[:150], "size_bytes": len(data), "submitted_at": utc_now(), "ip": ip, "sha256": __import__("hashlib").sha256(data).hexdigest(), "status": "received", "release_id": assignment.get("release_id"), "grading_history": []}
    # Every attempt keeps its original payload; selecting a newer attempt never deletes history.
    record["payload_retained"] = True
    record["request_id"] = request_id
    record["course_id"] = assignment.get("course_id")
    record["exam_title"] = assignment.get("exam_title")
    record["exam_id"] = assignment.get("exam_id")
    record["assessment_type"] = assignment.get("assessment_type", "test")
    record["full_name"] = read_json("students.json").get(student_id, {}).get("full_name", student_id)
    record["exam_snapshot"] = {"title": assignment.get("exam_title"), "exam_file": assignment.get("exam_file"), "duration_minutes": settings.get("exam_duration_minutes"), "extensions": settings.get("accepted_submission_extensions")}
    all_records.append(record)
    records[student_id] = all_records
    write_json("submissions.json", records)
    assignment["status"] = "submitted"
    assignments[student_id] = assignment
    write_json("assignments.json", assignments)
    audit("submission.accepted", student_id, ip, {"filename": saved_name, "size_bytes": len(data), "sha256": record["sha256"], "attempt": len(existing) + 1, "release_id": assignment.get("release_id")})
    return record
