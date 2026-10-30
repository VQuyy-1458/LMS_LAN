"""Classroom Submission Server built on Python's standard-library HTTP server.
Jinja2 is used only to render the existing HTML templates; no FastAPI, Pydantic,
Uvicorn, Starlette, or multipart package is required.
"""
from __future__ import annotations
import hashlib
import html
import ipaddress
import json
import mimetypes
import os
import secrets
import shutil
import socket
import ssl
import threading
import time
import traceback
import urllib.parse
import zipfile
from datetime import datetime, timezone, timedelta
from email.parser import BytesParser
from email.policy import default
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from .runtime import ThreadingHTTPServer, data_lease
from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader, select_autoescape
from .config import BASE_DIR, DATA_DIR, LOG_DIR, EXAM_DIR, UPLOAD_DIR, STATIC_DIR, TEMPLATE_DIR, HOST, PORT, SESSION_COOKIE, MAX_REQUEST_SIZE
from .config import REQUEST_IDLE_TIMEOUT_SECONDS, REQUEST_BODY_TIMEOUT_SECONDS
from .accounts import parse_accounts
from .http import inline_filename_header
from .storage import initialize, read_json, write_json, audit, utc_now, transaction, atomic_transaction
from .security import hash_password, verify_password, new_session, get_session, require_user, client_ip, login_allowed, record_login_failure, clear_login_failures, logout_session, revoke_student_sessions, check_origin, SecurityError, check_login_source
from .exams import list_exam_files, distribute_exams, start_exam, start_exam_session, remaining_seconds
from .submissions import accept_submission
from . import learning
from . import notifications as student_notifications
from . import admin_workspace, exam_catalog, programming, submission_rate, code_runner
from . import course_packages
from . import submission_archive, deadlines, exam_preflight, exam_timing
from .security import login_state

TEMPLATES = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=select_autoescape(["html", "xml"]))


def attendance_return(value):
    """Preserve a scanned attendance link through login; never redirect externally."""
    try:
        parsed=urllib.parse.urlsplit(value or "")
        if parsed.scheme or parsed.netloc or parsed.path!="/student/attendance": return ""
        params=urllib.parse.parse_qs(parsed.query)
        query={k:v[0] for k,v in params.items() if k in {"session","code","course"} and len(v)==1 and len(v[0])<=100}
        return "/student/attendance"+("?"+urllib.parse.urlencode(query) if query else "")
    except ValueError: return ""

class RequestData:
    def __init__(self, handler, form=None, files=None):
        self.headers = handler.headers
        self.cookies = handler.cookies
        self.client = SimpleNamespace(host=handler.client_address[0])
        self.form = form or {}
        self.files = files or {}
        self.path = urllib.parse.urlsplit(handler.path).path
        self.query = urllib.parse.parse_qs(urllib.parse.urlsplit(handler.path).query)
        self.method = handler.command
        self.scheme = "https" if os.getenv("CSS_TLS_CERT") and os.getenv("CSS_TLS_KEY") else "http"

class ClientError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail); self.status=status; self.detail=detail


def current_exam_for(student_id: str):
    return read_json("assignments.json").get(student_id)

def student_exam_snapshot(student_id):
    settings=read_json("settings.json"); item=current_exam_for(student_id)
    current=bool(item and item.get("release_id")==settings.get("exam_release_id"))
    active=current and settings.get("exam_state")=="started" and settings.get("exam_released")
    waiting = exam_timing.waiting(settings.get("exam_state"), settings.get("exam_started_at"))
    active = active and not waiting
    started=bool(current and item.get("started_at"))
    remaining=remaining_seconds(item) if started else None
    common_end=deadlines.exam_end(settings.get("exam_started_at"),settings.get("exam_duration_minutes"),settings.get("exam_ends_at")) if settings.get("exam_state") in {"started","ended"} else None
    active=active and (started or not common_end or common_end>datetime.now(timezone.utc))
    records=[r for r in read_json("submissions.json").get(student_id,[]) if current and r.get("release_id")==item.get("release_id")]
    limit=1 if settings.get("submission_policy")=="once" else int(settings.get("max_submissions",1))
    forced=bool(current and item.get("forced_submit"))
    return {"state":"scheduled" if waiting else settings.get("exam_state","idle"),"common_starts_at":settings.get("exam_started_at"),"assigned":current,"started":started,"status":item.get("status") if current else "not_assigned","exam_file":item.get("exam_file") if started else None,"started_at":item.get("started_at") if started else None,"ends_at":item.get("ends_at") if started else None,"remaining_seconds":remaining,"can_start":bool(active and not started and not forced and item.get("status")=="assigned"),"can_submit":bool(active and started and remaining>0 and not forced and len(records)<limit),"forced_submit":forced,"submission_count":len(records),"max_submissions":limit,"duration_minutes":settings.get("exam_duration_minutes",90),"password_enabled":settings.get("exam_password_enabled",False),"extensions":settings.get("accepted_submission_extensions",[".zip"]),"course_id":settings.get("exam_course_id") if current else None,"title":(settings.get("exam_title") or "Kỳ thi nộp file") if current else "Kỳ thi nộp file"}


def monitoring_snapshot(course_id="") -> dict:
    students, sessions = read_json("students.json"), read_json("sessions.json")
    assignments, submissions = read_json("assignments.json"), read_json("submissions.json")
    latest = {}; now = datetime.now(timezone.utc)
    for token, sess in sessions.items():
        if sess.get("role") != "student": continue
        sid = sess.get("user_id")
        if sid not in latest or sess.get("last_seen", "") > latest[sid].get("last_seen", ""):
            latest[sid] = {**sess, "session_token": token}
    result=[]
    for sid, student in students.items():
        sess=latest.get(sid); assignment=assignments.get(sid, {}); online=False
        if sess and sess.get("last_seen"):
            try: online=(now-datetime.fromisoformat(sess["last_seen"])).total_seconds() <= 45
            except (ValueError, TypeError): pass
        records=submissions.get(sid, [])
        telemetry=sess.get("telemetry",{}) if sess else {}
        alerts=[]
        if telemetry.get("visibility") == "hidden": alerts.append("tab_hidden")
        if telemetry.get("focused") is False: alerts.append("window_unfocused")
        if int(telemetry.get("tab_count",1) or 1)>1: alerts.append("multiple_tabs")
        result.append({"student_id":sid,"full_name":student.get("full_name",""),"active":student.get("active",True),"logged_in":online,"ip":sess.get("ip") if sess else student.get("last_ip"),"user_agent":sess.get("user_agent","") if sess else "","last_seen":sess.get("last_seen") if sess else student.get("last_seen"),"exam_file":assignment.get("exam_file"),"exam_status":assignment.get("status","not_assigned"),"started_at":assignment.get("started_at"),"ends_at":assignment.get("ends_at"),"remaining_seconds":remaining_seconds(assignment) if assignment.get("started_at") else None,"submission_count":len(records),"latest_submission":records[-1] if records else None,"telemetry":telemetry,"alerts":alerts})
    result=admin_workspace.scope_monitor(result,course_id)
    abnormal_count=sum(1 for row in result if row["alerts"])
    return {"occurred_at":utc_now(),"students":result,"online_count":sum(1 for row in result if row["logged_in"]),"abnormal_count":abnormal_count}

