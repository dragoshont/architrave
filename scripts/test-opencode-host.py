#!/usr/bin/env python3
"""OpenCode session bridge against a fake loopback server (fixture, not live evidence)."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from architrave_runtime import RunStore, RuntimeFailure
from opencode_host import OpenCodeServer, dispatch


class FakeOpenCode(BaseHTTPRequestHandler):
    scenario: dict = {}

    def log_message(self, *args):
        pass

    def reply(self, code, body=None):
        raw = b"" if body is None else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        s = self.scenario
        s.setdefault("calls", []).append(("GET", self.path))
        if self.path == "/api/info":
            return self.reply(200, {"version": "fixture", "pid": 1})
        if self.path.startswith("/api/agent/"):
            return self.reply(200 if self.path.endswith(("/explore", "/general")) else 404, {"data": {}})
        if self.path == "/api/session/active":
            if s.get("running") and not s.get("hang"):
                for relative in s.get("writes", []):
                    target = Path(s["workspace"]) / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text("worker edit\n", encoding="utf-8")
                s["running"] = False
            return self.reply(200, {"data": {"ses_fixture": {"type": "running"}} if s.get("running") else {}})
        if self.path == "/api/session/ses_fixture/permission":
            return self.reply(200, {"data": s.get("permissions", [])})
        if self.path == "/api/session/ses_fixture":
            return self.reply(200, {"data": {"id": "ses_fixture", "outcome": s.get("outcome", "succeeded"),
                                             "tokens": {"input": 10, "output": 5}}})
        if self.path.startswith("/api/session/ses_fixture/message"):
            return self.reply(200, {"data": [{"type": "assistant", "model": {"providerID": "p", "id": "m"}, "content": [
                {"type": "reasoning", "text": "hidden"}, {"type": "text", "text": "edited src/app.txt"}]}],
                "cursor": {}})
        self.reply(404, {"_tag": "NotFound", "message": self.path})

    def do_POST(self):
        s = self.scenario
        length = int(self.headers.get("content-length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        s.setdefault("calls", []).append(("POST", self.path))
        if self.path == "/api/session":
            s["agent"] = body["agent"]
            directory = s.get("directory", body["location"]["directory"])
            s["workspace"] = body["location"]["directory"]
            return self.reply(200, {"data": {"id": "ses_fixture", "location": {"directory": directory}}})
        if self.path == "/api/session/ses_fixture/prompt":
            s["prompt"] = body["text"]
            s["running"] = True
            return self.reply(200, {"data": {"id": "msg"}})
        if self.path == "/api/session/ses_fixture/interrupt":
            s["interrupted"] = True
            if not s.get("stuck"):
                s["running"] = False
            return self.reply(200, {"interrupted": True})
        self.reply(404, {"_tag": "NotFound", "message": self.path})


class OpenCodeHostTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="architrave opencode ")
        self.repo = Path(self.temp.name) / "app"
        self.repo.mkdir()
        for argv in (["git", "init", "-q"], ["git", "config", "user.email", "fixture@example.invalid"],
                     ["git", "config", "user.name", "Fixture"]):
            subprocess.run(argv, cwd=self.repo, check=True, capture_output=True)
        (self.repo / "README.md").write_text("fixture\n", encoding="utf-8")
        (self.repo / ".gitignore").write_text(
            ".architrave/runs/\n.architrave/worktrees/\n.architrave/runtime.key\n.architrave/resources.lock\n",
            encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "fixture"], cwd=self.repo, check=True, capture_output=True)
        self.store = RunStore(self.repo)
        FakeOpenCode.scenario = {}
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), FakeOpenCode)
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        self.server = OpenCodeServer(f"http://127.0.0.1:{self.http.server_port}", "opencode", "fixture")

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.temp.cleanup()

    def task(self, mutable=None, timeout=60):
        state = self.store.create(
            run_id="fixture", goal="OpenCode worker", outcome="Verified fixture", autonomy_scope="approved-program",
            policy_allow=[{"scope": "repository", "operations": ["edit"]}] if mutable else None,
            criteria=[{"id": "FIX", "description": "Fixture passes", "scope": "fixture", "risk": "R0",
                       "verificationType": "deterministic", "status": "UNTESTED", "evidenceRefs": [], "blocking": True}])
        self.store.add_task(state["runId"], {
            "id": "work", "objective": "Edit the fixture.", "workerProfile": "native", "pushback": "KEEP:test fixture",
            "acceptanceCriteria": ["FIX"], "risk": "R0", "mutablePaths": mutable or [],
            "workPacket": {"execution": None, "budget": {"timeoutSeconds": timeout, "maxOutputBytes": 4096}},
        })
        return state["runId"], "work"

    def test_round_trip_returns_bounded_candidate_without_completing_task(self):
        run_id, task_id = self.task(["src/**"])
        FakeOpenCode.scenario["writes"] = ["src/app.txt"]
        result = dispatch(self.store, self.server, run_id, task_id, None)
        self.assertEqual("candidate", result["status"])
        self.assertEqual(["src/app.txt"], result["changedPaths"])
        self.assertEqual("edited src/app.txt", result["summary"])
        self.assertEqual("general", FakeOpenCode.scenario["agent"])
        self.assertIn("Return a candidate", FakeOpenCode.scenario["prompt"])
        self.assertEqual(15, result["hostObservation"]["usageTotal"])
        self.assertEqual("p/m", result["hostObservation"]["effectiveModel"])
        state = self.store.load(run_id)
        self.assertEqual("ses_fixture", state["workers"][0]["nativeBinding"]["hostTaskId"])
        self.assertEqual("WAITING_RESOURCE", state["tasks"][0]["status"])
        self.assertEqual("UNTESTED", state["acceptanceCriteria"][0]["status"])

    def test_out_of_scope_edit_fails_candidate(self):
        run_id, task_id = self.task(["src/**"])
        FakeOpenCode.scenario["writes"] = ["README.md"]
        result = dispatch(self.store, self.server, run_id, task_id, None)
        self.assertEqual("failed", result["status"])
        self.assertIn("worker changed paths outside its WorkPacket", result["errors"])

    def test_timeout_interrupts_and_fails_instead_of_accepting_late_result(self):
        run_id, task_id = self.task(timeout=1)
        FakeOpenCode.scenario.update(hang=True)
        result = dispatch(self.store, self.server, run_id, task_id, None)
        self.assertEqual("failed", result["status"])
        self.assertEqual("cancelled", result["observedHostStatus"])
        self.assertTrue(FakeOpenCode.scenario["interrupted"])
        self.assertEqual("timeout", result["hostObservation"]["budgetStop"])
        with self.assertRaises(RuntimeFailure):
            self.store.complete_task(run_id, task_id, evidence_refs=[result["artifactRef"]])

    def test_pending_host_permission_is_reported_never_answered(self):
        run_id, task_id = self.task(timeout=1)
        FakeOpenCode.scenario.update(hang=True, permissions=[{"id": "per_1", "action": "shell", "resources": ["ls"]}])
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = dispatch(self.store, self.server, run_id, task_id, None)
        self.assertEqual("failed", result["status"])
        self.assertIn("pending OpenCode permission: shell", result["hostObservation"]["budgetStop"])
        self.assertIn("answer it in OpenCode", stderr.getvalue())
        self.assertFalse(any("/permission/" in path for _, path in FakeOpenCode.scenario["calls"]))

    def test_unconfirmed_termination_is_not_a_candidate(self):
        run_id, task_id = self.task(timeout=1)
        FakeOpenCode.scenario.update(hang=True, stuck=True)
        result = dispatch(self.store, self.server, run_id, task_id, None)
        self.assertEqual("failed", result["status"])
        self.assertEqual("timeout; termination unconfirmed", result["hostObservation"]["budgetStop"])

    def test_failed_outcome_is_not_a_candidate(self):
        run_id, task_id = self.task()
        FakeOpenCode.scenario["outcome"] = "failed"
        self.assertEqual("failed", dispatch(self.store, self.server, run_id, task_id, None)["status"])

    def test_workspace_mismatch_stops_before_prompt_and_closes_worker(self):
        run_id, task_id = self.task()
        FakeOpenCode.scenario["directory"] = str(self.repo)
        with self.assertRaises(RuntimeFailure) as error:
            dispatch(self.store, self.server, run_id, task_id, None)
        self.assertEqual("WORKSPACE_MISMATCH", error.exception.code)
        self.assertNotIn("prompt", FakeOpenCode.scenario)
        self.assertTrue(FakeOpenCode.scenario["interrupted"])
        self.assertEqual("FAILED", self.store.load(run_id)["workers"][0]["status"])

    def test_unknown_agent_is_rejected_before_session_creation(self):
        run_id, task_id = self.task()
        with self.assertRaises(RuntimeFailure) as error:
            dispatch(self.store, self.server, run_id, task_id, "missing-role")
        self.assertEqual("OPENCODE_HTTP", error.exception.code)
        self.assertNotIn(("POST", "/api/session"), FakeOpenCode.scenario["calls"])

    def test_only_loopback_http_servers_are_accepted(self):
        for url in ("https://127.0.0.1:4096", "http://example.com:4096", "http://10.0.0.5:4096"):
            with self.subTest(url=url), self.assertRaises(RuntimeFailure) as error:
                OpenCodeServer(url, "opencode", None)
            self.assertEqual("OPENCODE_SERVER_DENIED", error.exception.code)


if __name__ == "__main__":
    unittest.main()
