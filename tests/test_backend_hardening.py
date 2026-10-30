"""Regression checks for malformed requests, races and interrupted persistence."""
import copy
import hashlib
import http.client
import json
import os
import socket
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import test_learning as fixtures
from app import main, storage, learning, programming, exam_catalog, course_grades, code_runner, security, deadlines, maintenance
from app.runtime import data_lease, ThreadingHTTPServer


class BackendHardeningTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.LearningTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.request = self.fixture.request

    def test_bad_body_framing_is_rejected_before_read(self):
        headers = ["Content-Length: -1", "Content-Length: abc", "Content-Length: +1",
                   "Content-Length: 1,1", "Content-Length: 1\r\nContent-Length: 1",
                   "Transfer-Encoding: chunked", "Content-Length: 0\r\nTransfer-Encoding: chunked"]
        for value in headers:
            with self.subTest(header=value), socket.create_connection(("127.0.0.1", self.fixture.server.server_port),timeout=2) as connection:
                connection.sendall((f"POST /login HTTP/1.1\r\nHost: 127.0.0.1\r\n{value}\r\n\r\n").encode())
                response = http.client.HTTPResponse(connection)
                response.begin(); response.read()
                self.assertEqual(response.status, 400)
                self.assertEqual(response.getheader("Connection"), "close")

    def test_oversized_body_header_is_rejected_without_upload(self):
        with socket.create_connection(("127.0.0.1",self.fixture.server.server_port),timeout=2) as connection:
            connection.sendall(b"POST /login HTTP/1.1\r\nHost: localhost\r\nContent-Length: 999999999999999999999\r\n\r\n")
            response=http.client.HTTPResponse(connection);response.begin();response.read()
            self.assertEqual(response.status,413)

    def test_transaction_rolls_back_all_documents_and_audit_after_write_error(self):
        before = {name:storage.read_json(name) for name in ("students.json","settings.json")}
        audit_before = (storage.LOG_DIR / "audit.jsonl").read_bytes()
        original = storage.atomic_write
        failed = False
        def fail_once(path,value):
            nonlocal failed
            if path.name == "settings.json" and not failed:
                failed=True
                raise OSError("simulated disk error")
            return original(path,value)
        with patch.object(storage,"atomic_write",side_effect=fail_once):
            with self.assertRaises(OSError), storage.atomic_transaction():
                storage.write_json("students.json",{})
                storage.write_json("settings.json",{"partial":True})
                storage.audit("test.failure","teacher",None)
        self.assertEqual({name:storage.read_json(name) for name in before},before)
        self.assertEqual((storage.LOG_DIR / "audit.jsonl").read_bytes(),audit_before)
        self.assertFalse((storage.DATA_DIR / ".transaction.json").exists())

    def test_startup_recovers_prepared_transaction_but_keeps_committed_one(self):
        previous = storage.read_json("students.json")
        path = storage.DATA_DIR / ".transaction.json"
        journal={"state":"prepared","before":{"students.json":{"exists":True,"value":previous}},"audit_offset":(storage.LOG_DIR/"audit.jsonl").stat().st_size}
        storage.atomic_write(path,journal)
        storage.atomic_write(storage.DATA_DIR/"students.json",{})
        storage.initialize()
        self.assertEqual(storage.read_json("students.json"),previous)
        journal["state"]="committed"
        storage.atomic_write(path,journal)
        storage.atomic_write(storage.DATA_DIR/"students.json",{})
        storage.initialize()
        self.assertEqual(storage.read_json("students.json"),{})

    def test_nested_failure_aborts_outer_transaction(self):
        before=storage.read_json("settings.json")
        with self.assertRaises(RuntimeError),storage.atomic_transaction():
            storage.write_json("settings.json",{})
            try:
                with storage.atomic_transaction():
                    raise ValueError("nested")
            except ValueError:
                pass
        self.assertEqual(storage.read_json("settings.json"),before)

    def test_cached_documents_are_isolated_and_external_changes_detected(self):
        value=storage.read_json("students.json");value.clear()
        self.assertTrue(storage.read_json("students.json"))
        storage.atomic_write(storage.DATA_DIR/"students.json",{})
        self.assertEqual(storage.read_json("students.json"),{})

    def test_missing_document_does_not_mutate_default_state(self):
        (storage.DATA_DIR/"sessions.json").unlink()
        document=storage.read_json("sessions.json");document["unexpected"]={}
        self.assertEqual(storage.read_json("sessions.json"),{})

    def test_account_status_separates_disabled_and_temporary_lock(self):
        for _ in range(3):security.record_login_failure("s1")
        form={"active":"false"}
        for _ in range(2):
            code,result=self.request("/api/admin/accounts/s1/toggle",form=form)
            self.assertEqual(code,200,result);self.assertFalse(result["active"])
        code,result=self.request("/api/admin/accounts")
        row=next(s for s in result["students"] if s["student_id"]=="s1")
        self.assertFalse(row["active"]);self.assertTrue(row["login_locked"])
        self.assertGreater(row["login_retry_after_seconds"],0)
        self.assertNotIn("password_hash",row)
        self.assertEqual(self.request("/api/admin/accounts/s1/unlock-login",form={})[0],200)
        row=next(s for s in self.request("/api/admin/accounts")[1]["students"] if s["student_id"]=="s1")
        self.assertFalse(row["active"]);self.assertFalse(row["login_locked"])

    def test_login_cannot_restore_password_reset_or_locked_account(self):
        for action in ("reset-password","toggle"):
            with self.subTest(action=action):
                students=storage.read_json("students.json")
                students["s1"].update(active=True,password_hash=security.hash_password("student-pass"))
                storage.write_json("students.json",students)
                entered,release=threading.Event(),threading.Event()
                original=main.verify_password
                def paused(password,encoded):
                    result=original(password,encoded)
                    if password=="student-pass":
                        entered.set()
                        self.assertTrue(release.wait(5))
                    return result
                with patch.object(main,"verify_password",side_effect=paused),ThreadPoolExecutor(max_workers=1) as pool:
                    future=pool.submit(self.request,"/login","s1",{"username":"s1","password":"student-pass"})
                    try:
                        self.assertTrue(entered.wait(3))
                        code,result=self.request(f"/api/admin/accounts/s1/{action}",form={"new_password":"new-student-pass"})
                        self.assertEqual(code,200,result)
                    finally:
                        release.set()
                    self.assertEqual(future.result(timeout=3)[0],401)
                current=storage.read_json("students.json")["s1"]
                if action=="reset-password":
                    self.assertTrue(security.verify_password("new-student-pass",current["password_hash"]))
                else:
                    self.assertFalse(current["active"])
                self.assertFalse(any(row["user_id"]=="s1" for row in storage.read_json("sessions.json").values()))

    def test_historic_file_exam_cannot_change_participants_or_marks(self):
        course=self.fixture.course("s1,s2")
        stored={"id":"historic-file","type":"file","course_id":course,"title":"Historic","state":"ended","duration_minutes":60,"participants":["s1"],"assessment_type":"midterm","file_settings":{},"created_at":storage.utc_now()}
        storage.write_json("exam_catalog.json",[stored])
        before=course_grades.exam_marks(course,["s2"])
        code,result=self.request("/api/admin/exam-configurations/save",form={"id":"historic-file","type":"file","course_id":course,"title":"Changed","assessment_type":"midterm"})
        self.assertEqual(code,409,result)
        self.assertEqual(storage.read_json("exam_catalog.json"),[stored])
        self.assertEqual(course_grades.exam_marks(course,["s2"]),before)

    def file_exam(self):
        course=self.fixture.course()
        settings=storage.read_json("settings.json")
        settings.update({"exam_state":"distributed","exam_release_id":"hardening-release","exam_course_id":course,"exam_participants":["s1"],"exam_assessment_type":"midterm","accepted_submission_extensions":[".txt"]})
        storage.write_json("settings.json",settings)
        storage.write_json("assignments.json",{"s1":{"exam_file":"paper.txt","release_id":"hardening-release","status":"assigned","course_id":course,"assessment_type":"midterm"}})
        main.start_exam_session()
        self.assertEqual(self.request("/api/student/start","s1",{})[0],200)
        return course

    def test_file_submission_failure_leaves_no_receipt_payload_or_quota(self):
        self.file_exam()
        before=storage.read_json("assignments.json")
        original=storage.atomic_write
        failed=False
        def fail_once(path,value):
            nonlocal failed
            if path.name=="assignments.json" and not failed:
                failed=True
                raise OSError("simulated failed assignment commit")
            return original(path,value)
        with patch.object(storage,"atomic_write",side_effect=fail_once),patch.object(main.traceback,"print_exc"):
            code,result=self.request("/api/student/submit","s1",{"request_id":"failed-submit"},file=("answer.txt",b"answer"))
        self.assertEqual(code,500,result)
        self.assertEqual(storage.read_json("submissions.json"),{})
        self.assertEqual(storage.read_json("assignments.json"),before)
        self.assertEqual(list(main.UPLOAD_DIR.iterdir()),[])
        self.assertFalse(storage.read_json("submission_rate.json",{}).get("s1"))

    def test_file_retry_recovers_receipt_after_end_without_new_attempt(self):
        self.file_exam()
        first=self.request("/api/student/submit","s1",{"request_id":"same-file"},file=("answer.txt",b"answer"))
        self.assertEqual(first[0],200,first)
        self.assertEqual(self.request("/api/admin/end-exam",form={})[0],200)
        second=self.request("/api/student/submit","s1",{"request_id":"same-file"},file=("answer.txt",b"answer"))
        self.assertEqual(second,first)
        self.assertEqual(len(storage.read_json("submissions.json")["s1"]),1)
        self.assertEqual(len(storage.read_json("submission_rate.json")["s1"]),1)
        self.assertEqual(self.request("/api/student/submit","s1",{"request_id":"same-file"},file=("answer.txt",b"changed"))[0],409)

    def test_manual_exam_end_preserves_release_for_grades_and_history(self):
        course=self.file_exam()
        self.request("/api/student/submit","s1",{"request_id":"graded-file"},file=("answer.txt",b"answer"))
        records=storage.read_json("submissions.json");records["s1"][0]["score"]=8
        storage.write_json("submissions.json",records)
        before=course_grades.exam_marks(course,["s1"])
        self.assertEqual(self.request("/api/admin/end-exam",form={})[0],200)
        self.assertEqual(storage.read_json("settings.json")["exam_release_id"],"hardening-release")
        self.assertEqual(course_grades.exam_marks(course,["s1"]),before)
        self.assertEqual(len(self.request("/api/student/workspace","s1")[1]["exam_submissions"]),1)

    def test_latest_file_mark_wins_when_legacy_timestamps_tie(self):
        course=self.file_exam()
        common={"exam_id":"current","release_id":"hardening-release","submitted_at":"2026-01-01T00:00:00+00:00"}
        storage.write_json("submissions.json",{"s1":[{**common,"score":3},{**common,"score":9}]})
        self.assertEqual(course_grades.exam_marks(course,["s1"])["s1"][0]["score"],9)

    def programming_exam(self):
        course=self.fixture.course()
        code,result=self.request("/api/admin/exam-configurations/save",form={"type":"programming","course_id":course,"title":"Retry","languages":"python","problems":json.dumps([{"title":"Sum","tests":[{"input":"","output":"3","sample":True}]}])})
        self.assertEqual(code,200,result)
        exam_id=result["id"]
        self.assertEqual(self.request("/api/admin/programming/control",form={"exam_id":exam_id,"action":"start"})[0],200)
        self.assertEqual(self.request("/api/student/programming/start","s1",{"exam_id":exam_id})[0],200)
        return exam_id

    def test_concurrent_code_retry_only_saves_and_schedules_once(self):
        with patch.object(code_runner,"ready",return_value=True),patch.object(programming,"schedule") as schedule:
            exam_id=self.programming_exam()
            form={"exam_id":exam_id,"problem_index":"0","language":"python","request_id":"same-code"}
            with ThreadPoolExecutor(max_workers=2) as pool:
                replies=list(pool.map(lambda _:self.request("/api/student/programming/submit","s1",form,file=("answer.py",b"print(3)")),range(2)))
            self.assertTrue(all(reply[0]==200 for reply in replies),replies)
            self.assertEqual(replies[0][1]["submission"]["id"],replies[1][1]["submission"]["id"])
            self.assertEqual(len(programming.rows()),1)
            self.assertEqual(schedule.call_count,1)
            self.assertEqual(len(storage.read_json("submission_rate.json")["s1"]),1)
            self.assertEqual(self.request("/api/student/programming/submit","s1",form,file=("answer.py",b"print(4)"))[0],409)

    def test_code_commit_failure_cleans_source_and_does_not_schedule(self):
        with patch.object(code_runner,"ready",return_value=True),patch.object(programming,"schedule") as schedule:
            exam_id=self.programming_exam()
            original=storage.atomic_write
            failed=False
            def fail_once(path,value):
                nonlocal failed
                if path.name=="programming_submissions.json" and not failed:
                    failed=True
                    raise OSError("simulated code commit failure")
                return original(path,value)
            with patch.object(storage,"atomic_write",side_effect=fail_once),patch.object(main.traceback,"print_exc"):
                code,result=self.request("/api/student/programming/submit","s1",{"exam_id":exam_id,"language":"python","problem_index":"0","request_id":"failed-code"},file=("answer.py",b"print(3)"))
            self.assertEqual(code,500,result)
            self.assertEqual(programming.rows(),[])
            self.assertEqual(list(programming.FILES.iterdir()),[])
            schedule.assert_not_called()

    def test_session_polling_does_not_rewrite_session_for_each_request(self):
        req=type("Request",(),{"cookies":{"css_session":self.fixture.tokens["s1"]}})()
        with patch.object(security,"write_json",wraps=security.write_json) as writes:
            for _ in range(20):
                self.assertIsNotNone(security.get_session(req))
            writes.assert_not_called()
        sessions=storage.read_json("sessions.json")
        for row in sessions.values():row["last_seen"]="2000-01-01T00:00:00+00:00"
        storage.write_json("sessions.json",sessions)
        with patch.object(security,"write_json",wraps=security.write_json) as writes:
            security.get_session(req)
            self.assertEqual(writes.call_count,1)

    def test_login_length_and_source_quota_are_bounded(self):
        self.assertEqual(self.request("/login","s1",{"username":"x"*81,"password":"bad"})[0],400)
        now=time.time()
        storage.write_json("auth_throttle.json",{"127.0.0.1":[now]*120})
        self.assertEqual(self.request("/login","s1",{"username":"s1","password":"student-pass"})[0],429)
        self.assertEqual(len(storage.read_json("sessions.json")),3)

    def test_login_attempts_expire_and_do_not_grow_without_bound(self):
        storage.write_json("login_attempts.json",{f"old-{i}":{"failures":1,"window_start":time.time()-10000} for i in range(100)})
        security.record_login_failure("new")
        self.assertEqual(list(storage.read_json("login_attempts.json")),["new"])

    def test_deadline_refresh_coalesces_but_notices_configuration_changes(self):
        deadlines._last_refresh=None
        with patch.object(deadlines,"refresh",wraps=deadlines.refresh) as refresh:
            deadlines.maybe_refresh();deadlines.maybe_refresh()
            self.assertEqual(refresh.call_count,1)
            settings=storage.read_json("settings.json");settings["audit_test"]=True;storage.write_json("settings.json",settings)
            deadlines.maybe_refresh()
            self.assertEqual(refresh.call_count,2)

    def test_second_server_lease_is_rejected_and_released_after_exit(self):
        with data_lease(storage.DATA_DIR):
            with self.assertRaises(RuntimeError),data_lease(storage.DATA_DIR):
                pass
        with data_lease(storage.DATA_DIR):
            pass

    def test_rejected_lease_does_not_recreate_data_directory_during_maintenance(self):
        moved=storage.DATA_DIR.parent/"data-moved"
        with data_lease(storage.DATA_DIR):
            storage.DATA_DIR.rename(moved)
            try:
                with self.assertRaises(RuntimeError),data_lease(storage.DATA_DIR):pass
                self.assertFalse(storage.DATA_DIR.exists())
            finally:
                moved.rename(storage.DATA_DIR)

    def test_excess_connections_are_rejected_and_capacity_recovers(self):
        server=ThreadingHTTPServer(("127.0.0.1",0),main.Handler,max_workers=1)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        connection=socket.create_connection(server.server_address,timeout=2)
        try:
            deadline=time.monotonic()+2
            while server._slots.acquire(blocking=False):
                server._slots.release()
                if time.monotonic()>deadline:self.fail("First connection was not accepted")
                time.sleep(.01)
            extra=http.client.HTTPConnection(*server.server_address,timeout=2)
            extra.request("GET","/health");response=extra.getresponse();response.read()
            self.assertEqual(response.status,503);extra.close()
            connection.close()
            deadline=time.monotonic()+2
            while not server._slots.acquire(blocking=False):
                if time.monotonic()>deadline:self.fail("Capacity was not released")
                time.sleep(.01)
            server._slots.release()
        finally:
            connection.close();server.shutdown();server.server_close();thread.join(timeout=2)

    def test_backup_verify_and_restore_to_separate_root(self):
        course=self.fixture.course()
        task=self.fixture.create("assignment",course_id=course,title="Backup task",due_at=self.fixture.future)
        self.assertEqual(self.request("/api/learning/submit","s1",{"assignment_id":task,"request_id":"backup-example"},file=("answer.txt",b"kept answer"))[0],200)
        root=Path(self.fixture.temp.name)
        with patch.object(maintenance,"EXAM_DIR",root/"papers"):
            backup=maintenance.snapshot(root/"backups")
            again=maintenance.snapshot(root/"backups")
            self.assertTrue(backup.name.startswith("manual-"))
            self.assertTrue(again.name.startswith("manual-"))
            self.assertNotEqual(backup,again)
            self.assertTrue(maintenance.verify(again)["files"])
            manifest=maintenance.verify(backup)
            self.assertTrue(manifest["files"])
            restored=maintenance.restore_copy(backup,root/"restored")
            self.assertEqual(json.loads((restored/"data"/"students.json").read_text()),storage.read_json("students.json"))
            self.assertEqual(json.loads((restored/"data"/"sessions.json").read_text()),{})
            stored=learning.load()["submissions"][0]["stored_name"]
            self.assertEqual((restored/"learning-files"/stored).read_bytes(),b"kept answer")
            with self.assertRaises(ValueError):maintenance.restore_copy(backup,restored)
            (backup/"learning-files"/stored).write_bytes(b"corrupt")
            with self.assertRaises(ValueError):maintenance.verify(backup)

    def test_backup_rejects_dangling_payload_reference(self):
        data=learning.load()
        data["materials"].append({"id":"missing","stored_name":"missing.txt"})
        storage.write_json("learning.json",data)
        root=Path(self.fixture.temp.name)
        with patch.object(maintenance,"EXAM_DIR",root/"papers"),self.assertRaises(ValueError):
            maintenance.snapshot(root/"backups")

    def test_judge_budget_rejects_configuration_before_start(self):
        course=self.fixture.course()
        form={"type":"programming","course_id":course,"title":"Over budget","languages":"python",
              "problems":json.dumps([{"title":"Long","time_limit_ms":30000,"tests":[{"input":"","output":""}]*100}])}
        code,result=self.request("/api/admin/exam-configurations/save",form=form)
        self.assertEqual(code,400,result)
        old={"id":"old-budget","type":"programming","course_id":course,"title":"Old","state":"idle","participants":["s1"],"duration_minutes":60,"programming":{"languages":["python"],"problems":json.loads(form["problems"])}}
        storage.write_json("exam_catalog.json",[old])
        with patch.object(code_runner,"ready",return_value=True):
            code,result=self.request("/api/admin/programming/control",form={"exam_id":"old-budget","action":"start"})
        self.assertEqual(code,400,result)

    def test_invalid_tls_does_not_start_grading_and_closes_listener(self):
        missing=str(Path(self.fixture.temp.name)/"missing.pem")
        with patch.dict(os.environ,{"CSS_TLS_CERT":missing,"CSS_TLS_KEY":missing}),patch.object(main,"initialize"),patch.object(main,"ThreadingHTTPServer") as server,patch.object(programming,"resume") as resume,patch.object(programming,"shutdown") as shutdown,patch("builtins.print"):
            with self.assertRaises(FileNotFoundError):main._serve()
        resume.assert_not_called()
        shutdown.assert_called_once()
        server.return_value.server_close.assert_called_once()
