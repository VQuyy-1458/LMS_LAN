"""Disposable populated server for browser QA; no production records are imported."""
import json
import os
import sys
import tempfile
import io,zipfile,base64
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import config

with tempfile.TemporaryDirectory(prefix="classroom-student-qa-") as temp:
    root = Path(temp)
    for attr, name in (("DATA_DIR", "data"), ("LOG_DIR", "logs"), ("UPLOAD_DIR", "submissions"), ("EXAM_DIR", "exams")):
        setattr(config, attr, root / name)
        (root / name).mkdir()
    from app import main, learning, storage, programming
    # Roster/entry UI tests exercise opening an exam, not the Docker runner itself.
    if os.environ.get("CSS_ROSTER_QA") == "1":
        main.code_runner.ready = lambda: True
        main.code_runner.status = lambda: {"ready":True,"detail":"Fixture judge (UI only)","image_id":"qa-ui-image"}
        def fixture_reference(source, language, problem, **kwargs):
            return {"verdict":"AC","score":problem["points"],"passed":len(problem["tests"]),"total":len(problem["tests"]),"tests":[],"compile_log":""}
        main.code_runner.judge = fixture_reference
    programming.FILES = root / "code-files"
    from app.security import hash_password, new_session
    (root / "exams" / "de-thuc-hanh.txt").write_text("Viết chương trình giải bài tập và nộp file theo yêu cầu.", encoding="utf-8")
    learning.FILES = root / "files"
    password = hash_password("qa-password")
    storage.write_json("admins.json", {"qa-admin": {"password_hash": password, "active": True}})
    storage.write_json("students.json", {"QA001": {"full_name": "Nguyễn Minh Anh", "password_hash": password, "active": True}, "QAEMPTY": {"full_name": "Sinh viên mới", "password_hash": password, "active": True}})
    teacher = {"user_id": "qa-admin", "role": "admin"}
    def create(action, **form):
        if action == "attendance" and "event_id" not in form:
            form["event_id"] = create("event", course_id=form["course_id"], title=form.get("title", "Lesson"), kind="lesson", starts_at=storage.utc_now())
        return learning.mutate(teacher, action, form, {}, "127.0.0.1")["id"]
    course = create("course", code="CS101", name="Lập trình căn bản", semester="Học kỳ 1 · 2026–2027", student_ids="QA001", description="Không gian học tập C, C++ và Java. Xem tài liệu, hoàn thành bài tập và theo dõi kết quả của bạn.")
    second = create("course", code="CTDL02", name="Cấu trúc dữ liệu và giải thuật", semester="Học kỳ 1 · 2026–2027", student_ids="QA001", description="Ôn tập cấu trúc dữ liệu và kỹ năng giải quyết bài toán.")
    closed_course = create("course", code="OLD101", name="Khóa học đã tổng kết", semester="Học kỳ trước", student_ids="QA001")
    create("course-weights", course_id=closed_course, attendance="100", homework="0", midterm="0", final="0")
    create("complete-course", course_id=closed_course)
    future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    assignment = create("assignment", course_id=course, title="Bài tập 01: Cấu trúc điều khiển", description="Viết chương trình tính tổng các số chẵn từ 1 đến n. Nộp file mã nguồn hoặc file ZIP chứa bài làm.", due_at=future, max_attempts="3")
    create("event", course_id=course, title="Buổi 03: Vòng lặp và mảng", starts_at=(datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(), kind="lesson", location="Phòng thực hành A203", description="Ôn lại vòng lặp và chuẩn bị bài tập thực hành.")
    create("event", course_id=second, title="Tài liệu ôn tập đã cập nhật", starts_at=storage.utc_now(), kind="announcement", description="Các bạn xem lại tài liệu và chuẩn bị cho buổi học tiếp theo.")
    attendance = create("attendance", course_id=course, title="Điểm danh buổi thực hành", expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat())
    attendance_qr = create("attendance", course_id=course, title="Điểm danh buổi ôn tập", expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat())
    learning.mutate(teacher, "material", {"course_id":course,"title":"Hướng dẫn thực hành","description":"Các bước chuẩn bị bài tập."}, {"file":{"filename":"huong-dan.txt","data":b"Programming exercises"}}, "127.0.0.1")
    file_history=[]
    for version,text in enumerate(("First original file","Second original file"),1):
        filename=f"qa-file-{version}.txt"
        (root/"submissions"/filename).write_text(text,encoding="utf-8")
        file_history.append({"filename":filename,"original_filename":"answer.txt","submitted_at":(datetime.now(timezone.utc)-timedelta(minutes=3-version)).isoformat(),"release_id":"qa-archive-release","course_id":course,"exam_title":"Kỳ thi nộp file lưu trữ","status":"received","payload_retained":True,"size_bytes":len(text)})
    storage.write_json("submissions.json",{"QA001":file_history})
    storage.write_json("notifications.json", [{"id":"qa-message","student_id":None,"title":"Lớp học Lập trình căn bản sắp diễn ra","message":"Lớp học Lập trình căn bản sẽ diễn ra trong 30 phút nữa. Các bạn chuẩn bị bài tập và có mặt tại phòng A203.","created_by":"Quản lý đào tạo","created_at":storage.utc_now()}] + [{"id":f"qa-message-{i}","student_id":"QA001" if i % 4 == 0 else None,"title":f"Lịch học thực hành số {i:02}","message":"Lịch học và tài liệu thực hành đã được cập nhật. Các bạn xem lại nội dung trước khi đến lớp.","created_by":"Giảng viên","created_at":(datetime.now(timezone.utc)-timedelta(hours=i)).isoformat()} for i in range(1,14)])
    main.Handler.log_message = lambda *args: None
    server = main.ThreadingHTTPServer(("127.0.0.1",0),main.Handler)
    server.daemon_threads = True
    ready = {"port":server.server_port,"student":new_session("QA001","student","127.0.0.1","qa"),"empty":new_session("QAEMPTY","student","127.0.0.1","qa"),"admin":new_session("qa-admin","admin","127.0.0.1","qa"),"course":course,"assignment":assignment,"attendance":attendance,"attendance_qr":attendance_qr,"code":learning.load()["attendance"][0]["code"]}
    answer=io.BytesIO()
    with zipfile.ZipFile(answer,"w") as archive: archive.writestr("answer.txt","file-exam-original")
    ready["closed_course"] = closed_course
    ready["exam_zip"]=base64.b64encode(answer.getvalue()).decode()
    if os.environ.get("CSS_TIMING_QA") == "1":
        (root/"exams"/"timing-qa.txt").write_text("Private file exam question",encoding="utf-8")
    if os.environ.get("CSS_ENROLLMENT_QA") == "1":
        data = learning.load()
        c = learning.find(data, "courses", course)
        c.pop("enrollments", None)
        c.pop("enrollment_tracking_since", None)
        previous = (datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
        learning.find(data, "assignments", assignment).update(due_at=previous, closed_at=previous)
        session = learning.find(data, "attendance", attendance)
        session.update(lesson_at=previous, expires_at=previous, closed=True)
        learning.find(data, "events", session["event_id"])["starts_at"] = previous
        storage.write_json("learning.json", data)
        learning.initialize_enrollments()
    print("QA_READY " + json.dumps(ready),flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
