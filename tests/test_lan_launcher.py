import contextlib
import io
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import subprocess
import time
import unittest
from unittest.mock import patch,MagicMock

from app import lan_launcher as launcher


class LanLauncherTests(unittest.TestCase):
    def test_busy_port_is_skipped_without_stopping_other_application(self):
        with socket.socket() as busy:
            busy.bind(("0.0.0.0",0));busy.listen()
            port=busy.getsockname()[1]
            if port==65535:self.skipTest("No higher port")
            selected=launcher.available_port(port)
            self.assertNotEqual(selected,port)
            with socket.socket() as client:
                client.settimeout(1);client.connect(("127.0.0.1",port))

    def test_instance_check_rejects_another_server_on_same_port(self):
        info={"scheme":"http","port":8080,"instance":"ours"}
        for identity,expected in (("other",False),("ours",True)):
            response=io.BytesIO(json.dumps({"status":"ok","launcher_id":identity}).encode())
            opener=MagicMock();opener.open.return_value=response
            with patch.object(launcher.urllib.request,"build_opener",return_value=opener):
                self.assertEqual(launcher.probe_instance(info),expected)

    def test_check_mode_does_not_create_runtime_files_or_start_helpers(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/"unused"
            with patch.dict(os.environ,{"CSS_DATA_ROOT":str(root)}),patch.object(sys,"argv",["launcher","--check"]),patch.object(launcher,"add_docker_to_path"),patch.object(launcher,"available_port",return_value=8080),patch.object(launcher,"lan_addresses",return_value=["192.168.1.100"]),contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(launcher.main(),0)
            self.assertEqual(json.loads(output.getvalue())["bind"],"0.0.0.0")
            self.assertFalse(root.exists())

    def test_second_click_reuses_running_server_and_preserves_marker(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);marker=root/"logs"/"lan-launch"/"server.json";marker.parent.mkdir(parents=True)
            info={"root":str(launcher.ROOT),"instance":"existing","port":8087,"scheme":"http"}
            marker.write_text(json.dumps(info),encoding="utf-8")
            with patch.dict(os.environ,{"CSS_DATA_ROOT":str(root)}),patch.object(sys,"argv",["launcher","--no-browser","--skip-firewall","--skip-docker"]),patch.object(launcher,"probe_instance",return_value=True),patch.object(launcher,"add_docker_to_path"),patch.object(launcher,"data_lease") as lease,patch.object(launcher,"show_addresses") as show,contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(launcher.main(),0)
            lease.assert_not_called();show.assert_called_once_with(info,False)
            self.assertEqual(json.loads(marker.read_text()),info)

    @unittest.skipUnless(os.name=="nt","Windows Firewall integration")
    def test_existing_firewall_rule_does_not_request_elevation(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(launcher.subprocess,"run") as run,contextlib.redirect_stdout(io.StringIO()):
            run.return_value.returncode=0
            launcher.firewall(8080,Path(temp))
            self.assertEqual(run.call_count,1)
            self.assertEqual(run.call_args.args[0][-1],"-CheckOnly")

    def test_missing_docker_does_not_stop_web_or_attempt_installation(self):
        import threading
        with patch.object(launcher.shutil,"which",return_value=None),patch.object(launcher.subprocess,"Popen") as process,contextlib.redirect_stdout(io.StringIO()):
            launcher.prepare_docker(threading.Event(),Path("unused"))
        process.assert_not_called()

    def test_real_startup_lan_access_and_second_click(self):
        with tempfile.TemporaryDirectory(prefix="lms-lan-launch-") as temp:
            root=Path(temp)
            with socket.socket() as available:
                available.bind(("0.0.0.0",0));port=available.getsockname()[1]
            command=[sys.executable,"-u","-m","app.lan_launcher","--port",str(port),"--no-browser","--skip-docker","--skip-firewall"]
            environment={**os.environ,"CSS_DATA_ROOT":str(root),"PYTHONUTF8":"1","PYTHONDONTWRITEBYTECODE":"1"}
            environment.pop("CSS_TLS_CERT",None);environment.pop("CSS_TLS_KEY",None)
            with (root/"server.log").open("wb") as output:
                process=subprocess.Popen(command,cwd=launcher.ROOT,env=environment,stdout=output,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
                try:
                    deadline=time.monotonic()+20
                    info=None
                    while time.monotonic()<deadline:
                        if process.poll() is not None:self.fail((root/"server.log").read_text(encoding="utf-8"))
                        try:
                            info=json.loads((root/"logs"/"lan-launch"/"server.json").read_text())
                            if launcher.probe_instance(info):break
                        except (OSError,ValueError):pass
                        time.sleep(.1)
                    else:self.fail("Server was not ready: "+(root/"server.log").read_text(encoding="utf-8"))
                    opener=launcher.urllib.request.build_opener(launcher.urllib.request.ProxyHandler({}))
                    addresses=launcher.lan_addresses()
                    for address in ["127.0.0.1",*addresses]:
                        with opener.open(f'http://{address}:{info["port"]}/login',timeout=3) as response:
                            self.assertEqual(response.status,200)
                    second=subprocess.run(command,cwd=launcher.ROOT,env=environment,capture_output=True,timeout=10)
                    self.assertEqual(second.returncode,0,second.stderr.decode("utf-8","replace"))
                    current=json.loads((root/"logs"/"lan-launch"/"server.json").read_text())
                    self.assertEqual(current,info)
                    self.assertTrue(launcher.probe_instance(info))
                finally:
                    if process.poll() is None:
                        if os.name=="nt":subprocess.run(["taskkill","/PID",str(process.pid),"/T","/F"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                        else:process.terminate()
                    process.wait(timeout=10)
