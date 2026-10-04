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

from architrave_runtime import RunStore, RuntimeFailure


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

    def tearDown(self) -> None:
        self.temp.cleanup()

    def create(self, outcome: str = "Prove the current product objective.") -> str:
        return self.store.create(
            goal=outcome,
            outcome=outcome,
            criteria=[
                {
                    "id": "ACCEPT-001",
                    "description": outcome,
                    "scope": "product",
                    "risk": "R1",
                    "verificationType": "deterministic",
                    "status": "UNTESTED",
                    "evidenceRefs": [],
                    "blocking": True,
                }
            ],
            autonomy_scope="approved-program",
        )["runId"]

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
        task = {
            "id": task_id,
            "title": task_id,
            "objective": f"Complete {task_id}.",
            "workerProfile": "shell",
            "mutablePaths": [],
            "tools": [],
            "risk": "R1",
            "acceptanceCriteria": ["ACCEPT-001"],
            "requiredArtifacts": [],
            "gate": "synthetic",
        }
        task.update(overrides)
        return self.store.add_task(run_id, task)

    def test_existing_working_login_blocks_diagnostic_redesign(self) -> None:
        run_id = self.create("Keep the existing working login and verify the smallest difference.")
        with self.assertRaisesRegex(RuntimeFailure, "existing working implementation"):
            self.add_task(run_id, "replacement", changeKind="replacement-architecture", largeChange=True)
        evidence = self.evidence(run_id)
        self.store.record_reuse_baseline(
            run_id,
            path="existing-login.txt",
            difference="Compare the existing login response with the requested acceptance state.",
            evidence_refs=[evidence],
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
        state = self.store.replace_objective(
            run_id,
            outcome="Run the requested free-engine game acceptance test on the intended build.",
            criteria=[
                {
                    "id": "GAME-001",
                    "description": "The intended game build passes its minimal launch test.",
                    "scope": "game",
                    "risk": "R1",
                    "verificationType": "deterministic",
                    "status": "UNTESTED",
                    "evidenceRefs": [],
                    "blocking": True,
                }
            ],
            correction="Stay focused; you lost my ask and do not drift into bridge work.",
            next_cheapest_test="Launch the intended build once and record the result.",
            explicit_user_direction=True,
        )
        self.assertEqual(2, state["objective"]["version"])
        self.assertEqual(["product"], [lane["id"] for lane in state["lanes"]["active"]])
        bridge = next(task for task in state["tasks"] if task["id"] == "communications-bridge")
        self.assertEqual("DEFERRED", bridge["status"])
        checkpoint = self.store.human_checkpoint(run_id)
        self.assertEqual("Launch the intended build once and record the result.", checkpoint["nextCheapestTest"])
        self.assertEqual({"product"}, set(checkpoint["activeLanes"]))

    def test_wrong_provider_or_build_aborts_target_preflight(self) -> None:
        run_id = self.create("Test the intended provider build.")
        evidence = self.evidence(run_id)
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
            operations=["launch"],
            targetIdentity=intended,
            isMinimalAcceptanceTest=True,
        )
        observed = {**intended, "provider": "provider-b", "version": "1"}
        state = self.store.verify_target_identity(
            run_id,
            intended=intended,
            observed=observed,
            evidence_refs=[evidence],
        )
        self.assertEqual("MISMATCH", state["targetIdentity"]["status"])
        self.assertEqual("PAUSED", state["status"])
        with self.assertRaisesRegex(RuntimeFailure, "paused"):
            self.store.start_task(run_id, "launch-intended-build", worker_id="launcher")

    def test_correction_cancels_active_old_work_and_recomputes_next_test(self) -> None:
        run_id = self.create("Old objective.")
        self.add_task(run_id, "old-worker-one")
        self.add_task(run_id, "old-worker-two")
        self.store.start_task(run_id, "old-worker-one", worker_id="worker-one")
        self.store.start_task(run_id, "old-worker-two", worker_id="worker-two")
        state = self.store.replace_objective(
            run_id,
            outcome="Corrected product objective.",
            criteria=[
                {
                    "id": "NEW-001",
                    "description": "Corrected objective reaches acceptance.",
                    "scope": "product",
                    "risk": "R1",
                    "verificationType": "deterministic",
                    "status": "UNTESTED",
                    "evidenceRefs": [],
                    "blocking": True,
                }
            ],
            correction="Wrong target; use the existing working implementation.",
            next_cheapest_test="Diff and run the existing working path.",
            explicit_user_direction=True,
        )
        self.assertTrue(all(task["status"] == "DEFERRED" for task in state["tasks"]))
        self.assertTrue(all(worker["status"] == "FAILED" for worker in state["workers"]))
        self.add_task(
            run_id,
            "new-minimal-test",
            acceptanceCriteria=["NEW-001"],
            isMinimalAcceptanceTest=True,
        )
        state = self.store.start_task(run_id, "new-minimal-test", worker_id="new-worker")
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
        self.store.record_review_result(run_id, verdict="REVISE")
        state = self.store.record_review_result(run_id, verdict="REVISE")
        review = next(task for task in state["tasks"] if task["id"] == "micro-review")
        self.assertEqual("DEFERRED", review["status"])
        self.assertEqual("review.batch_required", self.store.events(run_id)[-1]["type"])
        self.assertEqual(
            "repeated review without new product evidence",
            state["focus"]["lastResetReason"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
