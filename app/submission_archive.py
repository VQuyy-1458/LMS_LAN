"""One archive over existing assignment, file-exam and code records; no duplicate payloads."""
import copy
import csv
import hashlib
import io
import json
import math
import re
import tempfile
import uuid
import unicodedata
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import learning, programming, submissions
from .storage import read_json, write_json, utc_now, audit, mutation


def _history(row, code=False):
    history = copy.deepcopy(row.get("grading_history", []))
    if not history and (row.get("result") if code else row.get("score") is not None):
        history = [{"id": "legacy", "graded_at": row.get("graded_at"), "graded_by": row.get("graded_by", "Trước khi lưu lịch sử"), **({"result": copy.deepcopy(row["result"])} if code else {"score": row["score"], "feedback": row.get("feedback", "")})}]
    return history


def _index():
    data = learning.load()
    courses = {c["id"]: c for c in data["courses"]}
    tasks = {a["id"]: a for a in data["assignments"]}
    students = read_json("students.json")
    rows = []
    def add(key, kind, row, sid, activity_id, title, path, root, when, attempt=None):
        code = kind == "code"
        history = _history(row, code)
        result = row.get("result")
        score = next((h["result"]["score"] for h in reversed(history) if h.get("result") and h["result"].get("score") is not None), None) if code else row.get("score")
        if code and result and result.get("score") is not None: score = result["score"]
        available = path.is_file() and path.resolve().is_relative_to(root.resolve())
        course = courses.get(row.get("course_id"), {})
        rows.append({"id": key, "kind": kind, "student_id": sid, "full_name": students.get(sid, {}).get("full_name") or row.get("full_name") or sid, "course_id": row.get("course_id") or "", "course_name": course.get("name") or row.get("course_name") or "Kỳ thi chung / khóa học cũ", "activity_id": activity_id, "title": title, "submitted_at": when, "attempt": attempt, "filename": row.get("original_filename") or row.get("filename", ""), "size_bytes": row.get("size_bytes", path.stat().st_size if available else 0), "sha256": row.get("sha256", ""), "ip": row.get("ip", ""), "score": score, "max_score": row.get("max_score", 100) if code else 10, "status": row.get("state", "queued") if code else "graded" if score is not None else "pending", "available": available, "language": row.get("language"), "grading_count": len(history), "selected": False, "_row": row, "_path": path, "_history": history, "_readonly": course.get("status") == "completed"})
    for row in data["submissions"]:
        add("assignment:"+row["id"], "assignment", row, row["student_id"], "assignment:"+row["assignment_id"], row.get("assignment_title") or tasks.get(row["assignment_id"], {}).get("title", "Bài tập cũ"), learning.FILES / row["stored_name"], learning.FILES, row["created_at"], row.get("attempt"))
    for sid, attempts in read_json("submissions.json").items():
        for row in attempts:
            key = "file:"+hashlib.sha256((sid+"\0"+row["filename"]).encode()).hexdigest()[:32]
            activity = "file:"+(row.get("release_id") or str(row.get("course_id"))+":"+str(row.get("exam_title")))
            add(key, "file", row, sid, activity, row.get("exam_title") or "Kỳ thi nộp file cũ", submissions.UPLOAD_DIR / row["filename"], submissions.UPLOAD_DIR, row.get("submitted_at", ""), row.get("attempt"))
    for row in programming.rows():
        add("code:"+row["id"], "code", row, row["student_id"], "code:"+row["exam_id"]+":"+str(row["problem_index"]), row["exam_title"]+" · "+row["problem_title"], programming.FILES / row["id"] / "source", programming.FILES, row["submitted_at"])
    groups = {}
    for row in rows: groups.setdefault((row["student_id"],row["activity_id"]), []).append(row)
    for group in groups.values():
        group.sort(key=lambda r: (r["submitted_at"], r.get("attempt") or 0))
        for i, row in enumerate(group, 1): row["attempt"] = i
        graded = [r for r in group if r["score"] is not None]
        chosen = max(graded, key=lambda r: (r["score"],r["attempt"])) if group[0]["kind"] == "code" and graded else group[-1] if group[0]["kind"] != "code" else None
        if chosen: chosen["selected"] = True
    return rows


def public(row):
    return {k: v for k, v in row.items() if not k.startswith("_")}


