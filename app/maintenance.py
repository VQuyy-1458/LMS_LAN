"""Verified snapshots and isolated restore rehearsals, without replacing live data."""
import argparse
import hashlib
import json
import logging
import os
import shutil
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import storage, learning, programming, submissions, code_runner
from .config import RUNTIME_DIR, EXAM_DIR, STATIC_DIR
from .runtime import data_lease

logger = logging.getLogger(__name__)


def roots():
    return {"data":storage.DATA_DIR, "learning-files":learning.FILES, "submissions":submissions.UPLOAD_DIR,
            "programming-submissions":programming.FILES, "de-thi":EXAM_DIR}


def digest(path):
    with path.open("rb") as source:
        value=hashlib.sha256()
        for block in iter(lambda:source.read(1024*1024),b""):value.update(block)
        return value.hexdigest()


def reference_issues(locations, metadata):
    issues=[]
    def require(category,name):
        root=locations[category].resolve()
        path=root/name
        if not path.resolve().is_relative_to(root) or not path.is_file():
            issues.append("Thiếu payload được tham chiếu: "+category+"/"+str(name))
    data=metadata.get("learning.json",{})
    for collection in ("materials","assignments","submissions"):
        for row in data.get(collection,[]):
            if row.get("stored_name"):require("learning-files",row["stored_name"])
    for rows in metadata.get("submissions.json",{}).values():
        for row in rows:
            if row.get("payload_retained",False):require("submissions",row["filename"])
    for row in metadata.get("programming_submissions.json",[]):
        require("programming-submissions",row["id"]+"/source")
        require("programming-submissions",row["id"]+"/problem.json")
    settings=metadata.get("settings.json",{})
    if settings.get("exam_state") in {"distributed","started"}:
        for row in metadata.get("assignments.json",{}).values():
            if row.get("release_id")==settings.get("exam_release_id") and row.get("exam_file"):require("de-thi",row["exam_file"])
    return issues


def snapshot(destination=None, prefix="manual"):
    destination = Path(destination) if destination else RUNTIME_DIR/"backups"
    destination.mkdir(parents=True,exist_ok=True)
    snapshot_name=prefix+"-"+datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")+"-"+uuid.uuid4().hex[:8]
    staged=destination/(".pending-"+snapshot_name)
    staged.mkdir()
    try:
        with learning.LOCK, storage.transaction():
            locations=roots()
            metadata={p.name:storage.read_json(p.name) for p in storage.DATA_DIR.glob("*.json") if not p.name.startswith(".")}
            payloads=[]
            for category,root in locations.items():
                if category=="data" or not root.exists():continue
                for path in root.rglob("*"):
                    if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root.resolve()) and not path.name.startswith("."):
                        payloads.append((category,path.relative_to(root),path))
        files=[]
        for name,value in metadata.items():
            target=staged/"data"/name
            storage.atomic_write(target,value)
            files.append({"path":target.relative_to(staged).as_posix(),"sha256":digest(target),"size":target.stat().st_size})
        for category,relative,source in payloads:
            target=staged/category/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            expected=digest(source)
            shutil.copyfile(source,target)
            with target.open("r+b") as output:output.flush();os.fsync(output.fileno())
            if digest(target)!=expected or digest(source)!=expected:raise RuntimeError("Một file đã thay đổi trong lúc backup; hãy thử lại.")
            files.append({"path":target.relative_to(staged).as_posix(),"sha256":expected,"size":target.stat().st_size})
        storage.atomic_write(staged/"manifest.json",{"version":1,"created_at":storage.utc_now(),"files":files})
        verify(staged)
        final=destination/snapshot_name
        staged.rename(final)
        return final
    except BaseException:
        if staged.resolve().parent==destination.resolve():shutil.rmtree(staged,ignore_errors=True)
        raise


