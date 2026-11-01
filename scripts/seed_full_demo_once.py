"""Create repeat-safe, fictional LMS courses, exams, submissions and grades.

Run on a stopped server after initial setup: python -m scripts.seed_full_demo_once
Existing accounts and course records are never replaced.
"""
import json
from datetime import datetime, time, timedelta, timezone
from app import config, exam_catalog, learning, storage
from app import submission_archive
from app.runtime import data_lease
from app.security import hash_password
from app.storage import read_json, write_json, utc_now, atomic_transaction, audit

ADMIN = {"role": "admin", "user_id": "admin"}
CODES = {"LTM-DEMO", "LTM-2026-A", "CSDL-2026-B", "WEB-2026-C"}
NEW_COURSES = [
    ("LTM-2026-A", "Lập trình mạng nâng cao", "Bài tập TCP Chat đa luồng"),
    ("CSDL-2026-B", "Cơ sở dữ liệu ứng dụng", "Bài tập thiết kế cơ sở dữ liệu"),
    ("WEB-2026-C", "Phát triển ứng dụng Web", "Bài tập xây dựng REST API"),
]
STUDENT_NAMES = [
    "Nguyễn Minh Anh", "Trần Quốc Bảo", "Lê Hoàng Gia Hân", "Phạm Đức Huy",
    "Vũ Khánh Linh", "Đỗ Tuấn Minh", "Bùi Ngọc Mai", "Hoàng Nhật Nam",
    "Đặng Phương Thảo", "Ngô Hải Yến",
]
ICT = timezone(timedelta(hours=7))
NOTES = {
    "LTM-DEMO": "TCP: socket, bind, listen, accept. Read in chunks; verify SHA-256 on file transfer.",
    "LTM-2026-A": "Network protocols: request/response framing, concurrent clients, timeout and retry.",
    "CSDL-2026-B": "Database design: primary and foreign keys, 3NF, transactions, indexes and query plans.",
    "WEB-2026-C": "REST API: HTTP verbs, validation, authorization, status codes and integration tests.",
}
FEEDBACK = [
    "Đáp ứng yêu cầu; cách trình bày rõ ràng.",
    "Chức năng chính đúng; cần thêm xử lý dữ liệu đầu vào.",
    "Thiết kế hợp lý; nên kiểm thử thêm trường hợp biên.",
    "Bài làm tốt; cần giải thích thêm lựa chọn kỹ thuật.",
]

def local_iso(day, hour, minute=0):
    return datetime.combine(day, time(hour, minute), ICT).astimezone(timezone.utc).isoformat()

