"""One-click LAN startup for this workspace; existing accounts are preserved."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
import webbrowser

from .runtime import data_lease

ROOT=Path(__file__).resolve().parents[1]


def lan_addresses():
    for destination in ("192.0.2.1","8.8.8.8"):
        try:
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as route:
                route.connect((destination,80))
                address=route.getsockname()[0]
                if not address.startswith(("127.","169.254.")) and address!="0.0.0.0":return [address]
        except OSError:
            pass
    return []


def available_port(preferred):
    for port in range(preferred,min(preferred+100,65536)):
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as probe:
            if hasattr(socket,"SO_EXCLUSIVEADDRUSE"):probe.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
            try:probe.bind(("0.0.0.0",port))
            except OSError:continue
            return port
    raise RuntimeError("Không tìm được cổng trống. Hãy đóng ứng dụng đang chiếm cổng rồi chạy lại.")


def probe_instance(info):
    try:
        context=ssl._create_unverified_context() if info["scheme"]=="https" else None
        # Bypass proxy settings for this local-only identity check.
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=context))
        with opener.open(f'{info["scheme"]}://127.0.0.1:{info["port"]}/health',timeout=1) as response:
            data=json.load(response)
        return data.get("status")=="ok" and data.get("launcher_id")==info["instance"]
    except (OSError,ValueError,KeyError,urllib.error.URLError):return False


def show_addresses(info,open_browser):
    print("\n"+"="*62)
    print("LMS_LAN ĐÃ SẴN SÀNG")
    local=f'{info["scheme"]}://127.0.0.1:{info["port"]}/login'
    print("Trên máy này : "+local)
    addresses=lan_addresses()
    for address in addresses:print(f'Máy khác LAN : {info["scheme"]}://{address}:{info["port"]}/login')
    if not addresses:print("Chưa thấy địa chỉ LAN. Hãy kết nối Wi-Fi hoặc dây mạng.")
    print("Các máy cần kết nối cùng mạng Wi-Fi/LAN.")
    print("Giữ cửa sổ chạy web mở. Nhấn Ctrl+C để dừng web.")
    print("="*62+"\n")
    if open_browser:webbrowser.open(local)


def quiet_process():
    options={"creationflags":getattr(subprocess,"CREATE_NO_WINDOW",0)}
    if os.name=="nt":
        startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
        options["startupinfo"]=startup
    return options


def firewall(port,logs):
    if os.name!="nt":return
    python=str(Path(getattr(sys,"_base_executable",sys.executable)).resolve())
    rule="LMS_LAN-Run-"+hashlib.sha256(str(ROOT).encode()).hexdigest()[:12]+"-"+str(port)
    args=["powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-File",str(ROOT/"scripts"/"enable_lan_firewall.ps1"),"-Port",str(port),"-PythonPath",python,"-RuleName",rule]
    try:
        checked=subprocess.run(args+["-CheckOnly"],capture_output=True,timeout=20,**quiet_process())
        if checked.returncode==0:
            print("[LAN] Quyền Windows Firewall đã sẵn sàng.");return
        print("[LAN] Đang mở quyền truy cập LAN. Chọn Yes nếu Windows hỏi quyền.")
        result=subprocess.run(args,capture_output=True,timeout=180,**quiet_process())
        (logs/"lan-firewall.log").write_bytes(result.stdout+result.stderr)
        if result.returncode==0:print("[LAN] Đã cho phép các máy trong mạng LAN truy cập web.")
        else:print("[LAN] Chưa có quyền Firewall. Chạy lại file và cho phép hộp thoại Windows; xem logs/lan-firewall.log.")
    except (OSError,subprocess.TimeoutExpired) as error:
        print("[LAN] Chưa cấu hình được Firewall: "+str(error))


def add_docker_to_path():
    candidates=[Path(os.getenv("ProgramFiles",r"C:\Program Files"))/"Docker"/"Docker"/"resources"/"bin",
                Path(os.getenv("LOCALAPPDATA",str(Path.home())))/"Programs"/"DockerDesktop"/"resources"/"bin"]
    for folder in candidates:
        if (folder/"docker.exe").is_file():os.environ["PATH"]=str(folder)+os.pathsep+os.environ.get("PATH","")


def prepare_docker(stop,logs):
    docker=shutil.which("docker")
    if not docker:
        print("[Bộ chấm] Chưa thấy Docker. Web vẫn dùng được; chấm code cần Docker Desktop.");return
    def engine_ready():
        try:
            result=subprocess.run([docker,"info","--format","{{.OSType}}"],capture_output=True,timeout=5,**quiet_process())
            return result.returncode==0 and result.stdout.strip()==b"linux"
        except (OSError,subprocess.TimeoutExpired):return False
    try:
        if not engine_ready():
            desktop=Path(os.getenv("ProgramFiles",r"C:\Program Files"))/"Docker"/"Docker"/"Docker Desktop.exe"
            if desktop.is_file():
                print("[Bộ chấm] Đang khởi động Docker Desktop...")
                subprocess.Popen([str(desktop)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**quiet_process())
            deadline=time.monotonic()+120
            while not stop.is_set() and time.monotonic()<deadline:
                if engine_ready():break
                stop.wait(2)
            else:
                if not stop.is_set():print("[Bộ chấm] Docker chưa sẵn sàng. Web đã chạy; hãy kiểm tra Docker Desktop.")
                return
        if stop.is_set():return
        image=os.getenv("CSS_JUDGE_IMAGE","classroom-judge:1")
        inspected=subprocess.run([docker,"image","inspect",image],capture_output=True,timeout=10,**quiet_process())
        if inspected.returncode:
            print("[Bộ chấm] Đang tạo image lần đầu; xem tiến độ tại logs/lan-docker-build.log.")
            with (logs/"lan-docker-build.log").open("wb") as output:
                process=subprocess.Popen([docker,"build","-t",image,str(ROOT/"judge")],stdout=output,stderr=subprocess.STDOUT,**quiet_process())
                deadline=time.monotonic()+1200
                while process.poll() is None and not stop.is_set() and time.monotonic()<deadline:stop.wait(1)
                if process.poll() is None:
                    process.terminate();process.wait(timeout=10)
                if stop.is_set():return
                if process.returncode:
                    print("[Bộ chấm] Tạo image chưa thành công; xem logs/lan-docker-build.log.");return
        print("[Bộ chấm] Docker và image chấm lập trình đã sẵn sàng.")
    except (OSError,subprocess.TimeoutExpired) as error:print("[Bộ chấm] "+str(error))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port",type=int,default=os.getenv("CSS_PORT","8080"))
    parser.add_argument("--no-browser",action="store_true")
    parser.add_argument("--skip-docker",action="store_true")
    parser.add_argument("--skip-firewall",action="store_true")
    parser.add_argument("--check",action="store_true")
    args=parser.parse_args()
    if not 1<=args.port<=65535:parser.error("Cổng phải từ 1 đến 65535.")
    runtime=Path(os.getenv("CSS_DATA_ROOT",str(ROOT))).resolve()
    logs=runtime/"logs";marker=logs/"lan-launch"/"server.json"
    add_docker_to_path()
    if args.check:
        print(json.dumps({"project":str(ROOT),"data_root":str(runtime),"bind":"0.0.0.0","available_port":available_port(args.port),"lan":lan_addresses(),"docker_found":bool(shutil.which("docker"))},ensure_ascii=False,indent=2));return 0
    def existing():
        try:info=json.loads(marker.read_text(encoding="utf-8"))
        except (OSError,ValueError):return None
        return info if info.get("root")==str(ROOT) and probe_instance(info) else None
    previous=existing()
    if previous:
        print("Web đã chạy ở cửa sổ khác. Đang mở lại trang đăng nhập.")
        show_addresses(previous,not args.no_browser)
        if not args.skip_firewall:firewall(previous["port"],logs)
        return 0
    try:
        with data_lease(logs/"lan-launch"):
            port=available_port(args.port)
            if port!=args.port:print(f"Cổng {args.port} đang được dùng. Web sẽ chạy ở cổng {port}.")
            os.environ.update(CSS_HOST="0.0.0.0",CSS_PORT=str(port),CSS_LAUNCH_ID=uuid.uuid4().hex)
            info={"root":str(ROOT),"instance":os.environ["CSS_LAUNCH_ID"],"port":port,"scheme":"https" if os.getenv("CSS_TLS_CERT") and os.getenv("CSS_TLS_KEY") else "http"}
            marker.write_text(json.dumps(info),encoding="utf-8")
            stop=threading.Event()
            def ready():
                deadline=time.monotonic()+40
                while not stop.is_set() and time.monotonic()<deadline:
                    if probe_instance(info):show_addresses(info,not args.no_browser);return
                    stop.wait(.3)
                if not stop.is_set():print("Web chưa phản hồi. Kiểm tra thông báo lỗi trong cửa sổ này.")
            threading.Thread(target=ready,daemon=True).start()
            if not args.skip_firewall:threading.Thread(target=firewall,args=(port,logs),daemon=True).start()
            if not args.skip_docker:threading.Thread(target=prepare_docker,args=(stop,logs),daemon=True).start()
            try:
                from .main import main as run
                run()
            finally:stop.set()
        return 0
    except RuntimeError as error:
        # Another click may arrive while the first window is still starting.
        for _ in range(20):
            previous=existing()
            if previous:
                show_addresses(previous,not args.no_browser);return 0
            time.sleep(.3)
        print("Không khởi động được web: "+str(error));return 1


if __name__=="__main__":raise SystemExit(main())