class Handler(BaseHTTPRequestHandler):
    server_version = "LAN-LMS/2.0"
    protocol_version = "HTTP/1.1"
    timeout = REQUEST_IDLE_TIMEOUT_SECONDS

    @property
    def cookies(self):
        jar=SimpleCookie()
        try: jar.load(self.headers.get("Cookie", ""))
        except Exception: pass
        return {k:v.value for k,v in jar.items()}

    def log_message(self, fmt, *args):
        print("[%s] %s - %s" % (self.log_date_time_string(), self.client_address[0], fmt % args))

    def _send(self, status=200, body=b"", content_type="text/html; charset=utf-8", headers=None, cookie=None, clear_cookie=False):
        # Admin POST responses are sent after leaving the shared data lock.
        if getattr(self, "_defer_response", False):
            self._pending_response = (status, body, content_type, headers, cookie, clear_cookie)
            return
        if isinstance(body, str): body=body.encode("utf-8")
        streaming = hasattr(body, "read")
        if streaming:
            position=body.tell(); body.seek(0,2); length=body.tell()-position; body.seek(position)
        else: length=len(body)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        # no-referrer makes browser form POSTs send Origin: null on HTTP LAN.
        # Retain same-origin request identity without weakening Origin validation.
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Permissions-Policy", "camera=(self), microphone=(), geolocation=()")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
        self.send_header("Cache-Control", "no-store")
        if self.close_connection:
            self.send_header("Connection", "close")
        for k,v in (headers or {}).items(): self.send_header(k,v)
        if cookie:
            secure = bool(os.getenv("CSS_TLS_CERT") and os.getenv("CSS_TLS_KEY"))
            self.send_header("Set-Cookie", f"{SESSION_COOKIE}={cookie}; Path=/; HttpOnly; SameSite=Strict; Max-Age=43200" + ("; Secure" if secure else ""))
        if clear_cookie: self.send_header("Set-Cookie", f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0")
        self.end_headers()
        if self.command != "HEAD":
            try:
                if streaming: shutil.copyfileobj(body,self.wfile,65536)
                else: self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError): pass

    def _json(self, data, status=200, headers=None):
        self._send(status, json.dumps(data,ensure_ascii=False).encode(), "application/json; charset=utf-8", headers)

    def _redirect(self, location, status=303, cookie=None, clear_cookie=False):
        self._send(status, b"", "text/plain; charset=utf-8", {"Location":location}, cookie=cookie, clear_cookie=clear_cookie)

    def _html(self, text, status=200): self._send(status, text, "text/html; charset=utf-8")

    def _render(self, name, **context): return TEMPLATES.get_template(name).render(**context)

    def _read_body(self, length):
        deadline = time.monotonic() + REQUEST_BODY_TIMEOUT_SECONDS
        original_timeout = self.connection.gettimeout()
        remaining = length
        body = bytearray()
        try:
            while remaining:
                budget = deadline - time.monotonic()
                if budget <= 0:
                    raise TimeoutError
                self.connection.settimeout(min(original_timeout, budget) if original_timeout is not None else budget)
                # read1 returns after one buffered/socket read, allowing a total
                # deadline even when a client continuously trickles bytes.
                chunk = self.rfile.read1(min(remaining, 65536))
                if not chunk:
                    if remaining > 0:
                        raise ClientError(400, "Dữ liệu gửi lên chưa đầy đủ. Vui lòng gửi lại yêu cầu.")
                    break
                body.extend(chunk)
                if len(body) > MAX_REQUEST_SIZE:
                    raise ClientError(413, "Request vượt giới hạn 50 MiB.")
                remaining -= len(chunk)
            if time.monotonic() > deadline:
                raise TimeoutError
            return bytes(body)
        except TimeoutError:
            raise ClientError(408, "Quá thời gian nhận dữ liệu. Vui lòng kiểm tra kết nối và gửi lại.") from None
        finally:
            self.connection.settimeout(original_timeout)

    def _parse_body(self):
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) > 1 or (lengths and (not lengths[0].strip().isascii() or not lengths[0].strip().isdecimal())):
            raise ClientError(400, "Content-Length không hợp lệ hoặc bị lặp.")
        if self.headers.get_all("Transfer-Encoding"):
            raise ClientError(400, "Kiểu truyền dữ liệu này không được hỗ trợ. Hãy gửi Content-Length hợp lệ.")
        if lengths and len(lengths[0].strip()) > 12:
            raise ClientError(413, "Request vượt giới hạn 50 MiB.")
        length = int(lengths[0].strip()) if lengths else 0
        if length > MAX_REQUEST_SIZE: raise ClientError(413, "Request vượt giới hạn 50 MiB.")
        body=self._read_body(length) if length else b""
        ctype=self.headers.get("Content-Type", "")
        form={}; files={}
        if ctype.startswith("application/x-www-form-urlencoded"):
            parsed=urllib.parse.parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True)
            form={k:v[-1] for k,v in parsed.items()}
        elif ctype.startswith("multipart/form-data"):
            msg=BytesParser(policy=default).parsebytes((f"Content-Type: {ctype}\r\nMIME-Version: 1.0\r\n\r\n".encode()+body))
            if msg.is_multipart():
                for part in msg.iter_parts():
                    name=part.get_param("name", header="content-disposition")
                    if not name: continue
                    payload=part.get_payload(decode=True) or b""
                    filename=part.get_filename()
                    if filename is not None: files[name]={"filename":filename,"data":payload,"content_type":part.get_content_type()}
                    else: form[name]=payload.decode(part.get_content_charset() or "utf-8", "replace")
        return body, RequestData(self,form,files)

    def _request(self, form=None, files=None): return RequestData(self,form,files)

    def _auth(self, req, role=None, touch=True):
        try:
            session = require_user(req, role, touch=touch)
            self._get_user_record(session)
            return session
        except SecurityError as e: raise ClientError(e.status,e.detail)

    def do_HEAD(self): self.do_GET()

    def do_GET(self):
        try:
            if urllib.parse.urlsplit(self.path).path.startswith('/api/'):
                deadlines.maybe_refresh()
            req=self._request(); path=req.path
            route_path = path.rstrip("/") or "/"
            if path.startswith("/static/"):
                rel=urllib.parse.unquote(path[len("/static/"):]); target=(STATIC_DIR/rel).resolve()
                if not target.is_relative_to(STATIC_DIR.resolve()) or not target.is_file(): return self._send(404,"Not found")
                ctype=mimetypes.guess_type(target.name)[0] or "application/octet-stream"
                return self._send(200,target.read_bytes(),ctype)
            if path=="/health": return self._json({"status":"ok","service":"LAN-LMS","time":utc_now(),"launcher_id":os.getenv("CSS_LAUNCH_ID")})
            if path=="/api/admin/readiness":
                self._auth(req,"admin")
                from .maintenance import doctor
                result=doctor()
                result["queue"]={"pending":sum(r.get("state") in {"queued","running"} for r in programming.rows())}
                return self._json(result,200 if result["ready"] else 503)
            if path=="/login": return self._html(self._render("login.html",error=None,next=attendance_return(req.query.get("next",[""])[0])))
            if path in {"/", "/student", "/student/dashboard", "/student/courses", "/student/calendar", "/student/attendance", "/student/assignments", "/student/exams", "/student/grades", "/student/history", "/student/notifications", "/student/profile"}:
                sess=get_session(req)
                if not sess:
                    destination=attendance_return(self.path)
                    return self._redirect("/login"+("?next="+urllib.parse.quote(destination,safe="") if destination else ""))
                if sess["role"]=="admin": return self._redirect("/admin")
                student=self._get_user_record(sess); assignment=current_exam_for(sess["user_id"]); settings=read_json("settings.json")
                return self._html(self._render("student.html",session=sess,student=student,assignment=assignment,settings=settings,remaining=remaining_seconds(assignment or {}) if assignment and assignment.get("started_at") else None))
            if path=="/admin/learning":
                self._auth(req,"admin")
                params={k:v[-1] for k,v in req.query.items() if k in {"course","tab"}}
                return self._redirect("/admin/courses"+("?"+urllib.parse.urlencode(params) if params else ""))
            if path=="/api/learning":
                return self._json(learning.snapshot(self._auth(req)))
            if path=="/api/learning/export-course":
                sess=self._auth(req,"admin")
                package=course_packages.export_course(req.query.get("course",[""])[0],sess)
                return self._send(200,json.dumps(package,ensure_ascii=False).encode(),"application/json; charset=utf-8",{"Content-Disposition":"attachment; filename*=UTF-8''"+urllib.parse.quote(package["course"]["code"]+".json",safe="")})
            if path.startswith("/api/learning/preview/") or path.startswith("/api/learning/view/"):
                sess=self._auth(req); parts=path.split("/")
                if len(parts)!=6: raise ClientError(404,"Không tìm thấy file.")
                if parts[3]=="preview": return self._json(learning.preview_file(parts[4],parts[5],sess))
                target,name=learning.file_for(parts[4],parts[5],sess)
                if target.suffix.lower()!=".pdf": raise ClientError(400,"Chỉ mở PDF trực tiếp; các định dạng khác dùng xem văn bản hoặc tải về.")
                return self._send(200,target.read_bytes(),"application/pdf",{"Content-Disposition":inline_filename_header(name)})
            if path.startswith("/api/learning/files/"):
                sess=self._auth(req); parts=path.split("/")
                if len(parts)!=6: raise ClientError(404,"Không tìm thấy file.")
                target,name=learning.file_for(parts[4],parts[5],sess)
                filename=urllib.parse.quote(name,safe="")
                return self._send(200,target.read_bytes(),"application/octet-stream",{"Content-Disposition":f"attachment; filename*=UTF-8''{filename}"})
            if path=="/api/student/workspace":
                sess=self._auth(req,"student"); sid=sess["user_id"]; student=self._get_user_record(sess)
                result=learning.snapshot(sess)
                result.update({"student":{"student_id":sid,"full_name":student.get("full_name",sid),"must_change_password":student.get("must_change_password",False)},"exam":student_exam_snapshot(sid),"exam_submissions":read_json("submissions.json").get(sid,[]),"notifications":[n for n in read_json("notifications.json",[]) if n.get("student_id") in (None,sid)],"server_time":utc_now()})
                result["notification_feed"]=student_notifications.feed(sid,result)
                result["programming"] = programming.snapshot(sid)
                result["exam"]["assessment_type"] = read_json("settings.json").get("exam_assessment_type", "test")
                settings=read_json("settings.json")
                common_end=deadlines.exam_end(settings.get("exam_started_at"),settings.get("exam_duration_minutes"),settings.get("exam_ends_at")) if settings.get("exam_state") in {"started","ended"} else None
                result["exam"]["common_ends_at"]=common_end.isoformat() if common_end else None
                result["exam"]["closed_automatically"]=settings.get("exam_closed_automatically",False)
                return self._json(result)
            if path=="/api/student/programming/submissions":
                sess=self._auth(req,"student")
                return self._json(programming.student_submissions(sess["user_id"],req.query.get("exam",[""])[0],req.query.get("problem",[""])[0]))
            if path=="/api/admin/programming/status":
                self._auth(req,"admin")
                return self._json(code_runner.status())
            if path=="/api/admin/exam-preflight":
                self._auth(req,"admin")
                return self._json(exam_preflight.review(req.query.get("exam",[""])[0]))
            if path=="/api/admin/programming/submissions":
                self._auth(req,"admin")
                exam_id=req.query.get("exam", [""])[0]
                return self._json({"submissions":[programming.public_submission(r, True) for r in programming.rows() if r["exam_id"]==exam_id]})
            if path.startswith("/api/programming/source/"):
                sess=self._auth(req); submission_id=path.rsplit("/",1)[-1]
                record=next((r for r in programming.rows() if r["id"]==submission_id),None)
                if not record or sess["role"]!="admin" and record["student_id"]!=sess["user_id"]: raise ClientError(404,"Không tìm thấy bài nộp.")
                return self._send(200,(programming.FILES / record["id"] / "source").read_bytes(),"application/octet-stream",{"Content-Disposition":inline_filename_header(record["original_filename"])})
            if path=="/api/student/notifications":
                sess=self._auth(req,"student")
                return self._json({"notifications":student_notifications.feed(sess["user_id"])})
            if path.startswith("/api/student/submissions/"):
                sess=self._auth(req,"student"); filename=urllib.parse.unquote(path[len("/api/student/submissions/"):])
                records=read_json("submissions.json").get(sess["user_id"],[])
                if not any(r["filename"]==filename and r.get("payload_retained",True) for r in records): raise ClientError(404,"File bài nộp không còn được lưu.")
                target=(UPLOAD_DIR/filename).resolve()
                if target.parent!=UPLOAD_DIR.resolve() or not target.is_file(): raise ClientError(404,"Không tìm thấy file.")
                return self._send(200,target.read_bytes(),"application/octet-stream",{"Content-Disposition":f"attachment; filename*=UTF-8''{urllib.parse.quote(filename,safe='')}"})
            admin_sections={
                "/admin/courses":"courses",
                "/admin/dashboard":"dashboard",
                "/admin/monitor":"monitor",
                "/admin/notifications":"notifications",
                "/admin/exam":"exam",
                "/admin/settings":"exam",
                "/admin/distribution":"exam",
                "/admin/accounts":"accounts",
                "/admin/submissions":"submissions",
                "/admin/server":"server",
                "/admin/admins":"admins",
            }
            if route_path=="/admin" or route_path in admin_sections:
                sess=self._auth(req,"admin")
                section=admin_sections.get(route_path, req.query.get("section", ["dashboard"])[0])
                if section in {"settings", "distribution"}:
                    section="exam"
                allowed={"dashboard","courses","monitor","notifications","exam","accounts","submissions","server","admins"}
                if section not in allowed: section="dashboard"
                selected_exam = next((r for r in exam_catalog.listing() if r["id"] == req.query.get("exam", [""])[0]), None) if section == "exam" else None
                return self._html(self._render("admin.html",session=sess,section=section,exam_engine_detail=bool(selected_exam and selected_exam["type"] == "file" and selected_exam["active"]),exam_files=list_exam_files(),settings={**read_json("settings.json"), **({"exam_state":"scheduled"} if exam_timing.waiting(read_json("settings.json").get("exam_state"),read_json("settings.json").get("exam_started_at")) else {})},monitoring=monitoring_snapshot(),course_count=len(learning.load()["courses"])))
            if path=="/admin/accounts-template.txt":
                self._auth(req,"admin")
                content="21010001|01/02/2003|Nguyen Van A\n21010002|15/08/2003|Tran Thi B\n"
                return self._send(200,content,"text/plain; charset=utf-8",{"Content-Disposition":"attachment; filename=student_accounts_template.txt"})
            if path=="/api/admin/monitor": self._auth(req,"admin"); return self._json(monitoring_snapshot(req.query.get("course",[""])[0]))
            if path.startswith("/api/admin/archive/"):
                sess=self._auth(req,"admin"); query={k:v[-1] for k,v in req.query.items()}; action=path.rsplit("/",1)[-1]
                if action=="list": return self._json(submission_archive.listing(query))
                if action=="detail": return self._json(submission_archive.detail(query.get("id")))
                if action=="csv": return self._send(200,submission_archive.export_csv(query),"text/csv; charset=utf-8",{"Content-Disposition":"attachment; filename=submissions.csv"})
                if action=="zip":
                    with submission_archive.export_zip(query) as stream:
                        return self._send(200,stream,"application/zip",{"Content-Disposition":"attachment; filename=submissions.zip"})
                if action in {"download","preview","view"}:
                    target,name=submission_archive.file_for(query.get("id"))
                    if action=="preview": return self._json(learning.preview_path(target,name,"/api/admin/archive/view?id="+urllib.parse.quote(query.get("id"),safe="")))
                    if action=="view" and target.suffix.lower()!=".pdf": raise ClientError(400,"Chỉ mở PDF trực tiếp.")
                    with target.open("rb") as stream:
                        disposition=inline_filename_header(name) if action=="view" else "attachment; filename*=UTF-8''"+urllib.parse.quote(name,safe="")
                        audit("archive.downloaded",sess["user_id"],client_ip(req),{"id":query.get("id")})
                        return self._send(200,stream,"application/pdf" if action=="view" else "application/octet-stream",{"Content-Disposition":disposition})
                raise ClientError(404,"Không tìm thấy thao tác kho bài nộp.")
            if path=="/api/admin/workspace":
                sess=self._auth(req,"admin")
                return self._json(admin_workspace.overview(sess,req.query.get("course",[""])[0]))
            if path=="/api/admin/exams": self._auth(req,"admin"); return self._json({"exams":list_exam_files()})
            if path=="/api/admin/accounts":
                self._auth(req,"admin")
                participants=set(read_json("settings.json").get("exam_participants") or [])
                attempts=read_json("login_attempts.json")
                return self._json({"server_time":utc_now(),"students":[{"student_id":sid,"full_name":s.get("full_name"),"active":s.get("active",True),"last_ip":s.get("last_ip"),"last_seen":s.get("last_seen"),"exam_participant":sid in participants,**login_state(sid,attempts)} for sid,s in read_json("students.json").items()]})
            if path=="/api/admin/submissions":
                self._auth(req,"admin"); students=read_json("students.json"); records=read_json("submissions.json"); result=[]
                course_id=req.query.get("course",[""])[0]
                admin_workspace.course_members(course_id)
                for sid,attempts in records.items():
                    for index,item in enumerate(attempts,start=1):
                        if not course_id or item.get("course_id")==course_id: result.append({"student_id":sid,"full_name":students.get(sid,{}).get("full_name",""),"attempt":index,**item})
                result.sort(key=lambda x:x.get("submitted_at",""),reverse=True); return self._json({"submissions":result})
            if path=="/api/admin/admins":
                self._auth(req,"admin"); return self._json({"admins":[{"username":n,"active":d.get("active",True),"created_at":d.get("created_at"),"created_by":d.get("created_by")} for n,d in read_json("admins.json").items()]})
            if path=="/api/admin/server-info":
                self._auth(req,"admin"); addresses=self._lan_addresses(); scheme="https" if (os.getenv("CSS_TLS_CERT") and os.getenv("CSS_TLS_KEY")) else "http"
                return self._json({"addresses":sorted(addresses),"current_url":f"{scheme}://{self.headers.get('host',f'127.0.0.1:{PORT}')}","port":PORT,"scheme":scheme})
            if path=="/api/student/exam":
                sess=self._auth(req,"student"); item=current_exam_for(sess["user_id"]); settings=read_json("settings.json")
                if not settings.get("exam_released") or not item or item.get("release_id")!=settings.get("exam_release_id"): raise ClientError(403,"Lượt thi đã kết thúc hoặc chưa được phân phối.")
                if not item.get("started_at"): raise ClientError(403,"Chỉ xem được đề sau khi bắt đầu làm bài.")
                if remaining_seconds(item)<=0: raise ClientError(403,"Đã hết giờ làm bài.")
                target=(EXAM_DIR/item["exam_file"]).resolve()
                if target.parent!=EXAM_DIR.resolve() or not target.is_file() or target.suffix.lower() not in {".pdf",".txt",".png",".jpg",".jpeg",".gif",".webp"}: raise ClientError(404,"File đề không còn tồn tại.")
                audit("exam.viewed",sess["user_id"],client_ip(req),{"exam_file":target.name})
                ctype=mimetypes.guess_type(target.name)[0] or "application/octet-stream"
                return self._send(200,target.read_bytes(),ctype,{"Content-Disposition":inline_filename_header(target.name)})
            if path=="/api/student/status":
                sess=self._auth(req,"student"); item=current_exam_for(sess["user_id"]); settings=read_json("settings.json")
                notifications=read_json("notifications.json", [])
                personal=[item for item in notifications if item.get("student_id") in (None, sess["user_id"])]
                return self._json({"assigned":bool(item),"started":bool(item and item.get("started_at")),"exam_file":item.get("exam_file") if item and item.get("started_at") else None,"status":item.get("status") if item else "not_assigned","remaining_seconds":remaining_seconds(item or {}) if item and item.get("started_at") else None,"started_at":item.get("started_at") if item else None,"ends_at":item.get("ends_at") if item else None,"server_time":utc_now(),"exam_state":settings.get("exam_state","idle"),"notifications":personal[-10:],"exam_password_enabled":settings.get("exam_password_enabled",False),"accepted_submission_extensions":settings.get("accepted_submission_extensions",[".zip"])})
            if path.startswith("/admin/submissions/"):
                sess=self._auth(req,"admin"); parts=[urllib.parse.unquote(x) for x in path.split("/")[3:]]
                if len(parts)!=2: raise ClientError(404,"Không tìm thấy file bài nộp.")
                sid,filename=parts; records=read_json("submissions.json")
                if not any(x.get("filename")==filename and x.get("payload_retained",True) for x in records.get(sid,[])): raise ClientError(404,"Không tìm thấy file bài nộp còn được lưu.")
                target=(UPLOAD_DIR/filename).resolve()
                if target.parent!=UPLOAD_DIR.resolve() or not target.is_file(): raise ClientError(404,"File bài nộp không tồn tại.")
                audit("admin.submission_downloaded",sess["user_id"],client_ip(req),{"student_id":sid,"filename":filename})
                return self._send(200,target.read_bytes(),mimetypes.guess_type(target.name)[0] or "application/octet-stream",{"Content-Disposition":f'attachment; filename="{target.name}"'})
            return self._send(404,"Không tìm thấy trang.")
        except (ClientError, SecurityError, learning.LearningError, submission_rate.SubmissionRateError) as e: return self._handle_error(e)
        except Exception:
            traceback.print_exc(); return self._json({"detail":"Lỗi máy chủ nội bộ."},500)

    def _get_user_record(self, sess):
        source="admins.json" if sess["role"]=="admin" else "students.json"; record=read_json(source).get(sess["user_id"])
        if not record or not record.get("active",True): raise ClientError(401,"Tài khoản không còn hoạt động.")
        return record

    def do_POST(self):
        try:
            req = self._request()
            check_origin(req)
            admin_request = req.path.startswith('/api/admin/')
            if admin_request:
                self._auth(req, "admin", touch=False)
            body, req = self._parse_body()
            if req.path == "/api/admin/exam-preflight/verify":
                sess = self._auth(req, "admin")
                return self._json(exam_preflight.verify_reference(sess, req.form, client_ip(req)))
            if req.path == "/api/admin/exam-preflight/open":
                req.preflight_runner = code_runner.status() if req.form.get("type") == "programming" else None
            if req.path == "/api/admin/programming/control" and req.form.get("action") == "start":
                req.judge_ready = code_runner.ready()
            if not admin_request:
                return self._do_POST(body, req)
            self._pending_response = None
            self._defer_response = True
            try:
                with learning.LOCK, atomic_transaction():
                    self._do_POST(body, req)
            finally:
                self._defer_response = False
            response = self._pending_response
            self._pending_response = None
            if response is not None:
                return self._send(*response)
        except (ClientError, SecurityError, learning.LearningError, submission_rate.SubmissionRateError) as e:
            # The unread/rejected body must never become a keep-alive request.
            self.close_connection = True
            try:
                return self._handle_error(e)
            finally:
                self._drain_rejected_request()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except Exception:
            self.close_connection = True
            traceback.print_exc()
            return self._json({"detail":"Lỗi máy chủ nội bộ."},500)

    def _do_POST(self, body, req):
        try:
            path=req.path; f=req.form; sess=None
            if path.startswith('/api/'):
                deadlines.maybe_refresh()
            if path=="/login":
                username=f.get("username","").strip(); password=f.get("password",""); ip=client_ip(req); key=username.casefold()
                if not username or len(username) > 80 or len(password) > 200:
                    raise ClientError(400, "Tên đăng nhập tối đa 80 ký tự và mật khẩu tối đa 200 ký tự.")
                check_login_source(ip)
                allowed,seconds=login_allowed(key)
                if not allowed:
                    audit("auth.login_locked",username,ip,{"retry_after_seconds":seconds}); return self._html(self._render("login.html",next=attendance_return(f.get("next")),error=f"Tài khoản tạm khóa. Vui lòng thử lại sau {max(1,seconds//60+1)} phút."),429)
                admins,students=read_json("admins.json"),read_json("students.json")
                role="admin" if username in admins else "student" if username in students else None
                record=admins.get(username) if role=="admin" else students.get(username) if role=="student" else None
                if not record or not record.get("active",True) or not verify_password(password,record.get("password_hash")):
                    seconds=record_login_failure(key); audit("auth.login_failed",username,ip,{"lockout_seconds":seconds}); msg="Thông tin đăng nhập không đúng."
                    if seconds: msg += " Đã khóa tạm trong 15 phút sau 3 lần sai."
                    return self._html(self._render("login.html",next=attendance_return(f.get("next")),error=msg),401)
                verified_hash = record.get("password_hash")
                with learning.LOCK, atomic_transaction():
                    accounts = read_json("admins.json" if role == "admin" else "students.json")
                    current = accounts.get(username)
                    if not current or not current.get("active", True) or current.get("password_hash") != verified_hash:
                        raise ClientError(401, "Thông tin tài khoản vừa thay đổi. Vui lòng đăng nhập lại.")
                    clear_login_failures(key)
                    if role=="student":
                        revoked=revoke_student_sessions(username)
                        if revoked: audit("auth.previous_session_revoked",username,ip,{"revoked_sessions":revoked})
                    token=new_session(username,role,ip,self.headers.get("user-agent",""))
                    if role=="student":
                        current["last_ip"]=ip; current["last_seen"]=utc_now(); write_json("students.json",accounts)
                    audit("auth.login_success",username,ip,{"role":role})
                return self._redirect("/admin" if role=="admin" else attendance_return(f.get("next")) or "/",cookie=token)
            if path=="/logout":
                sess=get_session(req)
                if sess: logout_session(sess["token"]); audit("auth.logout",sess["user_id"],client_ip(req),{})
                return self._redirect("/login",clear_cookie=True)
            if path=="/api/learning/import-course":
                sess=self._auth(req,"admin")
                return self._json(course_packages.import_course(req.files.get("file"),sess,client_ip(req)))
            if path.startswith("/api/learning/"):
                sess=self._auth(req)
                return self._json(learning.mutate(sess,path[len("/api/learning/"):],f,req.files,client_ip(req)))
            if path=="/api/student/change-password":
                with learning.LOCK, atomic_transaction():
                    sess=self._auth(req,"student"); students=read_json("students.json"); student=students[sess["user_id"]]
                    if not verify_password(f.get("current_password",""),student.get("password_hash")): raise ClientError(400,"Mật khẩu hiện tại không đúng.")
                    password=f.get("new_password","")
                    if len(password)<6 or len(password)>200: raise ClientError(400,"Mật khẩu mới phải dài từ 6 đến 200 ký tự.")
                    if password!=f.get("confirm_password"): raise ClientError(400,"Mật khẩu xác nhận không khớp.")
                    student.update({"password_hash":hash_password(password),"must_change_password":False}); write_json("students.json",students)
                    revoke_student_sessions(sess["user_id"])
                    audit("auth.password_changed",sess["user_id"],client_ip(req),{})
                return self._json({"ok":True})
            if path=="/api/student/notifications/read":
                sess=self._auth(req,"student")
                return self._json(student_notifications.mark_read(sess["user_id"],f.get("ids","").split(",") if f.get("ids") else [],f.get("all")=="true"))
            if path=="/api/admin/accounts/import":
                sess=self._auth(req,"admin"); text=f.get("pasted_text",""); file=req.files.get("account_file")
                if file and file.get("filename"):
                    if not file["filename"].lower().endswith(".txt"): raise ClientError(400,"Chỉ chấp nhận file .txt.")
                    payload=file["data"]
                    if len(payload)>2*1024*1024: raise ClientError(413,"File danh sách vượt quá 2 MiB.")
                    try: text += "\n"+payload.decode("utf-8-sig",errors="strict")
                    except UnicodeDecodeError: raise ClientError(400,"File .txt phải được mã hóa UTF-8.")
                rows,errors=parse_accounts(text); students=read_json("students.json"); created=[]; duplicates=[]
                for row in rows:
                    sid=row["student_id"]
                    if sid in students: duplicates.append(sid); continue
                    students[sid]={"student_id":sid,"full_name":row["full_name"],"password_hash":hash_password(row["dob"]),"active":True,"created_at":utc_now(),"last_ip":None,"last_seen":None,"must_change_password":False}; created.append(sid)
                write_json("students.json",students); audit("admin.accounts_imported",sess["user_id"],client_ip(req),{"created":len(created),"duplicates":duplicates,"parse_errors":errors})
                return self._json({"created_count":len(created),"created":created,"duplicates":duplicates,"errors":errors,"valid_rows":len(rows)})
            if path=="/api/admin/exam-participants":
                sess=self._auth(req,"admin")
                raw = f.get("student_ids", "")
                ids = [item.strip() for item in raw.replace(",", "\n").splitlines() if item.strip()]
                if not ids:
                    raise ClientError(400, "Hãy chọn hoặc nhập ít nhất một MSSV.")
                if len(ids) > 10000 or any(len(item) > 80 or not item.isalnum() for item in ids):
                    raise ClientError(400, "Danh sách MSSV không hợp lệ.")
                ids = list(dict.fromkeys(ids))
                students = read_json("students.json")
                created = []
                for sid in ids:
                    if sid not in students:
                        students[sid] = {"student_id": sid, "full_name": "Chưa cập nhật", "password_hash": hash_password(sid), "active": True, "created_at": utc_now(), "last_ip": None, "last_seen": None, "must_change_password": True}
                        created.append(sid)
                settings = read_json("settings.json")
                if settings.get("exam_course_id"):
                    _,members=admin_workspace.course_members(settings["exam_course_id"])
                    if not set(ids).issubset(members): raise ClientError(400,"Danh sách dự thi có sinh viên không thuộc khóa học của kỳ thi.")
                if settings.get("exam_state") == "started" or settings.get("exam_released"):
                    raise ClientError(409, "Không thể thay đổi danh sách dự thi khi kỳ thi đã bắt đầu.")
                settings["exam_participants"] = ids
                write_json("students.json", students)
                write_json("settings.json", settings)
                audit("admin.exam_participants_updated", sess["user_id"], client_ip(req), {"count": len(ids), "created": len(created)})
                return self._json({"ok": True, "student_ids": ids, "created": created, "count": len(ids)})
            if path=="/api/admin/exam-context":
                sess=self._auth(req,"admin")
                return self._json(admin_workspace.set_exam_context(sess,f,client_ip(req)))
            if path=="/api/admin/archive/grade":
                sess=self._auth(req,"admin")
                return self._json(submission_archive.grade(sess,f,client_ip(req)))
            if path=="/api/admin/exam-configurations/save":
                sess=self._auth(req,"admin")
                return self._json(exam_catalog.save(sess,f,client_ip(req)))
            if path=="/api/admin/exam-preflight/open":
                sess=self._auth(req,"admin")
                return self._json(exam_preflight.open_checked(sess,f,client_ip(req),getattr(req,"preflight_runner",None)))
            if path=="/api/admin/exam-timing":
                sess=self._auth(req,"admin")
                return self._json(exam_timing.update(sess,f,client_ip(req)))
            if path=="/api/admin/exam-configurations/activate":
                sess=self._auth(req,"admin")
                return self._json(exam_catalog.activate(sess,f,client_ip(req)))
            if path=="/api/admin/programming/participants":
                sess=self._auth(req,"admin")
                return self._json(exam_catalog.save_programming_participants(sess,f,client_ip(req)))
            if path=="/api/admin/programming/control":
                sess=self._auth(req,"admin")
                return self._json(programming.control(sess,f,client_ip(req),runner_ready=getattr(req,"judge_ready",None)))
            if path=="/api/admin/programming/rejudge":
                sess=self._auth(req,"admin")
                return self._json(programming.rejudge(sess,f,client_ip(req)))
            if path=="/api/student/programming/start":
                sess=self._auth(req,"student")
                return self._json(programming.start(sess,f,client_ip(req)))
            if path=="/api/student/programming/submit":
                sess=self._auth(req,"student")
                return self._json(programming.submit(sess,f,req.files.get("file"),client_ip(req)))
            if path.startswith("/api/admin/accounts/") and path.endswith("/reset-password"):
                sess=self._auth(req,"admin"); sid=urllib.parse.unquote(path[len("/api/admin/accounts/"):-len("/reset-password")].strip("/")); password=f.get("new_password","")
                if not password.strip() or len(password)<8 or len(password)>200: raise ClientError(400,"Mật khẩu mới phải dài từ 8 đến 200 ký tự.")
                students=read_json("students.json")
                if sid not in students: raise ClientError(404,"Không tìm thấy MSSV.")
                students[sid]["password_hash"]=hash_password(password); write_json("students.json",students)
                clear_login_failures(sid.casefold())
                revoke_student_sessions(sid)
                audit("admin.password_reset",sess["user_id"],client_ip(req),{"student_id":sid}); return self._json({"ok":True})
            if path.startswith("/api/admin/accounts/") and path.endswith("/unlock-login"):
                sess=self._auth(req,"admin"); sid=urllib.parse.unquote(path[len("/api/admin/accounts/"):-len("/unlock-login")].strip("/"))
                clear_login_failures(sid.casefold())
                audit("admin.login_lockout_cleared",sess["user_id"],client_ip(req),{"student_id":sid})
                return self._json({"ok":True})
            if path.startswith("/api/admin/accounts/") and path.endswith("/toggle"):
                sess=self._auth(req,"admin"); sid=urllib.parse.unquote(path[len("/api/admin/accounts/"):-len("/toggle")].strip("/")); students=read_json("students.json")
                if sid not in students: raise ClientError(404,"Không tìm thấy MSSV.")
                target=f.get("active")
                if target is not None and target not in {"true","false"}:raise ClientError(400,"Trạng thái tài khoản không hợp lệ.")
                students[sid]["active"]=(target=="true") if target is not None else not students[sid].get("active",True); write_json("students.json",students)
                if not students[sid]["active"]:
                    revoke_student_sessions(sid)
                audit("admin.account_toggled",sess["user_id"],client_ip(req),{"student_id":sid,"active":students[sid]["active"]}); return self._json({"active":students[sid]["active"]})
            if path=="/api/admin/settings":
                sess=self._auth(req,"admin")
                try: duration=int(f.get("exam_duration_minutes","90")); max_sub=int(f.get("max_submissions","1"))
                except ValueError: raise ClientError(400,"Thời lượng hoặc số lần nộp không hợp lệ.")
                policy=f.get("submission_policy","once")
                if not 1<=duration<=1440: raise ClientError(400,"Thời lượng phải từ 1 đến 1440 phút.")
                if policy not in {"once","configurable"}: raise ClientError(400,"Chính sách nộp không hợp lệ.")
                if not 1<=max_sub<=20: raise ClientError(400,"Số lần nộp phải từ 1 đến 20.")
                settings=read_json("settings.json")
                if settings.get("exam_released"): raise ClientError(409,"Không thể thay đổi cấu hình khi kỳ thi đang được phát. Hãy kết thúc lượt thi trước.")
                enabled=f.get("exam_password_enabled","false").lower() in {"true","1","on","yes"}; password=f.get("exam_password","")
                if enabled and password: settings["exam_password_hash"]=hash_password(password)
                elif enabled and not settings.get("exam_password_hash"): raise ClientError(400,"Hãy nhập mật khẩu đề khi bật tùy chọn này.")
                elif not enabled: settings["exam_password_hash"]=None
                extension_values = f.get("accepted_submission_extensions", ".zip").replace(",", " ").split()
                accepted_extensions = sorted({value if value.startswith(".") else f".{value}" for value in extension_values if value})
                if not accepted_extensions or any(len(value) > 10 for value in accepted_extensions):
                    raise ClientError(400, "Danh sách loại file nộp không hợp lệ.")
                settings.update({"exam_duration_minutes":duration,"submission_policy":policy,"max_submissions":max_sub,"overwrite_previous":f.get("overwrite_previous","false").lower() in {"true","1","on","yes"},"exam_password_enabled":enabled,"accepted_submission_extensions":accepted_extensions}); write_json("settings.json",settings)
                audit("admin.settings_updated",sess["user_id"],client_ip(req),{"exam_duration_minutes":duration,"submission_policy":policy,"max_submissions":max_sub,"exam_password_enabled":enabled}); return self._json({"ok":True,"settings":settings})
            if path=="/api/admin/distribute":
                sess=self._auth(req,"admin"); mode=f.get("mode","random"); config={}
                try:
                    selected_files = [value for value in f.get("exam_files", "").split(",") if value]
                    if mode=="selected": config={"exam_files":selected_files}
                    elif mode=="random": config={"exam_files":selected_files}
                    elif mode=="parity": config={"even_exam":f.get("even_exam",""),"odd_exam":f.get("odd_exam","")}
                    elif mode=="custom":
                        try:
                            modulus=int(f.get("custom_modulus","0"))
                        except ValueError:
                            raise ValueError("Số chia không hợp lệ.")
                        config={"last_digit_map":json.loads(f.get("last_digit_map","{}")),"custom_modulus":modulus,"exam_files":selected_files}
                    result=distribute_exams(mode,config)
                except (ValueError,json.JSONDecodeError) as e: raise ClientError(400,str(e))
                audit("admin.exam_distributed",sess["user_id"],client_ip(req),{"release_id":result["release_id"],"mode":mode}); return self._json(result)
            if path=="/api/admin/end-exam":
                sess=self._auth(req,"admin"); settings=read_json("settings.json"); old=settings.get("exam_release_id")
                if not settings.get("exam_released") or not old:
                    raise ClientError(409, "Hiện không có kỳ thi đang diễn ra.")
                ended=utc_now()
                settings.update({"exam_state":"ended","exam_released":False,"exam_ends_at":ended,"exam_ended_at":ended}); write_json("settings.json",settings); assignments=read_json("assignments.json")
                for item in assignments.values():
                    if item.get("release_id")==old:
                        item.setdefault("closed_at",ended)
                        item["ends_at"]=ended
                        if item.get("status")!="submitted": item["status"]="ended"
                write_json("assignments.json",assignments); audit("admin.exam_ended",sess["user_id"],client_ip(req),{"release_id":old,"ended_at":ended})
                return self._json({"ok":True,"note":"Lượt thi đã kết thúc; các đề đã phát của lượt cũ vẫn được giữ trong log nhưng không còn cho phép bắt đầu mới."})
            if path=="/api/admin/start-exam":
                self._auth(req,"admin")
                try: settings=start_exam_session()
                except ValueError as e: raise ClientError(409,str(e))
                return self._json({"ok":True,"state":settings["exam_state"],"started_at":settings["exam_started_at"]})
            if path.startswith("/api/admin/students/") and path.endswith("/force-submit"):
                sess=self._auth(req,"admin"); sid=urllib.parse.unquote(path[len("/api/admin/students/"):-len("/force-submit")])
                assignments=read_json("assignments.json"); item=assignments.get(sid)
                if req.query.get("course") and (not item or item.get("course_id")!=req.query["course"][0]): raise ClientError(403,"Bài thi không thuộc khóa học đang chọn.")
                if not item or item.get("status") not in {"assigned","in_progress"}: raise ClientError(404,"Sinh viên không có bài thi đang hoạt động.")
                item.update({"status":"submitted","forced_submit":True,"forced_submit_at":utc_now()}); assignments[sid]=item; write_json("assignments.json",assignments)
                audit("admin.forced_submission",sess["user_id"],client_ip(req),{"student_id":sid}); return self._json({"ok":True})
            if path.startswith("/api/admin/students/") and path.endswith("/adjust-time"):
                sess=self._auth(req,"admin"); sid=urllib.parse.unquote(path[len("/api/admin/students/"):-len("/adjust-time")]); minutes=exam_catalog.integer(f.get("minutes","0"),"Số phút gia hạn",-1440,1440)
                if minutes < -1440 or minutes > 1440: raise ClientError(400,"Số phút điều chỉnh không hợp lệ.")
                settings=read_json("settings.json")
                if settings.get("exam_state")!="started": raise ClientError(409,"Kỳ thi đã kết thúc, không thể gia hạn bài cũ.")
                assignments=read_json("assignments.json"); item=assignments.get(sid)
                if req.query.get("course") and (not item or item.get("course_id")!=req.query["course"][0]): raise ClientError(403,"Bài thi không thuộc khóa học đang chọn.")
                if not item or not item.get("ends_at"): raise ClientError(404,"Sinh viên chưa bắt đầu làm bài.")
                end=datetime.fromisoformat(item["ends_at"])+timedelta(minutes=minutes); item["ends_at"]=end.isoformat(timespec="seconds"); item["extra_time_seconds"]=item.get("extra_time_seconds",0)+minutes*60; assignments[sid]=item; write_json("assignments.json",assignments)
                audit("admin.exam_time_adjusted",sess["user_id"],client_ip(req),{"student_id":sid,"minutes":minutes}); return self._json({"ok":True,"ends_at":item["ends_at"]})
            if path=="/api/admin/notifications":
                sess=self._auth(req,"admin"); message=f.get("message","").strip(); raw_targets=f.get("student_ids","").strip()
                if not message or len(message)>1000: raise ClientError(400,"Nội dung thông báo không hợp lệ.")
                students=read_json("students.json")
                targets=list(dict.fromkeys(sid.strip() for sid in raw_targets.split(",") if sid.strip())) if raw_targets else [None]
                if any(target is not None and target not in students for target in targets): raise ClientError(404,"Không tìm thấy một hoặc nhiều MSSV.")
                with learning.LOCK:
                    notifications=read_json("notifications.json",[])
                    notifications.extend({"id":secrets.token_hex(8),"student_id":target,"message":message,"created_at":utc_now(),"created_by":sess["user_id"]} for target in targets)
                    write_json("notifications.json",notifications)
                audit("admin.notification_sent",sess["user_id"],client_ip(req),{"recipient_count":len(students) if targets == [None] else len(targets),"targeted":targets != [None]})
                return self._json({"ok":True,"recipient_count":len(students) if targets == [None] else len(targets)})
            if path=="/api/student/start":
                sess=self._auth(req,"student")
                try: item=start_exam(sess["user_id"],f.get("exam_password",""),client_ip(req))
                except PermissionError as e: raise ClientError(403,str(e))
                except ValueError as e: raise ClientError(400,str(e))
                return self._json({"ok":True,"exam_file":item["exam_file"],"started_at":item["started_at"],"ends_at":item["ends_at"],"remaining_seconds":remaining_seconds(item)})
            if path=="/api/student/submit":
                sess=self._auth(req,"student"); file=req.files.get("file")
                if not file or not file.get("filename"): raise ClientError(400,"Hãy chọn file bài làm.")
                data=file["data"]
                if len(data)>MAX_REQUEST_SIZE: raise ClientError(413,"File vượt giới hạn 50 MiB.")
                try: record=accept_submission(sess["user_id"],file["filename"],data,client_ip(req),f.get("request_id"))
                except ValueError as e: raise ClientError(400,str(e))
                return self._json({"ok":True,"submission":record})
            if path=="/api/student/telemetry":
                sess=self._auth(req,"student")
                def flag(name, default=False):
                    return f.get(name, str(default)).lower() in {"true","1","on","yes"}
                try: tab_count=max(1,min(20,int(f.get("tab_count","1"))))
                except ValueError: tab_count=1
                with transaction():
                    sessions=read_json("sessions.json"); token_key=sess["token_key"]
                    current=sessions.get(token_key)
                    if not current: raise ClientError(401,"Phiên đăng nhập không hợp lệ.")
                    current["telemetry"]={"visibility":"hidden" if f.get("visibility")=="hidden" else "visible","focused":flag("focused",True),"tab_count":tab_count,"browser":f.get("browser","")[:80],"updated_at":utc_now()}
                    current["last_seen"]=utc_now(); sessions[token_key]=current; write_json("sessions.json",sessions)
                return self._json({"ok":True})
            if path=="/api/admin/admins":
                sess=self._auth(req,"admin"); username=f.get("username","").strip(); password=f.get("password","")
                if not username or len(username)>80 or not all(c.isalnum() or c in "._-@" for c in username): raise ClientError(400,"Tên Admin không hợp lệ.")
                if len(password)<6 or len(password)>200: raise ClientError(400,"Mật khẩu Admin phải dài ít nhất 6 ký tự.")
                admins=read_json("admins.json")
                if username in admins or username in read_json("students.json"): raise ClientError(409,"Tên tài khoản đã tồn tại.")
                admins[username]={"username":username,"password_hash":hash_password(password),"active":True,"created_at":utc_now(),"created_by":sess["user_id"]}; write_json("admins.json",admins); audit("admin.admin_created",sess["user_id"],client_ip(req),{"new_admin":username})
                return self._json({"ok":True,"username":username})
            return self._json({"detail":"Không tìm thấy endpoint."},404)
        except (ClientError, SecurityError, learning.LearningError, submission_rate.SubmissionRateError): raise
        except Exception:
            raise

    def _drain_rejected_request(self):
        """Let the final error reach Windows clients before closing unread input.

        The response is already sent. Draining is bounded and never holds a
        business lock, including when a client ignores the early rejection.
        """
        try:
            self.wfile.flush()
            self.connection.shutdown(socket.SHUT_WR)
            deadline=time.monotonic()+.2
            remaining=65536
            while remaining and time.monotonic()<deadline:
                self.connection.settimeout(max(.001,deadline-time.monotonic()))
                try:
                    chunk=self.rfile.read1(min(remaining,8192))
                except OSError:
                    chunk=self.connection.recv(min(remaining,8192))
                if not chunk:break
                remaining-=len(chunk)
        except OSError:
            pass

    def _handle_error(self,e):
        status=getattr(e,"status",500); detail=getattr(e,"detail",str(e))
        if isinstance(e, submission_rate.SubmissionRateError):
            return self._json({"detail":detail,"retry_after":e.retry_after},429,{"Retry-After":str(e.retry_after)})
        if self.path.startswith("/api/") or self.path.startswith("/admin/submissions/") or self.path=="/api/student/exam": return self._json({"detail":detail},status)
        return self._html("<!doctype html><meta charset='utf-8'><title>Lỗi</title><h1>Yêu cầu không thể xử lý</h1><p>"+html.escape(detail)+"</p><p><a href='/'>Quay lại</a></p>",status)

    @staticmethod
    def _lan_addresses():
        # Ask the routing table for the active source IP instead of listing
        # every adapter (including stale, host-only and virtual addresses).
        # UDP connect selects a route without sending traffic or requiring DNS.
        for target in ("192.0.2.1","8.8.8.8"):
            try:
                with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
                    s.connect((target,80))
                    ip=ipaddress.ip_address(s.getsockname()[0])
                    if not (ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast):
                        return {str(ip)}
            except OSError: pass
        return set()

