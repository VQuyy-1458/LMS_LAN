"""Enrollment cutoffs for homework and attendance, with legacy-safe baselines."""
from datetime import datetime, timezone


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (TypeError, ValueError):
        return None


def member_ids(course, students):
    return list(students) if course.get("student_ids") is None else course["student_ids"]


def initialize(course, students, at, legacy=False):
    if "enrollments" in course:
        return False
    course["enrollments"] = {sid: {"joined_at": None if legacy else at, "include_previous": legacy}
                             for sid in member_ids(course, students)}
    course["enrollment_tracking_since"] = at if course.get("status") != "completed" else None
    return True


def info(course, student_id, students):
    saved = course.get("enrollments", {}).get(student_id)
    if saved is not None:
        return dict(saved)
    tracked = timestamp(course.get("enrollment_tracking_since"))
    if tracked is None:
        return {"joined_at": None, "include_previous": True}
    created = timestamp(students.get(student_id, {}).get("created_at"))
    joined = max(tracked, created) if created else tracked
    return {"joined_at": joined.isoformat(), "include_previous": False}


def applies(course, student_id, activity, kind, students):
    enrollment = info(course, student_id, students)
    joined = timestamp(enrollment.get("joined_at"))
    if enrollment.get("include_previous") or joined is None:
        return True
    when = timestamp(activity.get("due_at") if kind == "assignment" else
                     activity.get("lesson_at") or activity.get("created_at"))
    # Undated legacy activities retain their existing treatment.
    return when is None or when >= joined


def update_members(course, students, members, at, include_previous=False):
    initialize(course, students, at, legacy=True)
    previous = set(member_ids(course, students))
    for sid in members:
        if sid not in course["enrollments"]:
            # Automatic enrollment can predate conversion to a selected roster.
            course["enrollments"][sid] = (info(course, sid, students) if sid in previous else
                                         {"joined_at": at, "include_previous": include_previous})
    # Keep removed members' original cutoff if they later rejoin.
    course["student_ids"] = members
