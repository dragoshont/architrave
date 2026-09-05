#!/usr/bin/env python3

from __future__ import annotations

import copy
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))

from architrave_runtime import FileLock, RunStore, RuntimeFailure, parse_iso, state_summary, utc_now


class RuntimeV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.email", "architrave@example.invalid")
        self.git("config", "user.name", "Architrave Test")
        (self.repo / "README.md").write_text("# Fixture\n", encoding="utf-8")
        self.git("add", "README.md")
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

    def criterion(
        self, *, risk: str = "R1", verification: str = "deterministic", surface: str | None = None
    ) -> dict[str, object]:
        if surface is None and verification in {"reality", "e2e"}:
            surface = "web"
        return {
            "id": "OUTCOME-001",
            "description": "The fixture reaches a verified outcome.",
            "scope": "fixture",
            "risk": risk,
            "verificationType": verification,
            "surface": surface,
            "status": "UNTESTED",
            "evidenceRefs": [],
            "blocking": True,
        }

    def create(
        self,
        *,
        autonomy: str = "approved-program",
        risk: str = "R1",
        verification: str = "deterministic",
        allow: list[dict[str, object]] | None = None,
        confirmation: list[str] | None = None,
    ) -> dict[str, object]:
        return self.store.create(
            goal="Exercise the durable runtime.",
            outcome="The fixture reaches a verified outcome.",
            criteria=[self.criterion(risk=risk, verification=verification)],
            autonomy_scope=autonomy,
            policy_allow=allow or [],
            confirmation_required=confirmation or [],
        )

    def add_task(
        self,
        run_id: str,
        task_id: str,
        *,
        dependencies: list[str] | None = None,
        mutable: bool = False,
        side_effect: dict[str, str] | None = None,
        risk: str = "R1",
    ) -> dict[str, object]:
        return self.store.add_task(
            run_id,
            {
                "id": task_id,
                "title": task_id,
                "objective": f"Complete {task_id}.",
                "dependencies": dependencies or [],
                "workerProfile": "shell",
                "mutablePaths": ["README.md"] if mutable else [],
                "tools": ["test"],
                "risk": risk,
                "acceptanceCriteria": ["OUTCOME-001"],
                "requiredArtifacts": [f"evidence-{task_id}"],
                "gate": "fixture gate",
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
        surface: str = "web",
    ) -> str:
        path = self.store.run_dir(run_id) / "evidence" / f"{artifact_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        state = self.store.load(run_id)
        criteria = [criterion["id"] for criterion in state["acceptanceCriteria"] if criterion["blocking"]]
        if producer == "deterministic":
            payload = {"status": "pass", "exitCode": 0, "command": "fixture"}
        elif producer == "legibility":
            required_results = {
                "web": ["runtime.health", "web.e2e"],
                "electron": ["electron.launch", "electron.health", "electron.screenshot"],
                "ios": ["ios.build", "ios.install", "ios.launch", "ios.screenshot", "ios.blank-screen"],
            }[surface]
            payload = {
                "surface": surface,
                "status": "pass",
                "failed": [],
                "results": [{"name": name, "status": "pass"} for name in required_results],
            }
        elif producer == "mutation":
            payload = {
                "taskId": task_id,
                "operation": "deploy",
                "target": "homelab:fixture",
                "expected": {"version": "1.0.0", "digest": "sha256:test"},
                "result": {"status": "pass", "mismatches": [], "apply": {"status": "pass"}},
                "verification": {
                    "health": {"status": "pass"},
                    "version": {"stdout": "1.0.0"},
                    "digest": {"stdout": "sha256:test"},
                },
            }
        elif producer == "semantic-judge":
            payload = {
                "verdict": "PASS",
                "family": "claude" if "claude" in artifact_id else "gpt",
                "criteria": criteria,
            }
        elif producer == "external-proof":
            checkpoint = next(item for item in state["externalCheckpoints"] if item["status"] == "PENDING")
            payload = {
                "checkpointId": checkpoint["id"],
                "principal": checkpoint["principal"],
                "provider": checkpoint["provider"],
            }
        else:
            payload = {"note": artifact_id}
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        method = {
            "deterministic": self.store._record_deterministic_result,
            "legibility": lambda target_run, **kwargs: self.store._record_legibility_result(target_run, kind=f"{surface}-legibility", **kwargs),
            "mutation": self.store._record_mutation_receipt,
            "semantic-judge": self.store._record_semantic_verdict,
            "external-proof": self.store._record_external_proof,
            "coordinator": lambda target_run, **kwargs: self.store.record_artifact(target_run, kind="coordinator-note", **kwargs),
        }[producer]
        method(
            run_id,
            artifact_id=artifact_id,
            path=path.relative_to(self.store.repository).as_posix(),
            evidence_refs=[f"task:{task_id}"] if task_id else [],
        )
        return f"artifact:{artifact_id}"

    def finish_task(self, run_id: str, task_id: str, worker_id: str) -> None:
        self.store.start_task(run_id, task_id, worker_id=worker_id)
        self.store.finish_worker(run_id, task_id, worker_id=worker_id, status="FINISHED")
        evidence = self.evidence(run_id, f"evidence-{task_id}", task_id=task_id)
        self.store.record_gate(
            run_id,
            gate_id=f"gate-{task_id}",
            task_id=task_id,
            gate_type="deterministic",
            status="PASS",
            evidence_refs=[evidence],
        )
        self.store.complete_task(run_id, task_id, evidence_refs=[f"gate:gate-{task_id}"])

    def test_create_anchors_hash_chained_event_log(self) -> None:
        state = self.create()
        run_id = str(state["runId"])
        events = self.store.events(run_id)
        self.assertEqual("architrave.run.v2", state["schema"])
        self.assertEqual(1, len(events))
        self.assertEqual("run.created", events[0]["type"])
        self.assertEqual(events[0]["hash"], state["eventCursor"]["lastHash"])
        self.assertIsNone(state["pendingEvent"])
        self.assertTrue((self.store.run_dir(run_id) / "phase-ledger.md").is_file())
        self.assertTrue(self.store.key_path.is_file())
        if os.name != "nt":
            self.assertEqual(0o600, self.store.key_path.stat().st_mode & 0o777)

    def test_missing_runtime_key_fails_closed(self) -> None:
        state = self.create()
        run_id = str(state["runId"])
        self.store.key_path.unlink()
        with self.assertRaisesRegex(RuntimeFailure, "authentication key is unavailable"):
            self.store.load(run_id)

    @unittest.skipIf(os.name == "nt", "POSIX key permissions")
    def test_unsafe_runtime_key_permissions_fail_closed(self) -> None:
        state = self.create()
        run_id = str(state["runId"])
        self.store.key_path.chmod(0o644)
        with self.assertRaisesRegex(RuntimeFailure, "permissions or owner are unsafe"):
            self.store.load(run_id)

    def test_secret_like_values_are_not_persisted(self) -> None:
        secret = "sk-1234567890ABCDEFGHIJKLMN"
        state = self.store.create(
            goal=f"Do not persist {secret}.",
            outcome="Run evidence remains redacted.",
            criteria=[self.criterion()],
            autonomy_scope="approved-program",
        )
        run_id = str(state["runId"])
        state_text = (self.store.run_dir(run_id) / "run.json").read_text(encoding="utf-8")
        events_text = (self.store.run_dir(run_id) / "events.jsonl").read_text(encoding="utf-8")
        self.assertNotIn(secret, state_text)
        self.assertNotIn(secret, events_text)
        self.assertIn("[REDACTED]", state_text)

    def test_approved_program_automatically_releases_dependent_task(self) -> None:
        state = self.create(allow=[{"scope": "repository", "operations": ["edit"]}])
        run_id = str(state["runId"])
        self.add_task(run_id, "first", mutable=True)
        self.add_task(run_id, "second", dependencies=["first"])
        self.finish_task(run_id, "first", "worker-first")
        state = self.store.load(run_id)
        self.assertEqual("COMPLETED", next(task for task in state["tasks"] if task["id"] == "first")["status"])
        self.assertEqual("READY", next(task for task in state["tasks"] if task["id"] == "second")["status"])
        self.assertEqual("RUNNING", state["status"])

    def test_current_task_pauses_at_dependency_boundary(self) -> None:
        state = self.create(autonomy="current-task")
        run_id = str(state["runId"])
        self.add_task(run_id, "first")
        self.add_task(run_id, "second", dependencies=["first"])
        self.finish_task(run_id, "first", "worker-first")
        state = self.store.load(run_id)
        self.assertEqual("PAUSED", state["status"])
        self.assertEqual("READY", next(task for task in state["tasks"] if task["id"] == "second")["status"])
        resumed = self.store.resume(run_id)
        self.assertEqual("RUNNING", resumed["status"])

    def test_advisory_only_and_default_deny_block_mutation(self) -> None:
        state = self.create(
            autonomy="advisory-only",
            allow=[{"scope": "repository", "operations": ["edit"]}],
        )
        run_id = str(state["runId"])
        self.add_task(run_id, "mutate", mutable=True)
        with self.assertRaisesRegex(RuntimeFailure, "advisory-only"):
            self.store.start_task(run_id, "mutate", worker_id="worker")

        state = self.create()
        run_id = str(state["runId"])
        self.add_task(run_id, "mutate", mutable=True)
        with self.assertRaisesRegex(RuntimeFailure, "denied"):
            self.store.start_task(run_id, "mutate", worker_id="worker")

    def test_confirmation_and_scoped_deployment_policy(self) -> None:
        state = self.create(
            allow=[{"scope": "homelab:fixture", "operations": ["deploy"]}],
            confirmation=["deploy"],
        )
        run_id = str(state["runId"])
        denied = self.store.policy_check(run_id, "homelab:other", "deploy")
        pending = self.store.policy_check(run_id, "homelab:fixture", "deploy")
        allowed = self.store.policy_check(run_id, "homelab:fixture", "deploy", confirmed=True)
        self.assertEqual("denied", denied["status"])
        self.assertEqual("confirmation-required", pending["status"])
        self.assertEqual("allowed", allowed["status"])

    def test_external_wait_does_not_block_independent_ready_task(self) -> None:
        state = self.create()
        run_id = str(state["runId"])
        self.add_task(run_id, "auth-task")
        self.add_task(run_id, "independent")
        state, challenge = self.store.wait_external(
            run_id,
            checkpoint_id="auth-1",
            task_id="auth-task",
            checkpoint_type="MFA_REQUIRED",
            principal="fixture-user",
            provider="fixture-provider",
            reason="Complete synthetic MFA.",
        )
        self.assertEqual("RUNNING", state["status"])
        self.assertEqual(["independent"], [task["id"] for task in self.store.ready_tasks(run_id)])
        resolution_evidence = self.evidence(run_id, "auth-resolution", producer="external-proof")
        with self.assertRaisesRegex(RuntimeFailure, "human or coordinator"):
            self.store.resolve_external(
                run_id,
                checkpoint_id="auth-1",
                resolution_ref=resolution_evidence,
                challenge=challenge,
                actor="worker:forged",
            )
        with self.assertRaisesRegex(RuntimeFailure, "challenge is invalid"):
            self.store.resolve_external(
                run_id,
                checkpoint_id="auth-1",
                resolution_ref=resolution_evidence,
                challenge="forged-challenge",
                actor="human:fixture-user",
            )
        resolved = self.store.resolve_external(
            run_id,
            checkpoint_id="auth-1",
            resolution_ref=resolution_evidence,
            challenge=challenge,
            actor="human:fixture-user",
        )
        self.assertEqual({"auth-task", "independent"}, {task["id"] for task in resolved["tasks"] if task["status"] == "READY"})

    def test_pending_event_is_recovered_after_interrupted_commit(self) -> None:
        state = self.create()
        run_id = str(state["runId"])
        run_dir = self.store.run_dir(run_id)
        original_sequence = state["eventCursor"]["sequence"]
        with FileLock(run_dir / ".run.lock"):
            _, interrupted = self.store._load_locked(run_id)
            interrupted["revision"] += 1
            interrupted["updatedAt"] = utc_now()
            event = self.store._new_event(
                interrupted,
                "failure.injected",
                "test",
                None,
                {"phase": "before-event-append"},
                (),
            )
            interrupted["pendingEvent"] = event
            self.store._atomic_write(run_dir / "run.json", interrupted)
        recovered = self.store.load(run_id)
        self.assertEqual(original_sequence + 1, recovered["eventCursor"]["sequence"])
        self.assertIsNone(recovered["pendingEvent"])
        self.assertEqual("failure.injected", self.store.events(run_id)[-1]["type"])

    def test_completed_task_is_not_repeated_on_resume(self) -> None:
        state = self.create()
        run_id = str(state["runId"])
        self.add_task(run_id, "done")
        self.finish_task(run_id, "done", "worker-done")
        before = self.store.load(run_id)
        resumed = self.store.resume(run_id)
        task_before = next(task for task in before["tasks"] if task["id"] == "done")
        task_after = next(task for task in resumed["tasks"] if task["id"] == "done")
        self.assertEqual("COMPLETED", task_after["status"])
        self.assertEqual(task_before["attempts"], task_after["attempts"])

    def test_resume_requires_reconciliation_for_unknown_side_effect(self) -> None:
        state = self.create(allow=[{"scope": "homelab:fixture", "operations": ["deploy"]}])
        run_id = str(state["runId"])
        self.add_task(
            run_id,
            "deploy",
            side_effect={"operation": "deploy", "target": "homelab:fixture"},
            risk="R3",
        )
        self.store.start_task(run_id, "deploy", worker_id="worker-deploy")
        resumed = self.store.resume(run_id)
        task = next(task for task in resumed["tasks"] if task["id"] == "deploy")
        self.assertEqual("WAITING_RESOURCE", task["status"])
        self.assertEqual("UNCERTAIN", task["sideEffect"]["state"])
        receipt = self.evidence(run_id, "deployment-reconciliation", task_id="deploy", producer="mutation")
        reconciled = self.store.reconcile_side_effect(
            run_id,
            "deploy",
            result="applied",
            evidence_ref=receipt,
        )
        task = next(task for task in reconciled["tasks"] if task["id"] == "deploy")
        self.assertEqual("WAITING_RESOURCE", task["status"])
        self.assertEqual("CONFIRMED", task["sideEffect"]["state"])

    def test_mutation_receipt_cannot_reconcile_another_task(self) -> None:
        state = self.create(allow=[{"scope": "homelab:fixture", "operations": ["deploy"]}])
        run_id = str(state["runId"])
        self.add_task(
            run_id,
            "deploy-one",
            side_effect={"operation": "deploy", "target": "homelab:fixture"},
            risk="R3",
        )
        self.add_task(
            run_id,
            "deploy-two",
            side_effect={"operation": "deploy", "target": "homelab:fixture"},
            risk="R3",
        )
        for task_id in ("deploy-one", "deploy-two"):
            self.store.start_task(run_id, task_id, worker_id=f"worker-{task_id}")
            self.store.finish_worker(run_id, task_id, worker_id=f"worker-{task_id}", status="FAILED")
        receipt = self.evidence(run_id, "deploy-one-receipt", task_id="deploy-one", producer="mutation")
        with self.assertRaisesRegex(RuntimeFailure, "wrong producer|cannot prove not-applied"):
            self.store.reconcile_side_effect(run_id, "deploy-one", result="not-applied", evidence_ref=receipt)
        self.store.reconcile_side_effect(run_id, "deploy-one", result="applied", evidence_ref=receipt)
        with self.assertRaisesRegex(RuntimeFailure, "already consumed|does not bind to this task"):
            self.store.reconcile_side_effect(run_id, "deploy-two", result="applied", evidence_ref=receipt)

    def test_not_applied_requires_matching_reconciliation_receipt(self) -> None:
        state = self.create(allow=[{"scope": "homelab:fixture", "operations": ["deploy"]}])
        run_id = str(state["runId"])
        self.add_task(
            run_id,
            "deploy",
            side_effect={"operation": "deploy", "target": "homelab:fixture"},
            risk="R3",
        )
        self.store.start_task(run_id, "deploy", worker_id="worker-deploy")
        self.store.finish_worker(run_id, "deploy", worker_id="worker-deploy", status="FAILED")
        path = self.store.run_dir(run_id) / "evidence" / "not-applied.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "taskId": "deploy",
                    "operation": "deploy",
                    "target": "homelab:fixture",
                    "outcome": "not-applied",
                    "observedAt": "2026-08-13T00:00:00Z",
                    "observation": "live target remains at pre-operation digest",
                }
            ),
            encoding="utf-8",
        )
        self.store._record_reconciliation_receipt(
            run_id,
            artifact_id="not-applied",
            path=path.relative_to(self.store.repository).as_posix(),
            evidence_refs=["task:deploy"],
        )
        reconciled = self.store.reconcile_side_effect(
            run_id,
            "deploy",
            result="not-applied",
            evidence_ref="artifact:not-applied",
        )
        task = next(item for item in reconciled["tasks"] if item["id"] == "deploy")
        self.assertEqual("READY", task["status"])
        self.assertEqual("NONE", task["sideEffect"]["state"])
        self.store.start_task(run_id, "deploy", worker_id="worker-deploy-retry")
        self.store.finish_worker(run_id, "deploy", worker_id="worker-deploy-retry", status="FAILED")
        with self.assertRaisesRegex(RuntimeFailure, "already consumed"):
            self.store.reconcile_side_effect(
                run_id,
                "deploy",
                result="not-applied",
                evidence_ref="artifact:not-applied",
            )

    def test_duplicate_mutation_receipt_content_is_rejected(self) -> None:
        state = self.create(allow=[{"scope": "homelab:fixture", "operations": ["deploy"]}])
        run_id = str(state["runId"])
        self.add_task(
            run_id,
            "deploy",
            side_effect={"operation": "deploy", "target": "homelab:fixture"},
            risk="R3",
        )
        self.store.start_task(run_id, "deploy", worker_id="worker-deploy")
        self.store.finish_worker(run_id, "deploy", worker_id="worker-deploy", status="FAILED")
        receipt = self.evidence(run_id, "receipt-one", task_id="deploy", producer="mutation")
        artifact = next(item for item in self.store.load(run_id)["artifacts"] if item["id"] == receipt.split(":", 1)[1])
        with self.assertRaisesRegex(RuntimeFailure, "already registered"):
            self.store._record_mutation_receipt(
                run_id,
                artifact_id="receipt-two",
                path=artifact["path"],
                evidence_refs=["task:deploy"],
            )

    def test_forged_mutation_receipt_is_rejected(self) -> None:
        state = self.create(allow=[{"scope": "homelab:fixture", "operations": ["deploy"]}])
        run_id = str(state["runId"])
        self.add_task(
            run_id,
            "deploy",
            side_effect={"operation": "deploy", "target": "homelab:fixture"},
            risk="R3",
        )
        self.store.start_task(run_id, "deploy", worker_id="worker-deploy")
        self.store.finish_worker(run_id, "deploy", worker_id="worker-deploy", status="FAILED")
        path = self.store.run_dir(run_id) / "evidence" / "forged-receipt.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "taskId": "deploy",
                    "operation": "deploy",
                    "target": "homelab:fixture",
                    "expected": {"version": "1.0.0", "digest": "sha256:test"},
                    "result": {"status": "pass", "mismatches": [], "apply": {"status": "pass"}},
                    "verification": {
                        "health": {"status": "fail"},
                        "version": {"stdout": "stale"},
                        "digest": {"stdout": "sha256:wrong"},
                    },
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(RuntimeFailure, "health verification did not pass"):
            self.store._record_mutation_receipt(
                run_id,
                artifact_id="forged-receipt",
                path=path.relative_to(self.store.repository).as_posix(),
                evidence_refs=["task:deploy"],
            )

    def test_forged_mutation_version_and_digest_are_rejected_independently(self) -> None:
        cases = [
            ("version", "stale", "sha256:test", "observed version"),
            ("digest", "1.0.0", "sha256:wrong", "observed digest"),
        ]
        for label, observed_version, observed_digest, expected_error in cases:
            with self.subTest(label=label):
                state = self.create(allow=[{"scope": "homelab:fixture", "operations": ["deploy"]}])
                run_id = str(state["runId"])
                self.add_task(
                    run_id,
                    "deploy",
                    side_effect={"operation": "deploy", "target": "homelab:fixture"},
                    risk="R3",
                )
                self.store.start_task(run_id, "deploy", worker_id="worker-deploy")
                self.store.finish_worker(run_id, "deploy", worker_id="worker-deploy", status="FAILED")
                path = self.store.run_dir(run_id) / "evidence" / f"forged-{label}.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps(
                        {
                            "taskId": "deploy",
                            "operation": "deploy",
                            "target": "homelab:fixture",
                            "expected": {"version": "1.0.0", "digest": "sha256:test"},
                            "result": {"status": "pass", "mismatches": [], "apply": {"status": "pass"}},
                            "verification": {
                                "health": {"status": "pass"},
                                "version": {"stdout": observed_version},
                                "digest": {"stdout": observed_digest},
                            },
                        }
                    ),
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(RuntimeFailure, expected_error):
                    self.store._record_mutation_receipt(
                        run_id,
                        artifact_id=f"forged-{label}",
                        path=path.relative_to(self.store.repository).as_posix(),
                        evidence_refs=["task:deploy"],
                    )

    def test_event_tampering_is_detected(self) -> None:
        state = self.create()
        run_id = str(state["runId"])
        event_path = self.store.run_dir(run_id) / "events.jsonl"
        event = json.loads(event_path.read_text(encoding="utf-8"))
        event["payload"]["goal"] = "forged"
        event_path.write_text(json.dumps(event) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeFailure, "hash chain"):
            self.store.load(run_id)

    def test_worker_cannot_escalate_policy(self) -> None:
        state = self.create()
        run_id = str(state["runId"])
        before_events = len(self.store.events(run_id))

        def malicious(run: dict[str, object]) -> dict[str, object]:
            run["policy"]["allow"].append({"scope": "*", "operations": ["*"]})
            return {}

        with self.assertRaisesRegex(RuntimeFailure, "cannot modify"):
            self.store._transaction(
                run_id,
                malicious,
                event_type="worker.finished",
                actor="worker:malicious",
            )
        self.assertEqual([], self.store.load(run_id)["policy"]["allow"])
        self.assertEqual(before_events, len(self.store.events(run_id)))

    def test_direct_policy_tampering_is_detected(self) -> None:
        state = self.create()
        run_id = str(state["runId"])
        path = self.store.run_dir(run_id) / "run.json"
        forged = json.loads(path.read_text(encoding="utf-8"))
        forged["policy"]["allow"].append({"scope": "*", "operations": ["*"]})
        path.write_text(json.dumps(forged), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeFailure, "latest valid snapshot"):
            self.store.load(run_id)

    def test_checkpoint_deletion_is_detected(self) -> None:
        state = self.create()
        run_id = str(state["runId"])
        self.add_task(run_id, "checkpointed")
        self.finish_task(run_id, "checkpointed", "worker-checkpointed")
        path = self.store.run_dir(run_id) / "run.json"
        forged = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(forged["checkpoints"])
        forged["checkpoints"].pop()
        path.write_text(json.dumps(forged), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeFailure, "latest valid snapshot"):
            self.store.load(run_id)

    def test_stale_repository_pause_is_durable(self) -> None:
        state = self.create()
        run_id = str(state["runId"])
        (self.repo / "drift.txt").write_text("drift\n", encoding="utf-8")
        self.git("add", "drift.txt")
        self.git("commit", "-qm", "drift")
        with self.assertRaisesRegex(RuntimeFailure, "baseline drift"):
            self.store.resume(run_id)
        paused = self.store.load(run_id)
        self.assertEqual("PAUSED", paused["status"])
        self.assertEqual("run.paused", self.store.events(run_id)[-1]["type"])
        resumed = self.store.resume(run_id, accept_commit=True)
        self.assertEqual(self.git("rev-parse", "HEAD"), resumed["baseline"]["commit"])

    def test_repository_drift_blocks_task_start(self) -> None:
        state = self.create()
        run_id = str(state["runId"])
        self.add_task(run_id, "drifted")
        (self.repo / "drift.txt").write_text("drift\n", encoding="utf-8")
        self.git("add", "drift.txt")
        self.git("commit", "-qm", "drift")
        with self.assertRaisesRegex(RuntimeFailure, "baseline drift"):
            self.store.start_task(run_id, "drifted", worker_id="worker")

    def test_deterministic_failure_overrides_semantic_pass(self) -> None:
        state = self.create(verification="semantic")
        run_id = str(state["runId"])
        semantic_evidence = self.evidence(run_id, "semantic-evidence", producer="semantic-judge")
        self.store.record_gate(
            run_id,
            gate_id="semantic",
            task_id=None,
            gate_type="semantic",
            status="PASS",
            evidence_refs=[semantic_evidence],
            family="gpt",
        )
        self.store.set_criterion(run_id, "OUTCOME-001", "PASS", ["gate:semantic"])
        failed = self.store.record_gate(
            run_id,
            gate_id="build",
            task_id=None,
            gate_type="deterministic",
            status="FAIL",
            evidence_refs=["build:failed"],
        )
        self.assertEqual("FAILED", failed["status"])
        verified, completed = self.store.verify(run_id)
        self.assertFalse(completed)
        self.assertEqual("FAILED", verified["status"])

    def test_arbitrary_evidence_cannot_create_false_pass(self) -> None:
        state = self.create()
        run_id = str(state["runId"])
        with self.assertRaisesRegex(RuntimeFailure, "registered Run evidence"):
            self.store.set_criterion(run_id, "OUTCOME-001", "PASS", ["forged:anything"])
        with self.assertRaisesRegex(RuntimeFailure, "registered evidence"):
            self.store.set_criterion(run_id, "OUTCOME-001", "NOT_APPLICABLE", [])
        with self.assertRaisesRegex(RuntimeFailure, "registered Run evidence"):
            self.store.record_gate(
                run_id,
                gate_id="forged-pass",
                task_id=None,
                gate_type="deterministic",
                status="PASS",
                evidence_refs=["artifact:not-registered"],
            )
        coordinator_evidence = self.evidence(run_id, "coordinator-note", producer="coordinator")
        with self.assertRaisesRegex(RuntimeFailure, "untrusted producer"):
            self.store.record_gate(
                run_id,
                gate_id="coordinator-forged-pass",
                task_id=None,
                gate_type="deterministic",
                status="PASS",
                evidence_refs=[coordinator_evidence],
            )
        verified, completed = self.store.verify(run_id)
        self.assertFalse(completed)
        self.assertEqual("VERIFYING", verified["status"])

    # -- Finding #4: enforce criterion.verificationType and exact evidence bindings.

    def test_gate_type_verification_mismatch_is_rejected(self) -> None:
        state = self.create(verification="deterministic")
        run_id = str(state["runId"])
        legibility_evidence = self.evidence(run_id, "reality-evidence", producer="legibility")
        self.store.record_gate(
            run_id,
            gate_id="reality-gate",
            task_id=None,
            gate_type="reality",
            status="PASS",
            evidence_refs=[legibility_evidence],
            criteria=["OUTCOME-001"],
        )
        with self.assertRaisesRegex(RuntimeFailure, "verificationType"):
            self.store.set_criterion(run_id, "OUTCOME-001", "PASS", ["gate:reality-gate"])

    def test_gate_not_bound_to_criterion_is_rejected(self) -> None:
        state = self.store.create(
            goal="Exercise per-criterion gate binding.",
            outcome="Only gates bound to a criterion may satisfy it.",
            criteria=[
                {
                    "id": "OUTCOME-A",
                    "description": "First outcome.",
                    "scope": "fixture",
                    "risk": "R1",
                    "verificationType": "deterministic",
                    "status": "UNTESTED",
                    "evidenceRefs": [],
                    "blocking": True,
                },
                {
                    "id": "OUTCOME-B",
                    "description": "Second outcome.",
                    "scope": "fixture",
                    "risk": "R1",
                    "verificationType": "deterministic",
                    "status": "UNTESTED",
                    "evidenceRefs": [],
                    "blocking": True,
                },
            ],
            autonomy_scope="approved-program",
        )
        run_id = str(state["runId"])
        deterministic_evidence = self.evidence(run_id, "gate-b-evidence")
        self.store.record_gate(
            run_id,
            gate_id="gate-b",
            task_id=None,
            gate_type="deterministic",
            status="PASS",
            evidence_refs=[deterministic_evidence],
            criteria=["OUTCOME-B"],
        )
        with self.assertRaisesRegex(RuntimeFailure, "not bound to this criterion"):
            self.store.set_criterion(run_id, "OUTCOME-A", "PASS", ["gate:gate-b"])

    # -- Phase 2 follow-up Finding #4: taskless reality gates must not silently bind to every
    # blocking criterion, and reality/e2e evidence must be validated against a specific
    # verification surface rather than accepted for whatever criteria the caller names.

    def test_taskless_reality_gate_with_multiple_criteria_requires_explicit_binding(self) -> None:
        state = self.store.create(
            goal="Exercise taskless reality-gate criterion binding.",
            outcome="Only the surface actually exercised may be proven by a taskless gate.",
            criteria=[
                {
                    "id": "WEB-001",
                    "description": "The web surface is usable.",
                    "scope": "product",
                    "risk": "R3",
                    "verificationType": "reality",
                    "surface": "web",
                    "status": "UNTESTED",
                    "evidenceRefs": [],
                    "blocking": True,
                },
                {
                    "id": "IOS-001",
                    "description": "The iOS surface is usable.",
                    "scope": "product",
                    "risk": "R3",
                    "verificationType": "reality",
                    "surface": "ios",
                    "status": "UNTESTED",
                    "evidenceRefs": [],
                    "blocking": True,
                },
            ],
            autonomy_scope="approved-program",
        )
        run_id = str(state["runId"])
        legibility_evidence = self.evidence(run_id, "web-reality-evidence", producer="legibility")
        # Regression: previously a taskless reality gate with no explicit `criteria` silently
        # bound to every blocking criterion, so proof of the web surface alone would also have
        # (falsely) satisfied IOS-001, which this gate's evidence never exercised.
        with self.assertRaisesRegex(RuntimeFailure, "explicitly bind"):
            self.store.record_gate(
                run_id,
                gate_id="reality-web",
                task_id=None,
                gate_type="reality",
                status="PASS",
                evidence_refs=[legibility_evidence],
            )
        self.store.record_gate(
            run_id,
            gate_id="reality-web",
            task_id=None,
            gate_type="reality",
            status="PASS",
            evidence_refs=[legibility_evidence],
            criteria=["WEB-001"],
        )
        self.store.set_criterion(run_id, "WEB-001", "PASS", ["gate:reality-web"])
        with self.assertRaisesRegex(RuntimeFailure, "not bound to this criterion"):
            self.store.set_criterion(run_id, "IOS-001", "PASS", ["gate:reality-web"])

    def test_reality_gate_evidence_surface_mismatch_is_rejected(self) -> None:
        state = self.create(verification="reality")
        run_id = str(state["runId"])
        web_evidence = self.evidence(run_id, "web-reality-evidence", producer="legibility")
        with self.assertRaisesRegex(RuntimeFailure, "EVIDENCE_SURFACE_MISMATCH|does not match"):
            self.store.record_gate(
                run_id,
                gate_id="reality-web-declared-ios",
                task_id=None,
                gate_type="reality",
                status="PASS",
                evidence_refs=[web_evidence],
                criteria=["OUTCOME-001"],
                surface="ios",
            )
        # The matching surface remains accepted.
        self.store.record_gate(
            run_id,
            gate_id="reality-web-declared-web",
            task_id=None,
            gate_type="reality",
            status="PASS",
            evidence_refs=[web_evidence],
            criteria=["OUTCOME-001"],
            surface="web",
        )

    # -- Final blocker #2: reality/e2e criteria must own their expected verification surface,
    # and record_gate must compare evidence against that ownership rather than caller claims.

    def test_criterion_creation_enforces_surface_ownership_rules(self) -> None:
        with self.assertRaisesRegex(RuntimeFailure, "must declare the product surface"):
            self.store.create(
                goal="Exercise surface ownership validation.",
                outcome="A reality criterion without a declared surface is rejected.",
                criteria=[
                    {
                        "id": "NO-SURFACE-001",
                        "description": "Missing surface.",
                        "scope": "product",
                        "risk": "R2",
                        "verificationType": "reality",
                        "status": "UNTESTED",
                        "evidenceRefs": [],
                        "blocking": True,
                    }
                ],
                autonomy_scope="approved-program",
            )
        with self.assertRaisesRegex(RuntimeFailure, "invalid verification surface"):
            self.store.create(
                goal="Exercise surface ownership validation.",
                outcome="An unknown surface value is rejected.",
                criteria=[
                    {
                        "id": "BAD-SURFACE-001",
                        "description": "Invalid surface.",
                        "scope": "product",
                        "risk": "R2",
                        "verificationType": "reality",
                        "surface": "desktop",
                        "status": "UNTESTED",
                        "evidenceRefs": [],
                        "blocking": True,
                    }
                ],
                autonomy_scope="approved-program",
            )
        with self.assertRaisesRegex(RuntimeFailure, "must not declare a verification surface"):
            self.store.create(
                goal="Exercise surface ownership validation.",
                outcome="A non-reality/e2e criterion cannot declare a surface.",
                criteria=[
                    {
                        "id": "DET-SURFACE-001",
                        "description": "Deterministic criteria have no surface.",
                        "scope": "product",
                        "risk": "R1",
                        "verificationType": "deterministic",
                        "surface": "web",
                        "status": "UNTESTED",
                        "evidenceRefs": [],
                        "blocking": True,
                    }
                ],
                autonomy_scope="approved-program",
            )

    def test_reality_gate_evidence_surface_must_match_criterion_ownership_even_without_declared_surface(
        self,
    ) -> None:
        # Regression: a caller can simply omit the `surface` parameter to dodge the
        # declared-vs-evidence check; record_gate must still compare the evidence surface
        # against whatever surface the bound criterion itself owns, not trust the caller.
        state = self.store.create(
            goal="Exercise criterion-owned surface enforcement.",
            outcome="An iOS-owned criterion cannot be satisfied by web evidence.",
            criteria=[
                {
                    "id": "IOS-OWNED-001",
                    "description": "The iOS surface is usable.",
                    "scope": "product",
                    "risk": "R3",
                    "verificationType": "reality",
                    "surface": "ios",
                    "status": "UNTESTED",
                    "evidenceRefs": [],
                    "blocking": True,
                }
            ],
            autonomy_scope="approved-program",
        )
        run_id = str(state["runId"])
        web_evidence = self.evidence(run_id, "forged-web-evidence", producer="legibility")
        with self.assertRaisesRegex(RuntimeFailure, "criterion-owned verification surface"):
            self.store.record_gate(
                run_id,
                gate_id="reality-forged-surface",
                task_id=None,
                gate_type="reality",
                status="PASS",
                evidence_refs=[web_evidence],
                criteria=["IOS-OWNED-001"],
                # No `surface` declared at all -- the pre-fix code path had nothing left to
                # check once the caller stopped declaring a surface.
            )
        # Evidence for the criterion's actually-owned surface remains accepted.
        ios_evidence = self.evidence(run_id, "genuine-ios-evidence", producer="legibility", surface="ios")
        self.store.record_gate(
            run_id,
            gate_id="reality-genuine-surface",
            task_id=None,
            gate_type="reality",
            status="PASS",
            evidence_refs=[ios_evidence],
            criteria=["IOS-OWNED-001"],
        )

    def test_mutation_evidence_cannot_satisfy_a_criterion_owned_ios_surface(self) -> None:
        # Regression: criterion-owned surface enforcement must apply to every derived
        # reality/e2e evidence surface, not only legibility. A mutation receipt is always
        # surfaced "deployment" and must never be accepted as proof for an iOS-owned criterion.
        state = self.store.create(
            goal="Exercise criterion-owned surface enforcement across all evidence producers.",
            outcome="An iOS-owned criterion cannot be satisfied by deployment (mutation) evidence.",
            criteria=[
                {
                    "id": "IOS-OWNED-002",
                    "description": "The iOS surface is usable.",
                    "scope": "product",
                    "risk": "R3",
                    "verificationType": "reality",
                    "surface": "ios",
                    "status": "UNTESTED",
                    "evidenceRefs": [],
                    "blocking": True,
                }
            ],
            autonomy_scope="approved-program",
            policy_allow=[{"scope": "homelab:fixture", "operations": ["deploy"]}],
        )
        run_id = str(state["runId"])
        self.store.add_task(
            run_id,
            {
                "id": "deploy",
                "title": "deploy",
                "objective": "Deploy the fixture.",
                "dependencies": [],
                "workerProfile": "shell",
                "mutablePaths": [],
                "tools": ["test"],
                "risk": "R3",
                "acceptanceCriteria": ["IOS-OWNED-002"],
                "requiredArtifacts": ["evidence-deploy"],
                "gate": "fixture gate",
                "maxAttempts": 2,
                "sideEffect": {"operation": "deploy", "target": "homelab:fixture"},
            },
        )
        deployment_evidence = self.evidence(run_id, "forged-deployment-evidence", task_id="deploy", producer="mutation")
        with self.assertRaisesRegex(RuntimeFailure, "criterion-owned verification surface"):
            self.store.record_gate(
                run_id,
                gate_id="reality-forged-deployment-surface",
                task_id=None,
                gate_type="reality",
                status="PASS",
                evidence_refs=[deployment_evidence],
                criteria=["IOS-OWNED-002"],
            )

    def test_external_proof_evidence_cannot_satisfy_a_criterion_owned_web_surface(self) -> None:
        # Regression: criterion-owned surface enforcement must apply to every derived
        # reality/e2e evidence surface, not only legibility. An external-proof artifact is
        # always surfaced "runtime" and must never be accepted as proof for a web-owned
        # criterion.
        state = self.store.create(
            goal="Exercise criterion-owned surface enforcement across all evidence producers.",
            outcome="A web-owned criterion cannot be satisfied by external-proof (runtime) evidence.",
            criteria=[
                {
                    "id": "WEB-OWNED-002",
                    "description": "The web surface is usable.",
                    "scope": "product",
                    "risk": "R3",
                    "verificationType": "reality",
                    "surface": "web",
                    "status": "UNTESTED",
                    "evidenceRefs": [],
                    "blocking": True,
                }
            ],
            autonomy_scope="approved-program",
        )
        run_id = str(state["runId"])
        self.store.add_task(
            run_id,
            {
                "id": "task-a",
                "title": "task-a",
                "objective": "Complete task-a.",
                "dependencies": [],
                "workerProfile": "shell",
                "mutablePaths": [],
                "tools": ["test"],
                "risk": "R1",
                "acceptanceCriteria": ["WEB-OWNED-002"],
                "requiredArtifacts": ["evidence-task-a"],
                "gate": "fixture gate",
                "maxAttempts": 2,
                "sideEffect": None,
            },
        )
        self.store.wait_external(
            run_id,
            checkpoint_id="chk-a",
            task_id="task-a",
            checkpoint_type="MFA_REQUIRED",
            principal="user-a",
            provider="provider-a",
            reason="a",
        )
        runtime_evidence = self.evidence(run_id, "forged-runtime-evidence", producer="external-proof")
        with self.assertRaisesRegex(RuntimeFailure, "criterion-owned verification surface"):
            self.store.record_gate(
                run_id,
                gate_id="reality-forged-runtime-surface",
                task_id=None,
                gate_type="reality",
                status="PASS",
                evidence_refs=[runtime_evidence],
                criteria=["WEB-OWNED-002"],
            )

    def test_reality_gate_bound_to_criteria_with_conflicting_owned_surfaces_is_rejected(self) -> None:
        state = self.store.create(
            goal="Exercise conflicting surface ownership across bound criteria.",
            outcome="A single gate cannot simultaneously prove two different owned surfaces.",
            criteria=[
                {
                    "id": "WEB-OWNED-001",
                    "description": "The web surface is usable.",
                    "scope": "product",
                    "risk": "R3",
                    "verificationType": "reality",
                    "surface": "web",
                    "status": "UNTESTED",
                    "evidenceRefs": [],
                    "blocking": True,
                },
                {
                    "id": "ELECTRON-OWNED-001",
                    "description": "The electron surface is usable.",
                    "scope": "product",
                    "risk": "R3",
                    "verificationType": "reality",
                    "surface": "electron",
                    "status": "UNTESTED",
                    "evidenceRefs": [],
                    "blocking": True,
                },
            ],
            autonomy_scope="approved-program",
        )
        run_id = str(state["runId"])
        web_evidence = self.evidence(run_id, "conflict-web-evidence", producer="legibility")
        with self.assertRaisesRegex(RuntimeFailure, "conflicting verification surfaces"):
            self.store.record_gate(
                run_id,
                gate_id="reality-conflicting-surfaces",
                task_id=None,
                gate_type="reality",
                status="PASS",
                evidence_refs=[web_evidence],
                criteria=["WEB-OWNED-001", "ELECTRON-OWNED-001"],
            )

    def test_external_evidence_requires_external_verification_type(self) -> None:
        state = self.create(verification="deterministic")
        run_id = str(state["runId"])
        self.add_task(run_id, "auth-task")
        _, challenge = self.store.wait_external(
            run_id,
            checkpoint_id="chk-1",
            task_id="auth-task",
            checkpoint_type="MFA_REQUIRED",
            principal="fixture-user",
            provider="fixture-provider",
            reason="fixture",
        )
        proof = self.evidence(run_id, "proof", producer="external-proof")
        self.store.resolve_external(
            run_id,
            checkpoint_id="chk-1",
            resolution_ref=proof,
            challenge=challenge,
            actor="human:fixture-user",
        )
        with self.assertRaisesRegex(RuntimeFailure, "verificationType 'external'"):
            self.store.set_criterion(run_id, "OUTCOME-001", "PASS", ["external:chk-1"])

    def test_external_evidence_not_bound_to_criterion_is_rejected(self) -> None:
        state = self.store.create(
            goal="Exercise external checkpoint binding.",
            outcome="External evidence must bind to the resolving task's own criterion.",
            criteria=[
                {
                    "id": "OUTCOME-EXT",
                    "description": "Requires external proof.",
                    "scope": "fixture",
                    "risk": "R1",
                    "verificationType": "external",
                    "status": "UNTESTED",
                    "evidenceRefs": [],
                    "blocking": True,
                },
                {
                    "id": "OUTCOME-OTHER",
                    "description": "Unrelated outcome.",
                    "scope": "fixture",
                    "risk": "R1",
                    "verificationType": "deterministic",
                    "status": "UNTESTED",
                    "evidenceRefs": [],
                    "blocking": True,
                },
            ],
            autonomy_scope="approved-program",
        )
        run_id = str(state["runId"])
        self.store.add_task(
            run_id,
            {
                "id": "other-task",
                "title": "other-task",
                "objective": "Complete other-task.",
                "workerProfile": "shell",
                "mutablePaths": [],
                "tools": [],
                "risk": "R1",
                "acceptanceCriteria": ["OUTCOME-OTHER"],
                "requiredArtifacts": [],
                "gate": "fixture gate",
            },
        )
        _, challenge = self.store.wait_external(
            run_id,
            checkpoint_id="chk-1",
            task_id="other-task",
            checkpoint_type="MFA_REQUIRED",
            principal="fixture-user",
            provider="fixture-provider",
            reason="fixture",
        )
        run_dir = self.store.run_dir(run_id)
        proof_path = run_dir / "evidence" / "proof.json"
        proof_path.parent.mkdir(parents=True, exist_ok=True)
        proof_path.write_text(
            json.dumps({"checkpointId": "chk-1", "principal": "fixture-user", "provider": "fixture-provider"}) + "\n",
            encoding="utf-8",
        )
        self.store._record_external_proof(
            run_id,
            artifact_id="proof",
            path=proof_path.relative_to(self.store.repository).as_posix(),
            evidence_refs=["task:other-task"],
        )
        self.store.resolve_external(
            run_id,
            checkpoint_id="chk-1",
            resolution_ref="artifact:proof",
            challenge=challenge,
            actor="human:fixture-user",
        )
        # "chk-1" resolved for other-task (whose only criterion is OUTCOME-OTHER), so it must
        # not be usable to satisfy the unrelated OUTCOME-EXT criterion even though its
        # verificationType is "external".
        with self.assertRaisesRegex(RuntimeFailure, "not bound to this criterion"):
            self.store.set_criterion(run_id, "OUTCOME-EXT", "PASS", ["external:chk-1"])

    def test_registered_artifact_mutation_is_detected(self) -> None:
        state = self.create()
        run_id = str(state["runId"])
        reference = self.evidence(run_id, "immutable-evidence")
        artifact_id = reference.split(":", 1)[1]
        artifact = next(item for item in self.store.load(run_id)["artifacts"] if item["id"] == artifact_id)
        (self.store.repository / artifact["path"]).write_text("tampered\n", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeFailure, "content digest failed"):
            self.store.load(run_id)

    def test_high_risk_outcome_requires_reality_or_e2e_gate(self) -> None:
        state = self.create(risk="R3", verification="reality")
        run_id = str(state["runId"])
        self.add_task(run_id, "product", risk="R3")
        self.finish_task(run_id, "product", "worker-product")
        verifying, completed = self.store.verify(run_id)
        self.assertFalse(completed)
        self.assertEqual("VERIFYING", verifying["status"])
        reality_evidence = self.evidence(run_id, "reality-evidence", task_id="product", producer="legibility")
        self.store.record_gate(
            run_id,
            gate_id="reality",
            task_id="product",
            gate_type="reality",
            status="PASS",
            evidence_refs=[reality_evidence],
        )
        self.store.set_criterion(run_id, "OUTCOME-001", "PASS", ["gate:reality"])
        gpt_evidence = self.evidence(run_id, "judge-gpt-evidence", producer="semantic-judge")
        self.store.record_gate(
            run_id,
            gate_id="judge-gpt",
            task_id=None,
            gate_type="semantic",
            family="gpt",
            status="PASS",
            evidence_refs=[gpt_evidence],
        )
        claude_evidence = self.evidence(run_id, "judge-claude-evidence", producer="semantic-judge")
        self.store.record_gate(
            run_id,
            gate_id="judge-claude",
            task_id=None,
            gate_type="semantic",
            family="claude",
            status="PASS",
            evidence_refs=[claude_evidence],
        )
        completed_state, completed = self.store.verify(run_id)
        self.assertTrue(completed)
        self.assertEqual("COMPLETED", completed_state["status"])
        self.assertEqual("run.completed", self.store.events(run_id)[-1]["type"])

    def test_path_escape_is_rejected(self) -> None:
        state = self.create(allow=[{"scope": "repository", "operations": ["edit"]}])
        run_id = str(state["runId"])
        with self.assertRaisesRegex(RuntimeFailure, "non-escaping"):
            self.store.add_task(
                run_id,
                {
                    "id": "escape",
                    "title": "escape",
                    "objective": "Escape the workspace.",
                    "mutablePaths": ["../outside"],
                    "acceptanceCriteria": ["OUTCOME-001"],
                },
            )

    # -- Finding #3: external proof resolution must bind/consume proof to the exact
    # checkpoint/principal/provider, and a task must not ready until every checkpoint resolves.

    def test_external_proof_bound_to_wrong_checkpoint_is_rejected(self) -> None:
        state = self.create()
        run_id = str(state["runId"])
        self.add_task(run_id, "task-a")
        self.add_task(run_id, "task-b")
        self.store.wait_external(
            run_id,
            checkpoint_id="chk-a",
            task_id="task-a",
            checkpoint_type="MFA_REQUIRED",
            principal="user-a",
            provider="provider-a",
            reason="a",
        )
        _, challenge_b = self.store.wait_external(
            run_id,
            checkpoint_id="chk-b",
            task_id="task-b",
            checkpoint_type="MFA_REQUIRED",
            principal="user-b",
            provider="provider-b",
            reason="b",
        )
        # This proof is genuinely externally attested, but for checkpoint "chk-a" -- an
        # attacker (or a confused caller) must not be able to redeem it against "chk-b".
        proof_for_a = self.evidence(run_id, "proof-a", producer="external-proof")
        with self.assertRaisesRegex(RuntimeFailure, "does not bind"):
            self.store.resolve_external(
                run_id,
                checkpoint_id="chk-b",
                resolution_ref=proof_for_a,
                challenge=challenge_b,
                actor="human:user-b",
            )
        # chk-b remains unresolved and task-b remains blocked.
        state = self.store.load(run_id)
        self.assertEqual("PENDING", next(c for c in state["externalCheckpoints"] if c["id"] == "chk-b")["status"])
        self.assertEqual("WAITING_EXTERNAL", next(t for t in state["tasks"] if t["id"] == "task-b")["status"])

    def test_external_proof_replay_across_checkpoints_is_rejected(self) -> None:
        state = self.create()
        run_id = str(state["runId"])
        self.add_task(run_id, "auth-task")
        self.add_task(run_id, "other-task")
        _, challenge_1 = self.store.wait_external(
            run_id,
            checkpoint_id="chk-1",
            task_id="auth-task",
            checkpoint_type="MFA_REQUIRED",
            principal="fixture-user",
            provider="fixture-provider",
            reason="one",
        )
        proof = self.evidence(run_id, "proof-1", producer="external-proof")
        self.store.resolve_external(
            run_id,
            checkpoint_id="chk-1",
            resolution_ref=proof,
            challenge=challenge_1,
            actor="human:fixture-user",
        )
        _, challenge_2 = self.store.wait_external(
            run_id,
            checkpoint_id="chk-2",
            task_id="other-task",
            checkpoint_type="MFA_REQUIRED",
            principal="fixture-user",
            provider="fixture-provider",
            reason="two",
        )
        with self.assertRaisesRegex(RuntimeFailure, "already consumed"):
            self.store.resolve_external(
                run_id,
                checkpoint_id="chk-2",
                resolution_ref=proof,
                challenge=challenge_2,
                actor="human:fixture-user",
            )

    def test_task_stays_blocked_until_every_external_checkpoint_resolves(self) -> None:
        state = self.create()
        run_id = str(state["runId"])
        self.add_task(run_id, "auth-task")
        _, challenge_1 = self.store.wait_external(
            run_id,
            checkpoint_id="chk-1",
            task_id="auth-task",
            checkpoint_type="MFA_REQUIRED",
            principal="p1",
            provider="prov1",
            reason="one",
        )
        _, challenge_2 = self.store.wait_external(
            run_id,
            checkpoint_id="chk-2",
            task_id="auth-task",
            checkpoint_type="MFA_REQUIRED",
            principal="p2",
            provider="prov2",
            reason="two",
        )
        state = self.store.load(run_id)
        pending_ids = [c["id"] for c in state["externalCheckpoints"] if c["status"] == "PENDING"]
        self.assertEqual(["chk-1", "chk-2"], pending_ids)
        # Resolving the FIRST pending checkpoint must not prematurely ready the task while a
        # second checkpoint for the same task is still outstanding.
        proof_1 = self.evidence(run_id, "proof-1", producer="external-proof")
        resolved = self.store.resolve_external(
            run_id,
            checkpoint_id="chk-1",
            resolution_ref=proof_1,
            challenge=challenge_1,
            actor="human:p1",
        )
        task = next(t for t in resolved["tasks"] if t["id"] == "auth-task")
        self.assertEqual("WAITING_EXTERNAL", task["status"])
        # Resolving the remaining checkpoint releases the task.
        proof_2 = self.evidence(run_id, "proof-2", producer="external-proof")
        resolved = self.store.resolve_external(
            run_id,
            checkpoint_id="chk-2",
            resolution_ref=proof_2,
            challenge=challenge_2,
            actor="human:p2",
        )
        task = next(t for t in resolved["tasks"] if t["id"] == "auth-task")
        self.assertEqual("READY", task["status"])

    # -- Finding #5: enforce legal Run/task/worker transitions, including run status and
    # worker completion.

    def test_run_terminated_by_gate_failure_rejects_further_task_starts(self) -> None:
        state = self.create()
        run_id = str(state["runId"])
        self.add_task(run_id, "task-a")
        self.add_task(run_id, "task-b")
        failed = self.store.record_gate(
            run_id,
            gate_id="build",
            task_id="task-a",
            gate_type="deterministic",
            status="FAIL",
            evidence_refs=["build:failed"],
        )
        self.assertEqual("FAILED", failed["status"])
        # task-b never touched the failing gate and is still READY -- it must not be able to
        # resurrect a terminally FAILED Run back to RUNNING.
        state = self.store.load(run_id)
        self.assertEqual("FAILED", state["status"])
        self.assertEqual("READY", next(t for t in state["tasks"] if t["id"] == "task-b")["status"])
        with self.assertRaisesRegex(RuntimeFailure, "RUN_TERMINAL|terminal Run"):
            self.store.start_task(run_id, "task-b", worker_id="worker-b")
        self.assertEqual("FAILED", self.store.load(run_id)["status"])

    def test_worker_completion_after_lease_expiry_is_rejected(self) -> None:
        state = self.create()
        run_id = str(state["runId"])
        self.add_task(run_id, "slow")
        self.store.start_task(run_id, "slow", worker_id="worker-1", lease_seconds=1)
        time.sleep(1.2)
        with self.assertRaisesRegex(RuntimeFailure, "lease expired"):
            self.store.finish_worker(run_id, "slow", worker_id="worker-1", status="FINISHED")
        # the task remains RUNNING (still leased, even though expired) rather than silently
        # accepting a worker report that arrived after its lease window closed.
        task = next(t for t in self.store.load(run_id)["tasks"] if t["id"] == "slow")
        self.assertEqual("RUNNING", task["status"])

    # -- Phase 2 follow-up Finding #5: enforce legal Run/task transitions -- start_task must
    # reject a PAUSED Run until an explicit resume, and complete_task must require the owning
    # worker to have actually finished (or a legal waiting state), not merely RUNNING.

    def test_start_task_rejects_paused_run_until_explicit_resume(self) -> None:
        state = self.create(autonomy="current-task")
        run_id = str(state["runId"])
        self.add_task(run_id, "first")
        self.add_task(run_id, "second", dependencies=["first"])
        self.finish_task(run_id, "first", "worker-first")
        state = self.store.load(run_id)
        self.assertEqual("PAUSED", state["status"])
        self.assertEqual("READY", next(task for task in state["tasks"] if task["id"] == "second")["status"])
        with self.assertRaisesRegex(RuntimeFailure, "paused"):
            self.store.start_task(run_id, "second", worker_id="worker-second")
        resumed = self.store.resume(run_id)
        self.assertEqual("RUNNING", resumed["status"])
        self.store.start_task(run_id, "second", worker_id="worker-second")
        task = next(t for t in self.store.load(run_id)["tasks"] if t["id"] == "second")
        self.assertEqual("RUNNING", task["status"])

    def test_complete_task_rejects_a_still_running_task(self) -> None:
        # Regression: complete_task previously accepted RUNNING as a legal precursor state,
        # meaning anyone with runtime access -- including the worker's own subprocess calling
        # the CLI directly -- could complete a task while its own execution was still
        # in-flight, bypassing finish_worker and every post-execution validation
        # execute_work_packet performs.
        state = self.create()
        run_id = str(state["runId"])
        self.add_task(run_id, "solo")
        self.store.start_task(run_id, "solo", worker_id="worker-1")
        evidence = self.evidence(run_id, "evidence-solo", task_id="solo")
        self.store.record_gate(
            run_id,
            gate_id="gate-solo",
            task_id="solo",
            gate_type="deterministic",
            status="PASS",
            evidence_refs=[evidence],
        )
        with self.assertRaisesRegex(RuntimeFailure, "solo is RUNNING"):
            self.store.complete_task(run_id, "solo", evidence_refs=["gate:gate-solo"])
        # The legitimate path -- finish_worker first -- remains completable.
        self.store.finish_worker(run_id, "solo", worker_id="worker-1", status="FINISHED")
        self.store.complete_task(run_id, "solo", evidence_refs=["gate:gate-solo"])
        task = next(t for t in self.store.load(run_id)["tasks"] if t["id"] == "solo")
        self.assertEqual("COMPLETED", task["status"])

    # -- Finding #6: honor configured runtime defaults/autonomy/adapters/risk/parallelism and
    # declared retryability/backoff.

    def test_config_driven_autonomy_and_policy_defaults_apply_when_omitted(self) -> None:
        (self.repo / "architrave.config.json").write_text(
            json.dumps(
                {
                    "autonomy": {
                        "scope": "advisory-only",
                        "mutationPolicy": {
                            "allow": [{"scope": "repository", "operations": ["edit"]}],
                            "confirmationRequired": ["deploy"],
                        },
                    }
                }
            ),
            encoding="utf-8",
        )
        state = self.store.create(
            goal="Exercise configured defaults.",
            outcome="Config drives autonomy without explicit arguments.",
            criteria=[self.criterion()],
        )
        self.assertEqual("advisory-only", state["autonomy"]["scope"])
        self.assertEqual([{"scope": "repository", "operations": ["edit"]}], state["policy"]["allow"])
        self.assertEqual(["deploy"], state["policy"]["confirmationRequired"])

    def test_config_driven_worker_profile_and_risk_defaults_apply_when_omitted(self) -> None:
        (self.repo / "architrave.config.json").write_text(
            json.dumps(
                {
                    "workers": {"defaultAdapter": "codex", "enabledAdapters": ["codex", "shell"]},
                    "evaluation": {"defaultRisk": "R2"},
                }
            ),
            encoding="utf-8",
        )
        state = self.create()
        run_id = str(state["runId"])
        self.store.add_task(
            run_id,
            {
                "id": "implicit",
                "title": "implicit",
                "objective": "Rely on configured defaults.",
                "acceptanceCriteria": ["OUTCOME-001"],
            },
        )
        task = next(t for t in self.store.load(run_id)["tasks"] if t["id"] == "implicit")
        self.assertEqual("codex", task["workerProfile"])
        self.assertEqual("R2", task["risk"])

    def test_disabled_worker_adapter_is_rejected(self) -> None:
        (self.repo / "architrave.config.json").write_text(
            json.dumps({"workers": {"enabledAdapters": ["shell"]}}),
            encoding="utf-8",
        )
        state = self.create()
        run_id = str(state["runId"])
        with self.assertRaisesRegex(RuntimeFailure, "not enabled"):
            self.store.add_task(
                run_id,
                {
                    "id": "codex-task",
                    "title": "codex-task",
                    "objective": "Use a disabled adapter.",
                    "workerProfile": "codex",
                    "acceptanceCriteria": ["OUTCOME-001"],
                },
            )

    def test_max_parallel_limits_concurrent_task_starts(self) -> None:
        (self.repo / "architrave.config.json").write_text(
            json.dumps({"workers": {"maxParallel": 1}}),
            encoding="utf-8",
        )
        state = self.create()
        run_id = str(state["runId"])
        self.add_task(run_id, "task-a")
        self.add_task(run_id, "task-b")
        self.store.start_task(run_id, "task-a", worker_id="worker-a")
        with self.assertRaisesRegex(RuntimeFailure, "maxParallel"):
            self.store.start_task(run_id, "task-b", worker_id="worker-b")

    def test_retryable_worker_failure_reschedules_after_declared_backoff(self) -> None:
        state = self.create()
        run_id = str(state["runId"])
        self.store.add_task(
            run_id,
            {
                "id": "flaky",
                "title": "flaky",
                "objective": "Retry on a transient failure.",
                "workerProfile": "shell",
                "acceptanceCriteria": ["OUTCOME-001"],
                "maxAttempts": 2,
                "backoffSeconds": 1,
            },
        )
        self.store.start_task(run_id, "flaky", worker_id="worker-1")
        self.store.finish_worker(run_id, "flaky", worker_id="worker-1", status="FAILED")
        task = next(t for t in self.store.load(run_id)["tasks"] if t["id"] == "flaky")
        self.assertEqual("READY", task["status"])
        self.assertEqual(1, task["attempts"])
        self.assertIsNotNone(task["retryNotBefore"])
        with self.assertRaisesRegex(RuntimeFailure, "backoff"):
            self.store.start_task(run_id, "flaky", worker_id="worker-2")
        time.sleep(2.1)
        self.store.start_task(run_id, "flaky", worker_id="worker-2")
        task = next(t for t in self.store.load(run_id)["tasks"] if t["id"] == "flaky")
        self.assertEqual("RUNNING", task["status"])
        self.assertEqual(2, task["attempts"])

    def test_fractional_backoff_is_ceiled_and_cannot_be_bypassed_by_immediate_retry(self) -> None:
        # Regression: isoformat(timespec="seconds") truncates any fractional-second backoff,
        # which could round the persisted retryNotBefore *down* to "now" (or earlier) and let
        # an immediate retry slip through the declared backoff window undetected.
        state = self.create()
        run_id = str(state["runId"])
        self.store.add_task(
            run_id,
            {
                "id": "flaky-fast",
                "title": "flaky-fast",
                "objective": "Retry after a fractional backoff.",
                "workerProfile": "shell",
                "acceptanceCriteria": ["OUTCOME-001"],
                "maxAttempts": 2,
                "backoffSeconds": 5.2,
            },
        )
        self.store.start_task(run_id, "flaky-fast", worker_id="worker-1")
        before_failure = dt.datetime.now(dt.timezone.utc)
        self.store.finish_worker(run_id, "flaky-fast", worker_id="worker-1", status="FAILED")
        task = next(t for t in self.store.load(run_id)["tasks"] if t["id"] == "flaky-fast")
        retry_not_before = parse_iso(task["retryNotBefore"])
        # Compare against a captured lower bound rather than the wall clock after several
        # filesystem operations, which can legitimately exceed tiny backoffs on loaded CI.
        self.assertGreaterEqual(retry_not_before, before_failure + dt.timedelta(seconds=5.2))
        with self.assertRaisesRegex(RuntimeFailure, "backoff"):
            self.store.start_task(run_id, "flaky-fast", worker_id="worker-2")

    def test_fail_task_respects_retry_policy_and_terminates_when_exhausted(self) -> None:
        state = self.create()
        run_id = str(state["runId"])
        self.add_task(run_id, "solo")
        self.store.start_task(run_id, "solo", worker_id="worker-1")
        self.store.fail_task(run_id, "solo", "flaky infra")
        task = next(t for t in self.store.load(run_id)["tasks"] if t["id"] == "solo")
        self.assertEqual("READY", task["status"])
        self.assertEqual(1, task["attempts"])
        self.store.start_task(run_id, "solo", worker_id="worker-2")
        self.store.fail_task(run_id, "solo", "flaky infra")
        task = next(t for t in self.store.load(run_id)["tasks"] if t["id"] == "solo")
        self.assertEqual("FAILED", task["status"])

    def test_v1_summary_remains_migratable(self) -> None:
        legacy = self.repo / "legacy-summary.json"
        legacy.write_text(
            json.dumps(
                {
                    "schema": "architrave.run.v1",
                    "runId": "legacy",
                    "status": "in-progress",
                    "artifacts": {},
                    "phases": [
                        {
                            "phase": 1,
                            "name": "Grounding",
                            "status": "completed",
                            "scope": "Read repository truth.",
                            "gate": "Sources recorded.",
                        },
                        {
                            "phase": 2,
                            "name": "Implementation",
                            "status": "in-progress",
                            "scope": "Build the change.",
                            "gate": "Tests pass.",
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        migrated = self.store.migrate_v1(legacy)
        self.assertEqual("architrave.run.v2", migrated["schema"])
        self.assertEqual("advisory-only", migrated["autonomy"]["scope"])
        self.assertEqual(["legacy-1", "legacy-2"], [task["id"] for task in migrated["tasks"]])
        self.assertEqual(["COMPLETED", "READY"], [task["status"] for task in migrated["tasks"]])


if __name__ == "__main__":
    unittest.main(verbosity=2)