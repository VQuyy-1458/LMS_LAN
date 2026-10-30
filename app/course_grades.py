"""Course exam marks on a common ten-point scale; practice tests never contribute."""
import math

from .storage import read_json


def valid_score(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def exam_marks(course_id, student_ids):
    from .exam_catalog import listing
    exams = [e for e in listing() if e.get("course_id") == course_id and e.get("assessment_type") in {"midterm", "final"} and e.get("state") != "idle"]
    files = read_json("submissions.json", {})
    code = read_json("programming_submissions.json", [])
    indexed_code = {}
    for attempt in code:
        indexed_code.setdefault((attempt.get("exam_id"),attempt.get("student_id"),attempt.get("problem_index")),[]).append(attempt)
    result = {sid: [] for sid in student_ids}
    for exam in exams:
        for sid in student_ids:
            if sid not in exam.get("participants", []):
                continue
            score = None
            if exam["type"] == "file":
                attempts = [r for r in files.get(sid, []) if r.get("exam_id") == exam["id"] or (not r.get("exam_id") and exam.get("release_id") and r.get("release_id") == exam["release_id"])]
                # Legacy timestamps only have second precision; the later
                # appended receipt wins when two attempts share that timestamp.
                latest = max(reversed(attempts), key=lambda r: r.get("submitted_at", ""), default=None)
                if latest:
                    score = latest.get("score")
                elif exam["state"] == "ended":
                    score = 0
            else:
                problems = exam.get("programming", {}).get("problems", [])
                marks = []
                for index, problem in enumerate(problems):
                    attempts = indexed_code.get((exam["id"],sid,index),[])
                    points = []
                    for attempt in attempts:
                        grades = [h.get("result") for h in attempt.get("grading_history", [])] + [attempt.get("result")]
                        value = next((g["score"] for g in reversed(grades) if g and valid_score(g.get("score"))), None)
                        if value is not None:
                            points.append(max(0, min(problem["points"], value)))
                    marks.append(max(points) if points else 0 if not attempts and exam["state"] == "ended" else None)
                maximum = sum(p["points"] for p in problems)
                if marks and maximum and all(v is not None for v in marks):
                    score = 10 * sum(marks) / maximum
            result[sid].append({"exam_id": exam["id"], "title": exam["title"], "assessment_type": exam["assessment_type"], "score": round(max(0, min(10, score)), 2) if valid_score(score) else None})
    return result