def main():
    with data_lease(DATA_DIR):
        return _serve()


def _serve():
    initialize()
    learning.initialize_enrollments()
    for directory in (EXAM_DIR,UPLOAD_DIR):
        directory.mkdir(parents=True,exist_ok=True)
    cert,key=os.getenv("CSS_TLS_CERT"),os.getenv("CSS_TLS_KEY")
    if bool(cert)!=bool(key):
        raise RuntimeError("Cần cấu hình đủ CSS_TLS_CERT và CSS_TLS_KEY để bật HTTPS.")
    scheme="https" if cert and key else "http"
    print("="*66); print("CLASSROOM SUBMISSION SERVER (Python standard-library HTTP server)"); print("="*66)
    print(f"Local URL : {scheme}://127.0.0.1:{PORT}")
    for ip in sorted(Handler._lan_addresses()): print(f"LAN URL   : {scheme}://{ip}:{PORT}")
    if not (cert and key): print("WARNING   : HTTP mode; LAN traffic is not encrypted. Use trusted TLS certs for HTTPS.")
    print(f"Exam dir  : {EXAM_DIR}"); print(f"Upload dir: {UPLOAD_DIR}"); print("Ctrl+C to stop. Keep this terminal open during the exam."); print("="*66)
    server=ThreadingHTTPServer((HOST,PORT),Handler); server.daemon_threads=True
    deadline_stop=deadline_thread=backup_stop=backup_thread=None
    try:
        if cert and key:
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.load_cert_chain(cert,key); server.socket=context.wrap_socket(server.socket,server_side=True)
        programming.resume()
        deadline_stop,deadline_thread=deadlines.start_worker()
        from .maintenance import start_backups
        backup_stop,backup_thread=start_backups()
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt: print("\nStopping server...")
    finally:
        if deadline_stop:deadline_stop.set();deadline_thread.join(timeout=2)
        if backup_stop:backup_stop.set();backup_thread.join(timeout=2)
        server.server_close()
        programming.shutdown()

if __name__=="__main__": main()
