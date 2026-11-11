#!/usr/bin/env python3
"""Lifecycle authority with real migrated Run safety and operation-bound execution."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from architrave_runtime import RunStore, RuntimeFailure, find_task, utc_now
from legibility import LegibilityRunner
from lifecycle import StateStore
from platform_launch import configured_recipe


class LifecyclePolicy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        for args in (("init", "-q"), ("config", "user.email", "test@example.invalid"),
                     ("config", "user.name", "Test"), ("commit", "--allow-empty", "-qm", "baseline")):
            subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True)
        self.runtime = RunStore(self.root)
        self.state = StateStore(self.root)
        self.sequence = 0

    def command(self, operation, payload):
        self.sequence += 1
        return self.state.apply(dict(project_id="project", command_id=f"command-{self.sequence}",
                                     expected_revision=self.state.read()["revision"],
                                     operation=operation, payload=payload))

    def operation(self, *, action="deploy", target="sandbox:fixture"):
        if not self.state.selected():
            self.state.initialize("project")
        self.command("record_source", dict(id="owner", kind="owner", reference="fixture:owner-message",
                                           excerpt="Deploy only to the fixture target", available=True))
        self.command("record_request", dict(
            goal=dict(id="goal", outcome="Exercise the real fixture operation", source_refs=["owner"], disposition="active"),
            tasks=[dict(id="deploy", goal_id="goal", title="Deploy fixture", source_refs=["owner"],
                        depends_on=[], criteria=["criterion"], progress="", disposition="active",
                        activation="automatic", paths=["fixture"])],
            criteria=[dict(id="criterion", task_id="deploy", expected="Observe the requested fixture version",
                           source_refs=["owner"], kind="runtime")], constraints=[]))
        self.command("claim_task", dict(id="attempt", task_id="deploy", worker="worker", host="session:fixture"))
        self.command("record_operation", dict(id="operation", attempt_id="attempt", target=target,
                                              action=action, artifact="fixture:release",
                                              grant_ref="owner:reported-reference-is-not-permission"))

    def capsule(self, *, allow=True, confirmation=()):
        return self.runtime.create_lifecycle_operation(
            project_id="project", task_id="deploy", operation_id="operation",
            policy_allow=[{"scope": "sandbox:fixture", "operations": ["deploy"]}] if allow else [],
            confirmation_required=confirmation,
        )

    def legacy(self, *, uncertain=False):
        state = self.runtime.create(
            goal="Existing explicitly authorized deployment", outcome="Observe fixture deployment",
            criteria=[], policy_allow=[{"scope": "sandbox:fixture", "operations": ["deploy"]}],
            confirmation_required=["deploy"], autonomy_scope="approved-program")
        rid = state["runId"]
        self.runtime.add_task(rid, dict(id="deploy", objective="Deploy only the fixture target",
                                       acceptanceCriteria=[state["acceptanceCriteria"][0]["id"]],
                                       risk="R3", pushback="KEEP:fixture operation",
                                       sideEffect={"target": "sandbox:fixture", "operation": "deploy"}))
        if uncertain:
            self.runtime.start_task(rid, "deploy", worker_id="fixture-worker", confirmed=True)
            self.runtime.prepare_side_effect(rid, "deploy", operation="deploy", target="sandbox:fixture", confirmed=True)
            self.runtime.finish_worker(rid, "deploy", worker_id="fixture-worker", status="FINISHED")
        return rid

    def migrate(self, rid):
        return self.state.initialize("project", legacy_runs=[f".architrave/runs/{rid}"])

    def receipt(self, rid, *, applied=True, aid="receipt", version="1.2.3", task_id="deploy"):
        payload = dict(taskId=task_id, target="sandbox:fixture", operation="deploy")
        if applied:
            observed = (self.root / "fixture" / "version").read_text()
            payload.update(expected={"version": version, "digest": "sha256:fixture"},
                           result={"status": "pass", "mismatches": [], "apply": {"status": "pass"}},
                           verification={"health": {"status": "pass"},
                                         "version": {"stdout": observed}, "digest": {"stdout": "sha256:fixture"}})
            producer = self.runtime._record_mutation_receipt
        else:
            payload.update(outcome="not-applied", observedAt=utc_now(),
                           observation="Fixture version file is absent after target inspection")
            self.assertFalse((self.root / "fixture" / "version").exists())
            producer = self.runtime._record_reconciliation_receipt
        path = self.runtime.run_dir(rid) / "evidence" / f"{aid}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        producer(rid, artifact_id=aid, path=path.relative_to(self.root).as_posix(), evidence_refs=["task:deploy"])
        return f"artifact:{aid}"

    def deploy_fixture(self):
        path = self.root / "fixture" / "version"
        path.parent.mkdir(exist_ok=True)
        path.write_text("1.2.3", encoding="utf-8")

    def configure_runner(self, *, failing=False):
        def recipe(source):
            return configured_recipe([sys.executable, "-c", source])
        config = {"autonomy": {"mutationPolicy": {"allow": [{"scope": "sandbox:fixture", "operations": ["deploy"]}]}},
                  "runtime": {"deployment": {
                      "target": "sandbox:fixture",
                      "current": recipe("from pathlib import Path; p=Path('fixture/version'); print(p.read_text() if p.exists() else 'absent')"),
                      "apply": recipe("from pathlib import Path; p=Path('fixture'); p.mkdir(exist_ok=True); "
                                      + ("(p/'apply-count').write_text('1'); raise SystemExit(1)" if failing else
                                         "(p/'version').write_text('1.2.3')")),
                      "health": recipe("from pathlib import Path; assert Path('fixture/version').is_file()"),
                      "version": recipe("from pathlib import Path; print(Path('fixture/version').read_text())"),
                      "digest": recipe("print('sha256:fixture')"),
                  }}}
        (self.root / "architrave.config.json").write_text(json.dumps(config), encoding="utf-8")

    def test_migrated_grant_checkpoint_receipt_and_reconciliation_remain_usable(self):
        rid = self.legacy(uncertain=True)
        self.deploy_fixture()
        imported = self.migrate(rid)
        before = self.state.path.read_bytes()
        self.assertEqual("confirmation-required", self.runtime.policy_check(rid, "sandbox:fixture", "deploy")["status"])
        self.assertEqual("allowed", self.runtime.policy_check(rid, "sandbox:fixture", "deploy", confirmed=True)["status"])
        self.assertEqual("denied", self.runtime.policy_check(rid, "sandbox:other", "deploy", confirmed=True)["status"])
        _, challenge = self.runtime.wait_external(rid, checkpoint_id="auth", task_id="deploy",
                                                  checkpoint_type="AUTH_REQUIRED", principal="owner",
                                                  provider="fixture", reason="Confirm the existing target identity")
        proof = self.runtime.run_dir(rid) / "evidence" / "auth.json"
        proof.parent.mkdir(exist_ok=True)
        proof.write_text(json.dumps(dict(checkpointId="auth", principal="owner", provider="fixture")), encoding="utf-8")
        self.runtime._record_external_proof(rid, artifact_id="auth-proof", path=proof.relative_to(self.root).as_posix(),
                                            evidence_refs=["task:deploy"])
        self.runtime.resolve_external(rid, checkpoint_id="auth", resolution_ref="artifact:auth-proof",
                                      challenge=challenge, actor="human:owner")
        receipt = self.receipt(rid)
        result = self.runtime.reconcile_side_effect(rid, "deploy", result="applied", evidence_ref=receipt)
        self.assertEqual("CONFIRMED", find_task(result, "deploy")["sideEffect"]["state"])
        self.assertEqual("deploy", result["artifacts"][-1]["consumedByTask"])
        self.assertTrue(result["checkpoints"])
        self.assertEqual(before, self.state.path.read_bytes())
        self.assertIsNone(imported["conflicts"][0]["resolution"])
        self.assertIn("mutation.reconciled", [e["type"] for e in self.runtime.events(rid)])
        self.assertEqual(result, RunStore(self.root).load(rid))

    def test_migrated_not_applied_requires_real_matching_observation_and_no_dispatch(self):
        rid = self.legacy(uncertain=True)
        self.migrate(rid)
        with self.assertRaises(RuntimeFailure):
            self.runtime.reconcile_side_effect(rid, "deploy", result="not-applied", evidence_ref="artifact:missing")
        evidence = self.receipt(rid, applied=False)
        result = self.runtime.reconcile_side_effect(rid, "deploy", result="not-applied", evidence_ref=evidence)
        self.assertEqual("NONE", find_task(result, "deploy")["sideEffect"]["state"])
        self.assertEqual([], self.runtime.ready_tasks(rid))
        with self.assertRaisesRegex(RuntimeFailure, "compete"):
            self.runtime.start_task(rid, "deploy", worker_id="no-legacy-dispatch", confirmed=True)

    def test_selected_existing_operation_can_finish_through_original_runner(self):
        self.configure_runner()
        rid = self.legacy()
        self.runtime.start_task(rid, "deploy", worker_id="settled", confirmed=True)
        self.runtime.finish_worker(rid, "deploy", worker_id="settled", status="FINISHED")
        self.migrate(rid)
        result = LegibilityRunner(self.root, rid).apply_deployment(
            confirmed=True, expected_version="1.2.3", expected_digest="sha256:fixture", task_id="deploy")
        self.assertEqual("pass", result["status"])
        self.assertEqual("CONFIRMED", find_task(self.runtime.load(rid), "deploy")["sideEffect"]["state"])

    def test_import_never_reactivates_goal_tracking_or_unselected_runs(self):
        unselected = self.legacy()
        selected = self.legacy()
        self.migrate(selected)
        with self.assertRaisesRegex(RuntimeFailure, "explicitly selected"):
            self.runtime.policy_check(unselected, "sandbox:fixture", "deploy", confirmed=True)
        with self.assertRaisesRegex(RuntimeFailure, "competing"):
            self.runtime.create(goal="Competing goal", outcome="No", criteria=[])
        for event, mutate in (
            ("task.created", lambda s: None),
            ("mutation.allowed", lambda s: s.update(goal="Spoofed authority")),
            ("mutation.allowed", lambda s: s["tasks"][0].update(objective="Different intent")),
            ("mutation.allowed", lambda s: s["tasks"][0].update(status="RUNNING")),
            ("mutation.allowed", lambda s: s["tasks"][0]["sideEffect"].update(target="sandbox:other")),
        ):
            before = self.runtime.load(selected)
            with self.subTest(event=event), self.assertRaisesRegex(RuntimeFailure, "compete|authority|projections|dispatch"):
                self.runtime._transaction(selected, mutate, event_type=event)
            self.assertEqual(before, self.runtime.load(selected))

    def test_capsule_default_deny_ignores_config_and_nonauthorizing_grant_reference(self):
        self.configure_runner()
        self.operation()
        state = self.capsule(allow=False)
        rid = state["runId"]
        self.assertEqual([], state["policy"]["allow"])
        self.assertEqual("denied", self.runtime.policy_check(rid, "sandbox:fixture", "deploy", confirmed=True)["status"])
        with self.assertRaisesRegex(RuntimeFailure, "denied"):
            self.runtime.prepare_side_effect(rid, "deploy", operation="deploy", target="sandbox:fixture", confirmed=True)
        with self.assertRaises(RuntimeFailure):
            self.runtime.lifecycle_operation_observation(rid)
        self.assertEqual([], self.runtime.ready_tasks(rid))
        with self.assertRaisesRegex(RuntimeFailure, "compete"):
            self.runtime.start_task(rid, "deploy", worker_id="not-dispatchable")

    def test_real_capsule_deployment_uses_existing_runner_and_retained_receipt(self):
        self.configure_runner()
        self.operation()
        state = self.capsule(confirmation=["deploy"])
        rid = state["runId"]
        before = self.state.read()
        result = LegibilityRunner(self.root, rid).apply_deployment(
            confirmed=True, expected_version="1.2.3", expected_digest="sha256:fixture", task_id="deploy")
        self.assertEqual("pass", result["status"])
        self.assertEqual("1.2.3", (self.root / "fixture" / "version").read_text())
        recovered = RunStore(self.root)
        observation = recovered.lifecycle_operation_observation(rid)
        self.assertEqual("succeeded", observation["outcome"])
        self.assertIn("artifact:", observation["reference"])
        self.assertEqual(before, self.state.read())
        self.command("observe_operation", observation)
        self.assertEqual("succeeded", self.state.read()["operations"]["operation"]["outcome"])
        self.assertEqual(before["tasks"]["deploy"]["progress"], self.state.read()["tasks"]["deploy"]["progress"])
        self.assertEqual("UNTESTED", recovered.load(rid)["acceptanceCriteria"][0]["status"])
        with self.assertRaises(RuntimeFailure):
            self.capsule()
        with self.assertRaises(RuntimeFailure):
            recovered.prepare_side_effect(rid, "deploy", operation="deploy", target="sandbox:fixture", confirmed=True)

    def test_failed_apply_stays_uncertain_and_cannot_replay_before_reconciliation(self):
        self.configure_runner(failing=True)
        self.operation()
        rid = self.capsule()["runId"]
        runner = LegibilityRunner(self.root, rid)
        result = runner.apply_deployment(confirmed=True, expected_version="1.2.3",
                                         expected_digest="sha256:fixture", task_id="deploy")
        self.assertEqual("fail", result["status"])
        observation = self.runtime.lifecycle_operation_observation(rid)
        self.assertEqual("unknown", observation["outcome"])
        self.command("observe_operation", observation)
        with self.assertRaises(RuntimeFailure):
            runner.apply_deployment(confirmed=True, expected_version="1.2.3",
                                    expected_digest="sha256:fixture", task_id="deploy")
        self.assertEqual("1", (self.root / "fixture" / "apply-count").read_text())
        evidence = self.receipt(rid, applied=False)
        self.runtime.reconcile_side_effect(rid, "deploy", result="not-applied", evidence_ref=evidence)
        self.command("observe_operation", self.runtime.lifecycle_operation_observation(rid))
        self.assertEqual("failed", self.state.read()["operations"]["operation"]["outcome"])

    def test_capsule_preserves_checkpoint_authority_and_exact_policy_amendment(self):
        self.operation()
        rid = self.capsule(allow=False)["runId"]
        delta = {"addAllow": [{"scope": "sandbox:fixture", "operations": ["deploy"]}],
                 "addConfirmationRequired": ["deploy"]}
        _, challenge = self.runtime.request_policy_amendment(
            rid, checkpoint_id="grant", task_id="deploy", principal="owner", provider="host",
            delta=delta, reason="Exact owner-approved fixture grant", actor="human:owner")
        with self.assertRaises(RuntimeFailure):
            self.runtime.amend_policy(rid, checkpoint_id="grant", challenge="wrong", principal="owner",
                                      provider="host", delta=delta, actor="human:owner")
        self.runtime.amend_policy(rid, checkpoint_id="grant", challenge=challenge, principal="owner",
                                  provider="host", delta=delta, actor="human:owner")
        self.assertEqual("confirmation-required", self.runtime.policy_check(rid, "sandbox:fixture", "deploy")["status"])
        with self.assertRaises(RuntimeFailure):
            self.runtime.prepare_side_effect(rid, "deploy", operation="deploy", target="sandbox:fixture")
        self.runtime.prepare_side_effect(rid, "deploy", operation="deploy", target="sandbox:fixture", confirmed=True)
        self.assertEqual("SIDE_EFFECT_AMBIGUITY", self.runtime.load(rid)["checkpoints"][-1]["kind"])

    def test_pending_external_checkpoint_cannot_be_bypassed_by_operation_prepare(self):
        self.operation()
        rid = self.capsule()["runId"]
        self.runtime.wait_external(rid, checkpoint_id="auth", task_id="deploy", checkpoint_type="AUTH_REQUIRED",
                                   principal="owner", provider="fixture", reason="External target access")
        with self.assertRaisesRegex(RuntimeFailure, "checkpoint"):
            self.runtime.prepare_side_effect(rid, "deploy", operation="deploy", target="sandbox:fixture")
        self.assertEqual("NONE", find_task(self.runtime.load(rid), "deploy")["sideEffect"]["state"])

    def test_capsule_rejects_broader_grants_identity_mismatch_and_changed_intent(self):
        self.operation()
        for kwargs in (
            {"project_id": "wrong", "task_id": "deploy", "operation_id": "operation"},
            {"project_id": "project", "task_id": "wrong", "operation_id": "operation"},
            {"project_id": "project", "task_id": "deploy", "operation_id": "operation",
             "policy_allow": [{"scope": "sandbox:other", "operations": ["deploy"]}]},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(RuntimeFailure):
                self.runtime.create_lifecycle_operation(**kwargs)
        rid = self.capsule()["runId"]
        self.command("apply_correction", dict(collection="tasks", target="deploy", kind="defer",
                                              changes={"disposition": "deferred"}, source_refs=["owner"]))
        with self.assertRaises(RuntimeFailure):
            self.runtime.prepare_side_effect(rid, "deploy", operation="deploy", target="sandbox:fixture", confirmed=True)
        self.assertIsNone(find_task(self.runtime.load(rid), "deploy")["sideEffect"]["reconciliation"])

    def test_unrelated_lifecycle_revision_does_not_invalidate_operation(self):
        self.operation()
        rid = self.capsule()["runId"]
        self.command("set_phase", {"phase": "delivery"})
        self.runtime.prepare_side_effect(rid, "deploy", operation="deploy", target="sandbox:fixture", confirmed=True)
        self.assertEqual("UNCERTAIN", find_task(self.runtime.load(rid), "deploy")["sideEffect"]["state"])

    def test_runtime_target_operation_cannot_substitute_for_trusted_identity(self):
        self.operation(action="launch", target="runtime:fixture")
        state = self.runtime.create_lifecycle_operation(
            project_id="project", task_id="deploy", operation_id="operation",
            policy_allow=[{"scope": "runtime:fixture", "operations": ["launch"]}])
        with self.assertRaisesRegex(RuntimeFailure, "trusted identity"):
            self.runtime.prepare_side_effect(state["runId"], "deploy", operation="launch", target="runtime:fixture")
        self.assertEqual("NONE", find_task(self.runtime.load(state["runId"]), "deploy")["sideEffect"]["state"])

    def test_uncertain_capsule_reconciles_after_intent_changes_without_restoring_it(self):
        self.operation()
        rid = self.capsule()["runId"]
        self.runtime.prepare_side_effect(rid, "deploy", operation="deploy", target="sandbox:fixture")
        self.command("apply_correction", dict(collection="tasks", target="deploy", kind="defer",
                                              changes={"disposition": "deferred"}, source_refs=["owner"]))
        self.deploy_fixture()
        evidence = self.receipt(rid)
        self.runtime.reconcile_side_effect(rid, "deploy", result="applied", evidence_ref=evidence)
        self.command("observe_operation", self.runtime.lifecycle_operation_observation(rid))
        self.assertEqual("deferred", self.state.read()["tasks"]["deploy"]["disposition"])
        self.assertEqual("succeeded", self.state.read()["operations"]["operation"]["outcome"])

    def test_capsule_rejects_forged_receipt_and_preserves_receipt_tamper_checks(self):
        self.operation()
        rid = self.capsule()["runId"]
        self.runtime.prepare_side_effect(rid, "deploy", operation="deploy", target="sandbox:fixture")
        self.deploy_fixture()
        with self.assertRaisesRegex(RuntimeFailure, "version"):
            self.receipt(rid, version="wrong", aid="wrong-version")
        evidence = self.receipt(rid)
        self.runtime.reconcile_side_effect(rid, "deploy", result="applied", evidence_ref=evidence)
        state = self.runtime.load(rid)
        artifact = state["artifacts"][-1]
        path = self.root / artifact["path"]
        payload = json.loads(path.read_text())
        payload["target"] = "sandbox:other"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(RuntimeFailure):
            self.runtime.lifecycle_operation_observation(rid)

    def test_legacy_unknown_scope_denies_new_effects_but_retains_reconciliation(self):
        self.operation()
        original = self.state.read()
        older = self.state.read()
        older["attempts"]["attempt"].pop("scope")
        self.state._write(older)
        with self.assertRaisesRegex(RuntimeFailure, "assigned scope"):
            self.capsule()
        self.state._write(original)
        rid = self.capsule()["runId"]
        self.runtime.prepare_side_effect(rid, "deploy", operation="deploy", target="sandbox:fixture")
        older = self.state.read()
        older["attempts"]["attempt"].pop("scope")
        self.state._write(older)
        with self.assertRaisesRegex(RuntimeFailure, "assigned scope"):
            self.runtime.prepare_side_effect(rid, "deploy", operation="deploy", target="sandbox:fixture")
        self.deploy_fixture()
        evidence = self.receipt(rid)
        self.runtime.reconcile_side_effect(rid, "deploy", result="applied", evidence_ref=evidence)
        self.command("observe_operation", self.runtime.lifecycle_operation_observation(rid))
        self.assertEqual(self.state.read()["operations"]["operation"]["outcome"], "succeeded")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--schema-fixture":
        fixture = LifecyclePolicy()
        try:
            fixture.setUp()
            fixture.operation()
            Path(sys.argv[2]).write_text(json.dumps(fixture.capsule(), indent=2) + "\n", encoding="utf-8")
        finally:
            fixture.doCleanups()
    else:
        unittest.main()
