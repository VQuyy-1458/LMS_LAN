"""One persistent rolling quota shared by every student submission workflow."""
import math
import threading
import time
import uuid
from contextlib import contextmanager

from .storage import read_json, write_json, transaction

LOCK = threading.RLock()
LIMIT, WINDOW = 6, 60


class SubmissionRateError(Exception):
    status = 429

    def __init__(self, seconds):
        self.retry_after = seconds
        self.detail = f"Mỗi sinh viên chỉ được nộp tối đa 6 lần trong 60 giây, tính chung file và code. Vui lòng chờ {seconds} giây rồi nộp tiếp."
        super().__init__(self.detail)


@contextmanager
def guard(student_id):
    token = uuid.uuid4().hex
    with transaction():
        now = time.time()
        records = {sid: [r for r in rows if r["at"] > now-WINDOW] for sid, rows in read_json("submission_rate.json", {}).items()}
        records = {sid: rows for sid, rows in records.items() if rows}
        recent = records.setdefault(student_id, [])
        if len(recent) >= LIMIT:
            raise SubmissionRateError(max(1, math.ceil(min(r["at"] for r in recent)+WINDOW-now)))
        recent.append({"id": token, "at": now})
        write_json("submission_rate.json", records)
    try:
        yield
    except BaseException:
        with transaction():
            records = read_json("submission_rate.json", {})
            records[student_id] = [r for r in records.get(student_id, []) if r["id"] != token]
            write_json("submission_rate.json", records)
        raise
