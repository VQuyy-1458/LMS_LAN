"""Request I/O isolation checks using disposable classroom storage."""
import hashlib
import http.client
import socket
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import test_learning as fixtures
from app import learning, main, storage


class RequestIsolationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.LearningTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.request = self.fixture.request

    def connection(self, *, role="admin", origin=None, length=100):
        connection = socket.create_connection(("127.0.0.1", self.fixture.server.server_port), timeout=3)
        self.addCleanup(connection.close)
        host = f"127.0.0.1:{self.fixture.server.server_port}"
        headers = ["POST /api/admin/notifications HTTP/1.1", f"Host: {host}",
                   f"Origin: {origin or 'http://' + host}",
                   "Content-Type: application/x-www-form-urlencoded", f"Content-Length: {length}"]
        if role:
            headers.append(f"Cookie: css_session={self.fixture.tokens[role]}")
        connection.sendall(("\r\n".join(headers) + "\r\n\r\n").encode())
        return connection

    def response(self, connection):
        response = http.client.HTTPResponse(connection)
        response.begin()
        response.read()
        return response

    def test_unauthenticated_admin_rejected_before_body(self):
        response = self.response(self.connection(role=None))
        self.assertEqual(response.status, 401)
        self.assertEqual(response.getheader("Connection"), "close")
        self.assertEqual(storage.read_json("notifications.json"), [])

    def test_student_admin_request_rejected_before_body(self):
        self.assertEqual(self.response(self.connection(role="s1")).status, 403)

    def test_cross_origin_rejected_before_body(self):
        self.assertEqual(self.response(self.connection(origin="http://other.invalid")).status, 403)

    def test_early_rejection_response_survives_body_arriving_after_headers(self):
        payload=b"message=rejected"
        for _ in range(12):
            connection=self.connection(origin="http://other.invalid",length=len(payload))
            try:
                # http.client sends headers and body separately as well.
                connection.sendall(payload)
                self.assertEqual(self.response(connection).status,403)
            finally:
                connection.close()

    def test_slow_authenticated_upload_does_not_block_student_flows(self):
        course = self.fixture.course()
        task = self.fixture.create("assignment", course_id=course, title="Task", due_at=self.fixture.future)
        entered = threading.Event()
        original = main.Handler._read_body

        def observed(handler, length):
            entered.set()
            return original(handler, length)

        payload = b"message=completed-upload"
        with patch.object(main.Handler, "_read_body", observed):
            connection = self.connection(length=len(payload))
            try:
                connection.sendall(payload[:1])
                self.assertTrue(entered.wait(2))
                acquired = learning.LOCK.acquire(timeout=.3)
                if acquired:
                    learning.LOCK.release()
                self.assertTrue(acquired, "Reading a request body must not hold the learning lock")
                self.assertEqual(self.request("/login", "s2", {"username":"s2", "password":"student-pass"})[0], 303)
                self.assertEqual(self.request("/api/student/workspace", "s1")[0], 200)
                code, result = self.request("/api/learning/submit", "s1", {
                    "assignment_id":task, "request_id":"during-slow-upload"}, file=("answer.txt", b"student answer"))
                self.assertEqual(code, 200, result)
                self.assertEqual(storage.read_json("notifications.json"), [])
                connection.sendall(payload[1:])
                self.assertEqual(self.response(connection).status, 200)
            finally:
                connection.close()
        self.assertEqual(storage.read_json("notifications.json")[0]["message"], "completed-upload")

    def test_idle_upload_expires_without_mutation(self):
        with patch.object(main.Handler, "timeout", .15), patch.object(main, "REQUEST_BODY_TIMEOUT_SECONDS", 5):
            connection = self.connection()
            connection.sendall(b"m")
            response = self.response(connection)
        self.assertEqual(response.status, 408)
        self.assertEqual(response.getheader("Connection"), "close")
        self.assertEqual(storage.read_json("notifications.json"), [])

    def test_file_exam_download_and_submit_during_slow_admin_upload(self):
        course = self.fixture.course()
        root = Path(self.fixture.temp.name) / "papers"
        root.mkdir()
        paper = b"Solve the example problem."
        (root / "paper.txt").write_bytes(paper)
        settings = storage.read_json("settings.json")
        settings.update({"exam_state":"distributed", "exam_release_id":"request-test", "exam_course_id":course,
                         "exam_participants":["s1"], "accepted_submission_extensions":[".txt"]})
        storage.write_json("settings.json", settings)
        storage.write_json("assignments.json", {"s1":{"exam_file":"paper.txt", "release_id":"request-test",
                                                      "course_id":course, "status":"assigned"}})
        main.start_exam_session()
        self.assertEqual(self.request("/api/student/start", "s1", {})[0], 200)
        entered = threading.Event()
        original = main.Handler._read_body

        def observed(handler, length):
            entered.set()
            return original(handler, length)

        payload = b"message=file-exam-check"
        with patch.object(main, "EXAM_DIR", root), patch.object(main.Handler, "_read_body", observed):
            connection = self.connection(length=len(payload))
            try:
                connection.sendall(payload[:1])
                self.assertTrue(entered.wait(2))
                self.assertEqual(self.request("/api/student/exam", "s1"), (200, paper))
                code, result = self.request("/api/student/submit", "s1", {}, file=("answer.txt", b"my answer"))
                self.assertEqual(code, 200, result)
                connection.sendall(payload[1:])
                self.assertEqual(self.response(connection).status, 200)
            finally:
                connection.close()

    def test_continuous_trickle_cannot_extend_total_deadline(self):
        stop = threading.Event()
        with patch.object(main.Handler, "timeout", .3), patch.object(main, "REQUEST_BODY_TIMEOUT_SECONDS", .5):
            connection = self.connection(length=1000)

            def trickle():
                try:
                    while not stop.is_set():
                        connection.sendall(b"x")
                        stop.wait(.04)
                except OSError:
                    pass

            sender = threading.Thread(target=trickle, daemon=True)
            started = time.monotonic()
            sender.start()
            try:
                response = self.response(connection)
            finally:
                stop.set()
                sender.join(timeout=2)
        self.assertEqual(response.status, 408)
        self.assertLess(time.monotonic() - started, 2)
        self.assertEqual(storage.read_json("notifications.json"), [])

    def test_truncated_upload_rejected_without_mutation(self):
        connection = self.connection(length=100)
        connection.sendall(b"message=incomplete")
        connection.shutdown(socket.SHUT_WR)
        response = self.response(connection)
        self.assertEqual(response.status, 400)
        self.assertEqual(response.getheader("Connection"), "close")
        self.assertEqual(storage.read_json("notifications.json"), [])

    def test_revoked_session_is_checked_again_after_upload(self):
        entered = threading.Event()
        original = main.Handler._read_body

        def observed(handler, length):
            entered.set()
            return original(handler, length)

        payload = b"message=revoked"
        with patch.object(main.Handler, "_read_body", observed):
            connection = self.connection(length=len(payload))
            try:
                connection.sendall(payload[:1])
                self.assertTrue(entered.wait(2))
                main.logout_session(self.fixture.tokens["admin"])
                connection.sendall(payload[1:])
                self.assertEqual(self.response(connection).status, 401)
            finally:
                connection.close()
        self.assertEqual(storage.read_json("notifications.json"), [])

    def test_slow_response_does_not_hold_learning_lock(self):
        entered, release = threading.Event(), threading.Event()
        original = main.Handler._send

        def slow_send(handler, *args, **kwargs):
            if handler.path == "/api/admin/notifications" and not getattr(handler, "_defer_response", False):
                entered.set()
                if not release.wait(3):
                    raise RuntimeError("Response test was not released")
            return original(handler, *args, **kwargs)

        with patch.object(main.Handler, "_send", slow_send), ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.request, "/api/admin/notifications", "admin", {"message":"slow-response"})
            try:
                self.assertTrue(entered.wait(2))
                self.assertEqual(self.request("/api/student/workspace", "s1")[0], 200)
            finally:
                release.set()
            self.assertEqual(future.result(timeout=3)[0], 200)

    def test_multipart_larger_than_read_chunk_preserves_file(self):
        course = self.fixture.course()
        task = self.fixture.create("assignment", course_id=course, title="Task", due_at=self.fixture.future)
        contents = b"example answer\n" * 20000
        code, result = self.request("/api/learning/submit", "s1", {
            "assignment_id":task, "request_id":"multiple-read-chunks"}, file=("answer.txt", contents))
        self.assertEqual(code, 200, result)
        saved = next(row for row in learning.load()["submissions"] if row["id"] == result["id"])
        self.assertEqual(saved["sha256"], hashlib.sha256(contents).hexdigest())
