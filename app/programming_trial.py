"""Add isolated programming practice exams without replacing existing records.

Stop the application before running --apply. Run --verify to exercise the real
Docker judge with known solutions; it never creates student submissions.
"""
import argparse
import copy
import json
import math
import shutil
import socket
import sys
from datetime import datetime, timezone

from . import code_runner, exam_catalog, learning, programming, storage
from .config import BASE_DIR, PORT
from .security import hash_password

COURSE_CODE = "JUDGE-TRY-2026"
STUDENT_ID = "CHAMTHU01"
PASSWORD = "ThiThu2026!"


def cases(rows):
    return [{"input": value, "output": expected, "sample": i < 2}
            for i, (value, expected) in enumerate(rows)]


def problem(title, statement, tests, solution):
    return {"title": title, "statement": statement, "points": 50,
            "time_limit_ms": 2000, "memory_limit_mb": 256,
            "checker": "tokens", "tests": tests, "solution": solution}


def definitions():
    sums = [(2, 3), (-4, 9), (0, 0), (2147483647, 2147483647),
            (-1000000000, -1000000000), (17, -17), (999999999, 1), (-1, 0)]
    arrays = [[1, 9, 3, 2, 7], [-8], [-10, -3, -8, -4], [0] * 20,
              [1000000000, -1, 5], [7] * 10, list(range(-500, 500)), [2, 1]]
    gcds = [(12, 18), (0, 15), (0, 0), (-24, 36), (17, 19),
            (1000000000000, 250000000000), (-81, -27), (123456789, 987654321)]
    primes = [(2, "YES"), (9, "NO"), (1, "NO"), (0, "NO"),
              (-7, "NO"), (2147483647, "YES"), (49, "NO"), (97, "YES")]
    ranges = [([1, 2, 3, 4, 5], [(1, 3), (2, 5), (4, 4)]),
              ([-5], [(1, 1)]), ([0] * 10, [(1, 10)]),
              ([-3, -2, -1], [(1, 3), (2, 2)]),
              ([1000000000] * 10, [(1, 10), (3, 8)]),
              (list(range(-500, 500)), [(1, 1000), (501, 1000), (1, 500)]),
              ([7, -7, 7, -7], [(1, 4), (2, 3), (4, 4)]),
              ([5, 4, 3, 2, 1], [(i, j) for i in range(1, 6) for j in range(i, 6)])]
    range_tests = cases([(
        f"{len(a)} {len(q)}\n" + " ".join(map(str, a)) + "\n" +
        "".join(f"{left} {right}\n" for left, right in q),
        "".join(f"{sum(a[left-1:right])}\n" for left, right in q)
    ) for a, q in ranges])
    brackets = [("(())()", "YES"), (")(", "NO"), ("", "YES"),
                ("(()", "NO"), ("())(", "NO"), ("()" * 5000, "YES"),
                ("(" * 5000 + ")" * 5000, "YES"), ("(" * 100, "NO")]
    return [
        {"title": "Thi thử 01 · Nhập xuất và số nguyên", "problems": [
            problem("Tổng hai số nguyên", "Đọc hai số nguyên a, b trên stdin (|a|, |b| ≤ 2.147.483.647). In a + b. Kết quả có thể vượt số nguyên 32 bit; C/C++ và Java nên dùng kiểu 64 bit. Không in lời nhắc nhập.",
                    cases([(f"{a} {b}\n", f"{a+b}\n") for a, b in sums]),
                    "import sys\na,b=map(int,sys.stdin.buffer.read().split())\nprint(a+b)\n"),
            problem("Giá trị lớn nhất trong mảng", "Dòng đầu là n (1 ≤ n ≤ 10.000). Tiếp theo là n số nguyên ai, |ai| ≤ 10^9, có thể cách nhau bởi dấu cách hoặc xuống dòng. In giá trị lớn nhất. Mảng có thể chỉ gồm số âm.",
                    cases([(f"{len(a)}\n" + " ".join(map(str, a)) + "\n", f"{max(a)}\n") for a in arrays]),
                    "import sys\nv=list(map(int,sys.stdin.buffer.read().split()))\nprint(max(v[1:1+v[0]]))\n")]},
        {"title": "Thi thử 02 · Thuật toán số học", "problems": [
            problem("Ước chung lớn nhất", "Đọc hai số nguyên a, b, |a|, |b| ≤ 10^12. In UCLN không âm của |a| và |b|. Quy ước UCLN(0, 0) = 0.",
                    cases([(f"{a} {b}\n", f"{math.gcd(a,b)}\n") for a, b in gcds]),
                    "import math,sys\na,b=map(int,sys.stdin.buffer.read().split())\nprint(math.gcd(a,b))\n"),
            problem("Kiểm tra số nguyên tố", "Đọc số nguyên n, -10^9 ≤ n ≤ 2.147.483.647. In YES nếu n là số nguyên tố, ngược lại in NO (chữ in hoa). Các số nhỏ hơn 2 không phải số nguyên tố.",
                    cases([(f"{n}\n", f"{answer}\n") for n, answer in primes]),
                    "import math\nn=int(input())\nprint('YES' if n>=2 and all(n%d for d in range(2,math.isqrt(n)+1)) else 'NO')\n")]},
        {"title": "Thi thử 03 · Mảng và chuỗi", "problems": [
            problem("Truy vấn tổng đoạn", "Dòng đầu chứa n, q (1 ≤ n ≤ 10.000; 1 ≤ q ≤ 1.000). Dòng tiếp theo chứa n số nguyên ai, |ai| ≤ 10^9. Mỗi dòng trong q dòng sau chứa l, r (1 ≤ l ≤ r ≤ n), chỉ số bắt đầu từ 1. Với mỗi truy vấn, in tổng al + ... + ar trên một dòng. Dùng số nguyên 64 bit khi cần.",
                    range_tests,
                    "import sys\nv=iter(map(int,sys.stdin.buffer.read().split()))\nn,q=next(v),next(v)\np=[0]\nfor _ in range(n): p.append(p[-1]+next(v))\nfor _ in range(q):\n l,r=next(v),next(v)\n print(p[r]-p[l-1])\n"),
            problem("Dãy ngoặc đúng", "Đọc một dòng chỉ gồm '(' và ')', độ dài từ 0 đến 10.000. Dòng rỗng là dãy ngoặc đúng. In YES nếu mọi dấu ngoặc đều ghép cặp đúng thứ tự, ngược lại in NO.",
                    cases([(value + "\n", answer + "\n") for value, answer in brackets]),
                    "import sys\ns=sys.stdin.readline().strip()\nb=0\nok=True\nfor c in s:\n b+=1 if c=='(' else -1\n if b<0: ok=False\nprint('YES' if ok and b==0 else 'NO')\n")]}
    ]