def bootstrap():
    """Add the three requested courses and their ten fictional accounts if absent."""
    with learning.LOCK, atomic_transaction():
        students = read_json("students.json")
        ids = [f"DEMO{i:03d}" for i in range(1, 11)]
        for sid, name in zip(ids, STUDENT_NAMES):
            if sid not in students:
                students[sid] = {
                    "student_id": sid, "full_name": name,
                    "password_hash": hash_password("01012005"), "active": True,
                    "created_at": utc_now(), "created_by": "demo-seed",
                    "last_ip": None, "last_seen": None, "must_change_password": False,
                }
        write_json("students.json", students)
        today = datetime.now(ICT).date()
        monday = today + timedelta(days=(7 - today.weekday()) % 7 or 7)
        existing = {c["code"]: c for c in learning.load()["courses"]}
        for code, name, task_title in NEW_COURSES:
            if code in existing:
                continue
            result = learning.mutate(ADMIN, "course", {
                "name": name, "code": code, "group": "Nhóm mẫu",
                "semester": "Học kỳ 1 · 2026–2027",
                "description": "Khóa học giả lập phục vụ kiểm thử LMS.",
                "student_ids": " ".join(ids), "enrollment": "selected",
            }, {}, "127.0.0.1")
            cid = result["id"]
            learning.mutate(ADMIN, "assignment", {
                "course_id": cid, "title": task_title,
                "description": "Nộp bài thực hành kèm mô tả thiết kế và ca kiểm thử.",
                "due_at": local_iso(monday + timedelta(days=14), 23, 59),
                "max_attempts": "3",
            }, {}, "127.0.0.1")
            existing[code] = {"id": cid, "code": code, "name": name}

        # One lesson per day, Monday through Sunday, rotating the three courses.
        for day_index in range(7):
            code, name, _ = NEW_COURSES[day_index % 3]
            cid = existing[code]["id"]
            if any(e["course_id"] == cid and e.get("topic") == "Lịch học tuần đầy đủ"
                   and e["starts_at"] == local_iso(monday + timedelta(days=day_index), 8 + day_index % 3 * 3)
                   for e in learning.load()["events"]):
                continue
            learning.mutate(ADMIN, "event", {
                "course_id": cid, "title": f"Buổi học ngày {day_index + 1}",
                "topic": "Lịch học tuần đầy đủ",
                "description": "Thực hành và thảo luận nội dung học phần.",
                "starts_at": local_iso(monday + timedelta(days=day_index), 8 + day_index % 3 * 3),
                "location": f"Phòng máy {day_index % 3 + 1}", "kind": "lesson",
            }, {}, "127.0.0.1")

        catalog = read_json("exam_catalog.json", [])
        for ci, (code, name, _) in enumerate(NEW_COURSES):
            cid = existing[code]["id"]
            if any(e.get("course_id") == cid for e in catalog):
                continue
            for kind, number, offset in (("file", 1, 7), ("programming", 1, 8),
                                         ("file", 2, 21), ("programming", 2, 22)):
                form = {
                    "type": kind, "course_id": cid,
                    "title": f"{name} · {'Nộp file' if kind == 'file' else 'Lập trình'} {number}",
                    "description": "Kỳ thi giả lập để thử quy trình tổ chức và chấm thi.",
                    "duration_minutes": "60", "scheduled_at": local_iso(monday + timedelta(days=offset + ci * 2), 8),
                    "assessment_type": "midterm" if kind == "file" and number == 2 else
                                       "final" if kind == "programming" and number == 2 else "test",
                }
                if kind == "file":
                    form.update(submission_policy="configurable", max_submissions="2",
                                overwrite_previous="true", accepted_submission_extensions=".zip .pdf .txt")
                else:
                    form.update(languages="python,cpp", participant_ids="\n".join(ids),
                                problems=json.dumps([{
                                    "title": "Tổng hai số", "statement": "Đọc hai số nguyên và in tổng.",
                                    "points": 100, "time_limit_ms": 1000, "memory_limit_mb": 256,
                                    "checker": "tokens", "tests": [
                                        {"input": "2 3\n", "output": "5\n", "sample": True},
                                        {"input": "-2 7\n", "output": "5\n", "sample": False},
                                    ],
                                }], ensure_ascii=False))
                exam_catalog.save(ADMIN, form, "127.0.0.1")
            catalog = read_json("exam_catalog.json", [])

def text_for(code, sid, title, index):
    if code.startswith("CSDL"):
        content = ("CREATE TABLE courses (id INTEGER PRIMARY KEY, name VARCHAR(200) NOT NULL);\n"
                   "CREATE TABLE enrollments (course_id INTEGER NOT NULL, student_id VARCHAR(30) NOT NULL, "
                   "PRIMARY KEY (course_id, student_id));\n"
                   "SELECT course_id, COUNT(*) AS total FROM enrollments GROUP BY course_id;\n")
    elif code.startswith("WEB"):
        content = ("GET /courses: 200 hoặc 401. POST /courses: kiểm tra name, trả 201 hoặc 400.\n"
                   "GET /courses/{id}: kiểm tra quyền truy cập, trả 200 hoặc 404.\n"
                   "Kiểm thử: dữ liệu rỗng, phiên hết hạn, ID không tồn tại.\n")
    else:
        content = ("Server TCP nhận kết nối bằng socket, bind, listen, accept.\n"
                   "Mỗi client được xử lý riêng; đọc tối đa 4096 byte/lần, kiểm tra EOF.\n"
                   "Đóng kết nối trong finally, ghi log lỗi và đối chiếu SHA-256 khi truyền file.\n")
    return (f"BÀI LÀM MẪU\nMSSV: {sid}\nHọc phần: {code}\nĐề: {title}\n\n" + content +
            f"Đã chạy {3 + index % 4} ca kiểm thử; kiểm tra thêm đầu vào rỗng và kết nối bị ngắt.\n").encode("utf-8")

