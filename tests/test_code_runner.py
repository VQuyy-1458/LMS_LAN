"""Real Docker checks are opt-in; ordinary unit tests need no daemon."""
import os
import unittest
import subprocess
from types import SimpleNamespace
from unittest.mock import patch
from app import code_runner


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        # Mocked daemon failures must not leak into subsequent real-Docker tests.
        code_runner._last_status = None
        self.addCleanup(setattr,code_runner,"_last_status",None)

    def test_progress_reports_compilation_and_each_completed_test(self):
        problem={"points":10,"time_limit_ms":1000,"memory_limit_mb":256,"checker":"tokens","tests":[{"input":"1 2","output":"3","sample":True},{"input":"100 200","output":"300","sample":False}]}
        run={"exit":0,"stdout":"","stderr":"","overflow":False,"oom":False,"system_error":False,"time_ms":10}
        phases=[]
        with patch.object(code_runner,"ready",return_value=True),patch.object(code_runner,"_container",side_effect=[run,{**run,"stdout":"3"},{**run,"stdout":"300"}]):
            result=code_runner.judge(b"int main(){}","cpp",problem,progress=lambda *args:phases.append(args))
        self.assertEqual(result["verdict"],"AC")
        self.assertEqual(phases,[("compiling",0,2),("judging",0,2),("judging",1,2),("judging",2,2)])

    def test_judge_status_reports_missing_image_and_unresponsive_daemon(self):
        with patch.object(code_runner, "docker", return_value="docker"), patch.object(code_runner.subprocess, "run", return_value=SimpleNamespace(returncode=1, stderr=b"No such image: classroom-judge:1")):
            self.assertFalse(code_runner.status()["ready"])
            self.assertIn("image", code_runner.status()["detail"])
        with patch.object(code_runner, "docker", return_value="docker"), patch.object(code_runner.subprocess, "run", side_effect=subprocess.TimeoutExpired("docker", 8)):
            self.assertFalse(code_runner.ready())
            self.assertIn("không phản hồi", code_runner.status()["detail"])

    def test_cleanup_timeout_does_not_mask_a_grading_result(self):
        with patch.object(code_runner, "docker", return_value="docker"), patch.object(code_runner.subprocess, "run", side_effect=subprocess.TimeoutExpired("docker", 8)), self.assertLogs("app.code_runner", level="WARNING"):
            code_runner._remove_container("css-judge-test")

    def test_checker_modes(self):
        self.assertTrue(code_runner.matches("3 \n", "3", "tokens"))
        self.assertFalse(code_runner.matches("3 \n", "3\n", "exact"))
        self.assertTrue(code_runner.matches("3\r\n", "3\n", "exact"))


@unittest.skipUnless(os.getenv("CSS_JUDGE_TESTS") == "1", "Set CSS_JUDGE_TESTS=1 for actual Docker execution")
class DockerJudgeTests(unittest.TestCase):
    def setUp(self):
        self.problem = {"points": 10, "time_limit_ms": 1000, "memory_limit_mb": 256, "checker": "tokens", "tests": [{"input": "1 2\n", "output": "3\n", "sample": True}, {"input": "100 200\n", "output": "300", "sample": False}]}

    def test_four_toolchains(self):
        sources = {
            "c": b'#include <stdio.h>\nint main(){int a,b;scanf("%d%d",&a,&b);printf("%d\\n",a+b);}',
            "cpp": b'#include <iostream>\nint main(){int a,b;std::cin>>a>>b;std::cout<<a+b<<"\\n";}',
            "java": b'import java.util.*;public class Main{public static void main(String[]a){Scanner s=new Scanner(System.in);System.out.println(s.nextInt()+s.nextInt());}}',
            "python": b'a,b=map(int,input().split());print(a+b)',
        }
        for language, source in sources.items():
            with self.subTest(language=language):
                result = code_runner.judge(b'\xef\xbb\xbf'+source, language, self.problem)
                self.assertEqual(result["verdict"], "AC", result)
                self.assertEqual(result["score"], 10)

    def test_verdicts_and_partial_score(self):
        partial = code_runner.judge(b'print(3)', "python", self.problem)
        self.assertEqual((partial["verdict"], partial["score"], partial["passed"]), ("WA", 5, 1))
        self.assertEqual(partial["tests"][1]["actual"], "3\n")
        memory = code_runner.judge(b'a=bytearray(400_000_000);print(3)', "python", {**self.problem, "memory_limit_mb": 64, "time_limit_ms": 1500, "tests": self.problem["tests"][:1]})
        self.assertEqual(memory["verdict"], "MLE", memory)
        for source, language, verdict in [(b'int main( broken', "cpp", "CE"), (b'raise ValueError("bad")', "python", "RE"), (b'while True: pass', "python", "TLE"), (b'print("x"*2000000)', "python", "OLE")]:
            with self.subTest(verdict=verdict):
                result = code_runner.judge(source, language, {**self.problem, "time_limit_ms": 200 if verdict == "TLE" else 1500, "tests": self.problem["tests"][:1]})
                self.assertEqual(result["verdict"], verdict, result)

    def test_no_host_files_or_network(self):
        source = b'import os,socket\nassert not os.path.exists("/work/problem.json")\ntry:\n socket.create_connection(("1.1.1.1",80),0.1)\n print("network reachable")\nexcept OSError: print(3)'
        result = code_runner.judge(source, "python", {**self.problem, "tests": self.problem["tests"][:1]})
        self.assertEqual(result["verdict"], "AC", result)

    def test_child_exit_codes_are_not_mistaken_for_timeout(self):
        for code in (124,137,143):
            with self.subTest(code=code):
                result=code_runner.judge(f"raise SystemExit({code})".encode(),"python",{**self.problem,"tests":self.problem["tests"][:1]})
                self.assertEqual(result["verdict"],"RE",result)