def verify():
    results = []
    for exam in definitions():
        for item in exam["problems"]:
            result = code_runner.judge(item["solution"].encode(), "python", item)
            print(f"{item['title']}: {result['verdict']} {result['passed']}/{result['total']}", flush=True)
            results.append({"problem": item["title"], "result": result})
            if result["verdict"] != "AC":
                raise RuntimeError("Lời giải tham chiếu không đạt toàn bộ test.")
    path = BASE_DIR / "logs" / "trial-judge-verification.json"
    path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


def apply(draft=False):
    if not draft and not code_runner.ready():
        raise RuntimeError("Bộ chấm chưa sẵn sàng; chưa tạo hoặc mở kỳ thi.")
    manifest = storage.read_json("programming_trial.json", {})
    if manifest:
        if not draft:
            session = {"user_id": next(iter(storage.read_json("admins.json"))), "role": "admin"}
            for item in manifest["exams"]:
                if programming.exam(item["id"])["state"] == "idle":
                    programming.control(session, {"exam_id": item["id"], "action": "start"}, "127.0.0.1")
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return manifest
    backup = BASE_DIR / "backups" / ("before-programming-trial-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f"))
    backup.mkdir(parents=True)
    for name in ("students.json", "learning.json", "exam_catalog.json"):
        source = storage.DATA_DIR / name
        if source.exists(): shutil.copy2(source, backup / name)
    admins = storage.read_json("admins.json")
    session = {"user_id": next(iter(admins)), "role": "admin"}
    students = storage.read_json("students.json")
    if STUDENT_ID in students:
        raise RuntimeError("Tài khoản thi thử đã tồn tại; không đổi mật khẩu tài khoản cũ.")
    students[STUDENT_ID] = {"student_id": STUDENT_ID, "full_name": "Tài khoản thi thử bộ chấm", "active": True,
                            "password_hash": hash_password(PASSWORD), "created_at": storage.utc_now(), "created_by": session["user_id"], "must_change_password": False}
    storage.write_json("students.json", students)
    members = " ".join(sid for sid, row in students.items() if row.get("active", True))
    course_id = learning.mutate(session, "course", {"name": "Phòng thi thử bộ chấm lập trình", "code": COURSE_CODE,
        "semester": "Thi thử 2026", "description": "Ba kỳ thi thực hành, mỗi kỳ hai bài và 100 điểm. Chấm toàn bộ test mẫu và test ẩn; lấy điểm tốt nhất của từng bài. Các kỳ thi Test không tính vào điểm khóa học.",
        "enrollment": "selected", "student_ids": members}, {}, "127.0.0.1")["id"]
    exams = []
    for definition in definitions():
        problems = copy.deepcopy(definition["problems"])
        for item in problems: item.pop("solution")
        result = exam_catalog.save(session, {"type": "programming", "course_id": course_id,
            "title": definition["title"], "assessment_type": "test", "duration_minutes": "240",
            "description": "Thi thử chấm tự động: 2 bài × 50 điểm; mỗi bài 2 test mẫu và 6 test ẩn, chia đều điểm theo số test đạt. Đọc stdin, ghi stdout. Java dùng public class Main, không khai báo package. Có thể nộp lại để cải thiện điểm.",
            "languages": "c,cpp,java,python", "problems": json.dumps(problems, ensure_ascii=False)}, "127.0.0.1")
        if not draft:
            programming.control(session, {"exam_id": result["id"], "action": "start"}, "127.0.0.1")
        exams.append({"id": result["id"], "title": definition["title"]})
    manifest = {"course_id": course_id, "student_id": STUDENT_ID, "exams": exams,
                "created_at": storage.utc_now(), "backup": str(backup)}
    storage.write_json("programming_trial.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--draft", action="store_true", help="Create drafts while the judge is unavailable.")
    args = parser.parse_args()
    if args.verify:
        from .runtime import data_lease
        from .config import DATA_DIR
        with data_lease(DATA_DIR):
            verify()
    if args.apply:
        with socket.socket() as connection:
            connection.settimeout(1)
            if connection.connect_ex(("127.0.0.1", PORT)) == 0:
                parser.exit(1, "Dừng server đang chạy trước khi cập nhật kỳ thi thử.\n")
        try:
            from .runtime import data_lease
            from .config import DATA_DIR
            with data_lease(DATA_DIR):
                apply(draft=args.draft)
        except RuntimeError as error:
            parser.exit(1, str(error) + "\n")
    if not (args.verify or args.apply): parser.print_help()