def verify(courses, students):
    data = learning.load()
    archive = submission_archive.listing({})["stats"]
    if archive["missing"]:
        raise RuntimeError("Archive has missing source files")
    for course in courses:
        book = learning.gradebook(data, course, course.get("student_ids") or list(students))
        scores = [row["total"] for row in book["items"]]
        if any(score is None for score in scores):
            raise RuntimeError("Missing grades in " + course["code"])
        print(course["code"], "students", len(scores), "scores", min(scores), max(scores))
    print("archive", archive)
    print("materials", len(data["materials"]), "submissions", len(data["submissions"]),
          "manual_marks", len(data["grades"]))

def main():
    data, students = learning.load(), read_json("students.json")
    required = {code for code, _, _ in NEW_COURSES}
    if not required.issubset({c.get("code") for c in data["courses"]}):
        bootstrap()
        data, students = learning.load(), read_json("students.json")
    courses = [c for c in data["courses"] if c.get("code") in CODES]
    if not required.issubset({c["code"] for c in courses}):
        raise RuntimeError("Không tìm đủ ba khóa học mẫu.")
    if all(any(m["title"] == "[DEMO] Tài liệu " + c["code"]
               for m in data["materials"]) for c in courses):
        verify(courses, students)
        return
    counts = {"materials": 0, "submissions": 0, "graded": 0, "manual_marks": 0}
    with learning.LOCK, atomic_transaction():
        for ci, course in enumerate(courses):
            code, cid = course["code"], course["id"]
            members = course.get("student_ids") or list(students)
            learning.mutate(ADMIN, "material", {
                "course_id": cid, "title": "[DEMO] Tài liệu " + code,
                "topic": "Tài liệu tham khảo", "description": "Hướng dẫn ngắn cho khóa học mẫu.",
            }, {"file": {"filename": code.lower() + "-huong-dan.txt",
                         "data": (NOTES[code] + "\n").encode("utf-8")}}, "127.0.0.1")
            counts["materials"] += 1
            tasks = [a for a in data["assignments"] if a["course_id"] == cid]
            for si, sid in enumerate(members):
                for ai, task in enumerate(tasks):
                    existing = [s for s in learning.load()["submissions"]
                                if s["assignment_id"] == task["id"] and s["student_id"] == sid]
                    if existing:
                        continue
                    saved = learning.mutate(
                        {"role": "student", "user_id": sid}, "submit",
                        {"assignment_id": task["id"], "request_id": f"demo-full-{ci}-{si}-{ai}"},
                        {"file": {"filename": f"{sid}-{code}-bai-{ai + 1}.txt",
                                  "data": text_for(code, sid, task["title"], si)}}, "127.0.0.1")
                    counts["submissions"] += 1
                    score = round(5.8 + ((si * 5 + ci * 3 + ai * 2) % 11) * 0.34, 2)
                    learning.mutate(ADMIN, "grade", {
                        "submission_id": saved["id"], "score": str(score),
                        "feedback": FEEDBACK[(si + ai + ci) % len(FEEDBACK)],
                    }, {}, "127.0.0.1")
                    counts["graded"] += 1
                # These are explicitly manual sample marks. Existing scheduled exams stay usable.
                marks = {
                    "attendance": round(8.0 + ((si + ci) % 5) * 0.5, 2),
                    "midterm": round(5.7 + ((si * 7 + ci * 3) % 11) * 0.35, 2),
                    "final": round(5.9 + ((si * 5 + ci * 2) % 12) * 0.32, 2),
                }
                for component, score in marks.items():
                    learning.mutate(ADMIN, "grade-component", {
                        "course_id": cid, "student_id": sid,
                        "component": component, "score": str(score),
                    }, {}, "127.0.0.1")
                    counts["manual_marks"] += 1
        audit("demo.full_data_created", "admin", "127.0.0.1", counts)
    verify(courses, students)

if __name__ == "__main__":
    with data_lease(config.DATA_DIR):
        storage.initialize()
        main()
