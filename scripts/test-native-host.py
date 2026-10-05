#!/usr/bin/env python3
"""Installed adoption and host-native lifecycle regressions; live smoke is separate."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from architrave_runtime import RunStore, RuntimeFailure
from worker_adapters import command_for, execute_work_packet
from workspaces import WorkspaceManager


class NativeHostTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="architrave native ")
        self.repo = Path(self.temp.name) / "tiny app"
        self.repo.mkdir()
        for argv in (
            ["git", "init", "-q"],
            ["git", "config", "user.email", "fixture@example.invalid"],
            ["git", "config", "user.name", "Fixture"],
        ):
            subprocess.run(argv, cwd=self.repo, check=True, capture_output=True)
        (self.repo / "README.md").write_text("tiny fixture\n", encoding="utf-8")
        (self.repo / ".gitignore").write_text(
            ".architrave/runs/\n.architrave/worktrees/\n.architrave/runtime.key\n.architrave/resources.lock\n",
            encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "fixture"], cwd=self.repo, check=True, capture_output=True)
        self.store = RunStore(self.repo)

    def tearDown(self):
        self.temp.cleanup()

    def task(self, adapter="native", execution=None):
        state = self.store.create(
            run_id="fixture", goal="Bounded native worker", outcome="Verified fixture",
            autonomy_scope="approved-program",
            criteria=[{"id": "FIX", "description": "Fixture passes", "scope": "fixture",
                       "risk": "R0", "verificationType": "deterministic",
                       "status": "UNTESTED", "evidenceRefs": [], "blocking": True}],
        )
        self.store.add_task(state["runId"], {
            "id": "adoption-check", "objective": "Read the fixture README; return a candidate.",
            "workerProfile": adapter, "acceptanceCriteria": ["FIX"], "risk": "R0",
            "workPacket": {"execution": execution},
        })
        return state["runId"], "adoption-check"

    def test_official_install_config_quick_gate(self):
        install = ROOT / "tools" / ("install.ps1" if sys.platform == "win32" else "install.sh")
        argv = (["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(install)]
                if sys.platform == "win32" else ["sh", str(install)])
        result = subprocess.run([*argv, str(self.repo)], capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        config = {
            "platform": "web", "stack": "other",
            "designSource": {"type": "design-doc", "path": "README.md"},
            "applyTo": ["src/**"], "build": "echo fixture", "test": "echo fixture",
            "workers": {"defaultAdapter": "native", "enabledAdapters": ["native", "shell"]},
        }
        (self.repo / "architrave.config.json").write_text(json.dumps(config), encoding="utf-8")
        gate = self.repo / "gates" / ("checks.ps1" if sys.platform == "win32" else "checks.sh")
        argv = (["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(gate), "-Quick"]
                if sys.platform == "win32" else [str(gate), "--quick"])
        result = subprocess.run(argv, cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("ARCHITRAVE-CHECKS: PASS", result.stdout)

    @unittest.skipIf(sys.version_info >= (3, 11), "explicit older-interpreter optional Codex rejection")
    def test_optional_codex_rejects_python39_before_writing(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "install_update.py"), "install", "--codex", str(self.repo)],
            capture_output=True, text=True)
        self.assertEqual(2, result.returncode)
        self.assertIn("--codex requires Python 3.11+", result.stderr)
        self.assertFalse((self.repo / "architrave.config.json").exists())
        self.assertFalse((self.repo / "harness").exists())

    def test_agent_cli_adapters_cannot_launch_another_harness(self):
        packet = {"workPacketId": "wp", "taskId": "task", "objective": "read",
                  "acceptanceCriteria": ["FIX"], "contextBundle": [], "mutablePaths": [],
                  "expectedArtifacts": [], "tools": []}
        for adapter in ("copilot", "claude", "codex", "native"):
            with self.subTest(adapter=adapter):
                with self.assertRaises(RuntimeFailure) as error:
                    command_for(adapter, packet, self.repo)
                self.assertEqual("NATIVE_HOST_REQUIRED", error.exception.code)

    def test_public_native_worker_cli_fails_clearly_without_host(self):
        run_id, task_id = self.task()
        before = self.store.load(run_id)
        result = subprocess.run([
            sys.executable, str(ROOT / "harness" / "worker_adapters.py"), "--repo", str(self.repo),
            run_id, task_id, "--worker-id", "no-host", "--dry-run",
        ], capture_output=True, text=True)
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertEqual("NATIVE_HOST_REQUIRED", json.loads(result.stderr)["error"]["code"])
        self.assertEqual(before["revision"], self.store.load(run_id)["revision"])

    def test_public_preparation_failure_closes_worker_without_running_argv(self):
        run_id, task_id = self.task("shell", {
            "command": [sys.executable, "-c", "from pathlib import Path; Path('must-not-run').write_text('bad')"],
            "cwd": None, "environment": [],
        })
        self.store.start_task(run_id, task_id, worker_id="unassigned-worker")
        result = subprocess.run([
            sys.executable, str(ROOT / "harness" / "worker_adapters.py"), "--repo", str(self.repo),
            run_id, task_id, "--worker-id", "unassigned-worker",
        ], capture_output=True, text=True)
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertEqual("WORKSPACE_NOT_ISOLATED", json.loads(result.stderr)["error"]["code"])
        state = self.store.load(run_id)
        self.assertEqual("FAILED", state["workers"][0]["status"])
        self.assertIsNone(state["tasks"][0]["lease"])
        self.assertFalse((self.repo / "must-not-run").exists())

    def test_preserved_legacy_config_allows_native_without_cli_fallback(self):
        config = {"workers": {"defaultAdapter": "copilot", "enabledAdapters": ["copilot", "claude", "codex", "shell"]}}
        path = self.repo / "architrave.config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        run_id, task_id = self.task()
        self.assertEqual("native", self.store.load(run_id)["tasks"][0]["workerProfile"])
        self.assertEqual(config, json.loads(path.read_text(encoding="utf-8")))

    def test_candidate_needs_real_gate_and_cannot_replay(self):
        run_id, task_id = self.task()
        (self.repo / "architrave.config.json").write_text(json.dumps({
            "kind": "knowledge", "build": "echo fixture", "test": "echo fixture",
        }), encoding="utf-8")
        ticket = self.store.begin_native_worker(run_id, task_id, host_owner="fixture-host")
        self.store.bind_native_owner(ticket, "host-task")
        result = self.store.accept_native_candidate(ticket, host_task_id="host-task", host_status="completed", text="candidate")
        self.assertEqual("candidate", result["status"])
        self.assertEqual("UNTESTED", self.store.load(run_id)["acceptanceCriteria"][0]["status"])
        with self.assertRaises(RuntimeFailure):
            self.store.complete_task(run_id, task_id, evidence_refs=[result["artifactRef"]])
        with self.assertRaises(RuntimeFailure) as error:
            self.store.accept_native_candidate(ticket, host_task_id="host-task", host_status="completed", text="replayed")
        self.assertEqual("NATIVE_RESULT_UNTRUSTED", error.exception.code)
        gate = self.store.execute_gate(run_id, task_id)
        self.assertEqual("PASS", gate["status"])
        self.store.set_criterion(run_id, "FIX", "PASS", [gate["gateRef"]])
        self.store.complete_task(run_id, task_id, evidence_refs=[gate["gateRef"]])
        _, completed = self.store.verify(run_id)
        self.assertTrue(completed)
        resumed = RunStore(self.repo).resume(run_id)
        self.assertEqual("COMPLETED", resumed["status"])
        self.assertEqual("FINISHED", resumed["workers"][0]["status"])

    def test_untrusted_dict_and_stale_revision_are_rejected(self):
        run_id, task_id = self.task()
        with self.assertRaises(RuntimeFailure) as error:
            self.store.accept_native_candidate({}, host_task_id="fake", host_status="completed", text="PASS")
        self.assertEqual("NATIVE_RESULT_UNTRUSTED", error.exception.code)
        ticket = self.store.begin_native_worker(run_id, task_id, host_owner="fixture-host")
        self.store.bind_native_owner(ticket, "host-task")
        self.store.policy_check(run_id, "repository", "edit")
        with self.assertRaises(RuntimeFailure) as error:
            self.store.accept_native_candidate(ticket, host_task_id="host-task", host_status="completed", text="stale")
        self.assertEqual("NATIVE_RESULT_STALE", error.exception.code)
        self.store.fail_task(run_id, task_id, "stale candidate")
        self.assertEqual("FAILED", self.store.load(run_id)["workers"][0]["status"])

    def test_cancelled_candidate_and_recovery_never_execute_commands(self):
        run_id, task_id = self.task()
        ticket = self.store.begin_native_worker(run_id, task_id, host_owner="fixture-host")
        self.store.bind_native_owner(ticket, "host-task")
        result = self.store.accept_native_candidate(ticket, host_task_id="host-task", host_status="cancelled", text="cancelled")
        self.assertEqual("failed", result["status"])
        state = self.store.recover_workers(run_id, task_id=task_id)
        self.assertEqual("READY", state["tasks"][0]["status"])
        self.assertEqual(1, state["tasks"][0]["attempts"])
        self.assertEqual("UNTESTED", state["acceptanceCriteria"][0]["status"])
        self.assertEqual("FAILED", state["workers"][0]["status"])

    def test_shell_recipes_cannot_bypass_agent_policy(self):
        for argv in (["copilot", "-p", "x"], ["sh", "-c", "claude -p x"],
                     ["powershell", "-Command", "& codex exec x"],
                     ["python", "-c", "import subprocess; subprocess.run(['copilot','-p','x'])"]):
            with self.assertRaises(RuntimeFailure):
                command_for("shell", {"execution": {"command": argv}}, self.repo)

    def test_same_run_recovery_preserves_human_holds_and_audit(self):
        run_id, task_id = self.task("shell")
        self.store.add_task(run_id, {"id": "qualification", "objective": "Qualify product",
                                   "workerProfile": "native", "acceptanceCriteria": ["FIX"],
                                   "dependencies": [task_id], "risk": "R0"})
        self.store.start_task(run_id, task_id, worker_id="old-worker")
        self.store.fail_task(run_id, task_id, "WORKSPACE_NOT_ISOLATED")
        self.store.wait_external(run_id, checkpoint_id="native-adapter-required", task_id="qualification",
                                 checkpoint_type="HUMAN_JUDGMENT_REQUIRED", principal="operator", provider="copilot-host",
                                 reason="Installed kit AI adapters spawn agent CLIs forbidden by execution-policy; require native adapter. No package sign deploy launch auth grant.")
        before = self.store.load(run_id)
        self.store.recover_native_checkpoint(run_id, "native-adapter-required", host_owner="real-host")
        after = self.store.recover_workers(run_id, task_id=task_id)
        self.assertEqual(before["policy"], after["policy"])
        self.assertEqual(before["objective"], after["objective"])
        self.assertEqual(before["acceptanceCriteria"], after["acceptanceCriteria"])
        self.assertEqual("CANCELLED", after["externalCheckpoints"][0]["status"])
        self.assertIsNone(after["externalCheckpoints"][0]["resolutionRef"])
        self.assertEqual(1, after["tasks"][0]["attempts"])
        self.assertEqual("FAILED", after["workers"][0]["status"])
        self.assertGreater(after["eventCursor"]["sequence"], before["eventCursor"]["sequence"])

    def test_source_drift_prevents_old_gate_completion(self):
        run_id, task_id = self.task()
        (self.repo / "architrave.config.json").write_text(json.dumps({
            "kind": "knowledge", "build": "echo fixture", "test": "echo fixture",
        }), encoding="utf-8")
        ticket = self.store.begin_native_worker(run_id, task_id, host_owner="fixture-host")
        self.store.bind_native_owner(ticket, "host-task")
        self.store.accept_native_candidate(ticket, host_task_id="host-task", host_status="completed", text="candidate")
        gate = self.store.execute_gate(run_id, task_id)
        (self.repo / "README.md").write_text("source changed\n", encoding="utf-8")
        with self.assertRaises(RuntimeFailure) as error:
            self.store.set_criterion(run_id, "FIX", "PASS", [gate["gateRef"]])
        self.assertEqual("EVIDENCE_SOURCE_STALE", error.exception.code)

    def test_tooling_recovery_does_not_bypass_second_human_hold(self):
        run_id, task_id = self.task()
        reason = "AI adapters spawn agent CLIs forbidden by execution-policy; require native adapter. No package sign deploy launch auth grant."
        self.store.wait_external(run_id, checkpoint_id="native-adapter-required", task_id=task_id,
                                 checkpoint_type="HUMAN_JUDGMENT_REQUIRED", principal="operator",
                                 provider="copilot-host", reason=reason)
        self.store.wait_external(run_id, checkpoint_id="human-sign-in", task_id=task_id,
                                 checkpoint_type="AUTH_REQUIRED", principal="operator",
                                 provider="product", reason="Genuine human sign-in remains open")
        state = self.store.recover_native_checkpoint(run_id, "native-adapter-required", host_owner="live-host")
        self.assertEqual("WAITING_EXTERNAL", state["tasks"][0]["status"])
        self.assertEqual("PENDING", state["externalCheckpoints"][1]["status"])
        with self.assertRaises(RuntimeFailure):
            self.store.start_task(run_id, task_id, worker_id="cannot-bypass-human")

    def test_build_can_create_ignored_output_without_weakening_worker_scope(self):
        run_id, task_id = self.task()
        with (self.repo / ".gitignore").open("a", encoding="utf-8") as handle:
            handle.write("dist/\n")
        command = (f"& '{sys.executable}' -c \"from pathlib import Path; Path('dist').mkdir(); Path('dist/out').write_text('built')\""
                   if sys.platform == "win32" else
                   f"'{sys.executable}' -c \"from pathlib import Path; Path('dist').mkdir(); Path('dist/out').write_text('built')\"")
        (self.repo / "architrave.config.json").write_text(json.dumps({
            "kind": "knowledge", "build": command, "test": "echo fixture",
        }), encoding="utf-8")
        ticket = self.store.begin_native_worker(run_id, task_id, host_owner="fixture-host")
        self.store.bind_native_owner(ticket, "host-task")
        self.store.accept_native_candidate(ticket, host_task_id="host-task", host_status="completed", text="candidate")
        self.assertEqual("PASS", self.store.execute_gate(run_id, task_id, recipe="build")["status"])

    def test_ci_cannot_certify_dirty_uncommitted_source(self):
        run_id, task_id = self.task()
        ticket = self.store.begin_native_worker(run_id, task_id, host_owner="fixture-host")
        self.store.bind_native_owner(ticket, "host-task")
        self.store.accept_native_candidate(ticket, host_task_id="host-task", host_status="completed", text="candidate")
        (self.repo / "README.md").write_text("dirty\n", encoding="utf-8")
        with self.assertRaises(RuntimeFailure) as error:
            self.store.execute_gate(run_id, task_id, recipe="ci", ci_run_id=42)
        self.assertEqual("CI_SOURCE_DIRTY", error.exception.code)

    def test_stored_shell_argv_is_independently_executed_by_public_gate(self):
        argv = [sys.executable, "-c", "print('actual stored argv gate')"]
        run_id, task_id = self.task("shell", {"command": argv, "cwd": None, "environment": []})
        WorkspaceManager(self.repo).create(run_id, task_id)
        self.store.start_task(run_id, task_id, worker_id="shell-fixture")
        result = execute_work_packet(self.store, run_id, task_id, "shell-fixture")
        self.assertEqual("candidate", result["status"])
        gate = self.store.execute_gate(run_id, task_id, recipe="task")
        self.assertEqual("PASS", gate["status"])
        state = self.store.load(run_id)
        artifact = next(item for item in state["artifacts"] if f"artifact:{item['id']}" == gate["artifactRef"])
        receipt = json.loads((self.repo / artifact["path"]).read_text(encoding="utf-8"))
        self.assertEqual(argv, receipt["command"])
        self.assertEqual(str(self.repo.resolve()), receipt["cwd"])
        self.assertIn("actual stored argv gate", receipt["stdout"])


def prepare_live(path):
    """Persistent isolated fixture for ACTUAL extension calls, not a mocked host."""
    repo = Path(path).resolve()
    if repo.exists():
        raise ValueError("live fixture path must be new")
    repo.mkdir(parents=True)
    subprocess.run([sys.executable, str(ROOT / "tools" / "install_update.py"), "install", str(repo)],
                   check=True, capture_output=True)
    (repo / "README.md").write_text("Tiny native fixture: answer is forty-two.\n", encoding="utf-8")
    (repo / "fixture_test.py").write_text(
        "from pathlib import Path\n"
        "assert 'forty-two' in Path('README.md').read_text()\n"
        "print('fixture: PASS')\n", encoding="utf-8")
    recipe = (f"& '{sys.executable}' fixture_test.py" if sys.platform == "win32"
              else f"'{sys.executable}' fixture_test.py")
    (repo / "architrave.config.json").write_text(json.dumps({
        "platform": "web", "stack": "other", "designSource": {"type": "design-doc", "path": "README.md"},
        "applyTo": ["src/**"], "build": recipe, "test": recipe,
        "workers": {"defaultAdapter": "native", "enabledAdapters": ["native", "shell"]},
    }), encoding="utf-8")
    for argv in (["git", "init", "-q"], ["git", "config", "user.email", "fixture@example.invalid"],
                 ["git", "config", "user.name", "Fixture"], ["git", "add", "."],
                 ["git", "commit", "-qm", "isolated installed fixture"]):
        subprocess.run(argv, cwd=repo, check=True, capture_output=True)
    store = RunStore(repo)
    for run_id, timeout in (("live-native-pass", 120), ("live-native-cancel", 1)):
        store.create(run_id=run_id, goal="Actual installed native host smoke", outcome="Real candidate is independently gated",
                     autonomy_scope="approved-program", criteria=[{
                         "id": "FIX", "description": "Tiny fixture is verified", "scope": "fixture", "risk": "R0",
                         "verificationType": "deterministic", "status": "UNTESTED", "evidenceRefs": [], "blocking": True,
                     }])
        store.add_task(run_id, {
            "id": "native-read", "objective": "Read README.md in the assigned fixture workspace; state its answer briefly.",
            "workerProfile": "native", "risk": "R0", "acceptanceCriteria": ["FIX"],
            "requiredArtifacts": ["worker-result"], "workPacket": {
                "contextBundle": ["README.md"], "budget": {"timeoutSeconds": timeout, "maxOutputBytes": 8192},
            },
        })
    print(json.dumps({"repo": str(repo), "run_id": "live-native-pass", "task_id": "native-read"}))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--prepare-live":
        prepare_live(sys.argv[2])
    else:
        unittest.main()