def _natural_key(value):
    """Vietnamese base-letter order, then tones; compare digit groups numerically."""
    alphabet = "aăâbcdđeêfghijklmnoôơpqrstuưvwxyz"
    tones = {"\u0300": 1, "\u0309": 2, "\u0303": 3, "\u0301": 4, "\u0323": 5}
    result = []
    for part in re.split(r"(\d+)", str(value or "").casefold()):
        if part.isdigit():
            result.append((0, int(part)))
        else:
            letters, accents = [], []
            for char in unicodedata.normalize("NFC", part):
                decomposed = unicodedata.normalize("NFD", char)
                base = unicodedata.normalize("NFC", "".join(c for c in decomposed if c not in tones))
                letters.append(alphabet.index(base) if base in alphabet else ord(char) + 100)
                accents.append(next((tones[c] for c in decomposed if c in tones), 0))
            result.append((1, tuple(letters), tuple(accents)))
    return tuple(result)


def _sorted(rows, query):
    field, order = "submitted_at", query.get("order", "asc")
    if order not in {"asc", "desc"}:
        raise learning.LearningError(400, "Cách sắp xếp không hợp lệ.")
    def value(row):
        item = row.get(field)
        if field == "submitted_at": return learning.date_value(item).timestamp() if item else 0
        if field in {"attempt", "score"}: return item if item is not None else 0
        if field == "status": return ({"queued": 0, "running": 1, "pending": 2, "error": 3, "graded": 4, "done": 4}.get(item, 5), _natural_key(item))
        return _natural_key(item)
    present = [r for r in rows if r.get(field) is not None and r.get(field) != ""]
    missing = [r for r in rows if r.get(field) is None or r.get(field) == ""]
    return sorted(present, key=lambda r: (value(r), _natural_key(r.get("student_id")), r.get("attempt") or 0, r["id"]), reverse=order == "desc") + missing


def _filtered(rows, query):
    q = query.get("q", "").strip().casefold()
    result = rows
    if query.get("exam"):
        from . import exam_catalog
        exam = next((e for e in exam_catalog.listing() if e["id"] == query["exam"]), None)
        if not exam:
            raise learning.LearningError(404, "Không tìm thấy kỳ thi.")
        result = [r for r in result if r["kind"] == "code" and r["_row"].get("exam_id") == exam["id"]] if exam["type"] == "programming" else [r for r in result if r["kind"] == "file" and exam.get("release_id") and r["_row"].get("release_id") == exam["release_id"]]
    for field in ("course_id", "student_id", "kind", "activity_id"):
        value = query.get({"course_id": "course", "student_id": "student", "activity_id": "activity"}.get(field, field), "")
        if value: result = [r for r in result if r[field] == value]
    if q: result = [r for r in result if q in " ".join(str(r[k]) for k in ("student_id", "full_name", "title", "filename", "course_name")).casefold()]
    status = query.get("status", "")
    if status: result = [r for r in result if (not r["available"] if status == "missing" else r["status"] == status)]
    for key, offset in (("from", 0), ("to", 1)):
        if not query.get(key): continue
        try: bound = datetime.strptime(query[key], "%Y-%m-%d").replace(tzinfo=timezone(timedelta(hours=7)))+timedelta(days=offset)
        except ValueError: raise learning.LearningError(400, "Ngày lọc không hợp lệ.")
        result = [r for r in result if r["submitted_at"] and (learning.date_value(r["submitted_at"]) >= bound if key == "from" else learning.date_value(r["submitted_at"]) < bound)]
    return _sorted(result, query)


def listing(query):
    with learning.LOCK:
        all_rows = _index()
        rows = _filtered(all_rows, query)
        total = len(rows)
        stats = {"total": total, "students": len({r["student_id"] for r in rows}), "pending": sum(r["status"] in {"pending", "queued", "running"} for r in rows), "missing": sum(not r["available"] for r in rows)}
        if query.get("mode") == "group":
            groups = {}
            for row in rows: groups.setdefault((row["student_id"], row["activity_id"]), []).append(row)
            rows = [{**max(group,key=lambda r:(r["submitted_at"],r["attempt"])), "attempt_count": len(group)} for group in groups.values()]
            rows = _sorted(rows, query)
        page = learning.integer(query, "page", 1, 1, 1000000)
        pages = max(1, math.ceil(len(rows)/10)); page = min(page, pages)
        scoped = [r for r in all_rows if not query.get("course") or r["course_id"] == query["course"]]
        activities = {r["activity_id"]: r["title"] for r in scoped}
        return {"rows": [public(r) for r in rows[(page-1)*10:page*10]], "total": total, "display_total": len(rows), "page": page, "pages": pages, "stats": stats, "activities": [{"id": k, "title": v} for k,v in sorted(activities.items(),key=lambda p:p[1].casefold())]}


def find(key):
    row = next((r for r in _index() if r["id"] == key), None)
    if not row: raise learning.LearningError(404, "Không tìm thấy bản ghi bài nộp.")
    return row


