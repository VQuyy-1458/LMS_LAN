"""Prepare a complete LAN-LMS trial dataset, then replace live data with a backup.

Run --prepare first; stop the server before --apply STAGING_DIRECTORY.
Admin credentials are retained. All student/activity records are replaced.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import json
import secrets
import socket
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import code_runner, config, learning, storage
from .security import hash_password
from .seed_demo import NAMES, zipped

VERSION = "lan-lms-trial-v2"
VN = timezone(timedelta(hours=7))
DIRECTORIES = ("data", "learning-files", "submissions", "de-thi", "programming-submissions", "demo-inputs")
PASSWORD = "111111"

SUM_SOURCES = {
    "python": "a, b = map(int, input().split())\nprint(a + b)\n",
    "cpp": '#include <iostream>\nint main(){long long a,b;std::cin>>a>>b;std::cout<<a+b<<"\\n";}\n',
    "c": '#include <stdio.h>\nint main(void){long long a,b;scanf("%lld%lld",&a,&b);printf("%lld\\n",a+b);return 0;}\n',
    "java": 'import java.util.*; public class Main { public static void main(String[] args) { Scanner s=new Scanner(System.in); long a=s.nextLong(),b=s.nextLong(); System.out.println(a+b); } }\n',
}
SUM_TESTS = [
    {"input":"2 3\n","output":"5\n","sample":True},
    {"input":"-4 9\n","output":"5\n","sample":True},
    {"input":"0 0\n","output":"0\n","sample":False},
    {"input":"1000000000 1000000000\n","output":"2000000000\n","sample":False},
    {"input":"-123 -456\n","output":"-579\n","sample":False},
    {"input":"17 -17\n","output":"0\n","sample":False},
]
MAX_TESTS = [
    {"input":"5\n1 9 3 2 7\n","output":"9\n","sample":True},
    {"input":"1\n-8\n","output":"-8\n","sample":True},
    {"input":"4\n-10 -3 -8 -4\n","output":"-3\n","sample":False},
    {"input":"6\n0 0 0 0 0 0\n","output":"0\n","sample":False},
    {"input":"3\n1000000000 -1 5\n","output":"1000000000\n","sample":False},
]


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def prepare(root=None):
    root = Path(root or config.BASE_DIR).resolve()
    stamp = datetime.now(VN).strftime("%Y%m%d-%H%M%S")
    stage = root / "backups" / (".staging-trial-" + stamp + "-" + secrets.token_hex(2))
    for name in DIRECTORIES:
        (stage / name).mkdir(parents=True)
    now = datetime.now(VN).replace(microsecond=0)
    def at(days=0, minutes=0, hour=None):
        value = now + timedelta(days=days)
        if hour is not None: value = value.replace(hour=hour, minute=30, second=0)
        value += timedelta(minutes=minutes)
        return value.astimezone(timezone.utc).isoformat()
    def identity(key, days=0):
        return {"id":"trial-v2-"+key,"created_at":at(days),"created_by":VERSION}
    def payload(folder, stored, filename, content):
        raw = content.encode("utf-8") if isinstance(content, str) else content
        path = stage / folder / stored
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return {"original_filename":filename,"stored_name":stored,"size_bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}

    students = {}
    ids = [f"SV{i:03}" for i in range(1,21)]
    for sid, name in zip(ids,NAMES):
        students[sid] = {"student_id":sid,"full_name":name,"password_hash":hash_password(PASSWORD),"active":True,"created_at":at(-45),"created_by":VERSION,"must_change_password":False,"last_ip":None,"last_seen":None}
    data = copy.deepcopy(learning.EMPTY)
    definitions = [
        ("network","LTM-01","Lập trình mạng",ids,"Socket TCP/UDP, truyền file và ứng dụng Client–Server.",False),
        ("cpp","CPP-01","Lập trình C++",ids[:16],"Nhập xuất, mảng, hàm và thuật toán cơ bản.",False),
        ("database","CSDL-01","Cơ sở dữ liệu",ids[:12],"Mô hình quan hệ, SQL và thiết kế cơ sở dữ liệu.",False),
        ("python","PY-2025","Python căn bản",ids[:8],"Khóa đã hoàn thành để thử xem lại lịch sử và kết quả.",True),
    ]
    course_ids, tasks = {}, {}
    for key, code, title, members, description, completed in definitions:
        cid = "trial-v2-"+key
        course_ids[key] = cid
        data["courses"].append({**identity(key,-45),"code":code,"name":title,"group":"Nhóm 01","semester":"Học kỳ 1 · 2026–2027" if not completed else "Học kỳ hè · 2025–2026","description":description,"student_ids":members,"status":"completed" if completed else "active","weights":{"attendance":10,"homework":20,"midterm":30,"final":40}})
        for i in range(8 if completed else 12):
            day = -60+i*3 if completed else (-14+i*3 if i<4 else 0 if i==4 else (i-4)*3)
            lesson = {**identity(f"{key}-lesson-{i+1}",min(day,0)),"course_id":cid,"title":f"Buổi {i+1:02} · "+["Nhập môn và môi trường thực hành","Thực hành cơ bản","Xử lý dữ liệu","Ôn tập giữa kỳ","Thực hành tổng hợp","Hỏi đáp và luyện tập"][i%6],"description":"Đọc tài liệu, làm bài thực hành và điểm danh bằng QR trong buổi học.","kind":"lesson","starts_at":at(day,minutes=-10) if day==0 else at(day,hour=7 if key in {"network","cpp"} else 13),"location":"Phòng A203" if key in {"network","cpp"} else "Phòng B105"}
            data["events"].append(lesson)
            if i<4 or completed:
                records={sid:{"status":"late" if (j+i)%8==0 else "present","checked_in_at":lesson["starts_at"],"reason":""} for j,sid in enumerate(members) if (j+i)%7!=6}
                data["attendance"].append({**identity(f"{key}-attendance-{i+1}",day),"course_id":cid,"event_id":lesson["id"],"lesson_at":lesson["starts_at"],"title":lesson["title"],"description":"Điểm danh theo lịch học.","expires_at":at(day,minutes=60,hour=7 if key in {"network","cpp"} else 13),"closed":True,"code":secrets.token_hex(4).upper(),"records":records})
            elif i==4 and key=="network":
                data["attendance"].append({**identity("network-attendance-today"),"course_id":cid,"event_id":lesson["id"],"lesson_at":lesson["starts_at"],"title":lesson["title"],"description":"Phiên QR đang mở để dùng thử. SV001 chưa điểm danh.","expires_at":at(minutes=120),"closed":False,"code":secrets.token_hex(4).upper(),"records":{sid:{"status":"present","checked_in_at":at(),"reason":""} for sid in ids[1:4]}})
        materials = [
            ("Đề cương và cách đánh giá","de-cuong.txt",f"{title}\n{description}\n\nĐánh giá: chuyên cần 10%, bài tập 20%, giữa kỳ 30%, cuối kỳ 40%.\nGiữa kỳ lấy trung bình các kỳ thi giữa kỳ; Test không tính vào điểm khóa học.\n"),
            ("Hướng dẫn thực hành","huong-dan.txt","Đọc yêu cầu; chạy chương trình với test mẫu; kiểm tra tình huống biên; nộp file và xem biên nhận.\nĐiểm danh: mở mục Điểm danh trên điện thoại, quét QR giảng viên cung cấp.\nKỳ thi dùng đồng hồ chung kể từ lúc giảng viên mở.\n"),
            ("Ví dụ nhập xuất và kiểm thử","sum.cpp",SUM_SOURCES["cpp"]),
        ]
        if key=="database":materials[2]=("Ví dụ cơ sở dữ liệu thư viện","thu-vien.txt","CREATE TABLE doc_gia (id INTEGER PRIMARY KEY, ho_ten VARCHAR(100));\nCREATE TABLE sach (id INTEGER PRIMARY KEY, ten_sach VARCHAR(200));\nCREATE TABLE phieu_muon (doc_gia_id INTEGER, sach_id INTEGER, ngay_muon DATE);\nSELECT d.ho_ten, s.ten_sach FROM phieu_muon p JOIN doc_gia d ON d.id=p.doc_gia_id JOIN sach s ON s.id=p.sach_id;\n")
        if key=="python":materials[2]=("Ví dụ nhập xuất Python","sum.py",SUM_SOURCES["python"])
        if key=="network":materials[2]=("TCP Echo Server tham khảo","echo_server.py","import socket\nwith socket.socket() as server:\n    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)\n    server.bind(('0.0.0.0', 9000))\n    server.listen()\n    connection, address = server.accept()\n    with connection:\n        data = connection.recv(4096)\n        connection.sendall(data)\n")
        for i,(name,filename,text) in enumerate(materials):
            data["materials"].append({**identity(f"{key}-material-{i+1}",-10+i),"course_id":cid,"title":name,"topic":"Tài liệu học phần","description":"Tài liệu phục vụ thực hành và kiểm thử chức năng xem/tải.",**payload("learning-files",f"{key}-material-{i+1}-"+filename,filename,text)})
        tasks[cid] = []
        titles = ["Ôn tập kiến thức cơ bản","Xử lý dữ liệu và tình huống biên","Thực hành có đề đính kèm","Bài tập tổng hợp cuối chủ đề"] if not completed else ["Nhập xuất và biến","Mảng, hàm và vòng lặp"]
        for i,name in enumerate(titles):
            day = -40+i*5 if completed else [-7,-2,3,10][i]
            aid = f"trial-v2-{key}-task-{i+1}"
            exercise="Bài 1: Đọc hai số nguyên a, b và in a+b.\nBài 2: Đọc n và n số nguyên; in phần tử lớn nhất.\nKiểm thử số âm, số 0 và dữ liệu lớn."
            if key=="network":exercise="Bài 1: Viết TCP Echo Server lắng nghe cổng 9000 và trả lại chuỗi nhận từ client.\nBài 2: Viết client gửi UTF-8, nhận phản hồi; xử lý đóng kết nối và thông báo lỗi.\nNộp source, README và ít nhất ba tình huống kiểm thử."
            if key=="database":exercise="Bài 1: Thiết kế bảng độc giả, sách và phiếu mượn cho thư viện; khai báo khóa chính, khóa ngoại.\nBài 2: Viết SQL tìm sách đang mượn, số lượt mượn theo độc giả, sách chưa được mượn.\nNộp ZIP gồm schema.sql, queries.sql và dữ liệu kiểm thử."
            task={**identity(f"{key}-task-{i+1}",-20+i),"course_id":cid,"title":f"Bài tập {i+1:02} · {name}","topic":"Thực hành","description":f"Hoàn thành yêu cầu trong file đề bài của {title}. Nộp mã nguồn hoặc ZIP có README hướng dẫn chạy.\nTiêu chí: đúng chức năng 6 điểm, kiểm thử 2 điểm, trình bày 2 điểm.","due_at":at(day,hour=23),"max_attempts":5,**payload("learning-files",f"{key}-task-{i+1}.txt","de-bai.txt",f"{title} — {name}\n\n{exercise}\n")}
            if day<0: task["closed_at"]=task["due_at"]
            data["assignments"].append(task);tasks[cid].append(aid)
            for j,sid in enumerate(members):
                if not (completed or i==0 and j%5!=4 or i==1 and j%3!=2 or i==2 and j in (2,4,6)):
                    continue
                count=2 if i==1 and j%4==0 else 1
                for attempt in range(1,count+1):
                    graded=completed or i==0 or (i==1 and j%2==1)
                    score=round(6.5+(j%7)*.5,2) if graded else None
                    submitted=at(day-1 if day<0 else -1,minutes=attempt)
                    subid=f"{key}-{i+1}-{sid}-{attempt}"
                    record={**identity(subid),"created_at":submitted,"course_id":cid,"assignment_id":aid,"assignment_title":task["title"],"student_id":sid,"full_name":students[sid]["full_name"],"course_name":title,"attempt":attempt,"request_id":subid,"score":score,"feedback":"Bài làm đáp ứng yêu cầu; bổ sung thêm kiểm thử biên." if graded else "","ip":"127.0.0.1",**payload("learning-files",subid+".zip",f"{sid}_BT{i+1:02}_lan{attempt}.zip",zipped({"main.py":SUM_SOURCES["python"],"README.txt":f"Bài thực hành {title}; lần nộp {attempt}.\n"})),"grading_history":[]}
                    if graded:
                        entry={"id":subid+"-grade","score":score,"feedback":record["feedback"],"graded_at":submitted,"graded_by":"admin"}
                        record.update({"graded_at":submitted,"graded_by":"admin","grading_history":[entry]})
                    data["submissions"].append(record)
        if completed:
            for j,sid in enumerate(members):
                for component in ("midterm","final"):
                    data["grades"].append({**identity(f"{key}-{sid}-{component}",-25),"course_id":cid,"student_id":sid,"component":component,"score":round(7+(j%5)*.5,2)})
        data["events"].append({**identity(key+"-notice",-1),"course_id":cid,"title":"Tài liệu và bài thực hành đã cập nhật","description":"Xem mục Tài liệu và Bài tập; chú ý hạn nộp và kiểm tra lịch sử sau khi gửi bài.","kind":"announcement","starts_at":at(-1),"location":""})

    sum_problem={"title":"Tổng hai số nguyên","statement":"Đọc hai số nguyên a, b (|a|, |b| ≤ 10^9) từ stdin, in a+b ra stdout. Không in lời nhắc nhập.","points":100,"time_limit_ms":1000,"memory_limit_mb":256,"checker":"tokens","tests":copy.deepcopy(SUM_TESTS)}
    max_problem={"title":"Phần tử lớn nhất","statement":"Dòng đầu là n (1 ≤ n ≤ 100000); dòng sau gồm n số nguyên. In phần tử lớn nhất. Dữ liệu có thể toàn số âm.","points":100,"time_limit_ms":1500,"memory_limit_mb":256,"checker":"tokens","tests":copy.deepcopy(MAX_TESTS)}
    catalog=[]
    def exam(key,cid,title,category="test",state="idle",kind="programming",problems=None):
        course=next(c for c in data["courses"] if c["id"]==cid)
        row={"id":"trial-v2-"+key,"course_id":cid,"title":title,"description":"Bộ dùng thử LAN-LMS. Test dùng để luyện tập; giữa kỳ tính trung bình; mỗi khóa có một kỳ thi cuối kỳ.","type":kind,"assessment_type":category,"state":state,"duration_minutes":120 if state=="started" else 60,"scheduled_at":at(minutes=5) if state=="started" else at(2 if category=="midterm" else 7,hour=9),"participants":course["student_ids"],"created_at":at(-15)}
        if kind=="programming":row["programming"]={"languages":["c","cpp","java","python"],"problems":copy.deepcopy(problems or [sum_problem,max_problem])}
        else:row["file_settings"]={"exam_duration_minutes":row["duration_minutes"],"submission_policy":"configurable","max_submissions":20,"overwrite_previous":True,"accepted_submission_extensions":[".zip",".txt",".cpp",".c",".java",".py"]}
        if state=="started":row.update({"started_at":at(),"ends_at":at(minutes=120),"scheduled_at":at()})
        if state=="ended":row.update({"started_at":at(-4),"ends_at":at(-4,minutes=60),"ended_at":at(-4,minutes=60),"scheduled_at":at(-4)})
        catalog.append(row);return row
    file_exam=exam("file-test",course_ids["network"],"Test nộp file · Thực hành TCP",state="started",kind="file")
    old_file_exam=exam("file-history",course_ids["network"],"Test nộp file · Lịch sử buổi trước",state="ended",kind="file")
    old_file_exam["release_id"]="trial-v2-history-file-release"
    code_exam=exam("code-test",course_ids["network"],"Test chấm code · Tổng hai số và tìm max",state="started")
    exam("cpp-test",course_ids["cpp"],"Test lập trình C/C++/Java/Python",state="started")
    historical=exam("network-midterm-1",course_ids["network"],"Giữa kỳ 01 · Nhập xuất và số nguyên","midterm","ended",problems=[sum_problem])
    exam("network-midterm-2",course_ids["network"],"Giữa kỳ 02 · Mảng và thuật toán","midterm")
    exam("network-final",course_ids["network"],"Cuối kỳ · Thực hành lập trình mạng","final")
    exam("cpp-midterm",course_ids["cpp"],"Giữa kỳ · Nhập xuất và mảng","midterm")
    exam("cpp-final",course_ids["cpp"],"Cuối kỳ · Lập trình C++","final")
    exam("database-midterm",course_ids["database"],"Giữa kỳ · Thiết kế và truy vấn SQL","midterm",kind="file")
    exam("database-final",course_ids["database"],"Cuối kỳ · Cơ sở dữ liệu thư viện","final",kind="file")
    exam("python-final",course_ids["python"],"Cuối kỳ · Python căn bản","final","ended")

    if not code_runner.ready():
        raise RuntimeError("Docker/image classroom-judge:1 chưa sẵn sàng; chưa thay dữ liệu hiện tại.")
    programming_rows=[];attempts={}
    judge_examples=[(ids[0],"python",SUM_SOURCES["python"]),(ids[1],"cpp",SUM_SOURCES["cpp"]),(ids[2],"c",SUM_SOURCES["c"]),(ids[3],"java",SUM_SOURCES["java"]),(ids[4],"python","print(0)\n"),(ids[5],"cpp","int main( broken\n")]
    for i,(sid,language,source) in enumerate(judge_examples):
        print(f"Grading historical example {i+1}/{len(judge_examples)}: {language}",flush=True)
        result=code_runner.judge(source.encode("utf-8"),language,sum_problem)
        expected="AC" if i<4 else "WA" if i==4 else "CE"
        if result["verdict"]!=expected:raise RuntimeError(f"Bộ chấm trả {result['verdict']}, mong đợi {expected}; chưa thay dữ liệu.")
        subid=f"trial-v2-graded-{sid}"
        folder=stage/"programming-submissions"/subid;folder.mkdir()
        (folder/"source").write_bytes(source.encode("utf-8"))
        write_json(folder/"problem.json",sum_problem)
        when=at(-4,minutes=10+i)
        grade={"id":subid+"-grade","result":copy.deepcopy(result),"graded_at":when,"graded_by":"judge"}
        programming_rows.append({"id":subid,"exam_id":historical["id"],"exam_title":historical["title"],"course_id":historical["course_id"],"student_id":sid,"full_name":students[sid]["full_name"],"problem_index":0,"problem_title":sum_problem["title"],"max_score":100,"language":language,"original_filename":code_runner.LANGUAGES[language],"submitted_at":when,"state":"done","result":result,"size_bytes":len(source.encode("utf-8")),"sha256":hashlib.sha256(source.encode("utf-8")).hexdigest(),"ip":"127.0.0.1","grading_history":[grade],"graded_at":when})
        attempts[historical["id"]+":"+sid]={"started_at":historical["started_at"],"ends_at":historical["ends_at"],"status":"expired","closed_at":historical["ends_at"]}

    release="trial-v2-live-file-release"
    settings=copy.deepcopy(storage.DEFAULTS["settings.json"])
    settings.update(file_exam["file_settings"])
    settings.update({"exam_catalog_id":file_exam["id"],"exam_course_id":file_exam["course_id"],"exam_title":file_exam["title"],"exam_assessment_type":"test","exam_state":"started","exam_released":True,"exam_release_id":release,"exam_release_at":at(),"exam_started_at":at(),"exam_ends_at":at(minutes=120),"exam_closed_automatically":False,"exam_participants":ids,"distribution_mode":"selected","distribution_config":{"exam_files":["LAN_LMS_De_Thi_TCP.txt"]}})
    file_exam["release_id"]=release
    file_assignments={sid:{"exam_file":"LAN_LMS_De_Thi_TCP.txt","exam_id":file_exam["id"],"assessment_type":"test","course_id":file_exam["course_id"],"exam_title":file_exam["title"],"release_id":release,"assigned_at":at(),"started_at":None,"ends_at":None,"status":"assigned","ip_at_assignment":None} for sid in ids}
    (stage/"de-thi"/"LAN_LMS_De_Thi_TCP.txt").write_text("THỰC HÀNH NỘP FILE — LAN-LMS\n\nXây dựng TCP Client/Server gửi chuỗi và nhận phản hồi. Nộp ZIP gồm mã nguồn, README hướng dẫn chạy và mô tả kiểm thử.\nĐây là bài Test, không tính vào điểm khóa học. Giảng viên có thể chấm file trong kho Bài nộp.\n",encoding="utf-8")
    file_history={}
    for j,sid in enumerate(ids[6:10]):
        rows=[]
        for attempt in (1,2):
            stored=f"trial-v2-file-{sid}-{attempt}.zip"
            meta=payload("submissions",stored,f"{sid}_TCP_lan{attempt}.zip",zipped({"main.py":SUM_SOURCES["python"],"README.txt":"Bản nộp để thử xem lịch sử và chấm file.\n"}))
            score=8+j*.25 if j%2==0 else None
            when=at(-4,minutes=10+attempt)
            row={"id":stored[:-4],"attempt":attempt,"filename":stored,"original_filename":meta["original_filename"],"size_bytes":meta["size_bytes"],"sha256":meta["sha256"],"submitted_at":when,"course_id":old_file_exam["course_id"],"exam_id":old_file_exam["id"],"exam_title":old_file_exam["title"],"release_id":old_file_exam["release_id"],"assessment_type":"test","student_id":sid,"full_name":students[sid]["full_name"],"ip":"127.0.0.1","status":"received","payload_retained":True,"score":score,"feedback":"Đã nhận bài thực hành." if score is not None else "","grading_history":[]}
            if score is not None:row["grading_history"]=[{"id":stored+"-grade","score":score,"feedback":row["feedback"],"graded_at":at(),"graded_by":"admin"}]
            rows.append(row)
        file_history[sid]=rows

    notices=[{"id":f"trial-v2-notice-{i}","student_id":None if i%3 else ids[i%20],"title":["Kỳ thi Test lập trình đã mở","Bài tập mới có đề đính kèm","Điểm danh buổi thực hành hôm nay","Xem kết quả giữa kỳ 01"][i%4],"message":["Vào Lập trình mạng → Kỳ thi → Test chấm code để bắt đầu. Dùng bộ file trong demo-inputs để thử AC, WA, CE và TLE.","Xem đề bài, chọn file và nộp trước hạn. Mỗi lần nộp được lưu riêng để xem lại.","Giảng viên mở QR từ buổi học trên lịch; sinh viên quét ở mục Điểm danh.","Kết quả giữa kỳ và điểm bài tập được cập nhật trong Bảng điểm. Test không tính vào tổng kết."][i%4],"created_at":at(minutes=-i*35),"created_by":"Giảng viên"} for i in range(12)]
    values={"students.json":students,"learning.json":data,"exam_catalog.json":catalog,"settings.json":settings,"assignments.json":file_assignments,"submissions.json":file_history,"programming_submissions.json":programming_rows,"programming_attempts.json":attempts,"sessions.json":{},"login_attempts.json":{},"machines.json":{},"notifications.json":notices,"notification_reads.json":{},"submission_rate.json":{}}
    for name,value in values.items():write_json(stage/"data"/name,value)
    write_json(stage/"data"/"admins.json",storage.read_json("admins.json"))

    kit={"tong_hai_so.py":SUM_SOURCES["python"],"tong_hai_so.cpp":SUM_SOURCES["cpp"],"tong_hai_so.c":SUM_SOURCES["c"],"Main.java":SUM_SOURCES["java"],"tim_max.py":"n=int(input())\na=list(map(int,input().split()))\nprint(max(a))\n","sai_ket_qua.py":"print(0)\n","loi_bien_dich.cpp":"int main( broken\n","qua_thoi_gian.py":"while True:\n    pass\n","bai_tap_mau.zip":zipped({"main.py":SUM_SOURCES["python"],"README.txt":"Bài làm để thử nộp file và chấm thủ công.\n"})}
    csv_text=io.StringIO(newline="");writer=csv.DictWriter(csv_text,fieldnames=["input","output","sample"]);writer.writeheader();writer.writerows(SUM_TESTS)
    kit["testcase_tong_hai_so.csv"]=csv_text.getvalue()
    instructions=f"""# LAN-LMS — Bộ dùng thử mới

