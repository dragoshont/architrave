#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))

from architrave_runtime import RunStore, missing_gate_requirements


class LongBuildRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name) / "fixture"
        shutil.copytree(ROOT / "benchmarks" / "fixtures" / "tessera-shaped", self.repo)
        self.git("init", "-q")
        self.git("config", "user.email", "architrave@example.invalid")
        self.git("config", "user.name", "Architrave LongBuild")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        self.store = RunStore(self.repo)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=self.repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def add_task(
        self,
        run_id: str,
        task_id: str,
        *,
        dependencies: list[str] | None = None,
        criteria: list[str] | None = None,
        risk: str = "R2",
        side_effect: dict[str, str] | None = None,
    ) -> None:
        self.store.add_task(
            run_id,
            {
                "id": task_id,
                "title": task_id,
                "objective": f"Complete the {task_id} LongBuild slice.",
                "dependencies": dependencies or [],
                "workerProfile": "shell",
                "mutablePaths": [],
                "tools": ["fixture"],
                "risk": risk,
                "acceptanceCriteria": criteria or ["PRODUCT-001"],
                "requiredArtifacts": [f"evidence-{task_id}"],
                "gate": f"{task_id} fixture gate",
                "maxAttempts": 2,
                "sideEffect": side_effect,
            },
        )

    def evidence(
        self,
        run_id: str,
        artifact_id: str,
        *,
        task_id: str | None = None,
        producer: str = "deterministic",
    ) -> str:
        path = self.store.run_dir(run_id) / "evidence" / f"{artifact_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        state = self.store.load(run_id)
        criteria = [criterion["id"] for criterion in state["acceptanceCriteria"] if criterion["blocking"]]
        if producer == "deterministic":
            payload = {"status": "pass", "exitCode": 0, "command": "fixture"}
        elif producer == "legibility":
            payload = {
                "surface": "web",
                "status": "pass",
                "failed": [],
                "results": [
                    {"name": "runtime.health", "status": "pass"},
                    {"name": "web.e2e", "status": "pass"},
                ],
            }
        elif producer == "mutation":
            payload = {
                "taskId": task_id,
                "operation": "deploy",
                "target": "sandbox:fixture",
                "expected": {"version": "fixture-2026.08.13", "digest": "sha256:fixture-2026.08.13"},
                "result": {"status": "pass", "mismatches": [], "apply": {"status": "pass"}},
                "verification": {
                    "health": {"status": "pass"},
                    "version": {"stdout": "fixture-2026.08.13"},
                    "digest": {"stdout": "sha256:fixture-2026.08.13"},
                },
            }
        elif producer == "semantic-judge":
            payload = {
                "verdict": "PASS",
                "family": "claude" if "claude" in artifact_id else "gpt",
                "criteria": criteria,
            }
        else:
            checkpoint = next(item for item in state["externalCheckpoints"] if item["status"] == "PENDING")
            payload = {
                "checkpointId": checkpoint["id"],
                "principal": checkpoint["principal"],
                "provider": checkpoint["provider"],
            }
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        method = {
            "deterministic": self.store._record_deterministic_result,
            "legibility": lambda target_run, **kwargs: self.store._record_legibility_result(target_run, kind="web-legibility", **kwargs),
            "mutation": self.store._record_mutation_receipt,
            "semantic-judge": self.store._record_semantic_verdict,
            "external-proof": self.store._record_external_proof,
        }[producer]
        method(
            run_id,
            artifact_id=artifact_id,
            path=path.relative_to(self.store.repository).as_posix(),
            evidence_refs=[f"task:{task_id}"] if task_id else [],
        )
        return f"artifact:{artifact_id}"

    def finish(self, run_id: str, task_id: str, worker_id: str, *, gate_type: str = "deterministic") -> None:
        self.store.finish_worker(run_id, task_id, worker_id=worker_id, status="FINISHED")
        producer = "legibility" if gate_type in {"e2e", "reality"} else "deterministic"
        evidence = self.evidence(run_id, f"evidence-{task_id}", task_id=task_id, producer=producer)
        self.store.record_gate(
            run_id,
            gate_id=f"gate-{task_id}",
            task_id=task_id,
            gate_type=gate_type,
            status="PASS",
            evidence_refs=[evidence],
        )
        self.store.complete_task(run_id, task_id, evidence_refs=[f"gate:gate-{task_id}"])

    def test_approved_program_reaches_verified_outcome_after_recovery(self) -> None:
        state = self.store.create(
            goal="Deliver the Tessera-shaped fixture across every configured surface.",
            outcome="The multi-surface fixture is deployed and verified after its external checkpoint.",
            criteria=[
                {
                    "id": "PRODUCT-001",
                    "description": "The actual product and deployment satisfy the release contract.",
                    "scope": "product",
                    "risk": "R3",
                    "verificationType": "reality",
                    # The web e2e gate is the only legibility-backed (surface-ambiguous)
                    # evidence bound to this criterion; the deployment reality gate is
                    # mutation-producer evidence, which is pinned to "deployment" by producer
                    # type rather than by this declared surface.
                    "surface": "web",
                    "status": "UNTESTED",
                    "evidenceRefs": [],
                    "blocking": True,
                },
                {
                    "id": "AUTH-001",
                    "description": "Provider auth pauses and resumes through a trusted external checkpoint.",
                    "scope": "provider",
                    "risk": "R2",
                    "verificationType": "external",
                    "status": "UNTESTED",
                    "evidenceRefs": [],
                    "blocking": True,
                },
                {
                    "id": "DEPLOY-001",
                    "description": "The deployment task's own mutation is reconciled and verified in place.",
                    "scope": "deployment",
                    "risk": "R2",
                    "verificationType": "reality",
                    # Mutation-producer evidence is always surfaced "deployment"; this
                    # criterion is deliberately non-blocking so its risk-gate requirements
                    # never need an "e2e" gate (which only legibility evidence -- always
                    # web/electron/ios-surfaced -- can ever satisfy).
                    "surface": "deployment",
                    "status": "UNTESTED",
                    "evidenceRefs": [],
                    "blocking": False,
                },
            ],
            autonomy_scope="approved-program",
            policy_allow=[
                {"scope": "repository", "operations": ["edit", "build", "test"]},
                {"scope": "sandbox:fixture", "operations": ["deploy"]},
            ],
        )
        run_id = state["runId"]
        self.add_task(run_id, "backend")
        self.add_task(run_id, "web")
        self.add_task(run_id, "provider-auth", criteria=["AUTH-001"])
        self.add_task(
            run_id,
            "deployment",
            dependencies=["backend", "web"],
            risk="R3",
            criteria=["DEPLOY-001"],
            side_effect={"operation": "deploy", "target": "sandbox:fixture"},
        )
        self.add_task(
            run_id,
            "product-e2e",
            dependencies=["deployment", "provider-auth"],
            risk="R3",
        )

        self.assertEqual(
            {"backend", "web", "provider-auth"},
            {task["id"] for task in self.store.ready_tasks(run_id)},
        )
        self.store.start_task(run_id, "backend", worker_id="worker-backend")
        self.store.start_task(run_id, "web", worker_id="worker-web")
        self.store.start_task(run_id, "provider-auth", worker_id="worker-provider")
        running = self.store.load(run_id)
        self.assertEqual(3, sum(task["status"] == "RUNNING" for task in running["tasks"]))

        waiting, auth_challenge = self.store.wait_external(
            run_id,
            checkpoint_id="fixture-auth",
            task_id="provider-auth",
            checkpoint_type="AUTH_REQUIRED",
            principal="fixture-user",
            provider="fixture-mail",
            reason="Synthetic provider authentication is required.",
        )
        self.assertEqual("RUNNING", waiting["status"])
        provider_worker = next(worker for worker in waiting["workers"] if worker["id"] == "worker-provider")
        self.assertEqual("FINISHED", provider_worker["status"])

        self.finish(run_id, "backend", "worker-backend")
        self.finish(run_id, "web", "worker-web")
        self.assertEqual(["deployment"], [task["id"] for task in self.store.ready_tasks(run_id)])
        attempts_before_resume = {
            task["id"]: task["attempts"]
            for task in self.store.load(run_id)["tasks"]
            if task["id"] in {"backend", "web"}
        }

        self.store.start_task(run_id, "deployment", worker_id="worker-deploy")
        recovered = self.store.resume(run_id)
        deployment = next(task for task in recovered["tasks"] if task["id"] == "deployment")
        self.assertEqual("UNCERTAIN", deployment["sideEffect"]["state"])
        self.assertEqual("WAITING_RESOURCE", deployment["status"])
        self.assertEqual(
            attempts_before_resume,
            {
                task["id"]: task["attempts"]
                for task in recovered["tasks"]
                if task["id"] in {"backend", "web"}
            },
        )
        deployment_receipt = self.evidence(run_id, "deployment-receipt", task_id="deployment", producer="mutation")
        self.store.reconcile_side_effect(
            run_id,
            "deployment",
            result="applied",
            evidence_ref=deployment_receipt,
        )
        self.store.record_gate(
            run_id,
            gate_id="gate-deployment",
            task_id="deployment",
            gate_type="reality",
            status="PASS",
            evidence_refs=[deployment_receipt],
        )
        self.evidence(run_id, "evidence-deployment", task_id="deployment")
        self.store.complete_task(run_id, "deployment", evidence_refs=["gate:gate-deployment"])

        auth_evidence = self.evidence(
            run_id,
            "fixture-auth-resolution",
            task_id="provider-auth",
            producer="external-proof",
        )
        self.store.resolve_external(
            run_id,
            checkpoint_id="fixture-auth",
            resolution_ref=auth_evidence,
            challenge=auth_challenge,
            actor="human:fixture-user",
        )
        self.store.start_task(run_id, "provider-auth", worker_id="worker-provider-resumed")
        self.finish(run_id, "provider-auth", "worker-provider-resumed")
        self.store.record_gate(
            run_id,
            gate_id="gate-provider-auth-reality",
            task_id="provider-auth",
            gate_type="reality",
            status="PASS",
            evidence_refs=[auth_evidence],
            criteria=["AUTH-001"],
        )
        self.assertEqual(["product-e2e"], [task["id"] for task in self.store.ready_tasks(run_id)])

        self.store.start_task(run_id, "product-e2e", worker_id="worker-e2e")
        self.finish(run_id, "product-e2e", "worker-e2e", gate_type="e2e")
        # PRODUCT-001 (R3, surface "web") also needs its own "reality"-type PASS gate
        # (both from the risk-policy's explicit "reality" entry and from realityGate)
        # distinct from the "e2e"-type gate above. It is backed by the same web-surfaced
        # legibility evidence that product-e2e already produced -- the deployment task's
        # mutation-backed reality gate is intentionally kept off PRODUCT-001 since its
        # "deployment" evidence surface can never match PRODUCT-001's owned "web" surface.
        self.store.record_gate(
            run_id,
            gate_id="gate-product-reality",
            task_id=None,
            gate_type="reality",
            status="PASS",
            evidence_refs=["artifact:evidence-product-e2e"],
            criteria=["PRODUCT-001"],
        )
        self.store.set_criterion(run_id, "AUTH-001", "PASS", ["external:fixture-auth"])
        self.store.set_criterion(
            run_id, "PRODUCT-001", "PASS", ["gate:gate-product-e2e", "gate:gate-product-reality"]
        )
        gpt_evidence = self.evidence(run_id, "judge-gpt", producer="semantic-judge")
        self.store.record_gate(
            run_id,
            gate_id="judge-gpt",
            task_id=None,
            gate_type="semantic",
            family="gpt",
            status="PASS",
            evidence_refs=[gpt_evidence],
        )
        claude_evidence = self.evidence(run_id, "judge-claude", producer="semantic-judge")
        self.store.record_gate(
            run_id,
            gate_id="judge-claude",
            task_id=None,
            gate_type="semantic",
            family="claude",
            status="PASS",
            evidence_refs=[claude_evidence],
        )
        invariant = subprocess.run(
            [
                sys.executable,
                str(ROOT / "harness" / "invariant_engine.py"),
                "--repo",
                str(self.repo),
                "--run-id",
                run_id,
            ],
            cwd=self.repo,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, invariant.returncode, invariant.stderr or invariant.stdout)
        completed, outcome_pass = self.store.verify(run_id)
        self.assertTrue(
            outcome_pass,
            {
                "status": completed["status"],
                "missingRiskGates": missing_gate_requirements(
                    completed,
                    [criterion for criterion in completed["acceptanceCriteria"] if criterion["blocking"]],
                ),
            },
        )
        self.assertEqual("COMPLETED", completed["status"])
        self.assertEqual([], [task["id"] for task in completed["tasks"] if task["status"] != "COMPLETED"])

        event_types = [event["type"] for event in self.store.events(run_id)]
        self.assertIn("run.resumed", event_types)
        self.assertIn("external.wait_started", event_types)
        self.assertIn("external.wait_resolved", event_types)
        self.assertIn("mutation.reconciled", event_types)
        self.assertEqual("run.completed", event_types[-1])


if __name__ == "__main__":
    unittest.main(verbosity=2)