def verify(folder):
    folder=Path(folder).resolve()
    manifest=json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version")!=1 or not isinstance(manifest.get("files"),list):raise ValueError("Manifest backup không hợp lệ.")
    seen=set()
    for record in manifest["files"]:
        relative=Path(record["path"])
        path=folder/relative
        if not relative.parts or relative.is_absolute() or ".." in relative.parts or relative.parts[0] not in roots() or path.is_symlink() or not path.resolve().is_relative_to(folder) or record["path"] in seen:
            raise ValueError("Đường dẫn backup không hợp lệ.")
        seen.add(record["path"])
        if path.stat().st_size!=record["size"] or digest(path)!=record["sha256"]:raise ValueError("Backup bị thiếu hoặc sai hash: "+record["path"])
    if "data/students.json" not in seen or "data/settings.json" not in seen:raise ValueError("Backup thiếu dữ liệu bắt buộc.")
    metadata={path.name:json.loads(path.read_text(encoding="utf-8")) for path in (folder/"data").glob("*.json")}
    issues=reference_issues({category:folder/category for category in roots()},metadata)
    if issues:raise ValueError(issues[0])
    return manifest


def restore_copy(folder,target):
    manifest=verify(folder)
    target=Path(target).resolve()
    if target.exists() and any(target.iterdir()):raise ValueError("Chỉ phục hồi vào thư mục mới hoặc rỗng; dữ liệu đang dùng không bị ghi đè.")
    target.mkdir(parents=True,exist_ok=True)
    for record in manifest["files"]:
        destination=target/record["path"]
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(Path(folder)/record["path"],destination)
        if digest(destination)!=record["sha256"]:raise ValueError("File phục hồi sai hash.")
    # A restored environment must not resurrect old browser authentication.
    storage.atomic_write(target/"data"/"sessions.json",{})
    storage.atomic_write(target/"data"/"auth_throttle.json",{})
    return target


def doctor(execute=False):
    issues=[]
    with storage.transaction():
        metadata={}
        for path in storage.DATA_DIR.glob("*.json"):
            if not path.name.startswith("."):metadata[path.name]=storage.read_json(path.name)
        issues.extend(reference_issues(roots(),metadata))
    if shutil.disk_usage(storage.DATA_DIR).free < 512*1024*1024:issues.append("Dung lượng đĩa trống dưới 512 MiB.")
    if not (STATIC_DIR/"css"/"tailwind.css").is_file():issues.append("Thiếu CSS đã build.")
    judge=code_runner.status()
    if not judge["ready"]:issues.append(judge["detail"])
    if execute and judge["ready"]:
        problem={"points":1,"time_limit_ms":1000,"memory_limit_mb":256,"checker":"tokens","tests":[{"input":"","output":"3","sample":True}]}
        result=code_runner.judge(b"print(3)","python",problem)
        if result["verdict"]!="AC":issues.append("Chấm mẫu không đạt AC.")
    return {"ready":not issues,"issues":issues,"judge":judge}


def start_backups():
    stop=threading.Event()
    def run():
        if stop.wait(30):return
        while not stop.is_set():
            try:
                created=snapshot(prefix="auto")
                old=sorted(created.parent.glob("auto-*"),key=lambda p:p.name,reverse=True)
                for path in old[7:]:
                    if path.is_dir() and path.resolve().parent==created.parent.resolve() and (path/"manifest.json").is_file():shutil.rmtree(path)
            except Exception:logger.exception("Automatic backup failed")
            stop.wait(6*60*60)
    worker=threading.Thread(target=run,name="verified-backups",daemon=True);worker.start()
    return stop,worker


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=["check","backup","verify","restore-copy"])
    parser.add_argument("path",nargs="?")
    parser.add_argument("--target")
    parser.add_argument("--execute",action="store_true")
    args=parser.parse_args()
    if args.action=="check":
        with data_lease(storage.DATA_DIR):
            result=doctor(args.execute)
            print(json.dumps(result,ensure_ascii=False,indent=2))
            if not result["ready"]:raise SystemExit(1)
    elif args.action=="backup":
        with data_lease(storage.DATA_DIR):print(snapshot(args.target))
    elif args.action=="verify":print(json.dumps({"files":len(verify(args.path)["files"]),"valid":True}))
    elif args.action=="restore-copy":
        if not args.target:parser.error("restore-copy cần --target")
        print(restore_copy(args.path,args.target))


if __name__=="__main__":main()