Tạo lúc {now.strftime('%d/%m/%Y %H:%M')} (Việt Nam). Tài khoản admin được giữ nguyên.
Sinh viên: SV001 đến SV020. Mật khẩu chung: 111111.
SV001 là tài khoản chính; chưa bắt đầu kỳ thi Test và chưa điểm danh hôm nay.

## Thử chấm code
1. Đăng nhập SV001, mở Lập trình mạng → Kỳ thi → Test chấm code.
2. Bấm Bắt đầu. Đồng hồ chung đã chạy từ lúc nạp bộ dữ liệu, thời lượng 120 phút.
3. Bài Tổng hai số: nộp tong_hai_so.py/c/cpp hoặc Main.java đúng ngôn ngữ để nhận AC.
4. Nộp sai_ket_qua.py để thấy WA; loi_bien_dich.cpp cho CE; qua_thoi_gian.py cho TLE.
5. Bài Phần tử lớn nhất: dùng tim_max.py. Xem test mẫu; test ẩn không lộ input/output.
6. Giảng viên xem Bài nộp → Thi lập trình để kiểm tra input, output, lịch sử và chấm lại.

## Các luồng khác
- Nộp file: Kỳ thi → Test nộp file, dùng bai_tap_mau.zip; giữ được mọi lần nộp.
- Bài tập: chọn Thực hành có đề đính kèm; xem/tải đề, nộp file rồi chấm trong vai trò admin.
- Điểm danh: admin mở Lập trình mạng → Lịch & điểm danh → buổi hôm nay → xem QR; SV001 quét QR.
- Giữa kỳ 01 đã có kết quả chấm Docker thật. Giữa kỳ 02 và Cuối kỳ ở trạng thái nháp để mở thử.
- Test không tính điểm; nhiều giữa kỳ lấy trung bình; mỗi khóa chỉ có một kỳ thi cuối kỳ.
- Python căn bản là khóa đã hoàn thành, có bảng điểm và lịch sử để xem lại.
- Khi hết 120 phút, kỳ thi đang mở tự kết thúc. Có thể mở kỳ giữa kỳ/khóa C++ hoặc tạo Test mới trong Cấu hình kỳ thi.

