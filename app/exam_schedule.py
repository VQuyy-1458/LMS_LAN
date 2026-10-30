"""Open complete scheduled exams on the server clock, without reference-run gates."""
from datetime import datetime, timezone

from . import learning
from .storage import audit


def describe(row):
    """Validate saved metadata only; Docker availability is a grading concern."""
    if not row.get("scheduled_at") or not (
        row["type"] == "programming" and row["state"] == "idle"
        or row["type"] == "file" and row.get("active") and row["state"] == "distributed"
    ):
        return {"auto_start_ready": False, "auto_start_issues": []}
    from .exam_preflight import _snapshot
    try:
        _, report = _snapshot(row["id"], row=row, include_fingerprint=False)
    except (learning.LearningError, ValueError, OSError) as error:
        return {"auto_start_ready": False, "auto_start_issues": [str(error)]}
    issues = [c["detail"] for c in report["checks"] if not c["ok"]]
    return {"auto_start_ready": not issues, "auto_start_issues": issues, "planned_end": report["planned_end"]}


def refresh(now=None):
    """Called by the persistent deadline worker and request deadline refreshes.

    The caller holds the metadata transaction, so save/open/end cannot race.
    A restart inside the original window catches up without granting extra time.
    """
    from . import exam_catalog, programming, exams
    now = now or datetime.now(timezone.utc)
    for row in exam_catalog.listing():
        if not row.get("auto_start_ready"):
            continue
        begins = learning.date_value(row["scheduled_at"])
        ends = learning.date_value(row["planned_end"])
        if not begins <= now < ends:
            continue
        if row["type"] == "programming":
            # Publishing the exam must not wait on Docker or a reference solution.
            # Submissions still use the existing Docker readiness checks.
            programming.control({"user_id": "system", "role": "admin"}, {"exam_id": row["id"], "action": "start"}, None, runner_ready=True, now=now)
        else:
            exams.start_exam_session(now=now, actor="system")
        audit("exam.auto_started", "system", None, {"exam_id": row["id"], "scheduled_at": row["scheduled_at"], "ends_at": ends.isoformat()})
