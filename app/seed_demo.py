"""Add a separate, repeat-safe classroom dataset. Run with --apply to write it."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import secrets
import shutil
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config, exams, learning, storage
from .security import hash_password

VERSION = "classroom-demo-v1"
PASSWORD = "111111"
VN = timezone(timedelta(hours=7))
NAMES = ["Nguyễn Minh Anh", "Trần Quốc Bảo", "Lê Minh Châu", "Phạm Thị Duyên", "Hoàng Văn Em", "Võ Ngọc Hà", "Đặng Trung Hiếu", "Bùi Gia Huy", "Đỗ Khánh Linh", "Ngô Hoàng Long", "Nguyễn Thanh Mai", "Trần Hải Nam", "Lê Bảo Ngọc", "Phạm Đức Phúc", "Hoàng Minh Quân", "Võ Phương Thảo", "Đặng Anh Thư", "Bùi Quốc Trung", "Đỗ Ngọc Tú", "Ngô Hải Yến"]


def zipped(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return buffer.getvalue()


def seed_demo(project_root=None):
    root = Path(project_root or config.BASE_DIR)
    marker_path = storage.DATA_DIR / "demo_seed.json"
    if marker_path.exists():
        return {"status": "already-seeded", **json.loads(marker_path.read_text(encoding="utf-8"))}
    now = datetime.now(VN)
    stamp = now.strftime("%Y%m%d-%H%M%S")
    students = storage.read_json("students.json")
    data = learning.load()
    notices = storage.read_json("notifications.json", [])
    settings = storage.read_json("settings.json")
    assignments = storage.read_json("assignments.json")
    ids = [f"DEMO{i:03}" for i in range(1, 21)]
    if any(sid in students for sid in ids) or any(c["id"].startswith("demo-v1-") for c in data["courses"]):
        raise RuntimeError("Có dữ liệu trùng mã DEMO. Không thay đổi dữ liệu đang có.")
    pending_files = {}
    def iso(days=0, hour=None, minute=0):
        value = now + timedelta(days=days)
        if hour is not None:
            value = value.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return value.astimezone(timezone.utc).isoformat(timespec="seconds")
    def identity(key, days=0):
        return {"id": "demo-v1-" + key, "created_at": iso(days), "created_by": "demo-seed"}
    def file_metadata(key, filename, payload):
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        stored = "demo-v1-" + key + Path(filename).suffix
        target = learning.FILES / stored
        if target.exists():
            raise RuntimeError("File mẫu đã tồn tại; không ghi đè: " + str(target))
        pending_files[target] = payload
        return {"original_filename": filename, "stored_name": stored, "size_bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
    for index, sid in enumerate(ids):
        students[sid] = {"student_id": sid, "full_name": NAMES[index], "password_hash": hash_password(PASSWORD), "active": True, "created_at": iso(-25), "created_by": "demo-seed", "last_ip": None, "last_seen": None, "must_change_password": False}
    specifications = [
        ("network", "LTM-DEMO-01", "Lập trình mạng", ids[:16], "Thực hành socket, TCP/UDP và ứng dụng Client–Server.", False),
        ("database", "CSDL-DEMO-02", "Cơ sở dữ liệu", ids[8:], "Thiết kế dữ liệu, truy vấn SQL và quản lý giao dịch.", False),
        ("completed", "LT-DEMO-03", "Lập trình căn bản", ids[:8], "Khóa học đã tổng kết để kiểm tra lịch sử, bảng điểm và chế độ chỉ xem.", True),
    ]
    course_ids = []
    task_by_course = {}
    for key, code, name, members, description, completed in specifications:
        course = {**identity(key, -30), "code": code, "name": name, "semester": "Học kỳ 1 · 2026–2027" if not completed else "Học kỳ hè · 2025–2026", "student_ids": members, "description": description, "status": "completed" if completed else "active", "weights": {"attendance": 10, "homework": 20, "midterm": 30, "final": 40}}
        data["courses"].append(course)
        cid = course["id"]
        course_ids.append(cid)
        topics = ["Giới thiệu và thiết lập môi trường", "Cấu trúc chương trình", "Bài tập thực hành", "Xử lý lỗi", "Ôn tập giữa kỳ", "Thực hành tổng hợp"]
        for i in range(6 if completed else 12):
            day = -40 + i * 3 if completed else (-24 + i * 3 if i < 8 else 1 + (i - 8) * 3)
            data["events"].append({**identity(f"{key}-lesson-{i+1}", day), "course_id": cid, "title": f"Buổi {i+1:02}: {topics[i % len(topics)]}", "description": "Chuẩn bị tài liệu và hoàn thành phần thực hành trước buổi học.", "kind": "lesson", "starts_at": iso(day, 7 if key == "network" else 13, 30), "location": "Phòng thực hành A203" if key == "network" else "Phòng thực hành B105"})
        for i in range(3):
            data["events"].append({**identity(f"{key}-notice-{i}", -3+i), "course_id": cid, "title": ["Chào mừng đến với khóa học", "Tài liệu và bài tập đã được cập nhật", "Lưu ý quy định nộp bài"][i], "description": ["Theo dõi lịch học, tài liệu và các hoạt động trong không gian khóa học.", "Xem mục Tài liệu và Bài tập để chuẩn bị cho buổi thực hành tiếp theo.", "Kiểm tra tên file, nội dung và biên nhận sau khi nộp. Liên hệ giảng viên nếu cần hỗ trợ."][i], "kind": "announcement", "starts_at": iso(-3+i), "location": ""})
        material_contents = [
            ("Đề cương học phần", "de-cuong.txt", f"{name}\n\nMục tiêu: {description}\n\nĐánh giá: chuyên cần 10%, bài tập 20%, giữa kỳ 30%, cuối kỳ 40%.\nNộp bài theo hạn quy định và giữ lại biên nhận.\n"),
            ("Hướng dẫn thực hành", "huong-dan.txt", "1. Đọc yêu cầu bài tập.\n2. Viết và chạy thử chương trình trên máy.\n3. Đóng gói mã nguồn thành ZIP hoặc chọn file được cho phép.\n4. Nộp bài và kiểm tra lại lịch sử.\n"),
            ("Mã nguồn tham khảo", "vi-du.cpp", "#include <iostream>\nint main() { int n; std::cin >> n; std::cout << n * (n + 1) / 2; }\n"),
        ]
        for i, (title, filename, payload) in enumerate(material_contents):
            data["materials"].append({**identity(f"{key}-material-{i}", -15+i), "course_id": cid, "title": title, "description": "Học liệu dùng cho bộ dữ liệu kiểm thử của lớp.", **file_metadata(f"{key}-material-{i}", filename, payload)})
        network_titles = ["Bài tập 01 – Tổng quan giao thức mạng", "Bài tập 02 – Xây dựng TCP Client–Server", "Bài tập 03 – Truyền file trong mạng LAN", "Bài tập 04 – Xử lý nhiều kết nối", "Bài tập 05 – Ứng dụng chat đơn giản"]
        db_titles = ["Bài tập 01 – Thiết kế sơ đồ quan hệ", "Bài tập 02 – Truy vấn và kết nối bảng", "Bài tập 03 – Thực hành GROUP BY", "Bài tập 04 – Giao dịch và ràng buộc", "Bài tập 05 – Thiết kế cơ sở dữ liệu thư viện"]
        titles = network_titles if key == "network" else db_titles if key == "database" else ["Bài tập 01 – Biến và kiểu dữ liệu", "Bài tập 02 – Vòng lặp", "Bài tập 03 – Mảng và hàm"]
        task_ids = []
        for i, title in enumerate(titles):
            due_day = -35+i*7 if completed else [-10, -3, 3, 7, 14][i]
            task = {**identity(f"{key}-task-{i+1}", -25+i), "course_id": cid, "title": title, "description": f"Hoàn thành nội dung thực hành của {name}.\nNộp file ZIP chứa mã nguồn, README mô tả cách chạy và ví dụ đầu vào/đầu ra.\nTiêu chí: đúng yêu cầu (6 điểm), kiểm thử (2 điểm), trình bày và hướng dẫn (2 điểm).", "due_at": iso(due_day, 23, 59), "max_attempts": 3}
            data["assignments"].append(task)
            task_ids.append(task["id"])
            for j, sid in enumerate(members):
                should_submit = completed or (i == 0 and j % 5 != 4) or (i == 1 and j % 3 != 2) or (i == 2 and j in (2, 3, 5, 7, 9)) or (i == 3 and j in (1, 4))
                if not should_submit:
                    continue
                total_attempts = 2 if not completed and i == 1 and j % 4 == 0 else 1
                for attempt in range(1, total_attempts+1):
                    subkey = f"{key}-task-{i+1}-{sid}-{attempt}"
                    score = round(6 + (j % 8) * .5, 2) if completed or i == 0 or (i == 1 and j % 2 == 0 and attempt == total_attempts) else None
                    payload = zipped({"main.cpp": "#include <iostream>\nint main() { std::cout << \"Hello classroom\"; }\n", "README.txt": f"Bài nộp mẫu: {sid}\n{title}\nLần nộp: {attempt}\nĐây là dữ liệu kiểm thử, không phải kết quả của sinh viên thật.\n"})
                    data["submissions"].append({**identity(subkey, due_day-1 if due_day < 0 else -1), "course_id": cid, "assignment_id": task["id"], "student_id": sid, "attempt": attempt, "request_id": subkey, "score": score, "feedback": "Đã đáp ứng yêu cầu. Cần bổ sung mô tả các tình huống biên." if score is not None else "", **file_metadata(subkey, f"{sid}_BT{i+1:02}_lan{attempt}.zip", payload)})
        task_by_course[cid] = task_ids
        for i in range(6 if completed else 4):
            is_open = not completed and i == 3
            records = {}
            for j, sid in enumerate(members):
                if is_open:
                    if j not in (1, 3, 6):
                        continue
                elif j % 7 == 6:
                    continue
                records[sid] = {"status": "late" if j % 5 == 3 else "present", "checked_in_at": iso(0 if is_open else -20+i*3), "reason": "Bản ghi mẫu để kiểm tra chuyên cần."}
            data["attendance"].append({**identity(f"{key}-attendance-{i}", 0 if is_open else -20+i*3), "course_id": cid, "title": f"Điểm danh buổi {i+1:02}" + (" – Đang mở" if is_open else ""), "description": "Nhập mã hoặc quét QR do giảng viên hiển thị để xác nhận có mặt.", "expires_at": iso(1) if is_open else iso(-19+i*3), "code": secrets.token_hex(4).upper(), "closed": not is_open, "records": records})
        for j, sid in enumerate(members):
            if completed or j < 6:
                for component in (["midterm", "final"] if completed else ["midterm"]):
                    data["grades"].append({**identity(f"{key}-{sid}-{component}", -5), "course_id": cid, "student_id": sid, "component": component, "score": round(6.5 + (j % 6)*.5, 2)})
    for i in range(14):
        notices.append({"id": f"demo-v1-broadcast-{i}", "title": ["Lịch thực hành tuần này", "Nhắc hạn nộp bài", "Hướng dẫn kiểm tra kết quả học tập"][i % 3], "message": ["Các bạn kiểm tra lịch học trong khóa và chuẩn bị tài liệu trước khi đến lớp.", "Bài tập đang mở nhận bài. Kiểm tra hạn nộp, chọn file đúng định dạng và xác nhận biên nhận.", "Điểm và nhận xét của giảng viên được cập nhật trong mục Kết quả học tập."][i % 3], "student_id": ids[i % len(ids)] if i % 4 == 0 else None, "created_at": (now-timedelta(hours=i)).astimezone(timezone.utc).isoformat(timespec="seconds"), "created_by": "Giảng viên"})
    exam_names = ["DEMO_De_Thi_A.txt", "DEMO_De_Thi_B.txt"]
    for i, filename in enumerate(exam_names):
        target = exams.EXAM_DIR / filename
        if target.exists():
            raise RuntimeError("File đề mẫu đã tồn tại; không ghi đè: " + str(target))
        pending_files[target] = (f"KIỂM TRA THỰC HÀNH – ĐỀ {'AB'[i]}\nThời lượng 60 phút.\n\nBài 1 (5 điểm): Viết chương trình tính {'tổng các số chẵn' if i == 0 else 'tổng các số lẻ'} từ 1 đến n.\nBài 2 (5 điểm): Mô tả cách gửi và nhận file qua TCP.\n\nNộp file ZIP gồm mã nguồn và README hướng dẫn chạy. Có thể nộp tối đa 3 lần.\n").encode("utf-8")
    example_payload = zipped({"main.cpp": "#include <iostream>\nint main() { int n; std::cin >> n; int s = 0; for (int i=2;i<=n;i+=2) s+=i; std::cout << s; }\n", "README.txt": "File dùng để thử thao tác nộp bài. Có thể đổi nội dung và nộp lại để xem lịch sử.\n"})
    pending_files[root / "demo-inputs" / "DEMO001_bai_lam.zip"] = example_payload
    exam_ready = settings.get("exam_state") not in {"distributed", "started"} and not settings.get("exam_released")
    if exam_ready:
        release = "demo-v1-release-" + secrets.token_hex(6)
        settings.update({"exam_course_id": course_ids[0], "exam_title": "Kiểm tra thực hành – Bộ dữ liệu mẫu", "exam_state": "distributed", "exam_released": False, "exam_release_id": release, "exam_release_at": iso(), "exam_started_at": None, "exam_participants": ids[:16], "exam_duration_minutes": 60, "submission_policy": "configurable", "max_submissions": 3, "overwrite_previous": False, "accepted_submission_extensions": [".zip", ".txt", ".cpp", ".c", ".java"], "exam_password_enabled": False, "exam_password_hash": None, "distribution_mode": "selected", "distribution_config": {"exam_files": exam_names}})
        for i, sid in enumerate(ids[:16]):
            assignments[sid] = {"exam_file": exam_names[i % 2], "course_id": course_ids[0], "exam_title": settings["exam_title"], "release_id": release, "assigned_at": iso(), "started_at": None, "ends_at": None, "status": "assigned", "ip_at_assignment": None}
    backup = root / "backups" / ("before-demo-" + stamp)
    if backup.exists():
        raise RuntimeError("Thư mục sao lưu đã tồn tại. Hãy chạy lại sau một giây.")
    backup.mkdir(parents=True)
    shutil.copytree(storage.DATA_DIR, backup / "data")
    original = {name: (storage.DATA_DIR/name).read_bytes() if (storage.DATA_DIR/name).exists() else None for name in ["students.json", "learning.json", "notifications.json", "settings.json", "assignments.json"]}
    written = []
    marker = {"version": VERSION, "created_at": iso(), "backup": str(backup), "students": ids, "courses": course_ids, "primary_assignment": task_by_course[course_ids[0]][2], "exam_ready": exam_ready, "materials_added": 9, "assignments_added": 13, "submissions_added": sum(s["id"].startswith("demo-v1-") for s in data["submissions"])}
    try:
        for path, payload in pending_files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as output:
                output.write(payload)
            written.append(path)
        for name, value in [("students.json", students), ("learning.json", data), ("notifications.json", notices)]:
            storage.write_json(name, value)
        if exam_ready:
            storage.write_json("settings.json", settings)
            storage.write_json("assignments.json", assignments)
        storage.write_json("demo_seed.json", marker)
        storage.audit("setup.demo_seeded", "local-user", "127.0.0.1", {"version": VERSION, "backup": str(backup), "exam_ready": exam_ready})
    except Exception:
        for name, payload in original.items():
            path = storage.DATA_DIR/name
            if payload is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(payload)
        marker_path.unlink(missing_ok=True)
        for path in written:
            if path.resolve().is_relative_to(root.resolve()):
                path.unlink(missing_ok=True)
        raise
    return {"status": "created", **marker}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Add sample data, with a backup first. Stop the server before running.")
    args = parser.parse_args()
    if not args.apply:
        print("Will add 20 DEMO accounts, 3 courses, materials, assignments, submissions, attendance and notifications. Existing accounts/files are preserved. Run with --apply after stopping the server.")
        return
    storage.initialize()
    print(json.dumps(seed_demo(), ensure_ascii=True, indent=2))


if __name__ == "__main__":
    from .runtime import data_lease
    from .config import DATA_DIR
    with data_lease(DATA_DIR):
        main()