CSV test case và nguồn mẫu nằm cạnh file hướng dẫn này. Không in lời nhắc khi nhập dữ liệu.
"""
    kit["HUONG_DAN.md"]=instructions
    kit["tai_khoan.csv"]="student_id,full_name,password\n"+"\n".join(f"{sid},{students[sid]['full_name']},111111" for sid in ids)+"\n"
    for name,content in kit.items():
        (stage/"demo-inputs"/name).write_bytes(content.encode("utf-8") if isinstance(content,str) else content)
    (stage/"demo-inputs"/"LAN_LMS_Test_Kit.zip").write_bytes(zipped(kit))
    marker={"version":VERSION,"created_at":at(),"students":ids,"courses":course_ids,"active_code_exam":code_exam["id"],"active_file_exam":file_exam["id"],"counts":{"courses":len(data["courses"]),"students":len(students),"materials":len(data["materials"]),"assignments":len(data["assignments"]),"attendance_sessions":len(data["attendance"]),"exams":len(catalog),"assignment_attempts":len(data["submissions"]),"file_attempts":sum(map(len,file_history.values())),"real_judged_code_attempts":len(programming_rows)}}
    write_json(stage/"data"/"demo_seed.json",marker)
    validate(stage)
    print(json.dumps({"staging":str(stage),**marker},ensure_ascii=True,indent=2),flush=True)
    return stage


def validate(stage):
    stage=Path(stage)
    data=json.loads((stage/"data"/"learning.json").read_text(encoding="utf-8"))
    courses={c["id"] for c in data["courses"]}
    events={e["id"]:e for e in data["events"]}
    for key in ("materials","assignments","submissions"):
        for row in data[key]:
            if row["course_id"] not in courses:raise RuntimeError("Invalid course reference")
            if row.get("stored_name") and not (stage/"learning-files"/row["stored_name"]).is_file():raise RuntimeError("Missing learning payload")
    for row in data["attendance"]:
        if row["event_id"] not in events or events[row["event_id"]]["course_id"]!=row["course_id"]:raise RuntimeError("Unlinked attendance")
    catalog=json.loads((stage/"data"/"exam_catalog.json").read_text(encoding="utf-8"))
    for cid in courses:
        if sum(e["course_id"]==cid and e["assessment_type"]=="final" for e in catalog)!=1:raise RuntimeError("Expected one final per course")
    for row in json.loads((stage/"data"/"programming_submissions.json").read_text(encoding="utf-8")):
        source=stage/"programming-submissions"/row["id"]/"source"
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=row["sha256"]:raise RuntimeError("Missing or inconsistent source")


def apply(stage, root=None):
    root=Path(root or config.BASE_DIR).resolve();stage=Path(stage).resolve()
    if not stage.is_relative_to(root/"backups") or not stage.name.startswith(".staging-trial-"):
        raise RuntimeError("Staging directory must be the prepared folder inside this project's backups.")
    try:
        connection=socket.create_connection(("127.0.0.1",config.PORT),timeout=.5)
    except OSError:pass
    else:
        connection.close();raise RuntimeError("Stop the project server before applying the dataset.")
    validate(stage)
    now=datetime.now(timezone.utc)
    settings=json.loads((stage/"data"/"settings.json").read_text(encoding="utf-8"))
    settings.update({"exam_started_at":now.isoformat(),"exam_ends_at":(now+timedelta(minutes=120)).isoformat(),"exam_release_at":now.isoformat()})
    write_json(stage/"data"/"settings.json",settings)
    catalog=json.loads((stage/"data"/"exam_catalog.json").read_text(encoding="utf-8"))
    for exam in catalog:
        if exam["state"]=="started":exam.update({"started_at":now.isoformat(),"ends_at":(now+timedelta(minutes=120)).isoformat(),"scheduled_at":now.isoformat()})
    write_json(stage/"data"/"exam_catalog.json",catalog)
    # Read the latest admin credentials only after the live server has stopped.
    write_json(stage/"data"/"admins.json",json.loads((root/"data"/"admins.json").read_text(encoding="utf-8")))
    for name in ("sessions.json","login_attempts.json","submission_rate.json"):
        write_json(stage/"data"/name,{})
    stamp=datetime.now(VN).strftime("%Y%m%d-%H%M%S")
    backup=root/"backups"/("before-trial-reset-"+stamp+"-"+secrets.token_hex(2))
    backup.mkdir()
    moved=[];installed=[]
    try:
        for name in DIRECTORIES+("logs",):
            source=root/name;target=backup/name
            if source.parent!=root or not source.resolve().is_relative_to(root) or target.parent!=backup:raise RuntimeError("Unsafe move target")
            if source.exists():source.rename(target);moved.append(name)
        for name in DIRECTORIES:
            source=stage/name;target=root/name
            if not source.resolve().is_relative_to(stage) or target.parent!=root:raise RuntimeError("Unsafe install target")
            source.rename(target);installed.append(name)
        (root/"logs").mkdir()
        marker=json.loads((root/"data"/"demo_seed.json").read_text(encoding="utf-8"))
        marker.update({"backup":str(backup),"applied_at":now.isoformat()})
        write_json(root/"data"/"demo_seed.json",marker)
        storage.audit("setup.trial_dataset_replaced","local-user","127.0.0.1",{"backup":str(backup),"version":VERSION})
    except Exception:
        for name in reversed(installed):
            if (root/name).exists():(root/name).rename(stage/name)
        if (root/"logs").exists() and not any((root/"logs").iterdir()):(root/"logs").rmdir()
        for name in reversed(moved):(backup/name).rename(root/name)
        raise
    print(json.dumps({"status":"applied","backup":str(backup),"counts":marker["counts"]},ensure_ascii=True,indent=2),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare",action="store_true")
    parser.add_argument("--apply",metavar="STAGING_DIRECTORY")
    args=parser.parse_args()
    if args.apply:apply(args.apply)
    elif args.prepare:prepare()
    else:parser.print_help()


if __name__=="__main__":
    from .runtime import data_lease
    from .config import DATA_DIR
    with data_lease(DATA_DIR):
        main()
