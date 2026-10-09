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
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))

from architrave_runtime import (
    FileLock,
    RunStore,
    RuntimeFailure,
    _PolicyAuthorization,
    parse_iso,
    state_summary,
    missing_gate_requirements,
    utc_now,
)
from worker_adapters import workspace_fingerprint

_fixture_add_task = RunStore.add_task
RunStore.add_task = lambda self, run_id, task, actor="coordinator": _fixture_add_task(
    self, run_id, {"pushback": "KEEP:test fixture", **task}, actor)


class RuntimeV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.email", "architrave@example.invalid")
        self.git("config", "user.name", "Architrave Test")
        (self.repo / "README.md").write_text("# Fixture\n", encoding="utf-8")
        (self.repo / ".gitignore").write_text(".architrave/\n", encoding="utf-8")
        self.git("add", "README.md", ".gitignore")
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

    def runtime_cli(self, *args: str, expected: int = 0) -> dict[str, object]:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "harness" / "architrave_runtime.py"), "--repo", str(self.repo), *args],
            cwd=self.repo,
            capture_output=True,
            text=True,
        )
        self.assertEqual(expected, completed.returncode, completed.stderr or completed.stdout)
        stream = completed.stdout if completed.returncode == 0 else completed.stderr
        return json.loads(stream)

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
                "tools": ["fixture"],
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
        legacy_product_receipt: bool = False,
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
            if not legacy_product_receipt:
                payload["binding"] = {"runId": run_id, "objectiveVersion": state["objective"]["version"],
                                      "taskId": task_id, "criteria": criteria}
                payload["source"] = {"commit": self.git("rev-parse", "HEAD"),
                                     "sha256": workspace_fingerprint(self.repo, include_ignored=False)}
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
        if producer != "semantic-judge" and not legacy_product_receipt:
            payload.setdefault("binding", {"runId": run_id, "objectiveVersion": state["objective"]["version"],
                                           "taskId": task_id, "criteria": criteria})
            payload.setdefault("source", {"commit": self.git("rev-parse", "HEAD"),
                                          "sha256": workspace_fingerprint(self.repo, include_ignored=False)})
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

    def test_legacy_product_receipt_cannot_admit_current_taskless_pass(self) -> None:
        for gate_type in ("reality", "e2e"):
            with self.subTest(gate_type=gate_type):
                state = self.create(verification=gate_type)
                run_id = str(state["runId"])
                evidence = self.evidence(run_id, "legacy-product", producer="legibility", legacy_product_receipt=True)
                self.assertEqual(1, len(self.store.load(run_id)["artifacts"]))
                with self.assertRaisesRegex(RuntimeFailure, "historical product receipt"):
                    self.store.record_gate(run_id, gate_id="current-product", task_id=None, gate_type=gate_type,
                                           status="PASS", evidence_refs=[evidence], criteria=["OUTCOME-001"])
                self.assertEqual([], self.store.load(run_id)["gateResults"])

    def test_legacy_product_gate_remains_readable_but_cannot_verify_after_resume(self) -> None:
        state = self.create(verification="reality")
        run_id = str(state["runId"])
        evidence = self.evidence(run_id, "legacy-product", producer="legibility", legacy_product_receipt=True)
        # Model an authenticated old-version gate, not current admission.
        with mock.patch.object(self.store, "_assert_product_binding", return_value=None):
            self.store.record_gate(run_id, gate_id="historical-reality", task_id=None, gate_type="reality",
                                   status="PASS", evidence_refs=[evidence], criteria=["OUTCOME-001"])
            self.store.set_criterion(run_id, "OUTCOME-001", "PASS", ["gate:historical-reality"])
        (self.repo / "README.md").write_text("# Changed source\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-qm", "source changed after historical observation")
        self.store.resume(run_id, accept_commit=True)
        retained = self.store.load(run_id)
        self.assertEqual(1, len(retained["artifacts"]))
        self.assertEqual("historical-reality", retained["gateResults"][0]["id"])
        with self.assertRaisesRegex(RuntimeFailure, "historical product receipt"):
            self.store.record_gate(run_id, gate_id="current-reality", task_id=None, gate_type="reality",
                                   status="PASS", evidence_refs=[evidence], criteria=["OUTCOME-001"])
        with self.assertRaisesRegex(RuntimeFailure, "historical product receipt"):
            self.store.set_criterion(run_id, "OUTCOME-001", "PASS", ["gate:historical-reality"])
        with self.assertRaisesRegex(RuntimeFailure, "historical product receipt"):
            self.store.verify(run_id)

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
        run_dir = self.store.run_dir(run_id)
        self.assertTrue((run_dir / "recovery.json").is_file())
        self.assertFalse((run_dir / "phase-ledger.md").exists())
        self.assertFalse((run_dir / "summary.json").exists())
        self.assertFalse((run_dir / "snapshots").exists())
        self.assertTrue(self.store.key_path.is_file())
        if os.name != "nt":
            self.assertEqual(0o600, self.store.key_path.stat().st_mode & 0o777)

    def test_transitions_keep_one_compact_recovery_snapshot(self) -> None:
        state = self.create()
        run_id = str(state["runId"])
        for index in range(12):
            self.store.policy_check(run_id, f"scope-{index}", "observe")
        run_dir = self.store.run_dir(run_id)
        files = sorted(path.relative_to(run_dir).as_posix() for path in run_dir.rglob("*") if path.is_file())
        self.assertEqual([".run.lock", "events.jsonl", "recovery.json", "run.json"], files)
        self.assertLess((run_dir / "recovery.json").stat().st_size, 16_384)

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

    def test_policy_rejects_wildcards_at_creation_config_cli_and_load(self) -> None:
        for allow, confirmation in (
            ([{"scope": "*", "operations": ["edit"]}], []),
            ([{"scope": "repository", "operations": ["*"]}], []),
            ([], ["*"]),
        ):
            with self.assertRaisesRegex(RuntimeFailure, "exact"):
                self.store.create(
                    goal="Reject wildcard policy.",
                    outcome="Only exact policy grants are accepted.",
                    criteria=[self.criterion()],
                    autonomy_scope="approved-program",
                    policy_allow=allow,
                    confirmation_required=confirmation,
                )

        cli_rejected = self.runtime_cli(
            "run",
            "--run-id",
            "wildcard-cli",
            "--goal",
            "Reject wildcard policy.",
            "--outcome",
            "Only exact policy grants are accepted.",
            "--allow",
            "*:edit",
            expected=1,
        )
        self.assertEqual("INVALID_POLICY", cli_rejected["error"]["code"])

        (self.repo / "architrave.config.json").write_text(
            json.dumps(
                {
                    "autonomy": {
                        "mutationPolicy": {
                            "allow": [{"scope": "repository", "operations": ["*"]}],
                            "confirmationRequired": [],
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(RuntimeFailure, "exact"):
            self.store.create(
                goal="Reject configured wildcard policy.",
                outcome="Configured policy remains exact.",
                criteria=[self.criterion()],
            )
        (self.repo / "architrave.config.json").unlink()

        valid = self.create()
        valid_id = str(valid["runId"])
        path = self.store.run_dir(valid_id) / "run.json"
        forged = json.loads(path.read_text(encoding="utf-8"))
        forged["policy"]["allow"] = [{"scope": "*", "operations": ["edit"]}]
        path.write_text(json.dumps(forged), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeFailure, "exact"):
            self.store.load(valid_id)

        config_schema = json.loads((ROOT / "kit" / "architrave.config.schema.json").read_text(encoding="utf-8"))
        config_policy = config_schema["properties"]["autonomy"]["properties"]["mutationPolicy"]["properties"]
        run_schema = json.loads((ROOT / "harness" / "schemas" / "run-v2.schema.json").read_text(encoding="utf-8"))
        run_policy = run_schema["definitions"]["mutationPolicy"]["properties"]
        amendment_delta = (
            run_schema["definitions"]["externalCheckpoint"]["properties"]["policyAmendment"]["oneOf"][1]
            ["properties"]["delta"]["properties"]
        )
        exact_fields = [
            config_policy["allow"]["items"]["properties"]["scope"],
            config_policy["allow"]["items"]["properties"]["operations"]["items"],
            config_policy["confirmationRequired"]["items"],
            run_policy["allow"]["items"]["properties"]["scope"],
            run_policy["allow"]["items"]["properties"]["operations"]["items"],
            run_policy["confirmationRequired"]["items"],
            amendment_delta["addAllow"]["items"]["properties"]["scope"],
            amendment_delta["addAllow"]["items"]["properties"]["operations"]["items"],
            amendment_delta["addConfirmationRequired"]["items"],
        ]
        self.assertTrue(all(field.get("not") == {"const": "*"} for field in exact_fields))

    def test_public_cli_policy_amendment_corrects_scope_spelling_in_same_run(self) -> None:
        state = self.create(allow=[{"scope": "public-candidate", "operations": ["edit"]}])
        run_id = str(state["runId"])
        self.add_task(run_id, "mutable", mutable=True)
        denied = self.runtime_cli(
            "task-start",
            run_id,
            "mutable",
            "--worker-id",
            "worker-before-amendment",
            expected=1,
        )
        self.assertEqual("MUTATION_DENIED", denied["error"]["code"])

        requested = self.runtime_cli(
            "policy-amend-request",
            run_id,
            "--id",
            "policy-scope-correction",
            "--task-id",
            "mutable",
            "--principal",
            "release-owner",
            "--provider",
            "user-direction",
            "--actor",
            "human:release-owner",
            "--reason",
            "Correct public-candidate:edit to the runtime-required repository:edit scope.",
            "--add-allow",
            "repository:edit",
            "--add-confirmation-required",
            "edit",
        )
        challenge = requested["result"]["resolutionChallenge"]
        before_apply = self.store.load(run_id)
        amended = self.runtime_cli(
            "policy-amend",
            run_id,
            "policy-scope-correction",
            "--challenge",
            str(challenge),
            "--principal",
            "release-owner",
            "--provider",
            "user-direction",
            "--actor",
            "human:release-owner",
            "--add-allow",
            "repository:edit",
            "--add-confirmation-required",
            "edit",
        )
        self.assertEqual(["mutable"], amended["result"]["readyTasks"])
        current = self.store.load(run_id)
        self.assertEqual("deny", current["policy"]["default"])
        self.assertEqual(
            [
                {"scope": "public-candidate", "operations": ["edit"]},
                {"scope": "repository", "operations": ["edit"]},
            ],
            current["policy"]["allow"],
        )
        self.assertEqual(["edit"], current["policy"]["confirmationRequired"])
        for field in ("goal", "objective", "autonomy", "outcome", "acceptanceCriteria", "baseline", "focus", "lanes"):
            self.assertEqual(before_apply[field], current[field], field)
        self.assertEqual(
            [task["mutablePaths"] for task in before_apply["tasks"]],
            [task["mutablePaths"] for task in current["tasks"]],
        )
        self.runtime_cli(
            "task-start",
            run_id,
            "mutable",
            "--worker-id",
            "worker-after-amendment",
            "--confirmed",
        )

    def test_public_cli_policy_amendment_rejects_authority_mismatch_replay_and_staleness(self) -> None:
        state = self.create()
        run_id = str(state["runId"])
        self.add_task(run_id, "mutable", mutable=True)
        for label, actor in (("coordinator-request", "coordinator"), ("worker-request", "worker:forged")):
            rejected_request = self.runtime_cli(
                "policy-amend-request",
                run_id,
                "--id",
                label,
                "--task-id",
                "mutable",
                "--principal",
                "authorized-user",
                "--provider",
                "trusted-provider",
                "--actor",
                actor,
                "--reason",
                "Authorize the exact repository edit scope.",
                "--add-allow",
                "repository:edit",
                expected=1,
            )
            self.assertEqual("POLICY_AUTHORITY", rejected_request["error"]["code"])
        wildcard = self.runtime_cli(
            "policy-amend-request",
            run_id,
            "--id",
            "wildcard-request",
            "--task-id",
            "mutable",
            "--principal",
            "authorized-user",
            "--provider",
            "trusted-provider",
            "--actor",
            "human:authorized-user",
            "--reason",
            "Reject wildcard policy escalation.",
            "--add-allow",
            "*:*",
            expected=1,
        )
        self.assertEqual("INVALID_POLICY_AMENDMENT", wildcard["error"]["code"])
        requested = self.runtime_cli(
            "policy-amend-request",
            run_id,
            "--id",
            "policy-authority",
            "--task-id",
            "mutable",
            "--principal",
            "authorized-user",
            "--provider",
            "trusted-provider",
            "--actor",
            "human:authorized-user",
            "--reason",
            "Authorize the exact repository edit scope.",
            "--add-allow",
            "repository:edit",
        )
        challenge = str(requested["result"]["resolutionChallenge"])

        rejection_args = [
            ("wrong-principal", ["--principal", "other-user", "--provider", "trusted-provider", "--actor", "human:other-user", "--add-allow", "repository:edit"]),
            ("wrong-provider", ["--principal", "authorized-user", "--provider", "other-provider", "--actor", "human:authorized-user", "--add-allow", "repository:edit"]),
            ("wrong-challenge", ["--principal", "authorized-user", "--provider", "trusted-provider", "--actor", "human:authorized-user", "--add-allow", "repository:edit"]),
            ("wrong-delta", ["--principal", "authorized-user", "--provider", "trusted-provider", "--actor", "human:authorized-user", "--add-allow", "repository:build"]),
            ("coordinator-spoof", ["--principal", "authorized-user", "--provider", "trusted-provider", "--actor", "coordinator", "--add-allow", "repository:edit"]),
            ("worker-spoof", ["--principal", "authorized-user", "--provider", "trusted-provider", "--actor", "worker:authorized-user", "--add-allow", "repository:edit"]),
        ]
        for label, extra in rejection_args:
            supplied_challenge = "forged" if label == "wrong-challenge" else challenge
            rejected = self.runtime_cli(
                "policy-amend",
                run_id,
                "policy-authority",
                "--challenge",
                supplied_challenge,
                *extra,
                expected=1,
            )
            self.assertEqual("POLICY_AUTHORITY", rejected["error"]["code"], label)

        self.runtime_cli(
            "policy-amend",
            run_id,
            "policy-authority",
            "--challenge",
            challenge,
            "--principal",
            "authorized-user",
            "--provider",
            "trusted-provider",
            "--actor",
            "human:authorized-user",
            "--actor",
            "human:authorized-user",
            "--add-allow",
            "repository:edit",
        )
        replay = self.runtime_cli(
            "policy-amend",
            run_id,
            "policy-authority",
            "--challenge",
            challenge,
            "--principal",
            "authorized-user",
            "--provider",
            "trusted-provider",
            "--actor",
            "human:authorized-user",
            "--actor",
            "human:authorized-user",
            "--add-allow",
            "repository:edit",
            expected=1,
        )
        self.assertEqual("POLICY_AUTHORITY", replay["error"]["code"])

        no_checkpoint = self.runtime_cli(
            "policy-amend",
            run_id,
            "missing-checkpoint",
            "--challenge",
            challenge,
            "--principal",
            "authorized-user",
            "--provider",
            "trusted-provider",
            "--actor",
            "human:authorized-user",
            "--add-allow",
            "repository:edit",
            expected=1,
        )
        self.assertEqual("POLICY_CHECKPOINT_NOT_FOUND", no_checkpoint["error"]["code"])

        other = self.create()
        cross_run = self.runtime_cli(
            "policy-amend",
            str(other["runId"]),
            "policy-authority",
            "--challenge",
            challenge,
            "--principal",
            "authorized-user",
            "--provider",
            "trusted-provider",
            "--actor",
            "human:authorized-user",
            "--add-allow",
            "repository:edit",
            expected=1,
        )
        self.assertEqual("POLICY_CHECKPOINT_NOT_FOUND", cross_run["error"]["code"])

        stale = self.create()
        stale_id = str(stale["runId"])
        self.add_task(stale_id, "stale-task", mutable=True)
        stale_request = self.runtime_cli(
            "policy-amend-request",
            stale_id,
            "--id",
            "policy-stale",
            "--task-id",
            "stale-task",
            "--principal",
            "authorized-user",
            "--provider",
            "trusted-provider",
            "--actor",
            "human:authorized-user",
            "--reason",
            "Authorize the exact repository edit scope.",
            "--add-allow",
            "repository:edit",
        )
        self.store.policy_check(stale_id, "repository", "observe")
        stale_result = self.runtime_cli(
            "policy-amend",
            stale_id,
            "policy-stale",
            "--challenge",
            str(stale_request["result"]["resolutionChallenge"]),
            "--principal",
            "authorized-user",
            "--provider",
            "trusted-provider",
            "--actor",
            "human:authorized-user",
            "--add-allow",
            "repository:edit",
            expected=1,
        )
        self.assertEqual("POLICY_AUTHORITY", stale_result["error"]["code"])

        stale_objective = self.create()
        stale_objective_id = str(stale_objective["runId"])
        self.add_task(stale_objective_id, "policy-task", mutable=True)
        self.add_task(stale_objective_id, "correction-task")
        objective_request = self.runtime_cli(
            "policy-amend-request",
            stale_objective_id,
            "--id",
            "policy-old-objective",
            "--task-id",
            "policy-task",
            "--principal",
            "authorized-user",
            "--provider",
            "trusted-provider",
            "--actor",
            "human:authorized-user",
            "--reason",
            "Authorize the exact repository edit scope.",
            "--add-allow",
            "repository:edit",
        )
        _, correction_challenge = self.store.wait_external(
            stale_objective_id,
            checkpoint_id="objective-correction",
            task_id="correction-task",
            checkpoint_type="HUMAN_JUDGMENT_REQUIRED",
            principal="authorized-user",
            provider="user-direction",
            reason="Replace the synthetic objective.",
        )
        self.store.replace_objective(
            stale_objective_id,
            outcome="The replacement objective is current.",
            criteria=[self.criterion()],
            correction="Synthetic objective correction.",
            next_cheapest_test="Verify the replacement objective.",
            checkpoint_id="objective-correction",
            challenge=correction_challenge,
            actor="human:authorized-user",
        )
        stale_objective_result = self.runtime_cli(
            "policy-amend",
            stale_objective_id,
            "policy-old-objective",
            "--challenge",
            str(objective_request["result"]["resolutionChallenge"]),
            "--principal",
            "authorized-user",
            "--provider",
            "trusted-provider",
            "--actor",
            "human:authorized-user",
            "--add-allow",
            "repository:edit",
            expected=1,
        )
        self.assertEqual("POLICY_AUTHORITY", stale_objective_result["error"]["code"])

    def test_policy_amendment_rejects_transaction_bypass_and_mutation_in_progress(self) -> None:
        state = self.create()
        run_id = str(state["runId"])

        def malicious(run: dict[str, object]) -> dict[str, object]:
            run["policy"]["allow"].append({"scope": "repository", "operations": ["edit"]})
            return {}

        with self.assertRaisesRegex(RuntimeFailure, "policy-amendment checkpoint"):
            self.store._transaction(
                run_id,
                malicious,
                event_type="policy.amended",
                actor="human:forged",
            )
        self.assertEqual([], self.store.load(run_id)["policy"]["allow"])

        self.add_task(run_id, "private-capability-task", mutable=True)
        _, private_challenge = self.store.request_policy_amendment(
            run_id,
            checkpoint_id="private-capability",
            task_id="private-capability-task",
            principal="authorized-user",
            provider="trusted-provider",
            delta={"addAllow": [{"scope": "repository", "operations": ["edit"]}]},
            reason="Authorize repository edits.",
            actor="human:authorized-user",
        )

        def forged_private_authorization(run: dict[str, object]) -> dict[str, object]:
            checkpoint = next(
                item for item in run["externalCheckpoints"] if item["id"] == "private-capability"
            )
            run["policy"]["allow"] = [{"scope": "repository", "operations": ["edit"]}]
            checkpoint["status"] = "RESOLVED"
            checkpoint["resolvedAt"] = utc_now()
            checkpoint["resolvedBy"] = "human:authorized-user"
            checkpoint["resolutionRef"] = "policy:forged"
            next(task for task in run["tasks"] if task["id"] == "private-capability-task")["status"] = "READY"
            return {
                "_policyAuthorization": _PolicyAuthorization(
                    self.store._RunStore__policy_capability,
                    run["objective"]["version"],
                    run["revision"],
                    "private-capability",
                    "not-the-real-challenge",
                )
            }

        with self.assertRaisesRegex(RuntimeFailure, "policy-amendment checkpoint"):
            self.store._transaction(
                run_id,
                forged_private_authorization,
                event_type="policy.amended",
                actor="human:authorized-user",
            )
        self.assertNotEqual("not-the-real-challenge", private_challenge)

        active = self.create(allow=[{"scope": "repository", "operations": ["edit"]}])
        active_id = str(active["runId"])
        self.add_task(active_id, "running-mutation", mutable=True)
        self.add_task(active_id, "amendment-target", mutable=True)
        self.store.start_task(active_id, "running-mutation", worker_id="active-worker")
        unsafe = self.runtime_cli(
            "policy-amend-request",
            active_id,
            "--id",
            "policy-unsafe",
            "--task-id",
            "amendment-target",
            "--principal",
            "authorized-user",
            "--provider",
            "trusted-provider",
            "--actor",
            "human:authorized-user",
            "--reason",
            "Add confirmation for repository edits.",
            "--add-confirmation-required",
            "edit",
            expected=1,
        )
        self.assertEqual("POLICY_AMENDMENT_UNSAFE", unsafe["error"]["code"])

        for side_effect_state in ("PENDING", "UNCERTAIN"):
            side_effect_run = self.create(
                allow=[{"scope": "homelab:fixture", "operations": ["deploy"]}]
            )
            side_effect_id = str(side_effect_run["runId"])
            self.add_task(
                side_effect_id,
                "side-effect",
                side_effect={"operation": "deploy", "target": "homelab:fixture"},
            )
            self.add_task(side_effect_id, "policy-target", mutable=True)
            self.store.start_task(side_effect_id, "side-effect", worker_id=f"worker-{side_effect_state.lower()}")
            if side_effect_state == "UNCERTAIN":
                self.store.prepare_side_effect(
                    side_effect_id,
                    "side-effect",
                    operation="deploy",
                    target="homelab:fixture",
                )
            rejected = self.runtime_cli(
                "policy-amend-request",
                side_effect_id,
                "--id",
                f"policy-{side_effect_state.lower()}",
                "--task-id",
                "policy-target",
                "--principal",
                "authorized-user",
                "--provider",
                "trusted-provider",
                "--actor",
                "human:authorized-user",
                "--reason",
                "Authorize repository edits.",
                "--add-allow",
                "repository:edit",
                expected=1,
            )
            self.assertEqual("POLICY_AMENDMENT_UNSAFE", rejected["error"]["code"])

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

        with self.assertRaisesRegex(RuntimeFailure, "policy-amendment checkpoint"):
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
        with self.assertRaisesRegex(RuntimeFailure, "exact scopes|latest valid snapshot"):
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
        command = ("& '" + sys.executable.replace("'", "''") + "' -c \"raise SystemExit(1)\""
                   if os.name == "nt" else "'" + sys.executable + "' -c 'raise SystemExit(1)'")
        (self.repo / "architrave.config.json").write_text(json.dumps({
            "kind": "knowledge", "build": command, "test": command}), encoding="utf-8")
        self.git("add", "architrave.config.json")
        self.git("commit", "-qm", "configured failed command")
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
        self.add_task(run_id, "build")
        self.store.start_task(run_id, "build", worker_id="build-worker")
        self.store.finish_worker(run_id, "build", worker_id="build-worker", status="FINISHED")
        failed = self.store.execute_gate(run_id, "build")
        self.assertEqual("FAIL", failed["status"])
        verified, completed = self.store.verify(run_id)
        self.assertFalse(completed)
        self.assertEqual("FAILED", verified["status"])

    def test_unreferenced_old_source_pass_cannot_supply_risk_floor_credit(self) -> None:
        (self.repo / "architrave.config.json").write_text(json.dumps({
            "kind": "knowledge", "build": "git diff --check", "test": "git diff --check",
            "review": {"crossFamily": False}}), encoding="utf-8")
        self.git("add", "architrave.config.json")
        self.git("commit", "-qm", "source-bound gate fixture")
        for stale_type in ("deterministic", "reality"):
            with self.subTest(stale_type=stale_type):
                state = self.create(risk="R3", verification="reality")
                run_id = str(state["runId"])
                old = self.evidence(run_id, "old-floor", producer="legibility" if stale_type == "reality" else "deterministic")
                self.store.record_gate(run_id, gate_id="old-floor", task_id=None, gate_type=stale_type,
                    status="PASS", evidence_refs=[old], criteria=["OUTCOME-001"])
                (self.repo / "README.md").write_text("# Corrected " + stale_type + "\n", encoding="utf-8")
                self.git("add", "README.md")
                self.git("commit", "-qm", "corrected source")
                self.store.resume(run_id, accept_commit=True)
                other = "reality" if stale_type == "deterministic" else "deterministic"
                fresh = self.evidence(run_id, "fresh-other", producer="legibility" if other == "reality" else "deterministic")
                self.store.record_gate(run_id, gate_id="fresh-other", task_id=None, gate_type=other,
                    status="PASS", evidence_refs=[fresh], criteria=["OUTCOME-001"])
                semantic = self.evidence(run_id, "fresh-semantic", producer="semantic-judge")
                self.store.record_gate(run_id, gate_id="fresh-semantic", task_id=None, gate_type="semantic",
                    status="PASS", evidence_refs=[semantic], criteria=["OUTCOME-001"], family="gpt")
                current = self.store.load(run_id)
                expected = "deterministic" if stale_type == "deterministic" else "e2e-or-reality"
                self.assertIn("OUTCOME-001:" + expected,
                              missing_gate_requirements(current, current["acceptanceCriteria"]))
                replacement = self.evidence(run_id, "fresh-replacement",
                    producer="legibility" if stale_type == "reality" else "deterministic")
                self.store.record_gate(run_id, gate_id="fresh-replacement", task_id=None, gate_type=stale_type,
                    status="PASS", evidence_refs=[replacement], criteria=["OUTCOME-001"])
                current = self.store.load(run_id)
                self.assertEqual([], missing_gate_requirements(current, current["acceptanceCriteria"]))

    def test_corrected_source_pass_allows_completion_and_failed_task_recovery(self) -> None:
        command_fail = ("& '" + sys.executable.replace("'", "''") + "' -c \"raise SystemExit(1)\""
                        if os.name == "nt" else "'" + sys.executable + "' -c 'raise SystemExit(1)'")
        for recovering in (False, True):
            with self.subTest(recovering=recovering):
                (self.repo / "architrave.config.json").write_text(json.dumps({
                    "kind": "knowledge", "build": command_fail, "test": command_fail}), encoding="utf-8")
                self.git("add", "architrave.config.json")
                self.git("commit", "-qm", "failing source " + str(recovering))
                state = self.create()
                run_id = str(state["runId"])
                self.store.add_task(run_id, {"id": "delivery", "objective": "Build fixture",
                    "workerProfile": "shell", "acceptanceCriteria": ["OUTCOME-001"], "maxAttempts": 1})
                self.store.start_task(run_id, "delivery", worker_id="worker-one")
                self.store.finish_worker(run_id, "delivery", worker_id="worker-one", status="FINISHED")
                negative = self.store.execute_gate(run_id, "delivery")
                self.assertEqual("FAIL", negative["status"])
                if recovering:
                    self.store.fail_task(run_id, "delivery", "Known failed source")
                    with self.assertRaisesRegex(RuntimeFailure, "failed deterministic/product gate"):
                        self.store.recover_workers(run_id, task_id="delivery")
                (self.repo / "architrave.config.json").write_text(json.dumps({
                    "kind": "knowledge", "build": "git diff --check", "test": "git diff --check"}), encoding="utf-8")
                self.git("add", "architrave.config.json")
                self.git("commit", "-qm", "corrected source " + str(recovering))
                self.store.resume(run_id, accept_commit=True)
                if recovering:
                    self.store.recover_workers(run_id, task_id="delivery")
                    self.store.start_task(run_id, "delivery", worker_id="worker-two",
                                          retry_hypothesis="Corrected test recipe on a new accepted source commit")
                    self.store.finish_worker(run_id, "delivery", worker_id="worker-two", status="FINISHED")
                positive = self.store.execute_gate(run_id, "delivery")
                self.assertEqual("PASS", positive["status"])
                self.store.complete_task(run_id, "delivery", evidence_refs=[positive["gateRef"]])
                self.assertEqual("COMPLETED", self.store.load(run_id)["tasks"][0]["status"])
                self.assertTrue(any(gate["status"] == "FAIL" for gate in self.store.load(run_id)["gateResults"]))

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
                "tools": ["fixture"],
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
                "tools": ["fixture"],
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

    def test_review_records_reviewer_kind_and_flags_duplicate_family(self) -> None:
        state = self.create(risk="R3", verification="reality")
        run_id = str(state["runId"])
        (self.repo / "architrave.config.json").write_text(json.dumps({"review": {"crossFamily": True}}), encoding="utf-8")
        for gate_id, reviewer in (("judge-gpt", "host-native"), ("judge-claude", "architrave-judge")):
            self.store.record_gate(run_id, gate_id=gate_id, task_id=None, gate_type="semantic",
                                   family=gate_id.split("-")[1], reviewer=reviewer, status="PASS", effort="high:none",
                                   evidence_refs=[self.evidence(run_id, f"{gate_id}-evidence", producer="semantic-judge")])
        gates = {gate["id"]: gate for gate in self.store.load(run_id)["gateResults"]}
        self.assertEqual({"judge-gpt": "host-native", "judge-claude": "architrave-judge"},
                         {key: gate["reviewer"] for key, gate in gates.items()})
        self.assertEqual({"requested": "high", "effective": "none"}, gates["judge-gpt"]["effort"])
        with self.assertRaisesRegex(RuntimeFailure, "already passed"):
            self.store.record_gate(run_id, gate_id="judge-gpt-again", task_id=None, gate_type="semantic",
                                   family="gpt", reviewer="host-native", status="PASS",
                                   evidence_refs=[self.evidence(run_id, "judge-gpt-again-evidence", producer="semantic-judge")])

    def test_one_independent_review_passes_r3_without_cross_family(self) -> None:
        state = self.create(risk="R3", verification="reality")
        run_id = str(state["runId"])
        self.add_task(run_id, "product", risk="R3")
        self.finish_task(run_id, "product", "worker-product")
        self.store.record_gate(run_id, gate_id="reality", task_id="product", gate_type="reality", status="PASS",
                               evidence_refs=[self.evidence(run_id, "reality-evidence", task_id="product", producer="legibility")])
        self.store.set_criterion(run_id, "OUTCOME-001", "PASS", ["gate:reality"])
        self.store.record_gate(run_id, gate_id="judge-native", task_id=None, gate_type="semantic", family="gpt",
                               reviewer="host-native", status="PASS",
                               evidence_refs=[self.evidence(run_id, "judge-native-evidence", producer="semantic-judge")])
        _, completed = self.store.verify(run_id)
        self.assertTrue(completed)

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
                "backoffSeconds": 3,
            },
        )
        self.store.start_task(run_id, "flaky", worker_id="worker-1")
        self.store.finish_worker(run_id, "flaky", worker_id="worker-1", status="FAILED")
        task = next(t for t in self.store.load(run_id)["tasks"] if t["id"] == "flaky")
        self.assertEqual("READY", task["status"])
        self.assertEqual(1, task["attempts"])
        self.assertIsNotNone(task["retryNotBefore"])
        with self.assertRaisesRegex(RuntimeFailure, "backoff"):
            self.store.start_task(run_id, "flaky", worker_id="worker-2", retry_hypothesis="Check transient resource recovery")
        time.sleep(4.1)
        self.store.start_task(run_id, "flaky", worker_id="worker-2", retry_hypothesis="Check transient resource recovery")
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
            self.store.start_task(run_id, "flaky-fast", worker_id="worker-2", retry_hypothesis="Check transient resource recovery")

    def test_fail_task_respects_retry_policy_and_terminates_when_exhausted(self) -> None:
        state = self.create()
        run_id = str(state["runId"])
        self.add_task(run_id, "solo")
        self.store.start_task(run_id, "solo", worker_id="worker-1")
        self.store.fail_task(run_id, "solo", "flaky infra")
        task = next(t for t in self.store.load(run_id)["tasks"] if t["id"] == "solo")
        self.assertEqual("READY", task["status"])
        self.assertEqual(1, task["attempts"])
        self.store.start_task(run_id, "solo", worker_id="worker-2", retry_hypothesis="Inspect the failing infrastructure step")
        self.store.fail_task(run_id, "solo", "flaky infra")
        task = next(t for t in self.store.load(run_id)["tasks"] if t["id"] == "solo")
        self.assertEqual("FAILED", task["status"])

    def test_external_evidence_cannot_cross_objective_versions(self) -> None:
        state = self.store.create(
            goal="Resolve synthetic approval.",
            outcome="Synthetic approval is current.",
            criteria=[
                {
                    "id": "EXT-001",
                    "description": "Synthetic approval is current.",
                    "scope": "external",
                    "risk": "R1",
                    "verificationType": "external",
                    "status": "UNTESTED",
                    "evidenceRefs": [],
                    "blocking": True,
                }
            ],
            autonomy_scope="approved-program",
        )
        run_id = state["runId"]
        self.store.add_task(
            run_id,
            {
                "id": "external-task",
                "title": "External",
                "objective": "Resolve approval.",
                "workerProfile": "shell",
                "acceptanceCriteria": ["EXT-001"],
            },
        )
        _, challenge = self.store.wait_external(
            run_id,
            checkpoint_id="external-old",
            task_id="external-task",
            checkpoint_type="CONSENT_REQUIRED",
            principal="synthetic-user",
            provider="synthetic-provider",
            reason="Synthetic approval.",
        )
        evidence = self.evidence(run_id, "external-old-proof", producer="external-proof")
        self.store.resolve_external(
            run_id,
            checkpoint_id="external-old",
            resolution_ref=evidence,
            challenge=challenge,
            actor="human:synthetic-user",
        )
        self.store.add_task(
            run_id,
            {
                "id": "correction-task",
                "title": "Correction",
                "objective": "Authorize replacement.",
                "workerProfile": "shell",
                "acceptanceCriteria": ["EXT-001"],
            },
        )
        _, correction_challenge = self.store.wait_external(
            run_id,
            checkpoint_id="correction-checkpoint",
            task_id="correction-task",
            checkpoint_type="HUMAN_JUDGMENT_REQUIRED",
            principal="synthetic-user",
            provider="user-direction",
            reason="Replace the objective.",
        )
        self.store.replace_objective(
            run_id,
            outcome="Replacement approval is current.",
            criteria=[
                {
                    "id": "EXT-001",
                    "description": "Replacement approval is current.",
                    "scope": "external",
                    "risk": "R1",
                    "verificationType": "external",
                    "status": "UNTESTED",
                    "evidenceRefs": [],
                    "blocking": True,
                }
            ],
            correction="Explicit synthetic correction.",
            next_cheapest_test="Resolve the replacement approval.",
            checkpoint_id="correction-checkpoint",
            challenge=correction_challenge,
            actor="human:synthetic-user",
        )
        with self.assertRaisesRegex(RuntimeFailure, "superseded objective"):
            self.store.set_criterion(run_id, "EXT-001", "PASS", ["external:external-old"])

    def test_direct_transaction_cannot_bypass_objective_authorization(self) -> None:
        run_id = str(self.create()["runId"])
        original_objective = copy.deepcopy(self.store.load(run_id)["objective"])

        def mutate(state: dict[str, object]) -> dict[str, object]:
            state["objective"]["outcome"] = "Unauthorized replacement."
            state["objective"]["version"] = 2
            return {"objectiveVersion": 2}

        with self.assertRaisesRegex(RuntimeFailure, "trusted checkpoint"):
            self.store._transaction(
                run_id,
                mutate,
                event_type="objective.replaced",
                actor="human:synthetic-user",
            )
        state = self.store.load(run_id)
        self.assertEqual(original_objective, state["objective"])

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

    def test_pre_focus_run_v2_is_migrated_in_place(self) -> None:
        state = self.create()
        run_id = str(state["runId"])
        self.add_task(run_id, "legacy-task")
        run_dir = self.store.run_dir(run_id)
        legacy = self.store.load(run_id)
        legacy["tasks"][0]["workPacket"]["model"] = None
        for key in ("objective", "reuseBaseline", "focus", "lanes", "targetIdentity"):
            legacy.pop(key)
        events = self.store.events(run_id)
        events[-1]["payload"]["stateHash"] = self.store._state_hash(legacy)
        events[-1]["hash"] = self.store._event_hash(events[-1])
        legacy["eventCursor"] = {"sequence": len(events), "lastHash": events[-1]["hash"]}
        (run_dir / "run.json").write_text(
            json.dumps(legacy, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        (run_dir / "events.jsonl").write_text(
            "\n".join(json.dumps(event, separators=(",", ":")) for event in events) + "\n",
            encoding="utf-8",
        )
        (run_dir / "recovery.json").unlink()
        migrated = self.store.load(run_id)
        self.assertEqual(1, migrated["objective"]["version"])
        self.assertNotIn("model", migrated["tasks"][0]["workPacket"])
        self.assertTrue((run_dir / "recovery.json").is_file())
        self.assertEqual("run.migrated", self.store.events(run_id)[-1]["type"])


if __name__ == "__main__":
    unittest.main(verbosity=2)