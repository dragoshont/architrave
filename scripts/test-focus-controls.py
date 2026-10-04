#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))

from architrave_runtime import RunStore


class FocusControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.email", "architrave@example.invalid"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.name", "Architrave Test"], cwd=self.repo, check=True)
        (self.repo / "existing-login.txt").write_text("working\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "fixture"], cwd=self.repo, check=True)
        self.store = RunStore(self.repo)
        self.runtime = ROOT / "harness" / "architrave_runtime.py"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def create(
        self,
        outcome: str = "Prove the current product objective.",
        *,
        policy_allow: list[dict[str, object]] | None = None,
    ) -> str:
        arguments = [
            "run", "--goal", outcome, "--outcome", outcome, "--autonomy", "approved-program",
            "--criterion", f"ACCEPT-001|{outcome}|product|R1|deterministic",
        ]
        for grant in policy_allow or []:
            arguments.extend(["--allow", f"{grant['scope']}:{','.join(grant['operations'])}"])
        return self.cli(*arguments)["runId"]

    def cli(self, *arguments: str, expected: int = 0) -> dict[str, object]:
        process = subprocess.run(
            [sys.executable, str(self.runtime), "--repo", str(self.repo), *arguments],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(expected, process.returncode, process.stdout + process.stderr)
        payload = json.loads(process.stdout if process.stdout.strip() else process.stderr)
        return payload.get("result") or payload.get("error") or {}

    def evidence(self, run_id: str, artifact_id: str = "baseline-evidence") -> str:
        path = self.store.run_dir(run_id) / "evidence" / f"{artifact_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"status": "pass", "exitCode": 0, "command": "synthetic fixture"}) + "\n",
            encoding="utf-8",
        )
        self.store._record_deterministic_result(
            run_id,
            artifact_id=artifact_id,
            path=path.resolve().relative_to(self.store.repository).as_posix(),
            evidence_refs=[],
        )
        return f"artifact:{artifact_id}"

    def add_task(self, run_id: str, task_id: str, **overrides: object) -> dict[str, object]:
        arguments = [
            "task-add", run_id, "--id", task_id, "--title", task_id,
            "--objective", f"Complete {task_id}.", "--criteria",
            ",".join(overrides.get("acceptanceCriteria", ["ACCEPT-001"])),
        ]
        if overrides.get("workKind"):
            arguments.extend(["--work-kind", str(overrides["workKind"])])
        if overrides.get("lane"):
            arguments.extend(["--lane", str(overrides["lane"])])
        if overrides.get("changeKind"):
            arguments.extend(["--change-kind", str(overrides["changeKind"])])
        if overrides.get("isMinimalAcceptanceTest"):
            arguments.append("--minimal-test")
        if overrides.get("largeChange"):
            arguments.append("--large-change")
        if overrides.get("sideEffect"):
            side_effect = overrides["sideEffect"]
            arguments.extend(["--side-effect", f"{side_effect['operation']}@{side_effect['target']}"])
        if overrides.get("targetIdentity"):
            arguments.extend(["--target-json", json.dumps(overrides["targetIdentity"])])
        return self.cli(*arguments)

    def test_existing_working_login_blocks_diagnostic_redesign(self) -> None:
        run_id = self.create("Keep the existing working login and verify the smallest difference.")
        error = self.cli(
            "task-add", run_id, "--id", "replacement", "--title", "replacement",
            "--objective", "Replace the existing login.", "--criteria", "ACCEPT-001",
            "--change-kind", "replacement-architecture", "--large-change",
            expected=1,
        )
        self.assertEqual("REUSE_FIRST_REQUIRED", error["code"])
        difference = "Compare the existing login response with the requested acceptance state."
        self.cli(
            "reuse-verify", run_id, "--path", "existing-login.txt",
            "--difference", difference, "--test-command", sys.executable, "-c",
            "from pathlib import Path; assert Path('existing-login.txt').read_text().strip() == 'working'",
        )
        self.add_task(
            run_id,
            "minimal-login-test",
            workKind="diagnostic",
            isMinimalAcceptanceTest=True,
            changeKind="replacement-architecture",
        )
        self.add_task(run_id, "diagnostic-framework", workKind="diagnostic", largeChange=True)
        state = self.store.load(run_id)
        framework = next(task for task in state["tasks"] if task["id"] == "diagnostic-framework")
        self.assertEqual("DEFERRED", framework["status"])

    def test_correction_keeps_product_objective_and_defers_bridge_lane(self) -> None:
        run_id = self.create("Run the requested free-engine game acceptance test.")
        self.add_task(run_id, "game-test", isMinimalAcceptanceTest=True)
        self.add_task(run_id, "communications-bridge", workKind="communications", lane="bridge")
        self.add_task(run_id, "bridge-on-product-lane", workKind="communications", lane="product")
        wait = self.cli(
            "external-wait", run_id, "--id", "objective-correction", "--task-id", "game-test",
            "--type", "HUMAN_JUDGMENT_REQUIRED", "--principal", "synthetic-user",
            "--provider", "user-direction", "--reason", "Replace the objective.",
        )
        self.cli(
            "objective-replace", run_id,
            "--outcome", "Run the requested free-engine game acceptance test on the intended build.",
            "--criterion", "GAME-001|The intended game build passes its minimal launch test.|game|R1|deterministic",
            "--correction", "Stay focused; you lost my ask and do not drift into bridge work.",
            "--next-test", "Launch the intended build once and record the result.",
            "--checkpoint-id", "objective-correction", "--challenge", str(wait["resolutionChallenge"]),
            "--actor", "human:synthetic-user",
        )
        state = self.store.load(run_id)
        self.assertEqual(2, state["objective"]["version"])
        self.assertEqual(["product"], [lane["id"] for lane in state["lanes"]["active"]])
        bridge = next(task for task in state["tasks"] if task["id"] == "communications-bridge")
        self.assertEqual("DEFERRED", bridge["status"])
        product_bridge = next(task for task in state["tasks"] if task["id"] == "bridge-on-product-lane")
        self.assertEqual("DEFERRED", product_bridge["status"])
        self.assertNotIn("product", {lane["id"] for lane in state["lanes"]["deferred"]})
        checkpoint = self.store.human_checkpoint(run_id)
        self.assertEqual("Launch the intended build once and record the result.", checkpoint["nextCheapestTest"])
        self.assertEqual({"product"}, set(checkpoint["activeLanes"]))

    def test_wrong_provider_or_build_aborts_target_preflight(self) -> None:
        run_id = self.create(
            "Test the intended provider build.",
            policy_allow=[{"scope": "provider-a", "operations": ["launch"]}],
        )
        intended = {
            "provider": "provider-a",
            "artifact": "game.exe",
            "version": "2",
            "sha256": "a" * 64,
            "environment": "test",
            "workspace": "workspace-a",
            "acceptanceTarget": "provider-a game launch",
        }
        self.add_task(
            run_id,
            "launch-intended-build",
            sideEffect={"operation": "launch", "target": "provider-a"},
            targetIdentity=intended,
            isMinimalAcceptanceTest=True,
        )
        task = next(task for task in self.store.load(run_id)["tasks"] if task["id"] == "launch-intended-build")
        self.assertEqual(["launch"], task["operations"])
        observed = {**intended, "provider": "provider-b", "version": "1"}
        wait = self.cli(
            "external-wait", run_id, "--id", "target-check", "--task-id", "launch-intended-build",
            "--type", "SAFE_WRITE_TARGET_REQUIRED", "--principal", "synthetic-user",
            "--provider", "provider-a", "--reason", "Confirm target identity.",
        )
        forged = self.cli(
            "target-resolve", run_id, "--checkpoint-id", "target-check", "--challenge", "forged",
            "--intended-json", json.dumps(intended), "--observed-json", json.dumps(observed),
            "--actor", "human:synthetic-user", expected=1,
        )
        self.assertEqual("TARGET_IDENTITY_INVALID", forged["code"])
        self.cli(
            "target-resolve", run_id, "--checkpoint-id", "target-check",
            "--challenge", str(wait["resolutionChallenge"]), "--intended-json", json.dumps(intended),
            "--observed-json", json.dumps(observed), "--actor", "human:synthetic-user",
        )
        replay = self.cli(
            "target-resolve", run_id, "--checkpoint-id", "target-check",
            "--challenge", str(wait["resolutionChallenge"]), "--intended-json", json.dumps(intended),
            "--observed-json", json.dumps(intended), "--actor", "human:synthetic-user", expected=1,
        )
        self.assertEqual("TARGET_IDENTITY_INVALID", replay["code"])
        state = self.store.load(run_id)
        self.assertEqual("MISMATCH", state["targetIdentity"]["status"])
        self.assertEqual("PAUSED", state["status"])
        paused = self.cli(
            "task-start", run_id, "launch-intended-build", "--worker-id", "launcher",
            expected=1,
        )
        self.assertEqual("RUN_PAUSED", paused["code"])

        valid_run = self.create(
            "Launch the verified intended build.",
            policy_allow=[{"scope": "provider-a", "operations": ["launch"]}],
        )
        self.add_task(
            valid_run,
            "verified-launch",
            sideEffect={"operation": "launch", "target": "provider-a"},
            targetIdentity=intended,
            isMinimalAcceptanceTest=True,
        )
        valid_wait = self.cli(
            "external-wait", valid_run, "--id", "valid-target", "--task-id", "verified-launch",
            "--type", "SAFE_WRITE_TARGET_REQUIRED", "--principal", "synthetic-user",
            "--provider", "provider-a", "--reason", "Confirm target identity.",
        )
        self.cli(
            "target-resolve", valid_run, "--checkpoint-id", "valid-target",
            "--challenge", str(valid_wait["resolutionChallenge"]),
            "--intended-json", json.dumps(intended), "--observed-json", json.dumps(intended),
            "--actor", "human:synthetic-user",
        )
        self.cli("task-start", valid_run, "verified-launch", "--worker-id", "verified-worker")
        self.assertEqual("VERIFIED", self.store.load(valid_run)["targetIdentity"]["status"])

    def test_correction_cancels_active_old_work_and_recomputes_next_test(self) -> None:
        run_id = self.create(
            "Old objective.",
            policy_allow=[{"scope": "sandbox:fixture", "operations": ["deploy"]}],
        )
        old_evidence = self.evidence(run_id, "old-gate-evidence")
        self.store.record_gate(
            run_id,
            gate_id="old-objective-gate",
            task_id=None,
            gate_type="deterministic",
            status="PASS",
            evidence_refs=[old_evidence],
            criteria=["ACCEPT-001"],
        )
        self.add_task(
            run_id,
            "old-worker-one",
            sideEffect={"operation": "deploy", "target": "sandbox:fixture"},
        )
        self.add_task(run_id, "old-worker-two")
        self.add_task(run_id, "correction-auth")
        self.cli("task-start", run_id, "old-worker-one", "--worker-id", "worker-one")
        self.cli("task-start", run_id, "old-worker-two", "--worker-id", "worker-two")
        wait = self.cli(
            "external-wait", run_id, "--id", "correction-checkpoint", "--task-id", "correction-auth",
            "--type", "HUMAN_JUDGMENT_REQUIRED", "--principal", "synthetic-user",
            "--provider", "user-direction", "--reason", "Replace objective.",
        )
        self.cli(
            "objective-replace", run_id, "--outcome", "Corrected product objective.",
            "--criterion", "ACCEPT-001|Corrected objective reaches acceptance.|product|R1|deterministic",
            "--correction", "Wrong target; use the existing working implementation.",
            "--next-test", "Diff and run the existing working path.",
            "--checkpoint-id", "correction-checkpoint", "--challenge", str(wait["resolutionChallenge"]),
            "--actor", "human:synthetic-user",
        )
        state = self.store.load(run_id)
        uncertain = next(task for task in state["tasks"] if task["id"] == "old-worker-one")
        deferred = next(task for task in state["tasks"] if task["id"] == "old-worker-two")
        self.assertEqual("UNCERTAIN", uncertain["sideEffect"]["state"])
        self.assertEqual("WAITING_RESOURCE", uncertain["status"])
        self.assertEqual("DEFERRED", deferred["status"])
        self.assertTrue(all(worker["status"] == "FAILED" for worker in state["workers"]))
        error = self.cli(
            "criterion-set", run_id, "ACCEPT-001", "--status", "PASS",
            "--evidence", "gate:old-objective-gate", expected=1,
        )
        self.assertEqual("EVIDENCE_SUPERSEDED", error["code"])
        verified = self.cli("verify", run_id, expected=1)
        self.assertEqual("WAITING_RESOURCE", verified["status"])
        self.add_task(
            run_id,
            "new-minimal-test",
            acceptanceCriteria=["ACCEPT-001"],
            isMinimalAcceptanceTest=True,
        )
        self.cli("task-start", run_id, "new-minimal-test", "--worker-id", "new-worker")
        state = self.store.load(run_id)
        self.assertEqual("RUNNING", next(task for task in state["tasks"] if task["id"] == "new-minimal-test")["status"])

    def test_repeated_micro_reviews_require_batch_and_reset(self) -> None:
        run_id = self.create("Prove a minimal product slice before review.")
        evidence = self.evidence(run_id)
        self.store.record_gate(
            run_id,
            gate_id="minimal-gate",
            task_id=None,
            gate_type="deterministic",
            status="PASS",
            evidence_refs=[evidence],
            criteria=["ACCEPT-001"],
        )
        self.store.set_criterion(run_id, "ACCEPT-001", "PASS", ["gate:minimal-gate"])
        self.add_task(run_id, "micro-review", workKind="review")
        self.cli("review-record", run_id, "--verdict", "REVISE")
        self.cli("review-record", run_id, "--verdict", "REVISE")
        state = self.store.load(run_id)
        review = next(task for task in state["tasks"] if task["id"] == "micro-review")
        self.assertEqual("DEFERRED", review["status"])
        self.assertEqual("review.batch_required", self.store.events(run_id)[-1]["type"])
        self.assertEqual(
            "repeated review without new product evidence",
            state["focus"]["lastResetReason"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