def detail(key):
    with learning.LOCK:
        indexed = _index(); row = next((r for r in indexed if r["id"] == key), None)
        if not row: raise learning.LearningError(404, "Không tìm thấy bản ghi bài nộp.")
        history = sorted((r for r in indexed if r["student_id"] == row["student_id"] and r["activity_id"] == row["activity_id"]), key=lambda r:r["attempt"])
        snapshot = row["_row"].get("assignment_snapshot") or row["_row"].get("exam_snapshot")
        if row["kind"] == "code":
            path = programming.FILES / row["_row"]["id"] / "problem.json"
            if path.is_file(): snapshot = json.loads(path.read_text(encoding="utf-8"))
        return {"submission": public(row), "attempts": [public(r) for r in history], "grading_history": row["_history"], "record": programming.public_submission(row["_row"], True) if row["kind"] == "code" else {"score": row["score"], "feedback": row["_row"].get("feedback", ""), "graded_at": row["_row"].get("graded_at")}, "readonly": row["_readonly"], "snapshot": snapshot}


def file_for(key):
    with learning.LOCK:
        row = find(key)
        if not row["available"]: raise learning.LearningError(404, "Bản ghi còn được lưu nhưng file gốc không còn tồn tại (dữ liệu cũ).")
        return row["_path"], row["filename"]


@mutation
def grade(session, form, ip):
    with learning.LOCK:
        row = find(form.get("id"))
        if row["kind"] == "code": raise learning.LearningError(400, "Dùng Chấm lại để chấm mã nguồn với bộ test đã lưu.")
        if row["_readonly"]: raise learning.LearningError(409, "Khóa học đã tổng kết, chỉ được xem lại kết quả.")
        if row["kind"] == "assignment":
            return learning.mutate(session, "grade", {"submission_id": row["_row"]["id"], "score": form.get("score", ""), "feedback": form.get("feedback", "")}, {}, ip)
        try: score = float(form.get("score", ""))
        except ValueError: raise learning.LearningError(400, "Điểm phải từ 0 đến 10.")
        if not math.isfinite(score) or not 0 <= score <= 10: raise learning.LearningError(400, "Điểm phải từ 0 đến 10.")
        records = read_json("submissions.json")
        original = next(r for r in records[row["student_id"]] if r["filename"] == row["_row"]["filename"])
        history = _history(original)
        entry = {"id": uuid.uuid4().hex, "score": round(score,2), "feedback": learning.text(form,"feedback",4000,False), "graded_at": utc_now(), "graded_by": session["user_id"]}
        history.append(entry); original.update({k:v for k,v in entry.items() if k!="id"}); original["grading_history"] = history
        write_json("submissions.json", records)
        audit("archive.file_graded", session["user_id"], ip, {"id": row["id"], "score": score})
        return {"ok": True}


def _csv(rows):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(["id","student_id","full_name","course","activity","kind","attempt","submitted_at","filename","score","max_score","selected","available","sha256"])
    for row in rows:
        values = [row[k] for k in ("id","student_id","full_name","course_name","title","kind","attempt","submitted_at","filename","score","max_score","selected","available","sha256")]
        writer.writerow(["'"+str(v) if str(v).lstrip().startswith(("=","+","-","@")) else "" if v is None else v for v in values])
    return ("\ufeff"+buffer.getvalue()).encode("utf-8")


def export_csv(query):
    with learning.LOCK: return _csv(_filtered(_index(),query))


def export_zip(query):
    with learning.LOCK: rows = _filtered(_index(),query)
    if len(rows)>1000 or sum(r["size_bytes"] for r in rows if r["available"])>100*1024*1024:
        raise learning.LearningError(413, "Gói tải vượt 1.000 bản ghi hoặc 100 MiB. Hãy lọc theo lớp, sinh viên hoặc bài trước khi tải.")
    stream = tempfile.TemporaryFile()
    try:
        with zipfile.ZipFile(stream,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as package:
            package.writestr("metadata.csv",_csv(rows))
            for row in rows:
                safe = re.sub(r"[^\w.-]","_",row["student_id"])[:50]
                identity = row["id"].replace(":","_")
                suffix = Path(row["filename"]).suffix[:12]
                prefix = f"SV_{safe}/{identity}"
                if row["available"]: package.write(row["_path"],f"{prefix}/attempt_{row['attempt']}{suffix}")
                package.writestr(f"{prefix}/history.json",json.dumps({"submission":public(row),"grading_history":row["_history"]},ensure_ascii=False,indent=2))
        stream.seek(0); return stream
    except BaseException:
        stream.close(); raise
