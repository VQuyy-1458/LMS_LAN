"""HTTP integration checks with disposable storage; never touch classroom data."""
import copy
import http.client
import json
import tempfile
import threading
import unittest
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from app import learning, main, storage, submissions, exams, programming, code_runner, submission_rate, submission_archive, deadlines, exam_preflight, exam_timing
from app.security import hash_password, new_session, verify_password


class LearningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.patches = [patch.object(storage, "DATA_DIR", root / "data"), patch.object(storage, "LOG_DIR", root / "logs"), patch.object(learning, "FILES", root / "files"), patch.object(main, "UPLOAD_DIR", root / "exam-files"), patch.object(submissions, "UPLOAD_DIR", root / "exam-files"), patch.object(main.Handler, "log_message", lambda *args: None)]
        self.patches.append(patch.object(programming, "FILES", root / "code-files"))
        for p in self.patches:
            p.start()
        self.addCleanup(self.cleanup)
        (root / "logs").mkdir()
        storage.initialize()
        (root / "exam-files").mkdir()
        password = hash_password("student-pass")
        storage.write_json("admins.json", {"teacher": {"password_hash": password, "active": True}})
        storage.write_json("students.json", {sid: {"student_id": sid, "full_name": sid, "password_hash": password, "active": True} for sid in ("s1", "s2")})
        self.tokens = {"admin": new_session("teacher", "admin", "127.0.0.1", "test"), "s1": new_session("s1", "student", "127.0.0.1", "test"), "s2": new_session("s2", "student", "127.0.0.1", "test")}
        self.server = main.ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

    def cleanup(self):
        if hasattr(self, "server"):
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=2)
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def request(self, path, role="admin", form=None, file=None, origin=None):
        headers = {"Cookie": f"css_session={self.tokens[role]}"}
        method = "GET" if form is None else "POST"
        body = None
        if form is not None:
            headers["Origin"] = origin or f"http://127.0.0.1:{self.server.server_port}"
            if file:
                boundary = "learning-test-boundary"
                chunks = []
                for k, v in form.items():
                    chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
                chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{file[0]}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode() + file[1] + b"\r\n")
                chunks.append(f"--{boundary}--\r\n".encode())
                body = b"".join(chunks)
                headers["Content-Type"] = "multipart/form-data; boundary=" + boundary
            else:
                body = urllib.parse.urlencode(form)
                headers["Content-Type"] = "application/x-www-form-urlencoded"
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        payload = response.read()
        is_json = "application/json" in response.getheader("Content-Type", "")
        result = json.loads(payload) if is_json else payload
        code = response.status
        conn.close()
        return code, result

    def create(self, action, **fields):
        if action == "attendance" and "event_id" not in fields:
            fields["event_id"] = self.create("event", course_id=fields["course_id"], title=fields.get("title", "Lesson"), kind="lesson", starts_at=storage.utc_now())
        code, result = self.request("/api/learning/" + action, form=fields)
        self.assertEqual(code, 200, result)
        return result["id"]

    def course(self, members="s1"):
        return self.create("course", name="Course", code="CS1", semester="2026", student_ids=members)

    def test_admin_reset_password_clears_lockout_and_revokes_only_target_sessions(self):
        for _ in range(3):
            self.request("/login", role="s1", form={"username": "s1", "password": "wrong"})
        self.assertEqual(self.request("/login", role="s1", form={"username": "s1", "password": "student-pass"})[0], 429)
        code, result = self.request("/api/admin/accounts/s1/reset-password", form={"new_password": "replacement-pass"})
        self.assertEqual(code, 200, result)
        self.assertNotIn("s1", storage.read_json("login_attempts.json"))
        students = storage.read_json("students.json")
        self.assertTrue(verify_password("replacement-pass", students["s1"]["password_hash"]))
        self.assertFalse(verify_password("student-pass", students["s1"]["password_hash"]))
        sessions = list(storage.read_json("sessions.json").values())
        self.assertFalse(any(s["user_id"] == "s1" for s in sessions))
        self.assertTrue(any(s["user_id"] == "s2" for s in sessions))
        self.assertEqual(self.request("/login", role="s1", form={"username": "s1", "password": "replacement-pass"})[0], 303)

    def test_admin_reset_password_rejects_invalid_input_and_student_access(self):
        original = storage.read_json("students.json")
        for password in ("short", " " * 8, "x" * 201):
            self.assertEqual(self.request("/api/admin/accounts/s1/reset-password", form={"new_password": password})[0], 400)
        self.assertEqual(self.request("/api/admin/accounts/s1/reset-password", role="s2", form={"new_password": "replacement-pass"})[0], 403)
        self.assertEqual(storage.read_json("students.json"), original)

    def test_programming_trial_adds_three_open_exams_without_replacing_records(self):
        from app import programming_trial, exam_catalog
        original = copy.deepcopy(storage.read_json("students.json"))
        with patch.object(programming_trial, "BASE_DIR", Path(self.temp.name)), patch.object(code_runner, "ready", return_value=True), patch("builtins.print"):
            manifest = programming_trial.apply()
            self.assertEqual(programming_trial.apply(), manifest)
        students = storage.read_json("students.json")
        self.assertEqual({sid: students[sid] for sid in original}, original)
        self.assertTrue(verify_password(programming_trial.PASSWORD, students[programming_trial.STUDENT_ID]["password_hash"]))
        feed = programming.snapshot(programming_trial.STUDENT_ID)
        self.assertEqual(len(feed["exams"]), 3)
        self.assertTrue(all(row["can_start"] for row in feed["exams"]))
        self.assertTrue(all(row["problems"] == [] for row in feed["exams"]))
        for row in exam_catalog.listing():
            if row["type"] != "programming": continue
            self.assertEqual(row["assessment_type"], "test")
            self.assertEqual(len(row["programming"]["problems"]), 2)
            for item in row["programming"]["problems"]:
                self.assertNotIn("solution", item)
                self.assertEqual(len(item["tests"]), 8)
                self.assertEqual(sum(t["sample"] for t in item["tests"]), 2)

    def test_notifications_deduplicate_recipients_and_keep_messages_private(self):
        code, result = self.request("/api/admin/notifications", form={"message": "Riêng cho s1", "student_ids": "s1,s1"})
        self.assertEqual(code, 200, result)
        self.assertEqual(result["recipient_count"], 1)
        self.assertEqual(len(storage.read_json("notifications.json")), 1)
        first = self.request("/api/student/notifications", role="s1")[1]["notifications"]
        second = self.request("/api/student/notifications", role="s2")[1]["notifications"]
        self.assertTrue(any(n["description"] == "Riêng cho s1" for n in first))
        self.assertFalse(any(n["description"] == "Riêng cho s1" for n in second))
        before = storage.read_json("notifications.json")
        self.assertEqual(self.request("/api/admin/notifications", form={"message": "Sai MSSV", "student_ids": "s1,missing"})[0], 404)
        self.assertEqual(storage.read_json("notifications.json"), before)

    def test_concurrent_sessions_do_not_overwrite_other_logins(self):
        from concurrent.futures import ThreadPoolExecutor
        from app.security import get_session, logout_session
        barrier = threading.Barrier(12)
        def create_session(index):
            barrier.wait(timeout=5)
            return new_session(f"parallel-{index}", "admin", "127.0.0.1", "test")
        with ThreadPoolExecutor(max_workers=12) as pool:
            tokens = list(pool.map(create_session, range(12)))
        self.assertEqual(len(storage.read_json("sessions.json")), 15)
        for token in tokens:
            request = type("Request", (), {"cookies": {"css_session": token}})()
            self.assertIsNotNone(get_session(request))
            logout_session(token)
            self.assertIsNone(get_session(request))
        self.assertEqual(len(storage.read_json("sessions.json")), 3)

    def test_file_exam_common_deadline_late_start_extension_and_auto_close(self):
        course = self.course("s1,s2")
        start = datetime.now(timezone.utc).replace(microsecond=0)
        settings = storage.read_json("settings.json")
        settings.update({"exam_state":"distributed","exam_release_id":"shared-release","exam_duration_minutes":10,"exam_course_id":course})
        storage.write_json("settings.json",settings)
        storage.write_json("assignments.json",{sid:{"exam_file":"test.txt","course_id":course,"release_id":"shared-release","status":"assigned"} for sid in ("s1","s2")})
        with patch.object(exams,"datetime") as clock:
            clock.now.return_value=start
            exams.start_exam_session()
            clock.now.return_value=start+timedelta(minutes=1)
            first=exams.start_exam("s1")
            clock.now.return_value=start+timedelta(minutes=8)
            second=exams.start_exam("s2")
            self.assertEqual(first["ends_at"],second["ends_at"])
            self.assertEqual(learning.date_value(first["ends_at"]),start+timedelta(minutes=10))
            clock.now.return_value=start+timedelta(minutes=10)
            with self.assertRaises(ValueError): exams.start_exam("s1")
        records=storage.read_json("assignments.json")
        records["s2"]["ends_at"]=(start+timedelta(minutes=15)).isoformat()
        storage.write_json("assignments.json",records)
        received={"s1":[{"release_id":"shared-release","filename":"original.zip","sha256":"unchanged","submitted_at":start.isoformat()}]}
        storage.write_json("submissions.json",received)
        deadlines.refresh(start+timedelta(minutes=10))
        self.assertEqual(storage.read_json("assignments.json")["s1"]["status"],"expired")
        self.assertNotIn("closed_at",storage.read_json("assignments.json")["s2"])
        self.assertEqual(storage.read_json("settings.json")["exam_state"],"started")
        deadlines.refresh(start+timedelta(minutes=15))
        ended=storage.read_json("settings.json")
        self.assertEqual(ended["exam_state"],"ended")
        self.assertFalse(ended["exam_released"])
        self.assertTrue(ended["exam_closed_automatically"])
        self.assertEqual(ended["exam_release_id"],"shared-release")
        self.assertEqual(storage.read_json("submissions.json"),received)
        self.assertFalse(main.student_exam_snapshot("s2")["can_submit"])

    def test_programming_common_deadline_auto_end_and_late_submission_rejected(self):
        course=self.course("s1,s2")
        form={"course_id":course,"type":"programming","title":"Common clock","duration_minutes":"10","languages":"python","problems":json.dumps([{"title":"Sum","tests":[{"input":"1 2","output":"3"}]}])}
        exam_id=self.request("/api/admin/exam-configurations/save",form=form)[1]["id"]
        with patch.object(code_runner,"ready",return_value=True):
            self.assertEqual(self.request("/api/admin/programming/control",form={"exam_id":exam_id,"action":"start"})[0],200)
        row=programming.exam(exam_id)
        common_end=learning.date_value(row["ends_at"])
        before=programming.snapshot("s1")["exams"][0]
        self.assertEqual(before["started_at"],row["started_at"])
        self.assertEqual(learning.date_value(before["ends_at"]),common_end)
        self.assertTrue(before["can_start"])
        self.assertIsNone(before["attempt"])
        self.assertEqual(before["problems"],[])
        with patch.object(programming,"datetime") as clock:
            clock.now.return_value=common_end-timedelta(minutes=1)
            programming.start({"user_id":"s1","role":"student"},{"exam_id":exam_id},"127.0.0.1")
        self.assertEqual(learning.date_value(storage.read_json("programming_attempts.json")[exam_id+":s1"]["ends_at"]),common_end)
        after=programming.snapshot("s1")["exams"][0]
        self.assertEqual(after["started_at"],before["started_at"])
        self.assertEqual(after["ends_at"],before["ends_at"])
        self.assertNotEqual(after["attempt"]["started_at"],after["started_at"])
        deadlines.refresh(common_end)
        self.assertEqual(programming.exam(exam_id)["state"],"ended")
        self.assertEqual(storage.read_json("programming_attempts.json")[exam_id+":s1"]["status"],"expired")
        self.assertEqual(self.request("/api/student/programming/start","s2",{"exam_id":exam_id})[0],409)
        with patch.object(code_runner,"ready",return_value=True):
            self.assertEqual(self.request("/api/student/programming/submit","s1",{"exam_id":exam_id,"language":"python","problem_index":"0"},file=("answer.py",b"print(3)"))[0],409)
        self.assertEqual(programming.rows(),[])

    def test_expiration_worker_closes_assignment_without_browser_requests(self):
        import time
        course=self.course()
        due=(datetime.now(timezone.utc)+timedelta(milliseconds=200)).isoformat()
        task=self.create("assignment",course_id=course,title="Timed task",due_at=due)
        stop,thread=deadlines.start_worker()
        try:
            until=time.monotonic()+4
            while time.monotonic()<until and not learning.find(learning.load(),"assignments",task).get("closed_at"):
                time.sleep(.05)
            self.assertEqual(learning.find(learning.load(),"assignments",task)["closed_at"],due)
        finally:
            stop.set();thread.join(timeout=2)
        self.assertEqual(self.upload(task)[0],409)

    def test_assessment_types_and_one_final_across_file_and_code(self):
        course = self.course()
        endpoint = "/api/admin/exam-configurations/save"
        def save(category, kind="file", **extra):
            return self.request(endpoint, form={"type": kind, "assessment_type": category, "course_id": course, "title": category, "duration_minutes": "60", "languages": "python", **extra})
        self.assertEqual(save("test")[0], 200)
        self.assertEqual(save("test")[0], 200)
        self.assertEqual(save("midterm")[0], 200)
        self.assertEqual(save("midterm", "programming")[0], 200)
        code, final = save("final")
        self.assertEqual(code, 200, final)
        self.assertEqual(save("final", "programming")[0], 409)
        self.assertEqual(save("final", id=final["id"])[0], 200)
        self.assertEqual(save("invalid")[0], 400)
        self.assertEqual(save("midterm", course_id="")[0], 400)
        other = self.course()
        self.assertEqual(save("final", "programming", course_id=other)[0], 200)
        self.assertEqual(self.request(endpoint, "s1", {"type":"file", "title":"No"})[0], 403)

    def test_exam_marks_normalization_average_practice_exclusion_and_pending(self):
        course = self.course("s1,s2")
        catalog = [
            {"id":"mid-file", "course_id":course, "title":"Mid file", "type":"file", "assessment_type":"midterm", "state":"ended", "participants":["s1","s2"]},
            {"id":"mid-code", "course_id":course, "title":"Mid code", "type":"programming", "assessment_type":"midterm", "state":"ended", "participants":["s1","s2"], "programming":{"problems":[{"points":100},{"points":300}]}},
            {"id":"final-file", "course_id":course, "title":"Final", "type":"file", "assessment_type":"final", "state":"ended", "participants":["s1","s2"]},
            {"id":"practice", "course_id":course, "title":"Practice", "type":"file", "assessment_type":"test", "state":"ended", "participants":["s1","s2"]},
            {"id":"draft", "course_id":course, "title":"Draft", "type":"file", "assessment_type":"midterm", "state":"idle", "participants":["s1","s2"]},
        ]
        storage.write_json("exam_catalog.json", catalog)
        storage.write_json("submissions.json", {"s1":[{"exam_id":"mid-file","score":10,"submitted_at":"2026-01-01"},{"exam_id":"mid-file","score":6,"submitted_at":"2026-01-02"},{"exam_id":"final-file","score":9,"submitted_at":"2026-01-02"},{"exam_id":"practice","score":0,"submitted_at":"2026-01-02"}]})
        storage.write_json("programming_submissions.json", [
            {"exam_id":"mid-code","student_id":"s1","problem_index":0,"result":{"score":25}},
            {"exam_id":"mid-code","student_id":"s1","problem_index":0,"result":{"score":50}},
            {"exam_id":"mid-code","student_id":"s1","problem_index":1,"result":None,"grading_history":[{"result":{"score":300}}]},
        ])
        data = learning.load()
        book = learning.gradebook(data, data["courses"][0], ["s1","s2"])
        self.assertEqual(book["items"][0]["midterm"], 7.38)
        self.assertEqual(book["items"][0]["final"], 9)
        self.assertEqual(book["items"][1]["midterm"], 0)
        self.assertEqual(book["items"][1]["final"], 0)
        self.assertEqual(len(book["items"][0]["exam_results"]), 3)
        pending = storage.read_json("submissions.json")
        pending["s1"].append({"exam_id":"mid-file","score":None,"submitted_at":"2026-01-03"})
        storage.write_json("submissions.json", pending)
        self.assertIsNone(learning.gradebook(data,data["courses"][0],["s1"])["items"][0]["midterm"])

    def test_attendance_requires_scheduled_lesson_and_is_idempotent(self):
        course = self.course()
        self.assertEqual(self.request("/api/learning/attendance", form={"course_id":course,"title":"Free session","expires_at":self.future})[0],400)
        announcement = self.create("event",course_id=course,title="Notice",starts_at=self.future,kind="announcement")
        self.assertEqual(self.request("/api/learning/attendance",form={"course_id":course,"event_id":announcement})[0],400)
        lesson = self.create("event",course_id=course,title="Scheduled lesson",starts_at=self.future,kind="lesson")
        other = self.course()
        self.assertEqual(self.request("/api/learning/attendance",form={"course_id":other,"event_id":lesson})[0],400)
        session = self.create("attendance",course_id=course,event_id=lesson,duration_minutes="15")
        row = learning.load()["attendance"][0]
        self.assertEqual(row["title"],"Scheduled lesson")
        self.assertEqual(row["lesson_at"],self.future)
        self.assertEqual(self.request("/api/learning/check-in","s1",{"session_id":session,"code":row["code"]})[0],200)
        self.assertEqual(self.create("attendance",course_id=course,event_id=lesson),session)
        self.assertEqual(len(learning.load()["attendance"]),1)
        self.assertEqual(learning.load()["attendance"][0]["records"]["s1"]["status"],"present")

    def test_assignment_attachment_is_private_and_separate_from_materials(self):
        course = self.course()
        code, created = self.request("/api/learning/assignment",form={"course_id":course,"title":"Attached exercise","due_at":self.future},file=("exercise.txt",b"Solve exercise one"))
        self.assertEqual(code,200,created)
        path = "/api/learning/files/assignments/" + created["id"]
        self.assertEqual(self.request(path,"s1"),(200,b"Solve exercise one"))
        self.assertEqual(self.request(path,"s2")[0],403)
        own = self.request("/api/student/workspace","s1")[1]
        self.assertEqual(own["materials"],[])
        self.assertEqual(own["assignments"][0]["original_filename"],"exercise.txt")
        self.assertNotIn("stored_name",own["assignments"][0])
        self.assertEqual(self.request("/api/learning/preview/assignments/"+created["id"],"s1")[1]["text"],"Solve exercise one")

    def test_bulk_grade_save_atomic_validation_override_and_reset(self):
        course = self.course()
        endpoint = "/api/learning/gradebook-save"
        def save(items, role="admin"):
            return self.request(endpoint, role, {"course_id":course,"items":json.dumps(items)})
        valid = {"student_id":"s1","component":"final","score":"8.5"}
        self.assertEqual(save([valid,{"student_id":"s1","component":"midterm","score":11}])[0],400)
        self.assertEqual(learning.load()["grades"],[])
        self.assertEqual(save([{**valid,"student_id":"s2"}])[0],400)
        self.assertEqual(save([valid],"s1")[0],403)
        self.assertEqual(save([valid,{"student_id":"s1","component":"attendance","score":7}])[0],200)
        own = self.request("/api/student/workspace","s1")[1]["gradebooks"][0]["items"][0]
        self.assertEqual(own["final"],8.5)
        self.assertEqual(own["attendance"],7)
        self.assertEqual(own["automatic"]["attendance"],10)
        self.assertEqual(save([{"student_id":"s1","component":"attendance","score":""}])[0],200)
        own = self.request("/api/student/workspace","s1")[1]["gradebooks"][0]["items"][0]
        self.assertEqual(own["attendance"],10)
        self.assertEqual(own["final"],8.5)

    def test_shared_submission_rate_rolling_window_and_failed_attempts(self):
        course = self.course("s1,s2")
        assignment = self.create("assignment", course_id=course, title="Rate test", due_at=self.future, max_attempts="20")
        settings = storage.read_json("settings.json")
        settings.update({"exam_state":"started","exam_released":True,"exam_release_id":"rate-release","accepted_submission_extensions":[".txt"],"submission_policy":"configurable","max_submissions":20})
        storage.write_json("settings.json",settings)
        storage.write_json("assignments.json",{"s1":{"started_at":storage.utc_now(),"ends_at":self.future,"release_id":"rate-release","status":"in_progress"}})
        with patch.object(submission_rate.time,"time",return_value=1000):
            self.assertEqual(self.upload(assignment,request_id="invalid",payload=b"")[0],400)
            for i in range(3): self.assertEqual(self.upload(assignment,request_id=f"r{i}")[0],200)
            for i in range(3):
                code, response = self.request("/api/student/submit",role="s1",form={},file=("answer.txt",f"version{i}".encode()))
                self.assertEqual(code,200,response)
            code,response=self.upload(assignment,request_id="blocked")
            self.assertEqual(code,429); self.assertEqual(response["retry_after"],60)
            self.assertEqual(self.upload(assignment,request_id="r0")[0],200)  # idempotent retry isn't another submission
            self.assertEqual(self.upload(assignment,role="s2",request_id="other-student")[0],200)
        with patch.object(submission_rate.time,"time",return_value=1059):
            code,response=self.upload(assignment,request_id="not-yet")
            self.assertEqual(code,429); self.assertEqual(response["retry_after"],1)
        with patch.object(submission_rate.time,"time",return_value=1060):
            self.assertEqual(self.upload(assignment,request_id="allowed")[0],200)
        file_records=storage.read_json("submissions.json")["s1"]
        self.assertEqual(len(file_records),3)
        for i,row in enumerate(file_records): self.assertEqual((submissions.UPLOAD_DIR/row["filename"]).read_bytes(),f"version{i}".encode())

    def test_archive_attempts_grading_history_preview_export_and_privacy(self):
        course=self.course()
        assignment=self.assignment(course)
        first=self.upload(assignment,request_id="a1",payload=b"version one")[1]["id"]
        second=self.upload(assignment,request_id="a2",payload=b"version two")[1]["id"]
        self.create("grade",submission_id=first,score="7",feedback="First grade")
        self.create("grade",submission_id=first,score="8",feedback="Revised grade")
        code,listing=self.request("/api/admin/archive/list?course="+course)
        self.assertEqual(code,200)
        self.assertEqual(listing["total"],2)
        selected=next(r for r in listing["rows"] if r["selected"])
        self.assertEqual(selected["id"],"assignment:"+second)
        key="assignment:"+first
        encoded=urllib.parse.quote(key,safe="")
        detail=self.request("/api/admin/archive/detail?id="+encoded)[1]
        self.assertEqual([h["score"] for h in detail["grading_history"]],[7,8])
        self.assertEqual(len(detail["attempts"]),2)
        self.assertEqual(self.request("/api/admin/archive/download?id="+encoded)[1],b"version one")
        self.assertEqual(self.request("/api/admin/archive/preview?id="+encoded)[1]["text"],"version one")
        self.assertEqual(self.request("/api/admin/archive/list",role="s1")[0],403)
        self.assertEqual(self.request("/api/admin/archive/download?id="+encoded,role="s2")[0],403)
        grouped=self.request("/api/admin/archive/list?mode=group")[1]
        self.assertEqual(len(grouped["rows"]),1); self.assertEqual(grouped["rows"][0]["attempt_count"],2)
        self.assertEqual(self.request("/api/admin/archive/list?student=s2")[1]["total"],0)
        self.assertEqual(self.request("/api/admin/archive/list?from=bad")[0],400)
        self.assertEqual(self.request("/api/admin/archive/list?status=graded")[1]["total"],1)
        import io,zipfile
        package=self.request("/api/admin/archive/zip?student=s1")[1]
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            self.assertIn("metadata.csv",archive.namelist())
            self.assertIn(b"version one",[archive.read(n) for n in archive.namelist()])
            self.assertIn(b"version two",[archive.read(n) for n in archive.namelist()])
        source=learning.file_for("submissions",first,{"role":"admin","user_id":"teacher"})[0]
        source.unlink()
        missing=self.request("/api/admin/archive/detail?id="+encoded)[1]
        self.assertFalse(missing["submission"]["available"])
        self.assertEqual(self.request("/api/admin/archive/download?id="+encoded)[0],404)
        self.assertEqual(missing["grading_history"][0]["score"],7)

    def test_concurrent_submission_limit_has_six_slots_and_persistent_history(self):
        from concurrent.futures import ThreadPoolExecutor
        course=self.course()
        assignment=self.create("assignment",course_id=course,title="Concurrent",due_at=self.future,max_attempts="20")
        with patch.object(submission_rate.time,"time",return_value=5000), ThreadPoolExecutor(max_workers=8) as pool:
            responses=list(pool.map(lambda i:self.upload(assignment,request_id=f"concurrent-{i}"),range(8)))
        self.assertEqual(sorted(code for code,_ in responses),[200]*6+[429]*2)
        self.assertEqual(len(storage.read_json("submission_rate.json")["s1"]),6)
        self.assertEqual(self.request("/api/admin/archive/list")[1]["total"],6)

    def test_file_exam_archive_manual_grades_and_original_payloads(self):
        course=self.course()
        settings=storage.read_json("settings.json")
        settings.update({"exam_state":"started","exam_released":True,"exam_release_id":"archive-release","accepted_submission_extensions":[".txt"],"submission_policy":"configurable","max_submissions":3,"overwrite_previous":True})
        storage.write_json("settings.json",settings)
        storage.write_json("assignments.json",{"s1":{"started_at":storage.utc_now(),"ends_at":self.future,"release_id":"archive-release","status":"in_progress","course_id":course,"exam_title":"File exam"}})
        for version in (b"first file",b"second file"):
            self.assertEqual(self.request("/api/student/submit",role="s1",form={},file=("answer.txt",version))[0],200)
        catalog=self.request("/api/admin/archive/list?kind=file")[1]
        self.assertEqual(catalog["total"],2)
        first=next(r for r in catalog["rows"] if r["attempt"]==1)
        key=urllib.parse.quote(first["id"],safe="")
        self.assertEqual(self.request("/api/admin/archive/download?id="+key)[1],b"first file")
        for score in (6,9): self.assertEqual(self.request("/api/admin/archive/grade",form={"id":first["id"],"score":str(score),"feedback":"File grade"})[0],200)
        detail=self.request("/api/admin/archive/detail?id="+key)[1]
        self.assertEqual([g["score"] for g in detail["grading_history"]],[6,9])
        self.assertFalse(detail["submission"]["selected"])
        students=storage.read_json("students.json"); students["s1"]["full_name"]="=HYPERLINK(1)"; storage.write_json("students.json",students)
        exported=self.request("/api/admin/archive/csv")[1].decode("utf-8-sig")
        self.assertIn("'=HYPERLINK",exported)

    def test_programming_original_bom_and_rate_header(self):
        course=self.course()
        form={"course_id":course,"type":"programming","title":"Original source","languages":"python","problems":json.dumps([{"title":"Sum","tests":[{"input":"1 2","output":"3","sample":False}]}])}
        exam_id=self.request("/api/admin/exam-configurations/save",form=form)[1]["id"]
        with patch.object(code_runner,"ready",return_value=True),patch.object(programming,"schedule"):
            self.request("/api/admin/programming/control",form={"exam_id":exam_id,"action":"start"})
            self.request("/api/student/programming/start",role="s1",form={"exam_id":exam_id})
            original=b'\xef\xbb\xbfprint(3)'
            code,response=self.request("/api/student/programming/submit",role="s1",form={"exam_id":exam_id,"problem_index":"0","language":"python"},file=("source.py",original))
            self.assertEqual(code,200,response)
            key=urllib.parse.quote("code:"+response["submission"]["id"],safe="")
            self.assertEqual(self.request("/api/admin/archive/download?id="+key)[1],original)
            self.assertEqual(self.request("/api/admin/archive/detail?id="+key)[1]["submission"]["sha256"],__import__('hashlib').sha256(original).hexdigest())
        with patch.object(submission_rate.time,"time",return_value=5000):
            storage.write_json("submission_rate.json",{})
            for _ in range(6):
                with submission_rate.guard("s1"): pass
            conn=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=5)
            conn.request("POST","/api/student/submit",body="",headers={"Cookie":f"css_session={self.tokens['s1']}","Origin":f"http://127.0.0.1:{self.server.server_port}","Content-Type":"application/x-www-form-urlencoded"})
            # No file is validation failure, so use an assignment upload to reach the shared quota.
            response=conn.getresponse(); response.read(); conn.close()
            assignment=self.create("assignment",course_id=course,title="Rate header",due_at=self.future,max_attempts="20")
            boundary='rate-header-test'
            payload=(f'--{boundary}\r\nContent-Disposition: form-data; name="assignment_id"\r\n\r\n{assignment}\r\n--{boundary}\r\nContent-Disposition: form-data; name="request_id"\r\n\r\nheader\r\n--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.py"\r\nContent-Type: text/plain\r\n\r\nprint(3)\r\n--{boundary}--\r\n').encode()
            conn=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=5)
            conn.request("POST","/api/learning/submit",body=payload,headers={"Cookie":f"css_session={self.tokens['s1']}","Origin":f"http://127.0.0.1:{self.server.server_port}","Content-Type":"multipart/form-data; boundary="+boundary})
            response=conn.getresponse()
            self.assertEqual(response.status,429); self.assertEqual(response.getheader("Retry-After"),"60")
            response.read(); conn.close()

    def test_programming_lifecycle_privacy_deadline_and_rejudge_snapshot(self):
        course = self.course()
        spec = {"title": "Sum", "points": 10, "tests": [{"input": "1 2", "output": "3", "sample": True}, {"input": "secret-input", "output": "secret-output", "sample": False}]}
        fields = {"course_id": course, "type": "programming", "title": "Code exam", "languages": "python", "problems": json.dumps([spec])}
        _, created = self.request("/api/admin/exam-configurations/save", form=fields)
        exam_id = created["id"]
        with patch.object(code_runner, "ready", return_value=True), patch.object(programming, "schedule"):
            self.assertEqual(self.request("/api/admin/programming/control", role="s1", form={"exam_id": exam_id, "action": "start"})[0], 403)
            self.assertEqual(self.request("/api/admin/programming/control", form={"exam_id": exam_id, "action": "start"})[0], 200)
            code, blocked = self.request("/api/learning/complete-course", form={"course_id": course})
            self.assertEqual(code, 409)
            self.assertIn("kỳ thi lập trình", blocked["detail"])
            self.assertEqual(self.request("/api/admin/workspace")[1]["stats"]["running_exams"], 1)
            self.assertEqual(self.request("/api/admin/exam-configurations/save", form={**fields, "id": exam_id})[0], 409)
            self.assertEqual(self.request("/api/student/programming/start", role="s2", form={"exam_id": exam_id})[0], 403)
            pre = self.request("/api/student/workspace", role="s1")[1]["programming"]["exams"][0]
            self.assertEqual(pre["problems"], [])
            self.assertEqual(self.request("/api/student/programming/start", role="s1", form={"exam_id": exam_id})[0], 200)
            feed = self.request("/api/student/workspace", role="s1")[1]["programming"]
            self.assertNotIn("secret-input", json.dumps(feed))
            self.assertEqual(len(feed["exams"][0]["problems"][0]["samples"]), 1)
            form = {"exam_id": exam_id, "problem_index": "0", "language": "python"}
            self.assertEqual(self.request("/api/student/programming/submit", role="s1", form=form, file=("answer.cpp", b"print(3)"))[0], 400)
            code, result = self.request("/api/student/programming/submit", role="s1", form=form, file=("answer.py", b"print(3)"))
            self.assertEqual(code, 200, result)
            submission_id = result["submission"]["id"]
            graded = {"verdict": "WA", "score": 5, "passed": 1, "total": 2, "compile_log": "", "tests": [{"index": 1, "sample": True, "verdict": "AC", "input": "1 2", "expected": "3", "actual": "3", "stderr": ""}, {"index": 2, "sample": False, "verdict": "WA", "input": "secret-input", "expected": "secret-output", "actual": "echo-secret-input", "stderr": "secret-input"}]}
            def grading_with_progress(source, language, problem, progress, image=None):
                endpoint=f"/api/student/programming/submissions?exam={exam_id}&problem=0"
                progress("compiling",0,2)
                active=self.request(endpoint,role="s1")[1]["submissions"][0]
                self.assertEqual((active["state"],active["stage"]),("running","compiling"))
                progress("judging",1,2)
                active=self.request(endpoint,role="s1")[1]["submissions"][0]
                self.assertEqual((active["stage"],active["completed_tests"]),("judging",1))
                return graded
            with patch.object(code_runner, "judge", side_effect=grading_with_progress) as judge:
                programming._work(submission_id)
                self.assertEqual(judge.call_args.args[2]["tests"][1]["output"], "secret-output")
            endpoint=f"/api/student/programming/submissions?exam={exam_id}&problem=0"
            self.assertEqual(self.request(endpoint,role="s2")[0],403)
            self.assertEqual(self.request(endpoint.replace("problem=0","problem=99"),role="s1")[0],400)
            self.assertNotIn("secret-input",json.dumps(self.request(endpoint,role="s1")[1]))
            self.assertEqual(self.request(endpoint,role="s1")[1]["submissions"][0]["result"]["verdict"],"WA")
            student = self.request("/api/student/workspace", role="s1")[1]["programming"]["submissions"][0]
            self.assertEqual(student["result"]["score"], 5)
            self.assertNotIn("secret-input", json.dumps(student))
            admin = self.request("/api/admin/programming/submissions?exam="+exam_id)[1]["submissions"][0]
            self.assertEqual(admin["result"]["tests"][1]["actual"], "echo-secret-input")
            archive_key=urllib.parse.quote("code:"+submission_id,safe="")
            self.assertEqual(self.request("/api/admin/archive/detail?id="+archive_key)[1]["grading_history"][0]["result"]["score"],5)
            self.assertEqual(self.request("/api/programming/source/"+submission_id, role="s2")[0], 404)
            self.assertEqual(self.request("/api/programming/source/"+submission_id, role="s1")[1], b"print(3)")
            self.assertEqual(self.request("/api/admin/programming/rejudge", form={"submission_id": submission_id})[0], 200)
            self.assertEqual(self.request("/api/admin/programming/rejudge", form={"submission_id": submission_id})[0], 409)
            with patch.object(code_runner,"judge",return_value={**graded,"score":10,"passed":2,"verdict":"AC"}):
                programming._work(submission_id)
            archived=self.request("/api/admin/archive/detail?id="+archive_key)[1]
            self.assertEqual([g["result"]["score"] for g in archived["grading_history"]],[5,10])
            private=self.request("/api/student/workspace",role="s1")[1]["programming"]["submissions"][0]
            self.assertNotIn("secret-input",json.dumps(private))
            limited=self.create("assignment",course_id=course,title="Shared rate",due_at=self.future,max_attempts="20")
            for i in range(5): self.assertEqual(self.upload(limited,request_id=f"quota-{i}")[0],200)
            self.assertEqual(self.request("/api/student/programming/submit",role="s1",form=form,file=("answer.py",b"print(3)"))[0],429)
            attempts = storage.read_json("programming_attempts.json")
            attempts[exam_id+":s1"]["ends_at"] = (datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()
            storage.write_json("programming_attempts.json", attempts)
            self.assertEqual(self.request("/api/student/programming/submit", role="s1", form=form, file=("answer.py", b"print(3)"))[0], 409)
            self.assertEqual(self.request("/api/admin/programming/control", form={"exam_id": exam_id, "action": "end"})[0], 200)
            self.assertEqual(self.request("/api/student/programming/start", role="s1", form={"exam_id": exam_id})[0], 409)

    def code_exam(self, course_id="", **extra):
        fields = {"course_id": course_id, "title": "Roster code exam", "type": "programming", "languages": "python", "problems": json.dumps([{"title": "Sum", "tests": [{"input": "1 2", "output": "3"}]}]), **extra}
        code, result = self.request("/api/admin/exam-configurations/save", form=fields)
        self.assertEqual(code, 200, result)
        return result["id"], fields

    def test_programming_roster_persists_and_restricts_every_student_entry(self):
        course = self.course("s1,s2")
        exam_id, fields = self.code_exam(course)
        roster = {"exam_id": exam_id, "course_id": course, "student_ids": "s1,s1\ns1"}
        self.assertEqual(self.request("/api/admin/programming/participants", role="s1", form=roster)[0], 403)
        self.assertEqual(self.request("/api/admin/programming/participants", form=roster)[1]["student_ids"], ["s1"])
        self.assertEqual(self.request("/api/admin/exam-configurations/save", form={**fields, "id": exam_id, "title": "Edited"})[0], 200)
        self.assertEqual(programming.exam(exam_id)["participants"], ["s1"])
        with patch.object(code_runner, "ready", return_value=True), patch.object(programming, "schedule"):
            self.assertEqual(self.request("/api/admin/programming/control", form={"exam_id": exam_id, "action": "start"})[0], 200)
            self.assertEqual(programming.exam(exam_id)["participants"], ["s1"])
            self.assertEqual(self.request("/api/student/workspace", role="s2")[1]["programming"]["exams"], [])
            self.assertEqual(self.request("/api/student/programming/start", role="s2", form={"exam_id": exam_id})[0], 403)
            self.assertEqual(self.request("/api/student/programming/submit", role="s2", form={"exam_id": exam_id, "problem_index": "0", "language": "python"}, file=("a.py", b"print(3)"))[0], 403)
            self.assertEqual(self.request("/api/student/programming/start", role="s1", form={"exam_id": exam_id})[0], 200)
        self.assertEqual(self.request("/api/admin/programming/participants", form=roster)[0], 409)
        self.assertEqual(self.request("/api/admin/programming/control", form={"exam_id": exam_id, "action": "end"})[0], 200)
        self.assertEqual(self.request("/api/admin/programming/participants", form=roster)[0], 409)

    def test_programming_roster_account_creation_is_atomic_and_per_exam(self):
        exam_id, fields = self.code_exam()
        other_id, _ = self.code_exam(title="Other exam")
        other = copy.deepcopy(programming.exam(other_id))
        file_participants = storage.read_json("settings.json").get("exam_participants")
        old_hash = storage.read_json("students.json")["s1"]["password_hash"]
        code, saved = self.request("/api/admin/programming/participants", form={"exam_id": exam_id, "student_ids": "s1,NEW01\nNEW01"})
        self.assertEqual(code, 200, saved)
        self.assertEqual(saved["student_ids"], ["s1", "NEW01"])
        self.assertEqual(saved["created"], ["NEW01"])
        students = storage.read_json("students.json")
        self.assertTrue(verify_password("NEW01", students["NEW01"]["password_hash"]))
        self.assertTrue(students["NEW01"]["must_change_password"])
        self.assertEqual(students["s1"]["password_hash"], old_hash)
        self.assertEqual(programming.exam(other_id), other)
        self.assertEqual(storage.read_json("settings.json").get("exam_participants"), file_participants)
        for raw in ("", "s1,NEW02,bad-id", "x" * 81):
            self.assertEqual(self.request("/api/admin/programming/participants", form={"exam_id": exam_id, "student_ids": raw})[0], 400)
        self.assertEqual(storage.read_json("students.json"), students)
        self.assertEqual(self.request("/api/admin/exam-configurations/save", form={**fields, "id": exam_id, "languages": "invalid", "participant_ids": "NEW02"})[0], 400)
        self.assertNotIn("NEW02", storage.read_json("students.json"))
        self.assertEqual(self.request("/api/admin/exam-configurations/save", form={**fields, "id": exam_id, "participant_ids": "NEW02"})[0], 200)
        self.assertEqual(programming.exam(exam_id)["participants"], ["NEW02"])
        before_students = storage.read_json("students.json")
        original_write = storage.write_json
        def fail_catalog(name, value):
            if name == "exam_catalog.json":
                raise OSError("roster write failure")
            return original_write(name, value)
        with patch.object(programming.exam_catalog, "write_json", side_effect=fail_catalog):
            self.assertEqual(self.request("/api/admin/programming/participants", form={"exam_id": exam_id, "student_ids": "NEW03"})[0], 500)
        self.assertEqual(storage.read_json("students.json"), before_students)
        self.assertEqual(programming.exam(exam_id)["participants"], ["NEW02"])

    def test_programming_roster_validates_course_lock_and_current_membership(self):
        course = self.course()
        exam_id, fields = self.code_exam(course)
        for raw in ("s2", "NEW01"):
            self.assertEqual(self.request("/api/admin/programming/participants", form={"exam_id": exam_id, "student_ids": raw})[0], 400)
        self.assertNotIn("NEW01", storage.read_json("students.json"))
        self.assertEqual(self.request("/api/admin/programming/participants", form={"exam_id": exam_id, "course_id": "stale-course", "student_ids": "s1"})[0], 409)
        roster = {"exam_id": exam_id, "student_ids": "s1"}
        self.assertEqual(self.request("/api/admin/programming/participants", form=roster)[0], 200)
        self.create("course-members", course_id=course, student_ids="s2")
        with patch.object(code_runner, "ready", return_value=True):
            self.assertEqual(self.request("/api/admin/programming/control", form={"exam_id": exam_id, "action": "start"})[0], 409)
        self.create("course-members", course_id=course, student_ids="s1")
        students = storage.read_json("students.json");students["s1"]["active"] = False;storage.write_json("students.json", students)
        self.assertEqual(self.request("/api/admin/programming/participants", form=roster)[0], 400)
        with patch.object(code_runner, "ready", return_value=True):
            self.assertEqual(self.request("/api/admin/programming/control", form={"exam_id": exam_id, "action": "start"})[0], 409)
        self.create("course-weights", course_id=course, attendance="100", homework="0", midterm="0", final="0")
        self.create("complete-course", course_id=course)
        self.assertEqual(self.request("/api/admin/programming/participants", form=roster)[0], 409)

    def test_programming_roster_resets_when_exam_moves_to_another_course(self):
        first = self.course("s1,s2")
        second = self.create("course", name="Other", code="CS2", semester="2026", student_ids="s2")
        exam_id, fields = self.code_exam(first)
        self.assertEqual(self.request("/api/admin/programming/participants", form={"exam_id": exam_id, "student_ids": "s1"})[0], 200)
        self.assertEqual(self.request("/api/admin/exam-configurations/save", form={**fields, "id": exam_id, "course_id": second})[0], 200)
        row = programming.exam(exam_id)
        self.assertEqual(row["participants"], ["s2"])
        self.assertFalse(row.get("participants_configured", False))

    def test_exam_catalog_types_persistence_and_access(self):
        course = self.course()
        problem = {"title": "Sum", "statement": "Read a and b", "time_limit_ms": 1200, "memory_limit_mb": 128, "points": 50, "tests": [{"input": "1 2", "output": "3", "sample": False}]}
        form = {"course_id": course, "title": "Coding", "type": "programming", "languages": "cpp,python", "problems": json.dumps([problem]), "scheduled_at": self.future, "duration_minutes": "60"}
        code, created = self.request("/api/admin/exam-configurations/save", form=form)
        self.assertEqual(code, 200, created)
        row = next(r for r in self.request("/api/admin/workspace")[1]["exams"] if r["id"] == created["id"])
        self.assertEqual(row["programming"]["problems"][0]["tests"][0]["output"], "3")
        self.assertEqual(row["participants"], ["s1"])
        self.assertFalse(row["active"])
        self.assertEqual(self.request("/api/admin/exam-configurations/activate", form={"id": row["id"]})[0], 409)
        self.assertEqual(self.request("/api/admin/exam-configurations/save", role="s1", form=form)[0], 403)
        self.assertNotIn("exams", self.request("/api/learning", role="s1")[1])
        bad = dict(form, id=row["id"], languages="shell")
        self.assertEqual(self.request("/api/admin/exam-configurations/save", form=bad)[0], 400)
        bad = dict(form, id=row["id"], problems=json.dumps([{**problem, "title": 5}]))
        self.assertEqual(self.request("/api/admin/exam-configurations/save", form=bad)[0], 400)
        saved = next(r for r in self.request("/api/admin/workspace")[1]["exams"] if r["id"] == row["id"])
        self.assertEqual(saved["programming"]["languages"], ["cpp", "python"])

    def test_file_exam_activation_preserves_existing_release_and_old_configuration(self):
        course = self.course()
        self.assertEqual(self.request("/api/admin/exam-context", form={"course_id": course, "title": "Original"})[0], 200)
        form = {"course_id": course, "title": "New file exam", "type": "file", "duration_minutes": "45", "accepted_submission_extensions": ".zip .pdf", "submission_policy": "configurable", "max_submissions": "3"}
        code, created = self.request("/api/admin/exam-configurations/save", form=form)
        self.assertEqual(code, 200, created)
        settings = storage.read_json("settings.json")
        settings["exam_state"] = "distributed"
        storage.write_json("settings.json", settings)
        self.assertEqual(self.request("/api/admin/exam-configurations/activate", form={"id": created["id"]})[0], 409)
        self.assertEqual(storage.read_json("settings.json")["exam_title"], "Original")
        self.assertEqual(self.request("/api/admin/exam-configurations/save", form={**form, "id": "current"})[0], 409)
        settings["exam_state"] = "ended"
        storage.write_json("settings.json", settings)
        self.assertEqual(self.request("/api/admin/exam-configurations/activate", form={"id": created["id"]})[0], 200)
        settings = storage.read_json("settings.json")
        self.assertEqual(settings["exam_duration_minutes"], 45)
        self.assertEqual(settings["max_submissions"], 3)
        self.assertEqual(settings["accepted_submission_extensions"], [".pdf", ".zip"])
        self.assertEqual(self.request("/api/admin/exam-configurations/save", form={"id": created["id"], "type": "file", "course_id": course, "title": "New title", "metadata_only": "true"})[0], 200)
        self.assertEqual(storage.read_json("settings.json")["exam_duration_minutes"], 45)
        self.assertEqual(storage.read_json("settings.json")["max_submissions"], 3)
        rows = self.request("/api/admin/workspace")[1]["exams"]
        old = next(r for r in rows if r["id"] == "current")
        self.assertEqual(old["title"], "Original")
        self.assertEqual(old["state"], "ended")
        self.assertFalse(old["active"])
        self.assertEqual(sum(r["active"] for r in rows), 1)

    def test_exam_list_does_not_render_legacy_editor(self):
        self.assertNotIn(b'id="settings-form"', self.request("/admin?section=exam")[1])
        detail = self.request("/admin?section=exam&exam=current")[1]
        self.assertIn(b'id="settings-form"', detail)
        self.assertIn(b'id="distribution-form"', detail)
        self.assertIn(b'id="exam-participants"', detail)

    def assignment(self, course):
        return self.create("assignment", course_id=course, title="Task", due_at=self.future, max_attempts="2")

    def upload(self, assignment, role="s1", request_id="r1", payload=b"print(1)"):
        return self.request("/api/learning/submit", role, {"assignment_id": assignment, "request_id": request_id}, ("main.py", payload))

    def test_enrollment_and_private_files_and_scores(self):
        c = self.course()
        a = self.assignment(c)
        code, result = self.upload(a)
        self.assertEqual(code, 200)
        sid = result["id"]
        self.create("grade", submission_id=sid, score="8.5", feedback="Good")
        code, own = self.request("/api/student/workspace", "s1")
        self.assertEqual(code, 200)
        self.assertEqual(own["submissions"][0]["score"], 8.5)
        self.assertNotIn("stored_name", own["submissions"][0])
        self.assertNotIn("student_ids", own["courses"][0])
        self.assertNotIn("password_hash", own["student"])
        self.assertEqual(self.request("/api/learning/files/submissions/" + sid, "s1"), (200, b"print(1)"))
        preview = self.request("/api/learning/preview/submissions/" + sid, "s1")
        self.assertEqual(preview[0], 200)
        self.assertEqual(preview[1]["text"], "print(1)")
        self.assertEqual(self.request("/api/learning/files/submissions/" + sid, "s2")[0], 403)
        self.assertEqual(self.request("/api/learning/preview/submissions/" + sid, "s2")[0], 403)
        other = self.request("/api/student/workspace", "s2")[1]
        self.assertEqual(other["courses"], [])
        self.assertEqual(other["submissions"], [])

    def test_student_cannot_create_content_or_grade(self):
        code, _ = self.request("/api/learning/course", "s1", {"name": "Bad"})
        self.assertEqual(code, 403)
        self.assertEqual(self.request("/api/learning/grade", "s1", {"submission_id": "missing", "score": "10"})[0], 403)

    def test_submission_retry_and_attempt_limit(self):
        a = self.assignment(self.course())
        first = self.upload(a)
        self.assertEqual(first[0], 200)
        self.assertEqual(first, self.upload(a))
        self.assertEqual(self.upload(a, payload=b"different")[0], 409)
        self.assertEqual(self.upload(a, request_id="r2")[0], 200)
        self.assertEqual(self.upload(a, request_id="r3")[0], 409)
        self.assertEqual(len(learning.load()["submissions"]), 2)

    def test_expired_deadline_rejected_without_file(self):
        a = self.assignment(self.course())
        data = learning.load()
        data["assignments"][0]["due_at"] = "2000-01-01T00:00:00+00:00"
        storage.write_json("learning.json", data)
        self.assertEqual(self.upload(a)[0], 409)
        self.assertFalse(learning.FILES.exists())

    def test_completed_course_rejects_mutations(self):
        c = self.course()
        a = self.assignment(c)
        self.create("course-weights", course_id=c, attendance="100", homework="0", midterm="0", final="0")
        self.create("complete-course", course_id=c)
        self.assertEqual(self.upload(a)[0], 409)
        self.assertEqual(self.request("/api/learning/event", form={"course_id": c, "title": "New", "starts_at": self.future})[0], 409)
        self.assertEqual(self.request("/api/student/workspace", "s1")[0], 200)

    def test_attendance_code_is_private_and_closed_is_final(self):
        c = self.course()
        aid = self.create("attendance", course_id=c, title="Lesson", expires_at=self.future)
        admin = self.request("/api/learning")[1]["attendance"][0]
        student = self.request("/api/learning", "s1")[1]["attendance"][0]
        self.assertNotIn("code", student)
        self.assertNotIn("records", student)
        self.assertEqual(self.request("/api/learning/check-in", "s1", {"session_id": aid, "code": "wrong"})[0], 400)
        self.assertEqual(self.request("/api/learning/check-in", "s2", {"session_id": aid, "code": admin["code"]})[0], 403)
        self.assertEqual(self.request("/api/learning/check-in", "s1", {"session_id": aid, "code": admin["code"]})[0], 200)
        self.assertEqual(self.request("/api/learning/check-in", "s1", {"session_id": aid, "code": admin["code"]})[0], 200)
        self.assertEqual(len(learning.load()["attendance"][0]["records"]), 1)
        self.create("close-attendance", session_id=aid)
        repeated=self.request("/api/learning/check-in", "s1", {"session_id": aid, "code": admin["code"]})
        self.assertEqual(repeated[0],200)
        self.assertTrue(repeated[1]["already_checked_in"])
        self.assertEqual(self.request("/api/learning/attendance-record", form={"session_id": aid, "student_id": "s1", "status": "late", "reason": "reason"})[0], 409)

    def test_qr_checkin_reports_session_and_preserves_teacher_override(self):
        c=self.course()
        aid=self.create("attendance",course_id=c,title="QR lesson",expires_at=self.future)
        code=learning.load()["attendance"][0]["code"]
        self.create("attendance-record",session_id=aid,student_id="s1",status="absent",reason="Teacher override")
        response=self.request("/api/learning/check-in","s1",{"session_id":aid,"code":code})
        self.assertEqual(response[0],409)
        self.assertEqual(learning.load()["attendance"][0]["records"]["s1"]["status"],"absent")
        self.create("attendance-record",session_id=aid,student_id="s1",status="late",reason="Arrived late")
        response=self.request("/api/learning/check-in","s1",{"session_id":aid,"code":code})[1]
        self.assertEqual(response["course_id"],c)
        self.assertEqual(response["title"],"QR lesson")
        self.assertEqual(response["record"]["status"],"late")
        student=self.request("/api/student/workspace","s1")[1]["attendance"][0]
        self.assertEqual(student["session_status"],"open")
        self.assertNotIn("code",student)
        self.assertNotIn("records",student)

    def test_attendance_link_survives_login_without_open_redirect(self):
        destination='/student/attendance?session=0123456789abcdef0123&code=ABCDEF12'
        conn=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=5)
        conn.request("GET",destination); response=conn.getresponse()
        self.assertEqual(response.status,303)
        self.assertIn("/login?next=",response.getheader("Location"));response.read()
        form=urllib.parse.urlencode({"username":"s1","password":"student-pass","next":destination})
        headers={"Content-Type":"application/x-www-form-urlencoded","Origin":f"http://127.0.0.1:{self.server.server_port}"}
        conn.request("POST","/login",form,headers);response=conn.getresponse()
        self.assertEqual(response.getheader("Location"),destination);response.read()
        conn.request("POST","/login",urllib.parse.urlencode({"username":"s1","password":"student-pass","next":"https://bad.test/student/attendance"}),headers)
        response=conn.getresponse();self.assertEqual(response.getheader("Location"),"/");response.read();conn.close()

    def test_bad_grade_and_extension_rejected(self):
        a = self.assignment(self.course())
        self.assertEqual(self.request("/api/learning/submit", "s1", {"assignment_id": a, "request_id": "r1"}, ("run.exe", b"MZ"))[0], 400)
        sid = self.upload(a)[1]["id"]
        for score in ("nan", "inf", "11", "-1"):
            self.assertEqual(self.request("/api/learning/grade", form={"submission_id": sid, "score": score})[0], 400)

    def test_cross_origin_writes_rejected(self):
        self.assertEqual(self.request("/api/learning/course", form={"name": "Bad"}, origin="http://evil.example")[0], 403)

    def test_change_password_revokes_session(self):
        fields = {"current_password": "student-pass", "new_password": "new-password", "confirm_password": "new-password"}
        self.assertEqual(self.request("/api/student/change-password", "s1", fields)[0], 200)
        self.assertTrue(verify_password("new-password", storage.read_json("students.json")["s1"]["password_hash"]))
        self.assertEqual(self.request("/api/student/workspace", "s1")[0], 401)

    def test_gradebook_weights_privacy_and_required_scores(self):
        c = self.course(members="s1 s2")
        self.assertEqual(self.request("/api/learning/complete-course", form={"course_id": c})[0], 409)
        self.assertEqual(self.request("/api/learning/course-weights", form={"course_id": c, "attendance": "30"})[0], 400)
        self.create("course-weights", course_id=c, attendance="20", homework="0", midterm="0", final="80")
        self.create("grade-component", course_id=c, student_id="s1", component="final", score="8")
        own = self.request("/api/student/workspace", "s1")[1]["gradebooks"][0]
        self.assertEqual(len(own["items"]), 1)
        self.assertEqual(own["items"][0]["student_id"], "s1")
        self.assertEqual(own["items"][0]["total"], 8.4)
        self.create("grade-component", course_id=c, student_id="s1", component="final", score="")
        self.assertIsNone(self.request("/api/student/workspace", "s1")[1]["gradebooks"][0]["items"][0]["total"])

    def test_telemetry_uses_hashed_session_key(self):
        code, _ = self.request("/api/student/telemetry", "s1", {"visibility": "visible", "focused": "true", "tab_count": "2"})
        self.assertEqual(code, 200)
        self.assertEqual(len(storage.read_json("sessions.json")), 3)
        self.assertTrue(any(s.get("telemetry", {}).get("tab_count") == 2 for s in storage.read_json("sessions.json").values()))

    def test_notification_feed_and_read_receipts_are_personal(self):
        c = self.course()
        event = self.create("event", course_id=c, title="Course notice", starts_at=self.future, kind="announcement")
        storage.write_json("notifications.json", [
            {"id": "general", "message": "Everyone", "created_at": storage.utc_now()},
            {"id": "private", "message": "Only S1", "student_id": "s1", "created_at": storage.utc_now()},
            {"id": "other", "message": "Only S2", "student_id": "s2", "created_at": storage.utc_now()},
        ])
        code, result = self.request("/api/student/notifications", "s1")
        self.assertEqual(code, 200)
        self.assertEqual({r["id"] for r in result["notifications"]}, {"notice:general", "notice:private", "course:" + event})
        self.assertTrue(all(not r["read"] for r in result["notifications"]))
        self.assertEqual(self.request("/api/student/notifications/read", "s1", {"ids": "notice:other"})[0], 404)
        self.assertEqual(self.request("/api/student/notifications/read", "s1", {"ids": "notice:general"})[0], 200)
        own = self.request("/api/student/notifications", "s1")[1]["notifications"]
        self.assertTrue(next(r for r in own if r["id"] == "notice:general")["read"])
        self.assertTrue(all(not r["read"] for r in self.request("/api/student/notifications", "s2")[1]["notifications"]))
        self.assertEqual(self.request("/api/student/notifications/read", "s1", {"all": "true"})[0], 200)
        self.assertTrue(all(r["read"] for r in self.request("/api/student/workspace", "s1")[1]["notification_feed"]))
        self.assertEqual(self.request("/api/student/notifications", "admin")[0], 403)

    def test_admin_course_scope_keeps_full_monitor_details(self):
        c1 = self.course("s1")
        c2 = self.course("s2")
        storage.write_json("assignments.json", {"s1": {"course_id": c1, "exam_file": "one.txt", "status": "assigned"}, "s2": {"course_id": c2, "exam_file": "two.txt", "status": "assigned"}})
        storage.write_json("submissions.json", {"s1": [{"course_id": c1, "filename": "one.txt"}, {"filename": "legacy.txt"}], "s2": [{"course_id": c2, "filename": "two.txt"}]})
        code, result = self.request("/api/admin/monitor?course=" + c1)
        self.assertEqual(code, 200)
        self.assertEqual([r["student_id"] for r in result["students"]], ["s1"])
        row = result["students"][0]
        self.assertEqual(row["exam_file"], "one.txt")
        self.assertEqual(row["submission_count"], 1)
        for key in ("ip", "user_agent", "telemetry", "alerts", "remaining_seconds", "latest_submission"):
            self.assertIn(key, row)
        result = self.request("/api/admin/submissions?course=" + c1)[1]
        self.assertEqual([r["filename"] for r in result["submissions"]], ["one.txt"])
        self.assertEqual(self.request("/api/admin/monitor?course=missing")[0], 404)
        self.assertEqual(self.request("/api/admin/students/s2/force-submit?course="+c1, form={})[0], 403)
        self.assertEqual(self.request("/api/admin/workspace", "s1")[0], 403)

    def test_exam_monitor_isolates_code_roster_attempts_and_unique_ac_problems(self):
        course = self.course("s1,s2")
        fields = {"type": "programming", "course_id": course, "title": "Code monitor", "languages": "python",
                  "problems": json.dumps([{"title": name, "points": 10, "tests": [{"input": "", "output": "3"}]} for name in ("A", "B")])}
        first = self.request("/api/admin/exam-configurations/save", form=fields)[1]["id"]
        second = self.request("/api/admin/exam-configurations/save", form={**fields, "title": "Other code"})[1]["id"]
        for eid in (first, second):
            self.assertEqual(self.request("/api/admin/programming/participants", form={"exam_id": eid, "student_ids": "s1"})[0], 200)
        with patch.object(code_runner, "ready", return_value=True), patch.object(programming, "schedule"):
            for eid in (first, second):
                self.assertEqual(self.request("/api/admin/programming/control", form={"exam_id": eid, "action": "start"})[0], 200)
                self.assertEqual(self.request("/api/student/programming/start", "s1", {"exam_id": eid})[0], 200)
            for eid, index in ((first, 0), (first, 0), (first, 1), (second, 1)):
                code, response = self.request("/api/student/programming/submit", "s1", {"exam_id": eid, "problem_index": str(index), "language": "python"}, file=("answer.py", b"print(3)"))
                self.assertEqual(code, 200, response)
                submitted = programming.rows()
                submitted[-1]["state"] = "done"
                storage.write_json("programming_submissions.json", submitted)
        records = programming.rows()
        for row in records:
            ac = row["exam_id"] == second or row["problem_index"] == 0
            row.update(state="done", result={"verdict": "AC" if ac else "WA", "score": 10 if ac else 0, "tests": []})
        # A failed rejudge preserves the previous effective AC; duplicates count once.
        records[0]["grading_history"] = [{"result": records[0]["result"]}]
        records[0]["result"] = {"verdict": "SYSTEM_ERROR", "score": None, "tests": []}
        storage.write_json("programming_submissions.json", records)
        code, response = self.request("/api/admin/monitor?exam="+first+"&course="+course)
        self.assertEqual(code, 200, response)
        self.assertEqual(response["exam"]["id"], first)
        self.assertEqual([r["student_id"] for r in response["students"]], ["s1"])
        row = response["students"][0]
        self.assertEqual((row["accepted_problems"], row["total_problems"], row["submission_count"]), (1, 2, 3))
        self.assertFalse(row["can_force"])
        self.assertFalse(row["can_adjust"])
        self.assertEqual(row["ends_at"], storage.read_json("programming_attempts.json")[first+":s1"]["ends_at"])
        self.assertEqual(self.request("/api/admin/monitor?exam="+second)[1]["students"][0]["accepted_problems"], 1)
        archive = self.request("/api/admin/archive/list?exam="+first+"&student=s1")[1]
        self.assertEqual(archive["total"], 3, archive)
        self.assertTrue(all(r["activity_id"].startswith("code:"+first+":") for r in archive["rows"]))
        self.assertEqual(self.request("/api/admin/monitor?exam="+first, "s1")[0], 403)
        self.assertEqual(self.request("/api/admin/monitor?exam=missing")[0], 404)
        self.assertEqual(self.request("/api/admin/monitor?exam="+first+"&course="+self.course("s2"))[0], 403)
        original = storage.read_json("assignments.json")
        for action in ("force-submit", "adjust-time"):
            self.assertEqual(self.request("/api/admin/students/s1/"+action+"?exam="+first, form={"minutes": "5"})[0], 409)
        self.assertEqual(storage.read_json("assignments.json"), original)

    def test_exam_monitor_file_release_does_not_count_old_or_unrelated_submissions(self):
        course = self.course("s1,s2")
        settings = storage.read_json("settings.json")
        settings.update(exam_catalog_id="current", exam_state="started", exam_started_at=storage.utc_now(), exam_duration_minutes=10,
                        exam_course_id=course, exam_participants=["s1"], exam_release_id="current-release")
        storage.write_json("settings.json", settings)
        storage.write_json("assignments.json", {"s1": {"release_id": "current-release", "course_id": course, "exam_file": "current.txt", "status": "in_progress", "started_at": storage.utc_now(), "ends_at": self.future}})
        storage.write_json("submissions.json", {"s1": [{"release_id": "old-release", "filename": "old.zip"}, {"release_id": "current-release", "filename": "current.zip"}], "s2": [{"release_id": "current-release", "filename": "other.zip"}]})
        code, response = self.request("/api/admin/monitor?exam=current")
        self.assertEqual(code, 200, response)
        self.assertEqual(len(response["students"]), 1)
        self.assertEqual(response["students"][0]["submission_count"], 1)
        self.assertEqual(response["students"][0]["latest_submission"]["filename"], "current.zip")
        self.assertTrue(response["students"][0]["can_adjust"])
        self.assertEqual(response["exam"]["activity_id"], "file:current-release")
        settings.update(exam_release_id="new-release")
        storage.write_json("settings.json", settings)
        self.assertEqual(self.request("/api/admin/students/s1/force-submit?exam=current", form={})[0], 409)

    def test_exam_course_context_controls_distribution_and_submission(self):
        c1 = self.course("s1")
        c2 = self.course("s2")
        old = storage.read_json("settings.json")
        old.update({"exam_state": "ended", "exam_started_at": "2000-01-01T00:00:00+00:00"})
        storage.write_json("settings.json", old)
        self.assertEqual(self.request("/api/admin/exam-context", form={"course_id": c1, "title": "Midterm"})[0], 200)
        self.assertEqual(storage.read_json("settings.json")["exam_participants"], ["s1"])
        self.assertEqual(storage.read_json("settings.json")["exam_state"], "idle")
        self.assertIsNone(storage.read_json("settings.json")["exam_started_at"])
        exam_dir = Path(self.temp.name) / "exam-source"
        exam_dir.mkdir()
        (exam_dir / "task.txt").write_text("Exercise", encoding="utf-8")
        with patch.object(exams, "EXAM_DIR", exam_dir):
            code, _ = self.request("/api/admin/distribute", form={"mode": "selected", "exam_files": "task.txt"})
        self.assertEqual(code, 200)
        assigned = storage.read_json("assignments.json")
        self.assertEqual(set(assigned), {"s1"})
        self.assertEqual(assigned["s1"]["course_id"], c1)
        self.assertEqual(self.request("/api/admin/exam-context", form={"course_id": c2, "title": "Other"})[0], 409)
        self.assertEqual(self.request("/api/admin/start-exam", form={})[0], 200)
        self.assertEqual(self.request("/api/student/start", "s1", {})[0], 200)
        self.assertEqual(self.request("/api/student/start", "s2", {})[0], 400)
        settings = storage.read_json("settings.json")
        settings["accepted_submission_extensions"] = [".txt"]
        storage.write_json("settings.json", settings)
        self.assertEqual(self.request("/api/student/submit", "s1", {}, ("answer.txt", b"answer"))[0], 200)
        self.assertEqual(storage.read_json("submissions.json")["s1"][0]["course_id"], c1)
        self.assertEqual(self.request("/api/learning/complete-course", form={"course_id": c1})[0], 409)

    def test_exam_metadata_hidden_and_force_submit_enforced(self):
        settings = storage.read_json("settings.json")
        settings.update({"exam_release_id": "release", "exam_state": "started", "exam_released": True, "submission_policy": "configurable", "max_submissions": 3, "accepted_submission_extensions": [".txt"]})
        storage.write_json("settings.json", settings)
        assignment = {"release_id": "release", "status": "assigned", "exam_file": "secret.pdf"}
        storage.write_json("assignments.json", {"s1": assignment})
        exam = self.request("/api/student/workspace", "s1")[1]["exam"]
        self.assertTrue(exam["can_start"])
        self.assertIsNone(exam["exam_file"])
        assignment.update({"started_at": storage.utc_now(), "ends_at": self.future, "status": "in_progress"})
        storage.write_json("assignments.json", {"s1": assignment})
        self.assertEqual(self.request("/api/student/submit", "s1", {}, ("answer.txt", b"answer"))[0], 200)
        assignment.update({"forced_submit": True, "status": "submitted"})
        storage.write_json("assignments.json", {"s1": assignment})
        self.assertFalse(self.request("/api/student/workspace", "s1")[1]["exam"]["can_submit"])
        self.assertEqual(self.request("/api/student/submit", "s1", {}, ("answer.txt", b"answer"))[0], 400)

    def test_all_student_routes_render_without_exposing_password(self):
        for name in ("dashboard", "courses", "calendar", "attendance", "assignments", "exams", "history", "grades", "notifications", "profile"):
            code, html = self.request("/student/" + name, "s1")
            self.assertEqual(code, 200)
            self.assertIn(b"workspace-content", html)
            self.assertNotIn(b"password_hash", html)

    def test_courses_use_existing_admin_sidebar_and_legacy_redirect(self):
        for path in ("/admin/courses", "/admin?section=courses"):
            code, html = self.request(path)
            self.assertEqual(code, 200)
            text = html.decode("utf-8")
            self.assertIn('id="learning-content"', text)
            self.assertIn('href="/admin/courses"', text)
            self.assertIn("Khóa học", text)
            self.assertNotIn("Quản lý học tập", text)
            for section in ("monitor", "notifications", "exam", "accounts", "submissions", "server", "admins"):
                self.assertIn('/admin?section=' + section, text)
            self.assertEqual(text.count('<aside class="main-sidebar"'), 1)
        self.assertEqual(self.request("/admin/learning?course=old&tab=grades")[0], 303)
        self.assertEqual(self.request("/admin/courses", "s1")[0], 403)

    def test_demo_seed_preserves_existing_data_and_is_repeat_safe(self):
        from app.seed_demo import seed_demo
        original = copy.deepcopy(storage.read_json("students.json"))
        root = Path(self.temp.name)
        with patch.object(exams, "EXAM_DIR", root / "exam-sources"):
            result = seed_demo(root)
            self.assertEqual(result["status"], "created")
            self.assertTrue(result["exam_ready"])
            self.assertEqual(len(storage.read_json("students.json")), 22)
            for sid in original:
                self.assertEqual(storage.read_json("students.json")[sid], original[sid])
            self.assertTrue(verify_password("111111", storage.read_json("students.json")["DEMO001"]["password_hash"]))
            data = learning.load()
            self.assertEqual(len(data["courses"]), 3)
            self.assertEqual(len(data["assignments"]), 13)
            self.assertTrue(all((learning.FILES / r["stored_name"]).is_file() for r in data["materials"] + data["submissions"]))
            closed = next(c for c in data["courses"] if c["status"] == "completed")
            self.assertTrue(all(r["total"] is not None for r in learning.gradebook(data, closed, closed["student_ids"])["items"]))
            self.assertTrue((Path(result["backup"]) / "data" / "students.json").is_file())
            changed = storage.read_json("students.json")
            changed["DEMO001"]["password_hash"] = hash_password("changed-password")
            storage.write_json("students.json", changed)
            repeated = seed_demo(root)
            self.assertEqual(repeated["status"], "already-seeded")
            self.assertEqual(len(learning.load()["courses"]), 3)
            self.assertTrue(verify_password("changed-password", storage.read_json("students.json")["DEMO001"]["password_hash"]))

    def test_demo_seed_does_not_replace_an_active_exam(self):
        from app.seed_demo import seed_demo
        root = Path(self.temp.name)
        settings = storage.read_json("settings.json")
        settings.update({"exam_state": "started", "exam_released": True, "exam_release_id": "keep-release"})
        storage.write_json("settings.json", settings)
        assigned = {"s1": {"release_id": "keep-release", "exam_file": "keep.txt"}}
        storage.write_json("assignments.json", assigned)
        with patch.object(exams, "EXAM_DIR", root / "exam-sources"):
            result = seed_demo(root)
        self.assertFalse(result["exam_ready"])
        self.assertEqual(storage.read_json("settings.json"), settings)
        self.assertEqual(storage.read_json("assignments.json"), assigned)

    def test_reference_theme_does_not_apply_to_protected_pages(self):
        for section in ("monitor", "notifications"):
            code, html = self.request("/admin?section="+section)
            self.assertEqual(code, 200)
            self.assertNotIn(b"admin-design.css", html)
            self.assertNotIn(b"admin-design.js", html)
            self.assertNotIn(b"admin-redesign", html)
            self.assertIn(b"admin-sidebar.css", html)
            self.assertIn(b"admin-sidebar.js", html)
            self.assertIn(b"admin-sidebar-unified", html)
            self.assertIn("Không gian giảng dạy".encode(), html)
        self.assertIn(b"admin-design.css", self.request("/admin/courses")[1])

    @unittest.skipUnless(__import__('os').environ.get('CSS_JUDGE_TESTS') == '1', 'Requires Docker')
    def test_preflight_real_docker_reference_passes_sample_and_hidden_tests(self):
        import time
        exam_id,_=self.code_exam(self.course(),problems=json.dumps([{"title":"Sum","tests":[{"input":"1 2","output":"3","sample":True},{"input":"-4 9","output":"5","sample":False}]}]))
        report=self.request("/api/admin/exam-preflight?exam="+exam_id)[1]
        self.assertTrue(report["runner"]["ready"],report["runner"])
        code,job=self.request("/api/admin/exam-preflight/verify",form={"exam_id":exam_id,"fingerprint":report["fingerprint"],"problem_index":"0","language":"python","source":"import sys\nprint(sum(map(int,sys.stdin.read().split())))"})
        self.assertEqual(code,200,job)
        end=time.monotonic()+45
        while time.monotonic()<end:
            with exam_preflight._jobs_lock:
                state=exam_preflight._jobs[job["job_id"]]["state"]
            if state!="running":break
            time.sleep(.1)
        with exam_preflight._jobs_lock:
            result=copy.deepcopy(exam_preflight._jobs[job["job_id"]])
        self.assertEqual(result["state"],"done",result)
        self.assertEqual((result["result"]["verdict"],result["result"]["passed"]),("AC",2))
        self.assertTrue(self.request("/api/admin/exam-preflight?exam="+exam_id)[1]["can_open"])
        self.assertEqual(programming.rows(),[])

    def test_scheduled_code_blocks_early_entry_then_uses_planned_common_clock(self):
        begins=datetime.now(timezone.utc)+timedelta(minutes=5)
        exam_id,_=self.code_exam(self.course(),scheduled_at=begins.isoformat(),duration_minutes="10")
        with patch.object(code_runner,"ready",return_value=True):
            self.assertEqual(self.request("/api/admin/programming/control",form={"exam_id":exam_id,"action":"start"})[0],200)
        before=self.request("/api/student/workspace","s1")[1]["programming"]["exams"][0]
        self.assertEqual(before["state"],"scheduled")
        self.assertFalse(before["can_start"])
        self.assertEqual(before["problems"],[])
        self.assertEqual(self.request("/api/student/programming/start","s1",{"exam_id":exam_id})[0],409)
        self.assertEqual(storage.read_json("programming_attempts.json",{}),{})
        entered=begins+timedelta(minutes=1)
        with patch.object(exam_timing,"datetime",wraps=datetime) as clock,patch.object(programming,"datetime",wraps=datetime) as student_clock:
            clock.now.return_value=entered;student_clock.now.return_value=entered
            programming.start({"user_id":"s1","role":"student"},{"exam_id":exam_id},"127.0.0.1")
        attempt=storage.read_json("programming_attempts.json")[exam_id+":s1"]
        self.assertEqual(learning.date_value(attempt["ends_at"]),begins+timedelta(minutes=10))

    def test_code_timing_changes_waiting_and_running_update_existing_attempts(self):
        future=datetime.now(timezone.utc)+timedelta(hours=1)
        exam_id,_=self.code_exam(self.course(),scheduled_at=future.isoformat(),duration_minutes="10")
        with patch.object(code_runner,"ready",return_value=True):
            self.request("/api/admin/programming/control",form={"exam_id":exam_id,"action":"start"})
        begins=datetime.now(timezone.utc)-timedelta(minutes=1)
        form={"exam_id":exam_id,"scheduled_at":begins.isoformat(),"duration_minutes":"10"}
        self.assertEqual(self.request("/api/admin/exam-timing","s1",form)[0],403)
        self.assertEqual(self.request("/api/admin/exam-timing",form=form)[0],200)
        self.assertEqual(self.request("/api/student/programming/start","s1",{"exam_id":exam_id})[0],200)
        self.assertEqual(self.request("/api/admin/exam-timing",form={"exam_id":exam_id,"duration_minutes":"20"})[0],200)
        expected=begins+timedelta(minutes=20)
        self.assertEqual(learning.date_value(storage.read_json("programming_attempts.json")[exam_id+":s1"]["ends_at"]),expected)
        feed=self.request("/api/student/programming/submissions?exam="+exam_id+"&problem=0","s1")[1]
        self.assertEqual(learning.date_value(feed["ends_at"]),expected)
        self.assertEqual(self.request("/api/admin/exam-timing",form={"exam_id":exam_id,"scheduled_at":future.isoformat(),"duration_minutes":"20"})[0],409)
        self.assertEqual(self.request("/api/admin/exam-timing",form={"exam_id":exam_id,"duration_minutes":"0"})[0],400)
        end=datetime.now(timezone.utc)+timedelta(minutes=4)
        self.assertEqual(self.request("/api/admin/exam-timing",form={"exam_id":exam_id,"mode":"end","ends_at":end.isoformat()})[0],200)
        self.assertEqual(learning.date_value(programming.exam(exam_id)["ends_at"]),end)
        self.request("/api/admin/programming/control",form={"exam_id":exam_id,"action":"end"})
        self.assertEqual(self.request("/api/admin/exam-timing",form={"exam_id":exam_id,"duration_minutes":"30"})[0],409)

    def test_file_schedule_blocks_entry_and_timing_preserves_individual_extra_time(self):
        course=self.course()
        self.request("/api/admin/exam-context",form={"course_id":course,"title":"Scheduled file"})
        directory=Path(self.temp.name)/"timed-files";directory.mkdir();(directory/"task.txt").write_text("Question",encoding="utf-8")
        with patch.object(exams,"EXAM_DIR",directory):
            self.assertEqual(self.request("/api/admin/distribute",form={"mode":"selected","exam_files":"task.txt"})[0],200)
        future=datetime.now(timezone.utc)+timedelta(minutes=10)
        self.assertEqual(self.request("/api/admin/exam-timing",form={"exam_id":"current","scheduled_at":future.isoformat(),"duration_minutes":"10"})[0],200)
        self.assertEqual(self.request("/api/admin/start-exam",form={})[0],200)
        before=self.request("/api/student/workspace","s1")[1]["exam"]
        self.assertEqual(before["state"],"scheduled");self.assertFalse(before["can_start"])
        self.assertEqual(self.request("/api/student/start","s1",{})[0],400)
        begins=datetime.now(timezone.utc)-timedelta(minutes=1)
        self.assertEqual(self.request("/api/admin/exam-timing",form={"exam_id":"current","scheduled_at":begins.isoformat(),"duration_minutes":"10"})[0],200)
        self.assertEqual(self.request("/api/student/start","s1",{})[0],200)
        self.assertEqual(self.request("/api/admin/students/s1/adjust-time",form={"minutes":"5"})[0],200)
        self.assertEqual(self.request("/api/admin/exam-timing",form={"exam_id":"current","duration_minutes":"20"})[0],200)
        item=storage.read_json("assignments.json")["s1"]
        self.assertEqual(learning.date_value(item["ends_at"]),begins+timedelta(minutes=25))
        self.assertEqual(item["extra_time_seconds"],300)

    def finish_reference(self, exam_id, verdict="AC"):
        import time
        report = self.request("/api/admin/exam-preflight?exam="+exam_id)[1]
        result = {"verdict":verdict,"score":100 if verdict=="AC" else 0,"passed":1 if verdict=="AC" else 0,"total":1,"tests":[],"compile_log":""}
        with patch.object(code_runner,"judge",return_value=result):
            code, job = self.request("/api/admin/exam-preflight/verify",form={"exam_id":exam_id,"fingerprint":report["fingerprint"],"problem_index":"0","language":"python","source":"print(3)"})
            self.assertEqual(code,200,job)
            end=time.monotonic()+3
            while time.monotonic()<end:
                with exam_preflight._jobs_lock:
                    state=exam_preflight._jobs[job["job_id"]]["state"]
                if state!="running":break
                time.sleep(.01)
            self.assertEqual(state,"done")
        return self.request("/api/admin/exam-preflight?exam="+exam_id)[1]

    def test_preflight_reference_required_and_never_counts_as_student_work(self):
        exam_id,_=self.code_exam(self.course())
        ready={"ready":True,"detail":"Ready","image_id":"qa-image"}
        with patch.object(code_runner,"status",return_value=ready):
            report=self.request("/api/admin/exam-preflight?exam="+exam_id)[1]
            self.assertFalse(report["can_open"])
            form={"exam_id":exam_id,"type":"programming","fingerprint":report["fingerprint"]}
            self.assertEqual(self.request("/api/admin/exam-preflight?exam="+exam_id,"s1")[0],403)
            self.assertEqual(self.request("/api/admin/exam-preflight/open",form=form)[0],409)
            self.assertFalse(self.finish_reference(exam_id,"WA")["can_open"])
            self.assertEqual(self.request("/api/admin/exam-preflight/open",form=form)[0],409)
            report=self.finish_reference(exam_id)
            self.assertTrue(report["can_open"])
            self.assertEqual(programming.rows(),[])
            self.assertEqual(storage.read_json("programming_attempts.json",{}),{})
            self.assertEqual(self.request("/api/admin/exam-preflight/open",form=form)[0],200)
            self.assertEqual(programming.exam(exam_id)["state"],"started")
            self.assertEqual(self.request("/api/admin/exam-preflight/open",form=form)[0],409)

    def test_preflight_changed_config_roster_and_image_invalidate_confirmation(self):
        exam_id,_=self.code_exam(self.course())
        ready={"ready":True,"detail":"Ready","image_id":"qa-image"}
        with patch.object(code_runner,"status",return_value=ready):
            original=self.finish_reference(exam_id)
            ready["image_id"]="new-image"
            form={"exam_id":exam_id,"type":"programming","fingerprint":original["fingerprint"]}
            self.assertEqual(self.request("/api/admin/exam-preflight/open",form=form)[0],409)
            ready["image_id"]="qa-image"
            rows=storage.read_json("exam_catalog.json")
            next(e for e in rows if e["id"]==exam_id)["programming"]["problems"][0]["tests"][0]["output"]="4"
            storage.write_json("exam_catalog.json",rows)
            self.assertEqual(self.request("/api/admin/exam-preflight/open",form=form)[0],409)
            self.assertFalse(self.request("/api/admin/exam-preflight?exam="+exam_id)[1]["problems"][0]["verified"])
            students=storage.read_json("students.json");students["s1"]["active"]=False;storage.write_json("students.json",students)
            self.assertFalse(self.request("/api/admin/exam-preflight?exam="+exam_id)[1]["can_open"])

    def test_preflight_judge_runs_outside_learning_lock_and_limits_concurrency(self):
        import time
        exam_id,_=self.code_exam(self.course())
        entered,release=threading.Event(),threading.Event()
        def judge(*args,**kwargs):
            entered.set();release.wait(3)
            return {"verdict":"AC","score":100,"passed":1,"total":1,"tests":[],"compile_log":""}
        with patch.object(code_runner,"status",return_value={"ready":True,"detail":"Ready","image_id":"qa-image"}),patch.object(code_runner,"judge",side_effect=judge):
            report=self.request("/api/admin/exam-preflight?exam="+exam_id)[1]
            form={"exam_id":exam_id,"fingerprint":report["fingerprint"],"problem_index":"0","language":"python","source":"print(3)"}
            job=self.request("/api/admin/exam-preflight/verify",form=form)[1]
            try:
                self.assertTrue(entered.wait(1))
                self.assertTrue(learning.LOCK.acquire(blocking=False));learning.LOCK.release()
                self.assertEqual(self.request("/api/student/workspace","s1")[0],200)
                self.assertEqual(self.request("/api/admin/exam-preflight/verify",form=form)[0],429)
            finally:
                release.set()
                end=time.monotonic()+3
                while time.monotonic()<end and exam_preflight._jobs[job["job_id"]]["state"]=="running":time.sleep(.01)

    def test_preflight_file_reviews_assigned_roster_and_existing_files(self):
        course=self.course()
        self.assertEqual(self.request("/api/admin/exam-context",form={"course_id":course,"title":"File review"})[0],200)
        directory=Path(self.temp.name)/"review-files";directory.mkdir();(directory/"task.txt").write_text("Question",encoding="utf-8")
        with patch.object(exams,"EXAM_DIR",directory):
            self.assertFalse(self.request("/api/admin/exam-preflight?exam=current")[1]["can_open"])
            self.assertEqual(self.request("/api/admin/distribute",form={"mode":"selected","exam_files":"task.txt"})[0],200)
            report=self.request("/api/admin/exam-preflight?exam=current")[1]
            self.assertTrue(report["can_open"])
            self.assertEqual(report["participants"][0]["student_id"],"s1")
            (directory/"task.txt").write_text("Changed question",encoding="utf-8")
            self.assertEqual(self.request("/api/admin/exam-preflight/open",form={"exam_id":"current","type":"file","fingerprint":report["fingerprint"]})[0],409)
            report=self.request("/api/admin/exam-preflight?exam=current")[1]
            self.assertEqual(self.request("/api/admin/exam-preflight/open",form={"exam_id":"current","type":"file","fingerprint":report["fingerprint"]})[0],200)

    def enrollment_fixture(self, all_students=False):
        c = self.course("s1")
        old_task = self.assignment(c)
        lesson = self.create("event", course_id=c, title="Before joining", kind="lesson", starts_at=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat())
        attendance = self.create("attendance", course_id=c, event_id=lesson, expires_at=self.future)
        self.create("close-attendance", session_id=attendance)
        data = learning.load()
        course = learning.find(data, "courses", c)
        course.pop("enrollments", None)
        course.pop("enrollment_tracking_since", None)
        if all_students:
            course["student_ids"] = None
        learning.find(data, "assignments", old_task)["due_at"] = (datetime.now(timezone.utc)-timedelta(days=1)).isoformat()
        storage.write_json("learning.json", data)
        return c, old_task, attendance

    def test_enrollment_late_join_excludes_old_work_but_keeps_open_tasks_and_privacy(self):
        c, old, attendance = self.enrollment_fixture()
        open_task = self.assignment(c)
        self.create("course-members", course_id=c, student_ids="s1,s2")
        data = learning.load()
        course = learning.find(data, "courses", c)
        book = {r["student_id"]: r for r in learning.gradebook(data, course, ["s1", "s2"])["items"]}
        self.assertEqual((book["s1"]["attendance"], book["s1"]["homework"]), (9, 0))
        self.assertEqual((book["s2"]["attendance"], book["s2"]["homework"]), (10, None))
        self.assertEqual((book["s2"]["excluded_assignments"], book["s2"]["excluded_attendance"]), (1, 1))
        self.assertFalse(course["enrollments"]["s2"]["include_previous"])
        own = self.request("/api/student/workspace", "s2")[1]
        self.assertFalse(next(r for r in own["assignments"] if r["id"] == old)["grading_applicable"])
        self.assertTrue(next(r for r in own["assignments"] if r["id"] == open_task)["grading_applicable"])
        self.assertFalse(own["attendance"][0]["grading_applicable"])
        self.assertNotIn("excluded_student_ids", own["attendance"][0])
        self.assertNotIn("enrollments", own["courses"][0])
        self.assertNotIn("student_ids", own["courses"][0])
        self.assertEqual(own["courses"][0]["enrollment"], course["enrollments"]["s2"])
        admin = self.request("/api/learning")[1]
        self.assertEqual(admin["attendance"][0]["excluded_student_ids"], ["s2"])
        result = self.upload(open_task, "s2")[1]
        self.create("grade", submission_id=result["id"], score="8", feedback="Good")
        row = self.request("/api/student/workspace", "s2")[1]["gradebooks"][0]["items"][0]
        self.assertEqual(row["homework"], 8)
        self.create("grade-component", course_id=c, student_id="s2", component="attendance", score="7")
        self.assertEqual(self.request("/api/student/workspace", "s2")[1]["gradebooks"][0]["items"][0]["attendance"], 7)

    def test_enrollment_include_previous_and_rejoin_preserve_original_policy(self):
        c, old, attendance = self.enrollment_fixture()
        self.create("course-members", course_id=c, student_ids="s1,s2", include_previous="true")
        original = copy.deepcopy(learning.load()["courses"][0]["enrollments"])
        row = self.request("/api/student/workspace", "s2")[1]["gradebooks"][0]["items"][0]
        self.assertEqual((row["attendance"], row["homework"]), (9, 0))
        self.create("course-members", course_id=c, student_ids="s1")
        self.create("course-members", course_id=c, student_ids="s1,s2", include_previous="false")
        self.assertEqual(learning.load()["courses"][0]["enrollments"], original)
        before = copy.deepcopy(learning.load())
        self.assertEqual(self.request("/api/learning/course-members", form={"course_id":c,"student_ids":"s1,s2","include_previous":"bad"})[0], 400)
        self.assertEqual(learning.load(), before)

    def test_enrollment_baseline_preserves_legacy_and_tracks_future_automatic_members(self):
        c, old, attendance = self.enrollment_fixture(all_students=True)
        data = learning.load()
        before = learning.gradebook(data, data["courses"][0], ["s1", "s2"])["items"]
        self.assertEqual(learning.initialize_enrollments(), 1)
        self.assertEqual(learning.initialize_enrollments(), 0)
        data = learning.load()
        after = learning.gradebook(data, data["courses"][0], ["s1", "s2"])["items"]
        self.assertEqual(before, after)
        students = storage.read_json("students.json")
        students["s3"] = {"student_id":"s3","full_name":"New auto member","created_at":storage.utc_now(),"active":True}
        storage.write_json("students.json", students)
        s3 = learning.snapshot({"user_id":"s3","role":"student"})
        self.assertFalse(s3["assignments"][0]["grading_applicable"])
        self.assertEqual(s3["gradebooks"][0]["items"][0]["attendance"], 10)
        joined = s3["courses"][0]["enrollment"]
        self.create("course-members", course_id=c, student_ids="s1,s2,s3", include_previous="true")
        self.assertEqual(learning.load()["courses"][0]["enrollments"]["s3"], joined)

    def test_course_edit_and_membership_keep_accounts_and_readonly_rules(self):
        c = self.create("course", name="Empty", code="EMPTY", semester="2026", enrollment="selected")
        self.assertEqual(learning.load()["courses"][0]["student_ids"], [])
        self.create("course-members", course_id=c, student_ids="s1")
        self.create("course-update", course_id=c, name="Updated", code="UP", semester="2026", group="Group 1")
        self.assertEqual(learning.load()["courses"][0]["name"], "Updated")
        self.assertEqual(self.request("/api/learning/course-members", "s1", {"course_id": c, "student_ids": "s2"})[0], 403)
        self.assertEqual(self.request("/api/learning/course-members", form={"course_id": c, "student_ids": "missing"})[0], 400)
        self.create("course-members", course_id=c, student_ids="")
        self.assertIn("s1", storage.read_json("students.json"))
        self.create("complete-course", course_id=c)
        self.assertEqual(self.request("/api/learning/course-update", form={"course_id": c, "name": "No"})[0], 409)

    def test_course_package_roundtrip_excludes_personal_records_and_rolls_back(self):
        import base64
        c = self.course()
        a = self.assignment(c)
        self.upload(a)
        code, attached = self.request("/api/learning/assignment",form={"course_id":c,"title":"Attached task","due_at":self.future},file=("task.txt",b"Attached task content"))
        self.assertEqual(code,200,attached)
        code, result = self.request("/api/learning/material", form={"course_id": c, "title": "Notes"}, file=("notes.txt", b"Teaching content"))
        self.assertEqual(code, 200)
        code, package = self.request("/api/learning/export-course?course="+c)
        self.assertEqual(code, 200)
        self.assertNotIn("student_ids", package["course"])
        self.assertNotIn("submissions", package)
        self.assertNotIn("grades", package)
        self.assertEqual(self.request("/api/learning/export-course?course="+c,"s1")[0],403)
        code, imported = self.request("/api/learning/import-course", form={}, file=("course.json",json.dumps(package).encode()))
        self.assertEqual(code,200,imported)
        copied = learning.find(learning.load(),"courses",imported["id"])
        self.assertEqual(copied["student_ids"],[])
        self.assertNotEqual(copied["id"],c)
        copied_task = next(a for a in learning.load()["assignments"] if a["course_id"] == copied["id"] and a.get("original_filename") == "task.txt")
        self.assertEqual(self.request("/api/learning/files/assignments/"+copied_task["id"])[1],b"Attached task content")
        self.assertEqual(len(learning.load()["submissions"]),1)
        bad=copy.deepcopy(package)
        bad["materials"].append({"title":"Bad","filename":"program.exe","data_base64":base64.b64encode(b"MZ").decode()})
        before=learning.load()
        files=set(learning.FILES.iterdir())
        self.assertEqual(self.request("/api/learning/import-course",form={},file=("bad.json",json.dumps(bad).encode()))[0],400)
        self.assertEqual(learning.load(),before)
        self.assertEqual(set(learning.FILES.iterdir()),files)


if __name__ == "__main__":
    unittest.main()
