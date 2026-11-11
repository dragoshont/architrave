#!/usr/bin/env python3
"""Real-path lifecycle acceptance, persistence, CLI and rendering regressions."""
from __future__ import annotations

import copy
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from lifecycle import StateError, StateStore, encode, inputs, parse, reported_machine, seal, snapshot, task_projection
from architrave_runtime import RunStore, RuntimeFailure
import program_board

NOW = "2026-11-11T17:00:00Z"


def writer(root, cid, ready, output):
    ready.wait()
    try:
        receipt = StateStore(root).apply(dict(project_id="project", command_id=cid,
                                             expected_revision=0, operation="set_phase", payload={"phase": "review"}))
        output.put(("ok", receipt["revision"]))
    except StateError as exc:
        output.put((exc.code, None))


class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = StateStore(self.root)
        self.store.initialize("project")
        self.sequence = 0

    def command(self, op, payload, **kwargs):
        self.sequence += 1
        command = dict(project_id="project", command_id=f"command-{self.sequence}",
                       expected_revision=self.store.read()["revision"], operation=op, payload=payload)
        return self.store.apply(command, **kwargs)

    def source(self, sid="owner", kind="owner"):
        self.command("record_source", dict(id=sid, kind=kind, reference=f"message:{sid}",
                                           excerpt="Do local work; defer deployment. <script>alert(1)</script>", available=True))

    def request(self, tid="local", *, disposition="active", activation="automatic", paths=None):
        if "owner" not in self.store.read()["sources"]:
            self.source()
        goal = dict(id=f"goal-{tid}", outcome=f"Outcome {tid}", source_refs=["owner"], disposition="active")
        task = dict(id=tid, goal_id=goal["id"], title=f"Implement {tid}", source_refs=["owner"],
                    depends_on=[], criteria=[f"criterion-{tid}"], progress="", disposition=disposition,
                    activation=activation, paths=[f"src/{tid}"] if paths is None else paths)
        criterion = dict(id=f"criterion-{tid}", task_id=tid, expected=f"Actual result for {tid}",
                         source_refs=["owner"], kind="implementation")
        self.command("record_request", dict(goal=goal, tasks=[task], criteria=[criterion], constraints=[]))

    def correction(self, target, changes, *, collection="tasks", kind="revise", source="owner"):
        return self.command("apply_correction", dict(collection=collection, target=target, changes=changes,
                                                     source_refs=[source], kind=kind))

    def claim(self, tid="local", aid="attempt", *, read_only=False):
        self.command("claim_task", dict(id=aid, task_id=tid, worker="worker", host="session:1", read_only=read_only))

    def observation(self, activity, *, aid="attempt", ack=False):
        self.command("observe_attempt", dict(attempt_id=aid, activity=activity, stop_acknowledged=ack,
                                             reference="host:observation", observed_at=NOW))

    def identity(self, candidate="workspace:tree-sha"):
        return dict(candidate=candidate, source="git:source-sha", base="git:base-sha", check_inputs="checks:input-sha")

    def result(self, aid="attempt", *, identity=None):
        identity = self.identity() if identity is None else identity
        return self.command("record_result", dict(attempt_id=aid, artifact=identity["candidate"],
                                                 summary="Written candidate", identity=identity))

    def evidence(self, eid="proof", cid="criterion-local", *, aid="attempt", identity=None):
        state = self.store.read()
        row = state["attempts"].get(aid)
        payload = dict(id=eid, criterion_id=cid, inputs=inputs(state, state["criteria"][cid]["task_id"], cid),
                       artifact="test:result-sha", method="actual CLI check", result="pass", observed_at=NOW,
                       identity=identity or (row["result"]["identity"] if row and row["result"] else self.identity()),
                       limitations="Source regression, not live-host qualification")
        if row:
            payload["attempt_id"] = aid
        self.command("record_evidence", payload)

    def operation(self, oid="integration", action="source-mutation", *, aid="attempt", target="git:owned-branch",
                  identity=None):
        payload = dict(id=oid, attempt_id=aid, target=target, action=action, artifact="workspace:tree-sha",
                       grant_ref="owner:scoped-source-work")
        if action == "integrate" or identity is not None:
            payload["identity"] = identity or self.store.read()["attempts"][aid]["result"]["identity"]
            payload["artifact"] = payload["identity"]["candidate"]
        return self.command("record_operation", payload)

    def observe_operation(self, outcome, *, reconcile=False, oid="integration", identity=None):
        payload = dict(id=oid, outcome=outcome, reference="target:read-back", observed_at=NOW,
                       reconciliation=reconcile)
        operation = self.store.read()["operations"][oid]
        if outcome == "succeeded" and operation["action"] == "integrate":
            payload["identity"] = identity or operation["identity"]
        return self.command("observe_operation", payload)

    def test_vertical_owner_update_next_action_and_same_revision_board(self):
        self.request()
        self.request("deploy", disposition="deferred", activation="explicit_owner_direction")
        view = snapshot(self.store.read(), now=NOW)
        self.assertEqual(view["next_action"], {"kind": "work", "task_id": "local"})
        self.correction("local", {"title": "Use the authenticated gateway"})
        self.command("record_progress", dict(task_id="local", progress="Code ready"))
        state = self.store.read()
        self.assertEqual(state["tasks"]["deploy"]["disposition"], "deferred")
        data = program_board.build(self.root, "11111111-1111-1111-1111-111111111111")
        self.assertEqual(data["lifecycle"]["revision"], state["revision"])
        page = program_board.render(data)
        self.assertIn("Use the authenticated gateway", page)
        self.assertIn("explicit_owner_direction", page)
        self.assertIn("unverified", page)
        self.assertNotIn("state completion: pass", page)

    def test_targeted_corrections_preserve_unaffected_work_and_ids(self):
        self.request()
        self.request("unrelated")
        before = self.store.read()
        self.correction("local", {"title": "Renamed", "depends_on": ["unrelated"]}, kind="reorder")
        after = self.store.read()
        self.assertEqual(before["tasks"]["unrelated"], after["tasks"]["unrelated"])
        self.assertEqual(list(before["tasks"]), list(after["tasks"]))
        self.assertEqual(after["corrections"][0]["before"]["title"], "Implement local")
        self.assertEqual(after["corrections"][0]["source_refs"], ["owner"])

    def test_proposals_questions_and_deferred_dependencies_do_not_activate(self):
        self.request()
        self.request("proposal", disposition="proposed")
        self.request("later", disposition="deferred", activation="explicit_owner_direction")
        self.correction("later", {"depends_on": ["local"]})
        self.command("record_progress", dict(task_id="local", progress="Code ready"))
        for tid in ("proposal", "later"):
            with self.assertRaisesRegex(StateError, "HELD"):
                self.claim(tid, "attempt-" + tid)
        self.assertEqual(self.store.read()["attempts"], {})

    def test_decisions_partial_answers_and_existing_answers_persist(self):
        self.request()
        self.request("other")
        for did, tid in (("choice", "local"), ("other-choice", "other")):
            self.command("record_question", dict(id=did, question="Choose behavior", alternatives=["A", "B"],
                                                 affected=[tid], source_refs=["owner"],
                                                 resolution=None, resolution_sources=[]))
        self.command("resolve_decision", dict(id="choice", resolution="A", source_refs=["owner"]))
        view = snapshot(self.store.read(), now=NOW)
        self.assertEqual(view["next_action"]["task_id"], "local")
        self.assertTrue(view["tasks"][1]["holds"])
        self.assertEqual(StateStore(self.root).read()["decisions"]["choice"]["resolution"], "A")
        with self.assertRaisesRegex(StateError, "DECISION"):
            self.command("resolve_decision", dict(id="choice", resolution="B", source_refs=["owner"]))

    def test_stop_request_ack_and_terminal_observation_keep_ownership(self):
        self.request()
        self.claim()
        self.command("request_stop", {"attempt_id": "attempt"})
        self.observation("running", ack=True)
        with self.assertRaisesRegex(StateError, "HELD"):
            self.claim(aid="replacement")
        self.observation("cancelled")
        self.claim(aid="replacement")
        self.assertEqual(self.store.read()["attempts"]["attempt"]["stop"], "acknowledged")

    def test_restart_unknown_activity_does_not_release_owner(self):
        self.request()
        self.claim()
        self.store = StateStore(self.root)
        self.assertEqual(self.store.read()["attempts"]["attempt"]["activity"], "unknown")
        with self.assertRaisesRegex(StateError, "HELD"):
            self.claim(aid="replacement")

    def test_overlapping_paths_and_same_task_are_exclusive(self):
        self.request(paths=["src"])
        self.request("other", paths=["src/child.py"])
        self.claim()
        with self.assertRaisesRegex(StateError, "HELD"):
            self.claim("other", "other-attempt")

    def test_attempt_ownership_uses_frozen_assignment_not_corrected_paths(self):
        self.request(paths=["src/original"])
        self.request("overlap", paths=["src/original/child.py"])
        self.request("new-scope", paths=["src/replacement"])
        self.claim()
        self.correction("local", {"paths": ["src/replacement"]})
        state = self.store.read()
        self.assertEqual(state["attempts"]["attempt"]["scope"], {"mode": "mutable", "paths": ["src/original"]})
        with self.assertRaisesRegex(StateError, "HELD.*attempt"):
            self.claim("overlap", "overlap-attempt")
        self.claim("new-scope", "new-attempt")
        self.assertEqual(self.store.read()["attempts"]["attempt"]["scope"]["paths"], ["src/original"])

    def test_empty_mutable_scope_rejected_and_explicit_read_only_review_runs(self):
        self.request("review", paths=[])
        before = self.store.read()
        with self.assertRaisesRegex(StateError, "SCOPE"):
            self.claim("review", "review-attempt")
        self.assertEqual(self.store.read(), before)
        self.claim("review", "review-attempt", read_only=True)
        self.request()
        self.claim()
        self.assertEqual(self.store.read()["attempts"]["review-attempt"]["scope"],
                         {"mode": "read_only", "paths": []})
        with self.assertRaisesRegex(StateError, "READ_ONLY"):
            self.operation(aid="review-attempt")
        self.result("review-attempt")
        self.observation("completed", aid="review-attempt")
        self.assertEqual(self.store.read()["attempts"]["review-attempt"]["activity"], "completed")

    def test_legacy_missing_scope_stays_readable_but_fails_closed(self):
        self.request(paths=["src/one"])
        self.request("two", paths=["src/two"])
        self.request("three", paths=["src/three"])
        self.claim()
        self.claim("two", "two-attempt")
        legacy = self.store.read()
        for row in legacy["attempts"].values():
            del row["scope"]
        seal(legacy)
        self.store.path.write_bytes(encode(legacy))
        self.store = StateStore(self.root)
        self.correction("local", {"paths": []})
        view = snapshot(self.store.read(), now=NOW)
        self.assertTrue(all(a["scope_status"] == "unavailable" and "scope" not in a for a in view["attempts"]))
        with self.assertRaisesRegex(StateError, "HELD.*attempt"):
            self.claim("three", "three-attempt")
        self.observation("cancelled")
        with self.assertRaisesRegex(StateError, "HELD.*two-attempt"):
            self.claim("three", "three-attempt")
        self.observation("cancelled", aid="two-attempt")
        self.claim("three", "three-attempt")

    def test_uncertain_operation_holds_frozen_paths_after_terminal_attempt(self):
        self.request(paths=["src/original"])
        self.request("overlap", paths=["src/original/child.py"])
        self.request("disjoint", paths=["src/replacement"])
        self.claim()
        self.operation()
        self.observe_operation("unknown")
        self.observation("completed")
        self.correction("local", {"paths": ["src/replacement"]})
        with self.assertRaisesRegex(StateError, "HELD.*operation"):
            self.claim("overlap", "overlap-attempt")
        self.claim("disjoint", "disjoint-attempt")
        self.observe_operation("failed", reconcile=True)
        self.claim("overlap", "overlap-attempt")

    def test_legacy_uncertain_operation_with_unknown_scope_holds_disjoint_mutation(self):
        self.request()
        self.request("unrelated")
        self.claim()
        self.operation()
        self.observation("completed")
        legacy = self.store.read()
        del legacy["attempts"]["attempt"]["scope"]
        seal(legacy)
        self.store.path.write_bytes(encode(legacy))
        with self.assertRaisesRegex(StateError, "HELD.*operation"):
            self.claim("unrelated", "new-attempt")
        self.observe_operation("failed", reconcile=True)
        self.claim("unrelated", "new-attempt")

    def test_same_target_different_action_and_disjoint_tasks_require_reconciliation(self):
        for outcome in ("intended", "unknown"):
            with self.subTest(outcome=outcome):
                first, second = "first-" + outcome, "second-" + outcome
                self.request(first)
                self.request(second)
                self.claim(first, first)
                self.claim(second, second)
                self.operation(first, "create", aid=first, target="cloud:" + outcome)
                if outcome == "unknown":
                    self.observe_operation("unknown", oid=first)
                before = self.store.read()
                with self.assertRaisesRegex(StateError, "RECONCILE_FIRST"):
                    self.operation(second, "delete", aid=second, target="cloud:" + outcome)
                self.assertEqual(self.store.read(), before)
                self.observe_operation("failed", reconcile=True, oid=first)
                self.operation(second, "delete", aid=second, target="cloud:" + outcome)

    def test_same_intent_candidates_cannot_reuse_other_attempt_checks(self):
        self.request()
        self.claim(aid="candidate-a")
        self.result("candidate-a", identity=self.identity("workspace:candidate-a"))
        self.observation("completed", aid="candidate-a")
        self.evidence("proof-a", aid="candidate-a")
        original_inputs = self.store.read()["attempts"]["candidate-a"]["inputs"]
        self.claim(aid="candidate-b")
        self.result("candidate-b", identity=self.identity("workspace:candidate-b"))
        self.observation("completed", aid="candidate-b")
        self.operation(action="integrate", aid="candidate-b")
        self.observe_operation("succeeded")
        self.assertEqual(self.store.read()["attempts"]["candidate-b"]["inputs"], original_inputs)
        before = self.store.read()
        with self.assertRaisesRegex(StateError, "CHECKS"):
            self.command("integrate_candidate", dict(attempt_id="candidate-b", operation_id="integration",
                                                      checks=["proof-a"]))
        self.assertEqual(self.store.read(), before)
        self.evidence("proof-b", aid="candidate-b")
        self.command("integrate_candidate", dict(attempt_id="candidate-b", operation_id="integration",
                                                  checks=["proof-b"]))
        view = snapshot(self.store.read(), now=NOW)
        proofs = view["tasks"][0]["acceptance"][0]["evidence"]
        self.assertEqual([e["applicability"] for e in proofs], ["current", "current"])
        self.assertEqual([e["identity"]["candidate"] for e in proofs],
                         ["workspace:candidate-a", "workspace:candidate-b"])

    def test_checks_and_integration_bind_every_reported_identity_component(self):
        self.request()
        self.claim()
        self.result()
        self.observation("completed")
        self.evidence()
        for field in ("candidate", "source", "base", "check_inputs"):
            with self.subTest(field=field):
                wrong = self.identity()
                wrong[field] = "different:" + field
                before = self.store.read()
                with self.assertRaisesRegex(StateError, "RESULT"):
                    self.operation("wrong-operation-" + field, "integrate", identity=wrong)
                self.assertEqual(self.store.read(), before)
                self.evidence("wrong-proof-" + field, identity=wrong)
        self.operation(action="integrate")
        self.observe_operation("succeeded")
        for field in ("candidate", "source", "base", "check_inputs"):
            with self.subTest(check=field), self.assertRaisesRegex(StateError, "CHECKS"):
                self.command("integrate_candidate", dict(attempt_id="attempt", operation_id="integration",
                                                          checks=["wrong-proof-" + field]))
        self.command("integrate_candidate", dict(attempt_id="attempt", operation_id="integration", checks=["proof"]))

    def test_integration_compares_observed_identity_not_only_intended_identity(self):
        self.request()
        self.claim()
        self.result()
        self.observation("completed")
        self.evidence()
        self.operation(action="integrate")
        before = self.store.read()
        with self.assertRaisesRegex(StateError, "IDENTITY_UNAVAILABLE"):
            self.command("observe_operation", dict(id="integration", outcome="succeeded", reference="target:read-back",
                                                    observed_at=NOW, reconciliation=False))
        self.assertEqual(self.store.read(), before)
        observed = self.identity()
        observed["base"] = "git:different-actual-base"
        self.observe_operation("succeeded", identity=observed)
        with self.assertRaisesRegex(StateError, "OPERATION"):
            self.command("integrate_candidate", dict(attempt_id="attempt", operation_id="integration", checks=["proof"]))
        state = self.store.read()
        self.assertEqual(state["operations"]["integration"]["observation"]["identity"], observed)
        self.assertFalse(state["attempts"]["attempt"]["integrated"])

    def test_checks_for_identical_candidate_still_bind_exact_attempt(self):
        self.request()
        for aid in ("first", "second"):
            self.claim(aid=aid)
            self.result(aid)
            self.observation("completed", aid=aid)
        self.evidence("first-proof", aid="first")
        self.operation(action="integrate", aid="second")
        self.observe_operation("succeeded")
        with self.assertRaisesRegex(StateError, "CHECKS"):
            self.command("integrate_candidate", dict(attempt_id="second", operation_id="integration", checks=["first-proof"]))
        self.assertEqual(snapshot(self.store.read(), now=NOW)["tasks"][0]["acceptance"][0]["evidence"][0]["applicability"],
                         "current")

    def test_legacy_unbound_proof_and_operation_are_not_blessed(self):
        self.request()
        self.claim()
        self.result()
        self.observation("completed")
        self.evidence()
        self.operation(action="integrate")
        self.observe_operation("succeeded")
        legacy = self.store.read()
        del legacy["evidence"]["proof"]["identity"]
        del legacy["operations"]["integration"]["identity"]
        seal(legacy)
        self.store.path.write_bytes(encode(legacy))
        view = snapshot(self.store.read(), now=NOW)
        self.assertEqual(view["tasks"][0]["acceptance"][0]["evidence"][0]["applicability"], "unavailable")
        with self.assertRaisesRegex(StateError, "CHECKS"):
            self.command("integrate_candidate", dict(attempt_id="attempt", operation_id="integration", checks=["proof"]))
        self.evidence("new-proof")
        with self.assertRaisesRegex(StateError, "OPERATION"):
            self.command("integrate_candidate", dict(attempt_id="attempt", operation_id="integration", checks=["new-proof"]))
        legacy = self.store.read()
        del legacy["attempts"]["attempt"]["result"]["identity"]
        seal(legacy)
        self.store.path.write_bytes(encode(legacy))
        with self.assertRaisesRegex(StateError, "IDENTITY_UNAVAILABLE"):
            self.command("integrate_candidate", dict(attempt_id="attempt", operation_id="integration", checks=["new-proof"]))
        self.assertNotIn("identity", self.store.read()["attempts"]["attempt"]["result"])

    def test_late_result_retained_but_conflicting_integration_rejected(self):
        self.request()
        self.claim()
        self.correction("goal-local", {"outcome": "Changed required behavior"}, collection="goals")
        self.result()
        self.observation("completed")
        self.evidence()
        with self.assertRaisesRegex(StateError, "STALE_INPUTS"):
            self.command("integrate_candidate", dict(attempt_id="attempt", operation_id="none", checks=["proof"]))
        self.assertIsNotNone(self.store.read()["attempts"]["attempt"]["result"])

    def test_unrelated_revision_does_not_invalidate_candidate_and_integration_is_observed(self):
        self.request()
        self.claim()
        self.request("unrelated")
        self.result()
        self.observation("completed")
        self.evidence()
        self.operation(action="integrate")
        self.observe_operation("succeeded")
        self.command("integrate_candidate", dict(attempt_id="attempt", operation_id="integration", checks=["proof"]))
        self.assertTrue(self.store.read()["attempts"]["attempt"]["integrated"])

    def test_result_idempotence_and_payload_conflict(self):
        self.request()
        self.claim()
        self.result()
        self.result()
        before = self.store.read()
        with self.assertRaisesRegex(StateError, "RESULT_CONFLICT"):
            self.command("record_result", dict(attempt_id="attempt", artifact="other", summary="different",
                                                identity=self.identity("other")))
        self.assertEqual(self.store.read(), before)

    def test_command_retry_returns_original_receipt_after_later_revision(self):
        command = dict(project_id="project", command_id="stable", expected_revision=0,
                       operation="set_phase", payload={"phase": "review"})
        first = self.store.apply(command)
        self.command("set_phase", {"phase": "implementation"})
        self.assertEqual(first, self.store.apply(command))
        before = self.store.read()
        command["payload"]["phase"] = "held"
        with self.assertRaisesRegex(StateError, "IDEMPOTENCY_CONFLICT"):
            self.store.apply(command)
        self.assertEqual(before, self.store.read())

    def test_concurrent_expected_revision_has_one_winner(self):
        context = multiprocessing.get_context("spawn")
        ready, output = context.Event(), context.Queue()
        workers = [context.Process(target=writer, args=(self.root, str(n), ready, output)) for n in range(2)]
        for process in workers:
            process.start()
        ready.set()
        for process in workers:
            process.join(20)
            self.assertEqual(process.exitcode, 0)
        outcomes = sorted(output.get(timeout=2)[0] for _ in workers)
        self.assertEqual(outcomes, ["STALE_REVISION", "ok"])
        self.assertEqual(len(self.store.read()["receipts"]), 1)

    def test_crash_before_and_after_replace_keeps_matching_receipt(self):
        for after in (False, True):
            root = self.root / str(after)
            StateStore(root).initialize("project")
            code = """
import os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from lifecycle import StateStore
original = os.replace
def crash(src, dst):
    if sys.argv[3] == 'True':
        original(src, dst)
    os._exit(37)
os.replace = crash
StateStore(sys.argv[2]).apply(dict(project_id='project', command_id='crash', expected_revision=0,
                                 operation='set_phase', payload={'phase':'review'}))
"""
            result = subprocess.run([sys.executable, "-c", code, str(ROOT / "harness"), str(root), str(after)])
            self.assertEqual(result.returncode, 37)
            state = StateStore(root).read()
            self.assertEqual(state["revision"], 1 if after else 0)
            self.assertEqual("crash" in state["receipts"], after)

    def test_unknown_external_outcome_requires_reconciliation_before_retry(self):
        self.request()
        self.claim()
        self.operation()
        self.observe_operation("unknown")
        with self.assertRaisesRegex(StateError, "RECONCILE_FIRST"):
            self.operation("duplicate")
        with self.assertRaisesRegex(StateError, "RECONCILE_FIRST"):
            self.observe_operation("succeeded")
        self.observe_operation("succeeded", reconcile=True)
        self.assertTrue(self.store.read()["operations"]["integration"]["reconciled"])

    def test_strict_yaml_profile_and_unknown_schema_and_unsupported_edits(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e9999}', b'{"x":-1e9999}', b"x: yes", b'{"x": [}',
                    b'{"x":' + b"[" * 50 + b"0" + b"]" * 50 + b"}"):
            with self.subTest(raw=raw[:30]), self.assertRaises(StateError):
                parse(raw)
        state = self.store.read()
        state["schema"] = "unknown"
        seal(state)
        self.store.path.write_bytes(encode(state))
        with self.assertRaisesRegex(StateError, "SCHEMA"):
            self.store.read()
        state["schema"] = "architrave.lifecycle.v1"
        seal(state)
        state["phase"] = "review"
        self.store.path.write_bytes(encode(state))
        with self.assertRaisesRegex(StateError, "UNSUPPORTED_EDIT"):
            self.store.read()

    def test_cycle_and_invalid_reference_roll_back(self):
        self.request()
        before = self.store.read()
        for changes in ({"depends_on": ["local"]}, {"depends_on": ["missing"]}, {"paths": ["../outside"]}):
            with self.assertRaises(StateError):
                self.correction("local", changes)
            self.assertEqual(before, self.store.read())

    def test_scope_and_claimed_human_role_do_not_grant_authority(self):
        self.request()
        self.claim()
        with self.assertRaisesRegex(StateError, "ROLE"):
            self.command("apply_correction", dict(collection="tasks", target="local", changes={"title": "forged"},
                                                  kind="revise", source_refs=["owner"]), worker="worker")
        with self.assertRaisesRegex(StateError, "SHAPE"):
            self.command("record_source", dict(id="forged", kind="owner", reference="worker:forward",
                                               excerpt="deploy", available=True, actor="human"))
        self.source("document", "document")
        with self.assertRaisesRegex(StateError, "OWNER_SOURCE"):
            self.command("apply_correction", dict(collection="tasks", target="local", changes={"disposition": "cancelled"},
                                                  kind="cancel", source_refs=["document"]))

    def test_criterion_only_changes_preserve_unaffected_evidence(self):
        self.request()
        self.command("add_criterion", dict(id="criterion-runtime", task_id="local", expected="Runtime result",
                                          source_refs=["owner"], kind="runtime"))
        self.evidence()
        self.evidence("runtime-proof", "criterion-runtime")
        self.correction("criterion-runtime", {"expected": "Changed runtime result"}, collection="criteria")
        criteria = snapshot(self.store.read(), now=NOW)["tasks"][0]["acceptance"]
        self.assertEqual(criteria[0]["evidence"][0]["applicability"], "current")
        self.assertEqual(criteria[1]["evidence"][0]["applicability"], "stale")

    def test_material_corrections_stale_readiness_and_reopen_only_affected_work(self):
        self.request("unrelated")
        self.evidence("unrelated-proof", "criterion-unrelated")
        self.command("record_progress", dict(task_id="unrelated", progress="Code ready"))
        for change in ("requirement", "criterion", "constraint", "retirement", "addition"):
            with self.subTest(change=change):
                tid, cid = "task-" + change, "constraint-" + change
                self.request(tid)
                self.request(tid + "-dependent")
                self.correction(tid + "-dependent", {"depends_on": [tid]})
                self.command("record_request", dict(goal=self.store.read()["goals"]["goal-" + tid], tasks=[], criteria=[],
                                                     constraints=[dict(id=cid, statement="Keep monitoring",
                                                                       applies_to=[tid], source_refs=["owner"],
                                                                       disposition="active")]))
                self.command("record_progress", dict(task_id=tid, progress="Code ready"))
                before = self.store.read()
                if change == "requirement":
                    self.correction("goal-" + tid, {"outcome": "Require authenticated execution"}, collection="goals")
                elif change == "criterion":
                    self.correction("criterion-" + tid, {"expected": "Check the actual new result"}, collection="criteria")
                elif change == "constraint":
                    self.correction(cid, {"statement": "Keep monitoring and its alerts"}, collection="constraints")
                elif change == "retirement":
                    self.correction(cid, {"disposition": "retired"}, collection="constraints", kind="retire")
                else:
                    self.command("add_criterion", dict(id="additional", task_id=tid, expected="New required behavior",
                                                       source_refs=["owner"], kind="implementation"))
                state = self.store.read()
                view = snapshot(state, now=NOW, task_ids=[tid, tid + "-dependent", "unrelated"])
                self.assertEqual(view["tasks"][0]["progress"], "Code ready")
                self.assertEqual(view["tasks"][0]["readiness"], "stale")
                self.assertEqual(view["next_action"], {"kind": "reevaluate", "task_id": tid})
                self.assertIn("dependency " + tid, view["tasks"][1]["holds"])
                self.assertEqual(before["tasks"]["unrelated"], state["tasks"]["unrelated"])
                self.assertEqual(view["tasks"][2]["readiness"], "current")
                self.assertEqual(view["tasks"][2]["acceptance"][0]["evidence"][0]["applicability"], "current")
                self.claim(tid, "reevaluate-" + change)
                self.assertEqual(self.store.read()["tasks"][tid]["progress"], "In progress")

    def test_title_and_order_only_corrections_preserve_readiness_candidate_and_checks(self):
        for tid in ("alpha", "beta"):
            self.request(tid)
            self.command("record_progress", dict(task_id=tid, progress="Code ready"))
        self.request(paths=["src/one", "src/two"])
        self.command("add_criterion", dict(id="second", task_id="local", expected="Another actual result",
                                          source_refs=["owner"], kind="implementation"))
        self.correction("local", {"depends_on": ["alpha", "beta"]})
        self.claim()
        self.result()
        self.observation("completed")
        self.evidence()
        self.evidence("second-proof", "second")
        self.command("record_progress", dict(task_id="local", progress="Code ready"))
        before = self.store.read()
        self.source("rename-direction")
        self.correction("local", {"title": "Readable label only"}, source="rename-direction")
        self.correction("local", {"paths": ["src/two", "src/one"], "depends_on": ["beta", "alpha"],
                                   "criteria": ["second", "criterion-local"]}, kind="reorder")
        self.request("elsewhere")
        self.correction("goal-elsewhere", {"outcome": "An unrelated changed requirement"}, collection="goals")
        state = self.store.read()
        self.assertEqual(inputs(before, "local"), inputs(state, "local"))
        view = snapshot(state, now=NOW, task_ids=["local"])
        self.assertEqual(view["tasks"][0]["readiness"], "current")
        self.assertTrue(all(c["evidence"][0]["applicability"] == "current" for c in view["tasks"][0]["acceptance"]))
        self.assertEqual(view["attempts"][0]["applicability"], "current")
        self.assertEqual(view["next_action"]["kind"], "review")
        self.operation(action="integrate")
        self.observe_operation("succeeded")
        self.command("integrate_candidate", dict(attempt_id="attempt", operation_id="integration",
                                                  checks=["proof", "second-proof"]))

    def test_legacy_code_ready_without_binding_is_explicitly_unavailable(self):
        self.request()
        self.command("record_progress", dict(task_id="local", progress="Code ready"))
        legacy = self.store.read()
        del legacy["tasks"]["local"]["ready_inputs"]
        seal(legacy)
        self.store.path.write_bytes(encode(legacy))
        view = snapshot(StateStore(self.root).read(), now=NOW)
        self.assertEqual(view["tasks"][0]["progress"], "Code ready")
        self.assertEqual(view["tasks"][0]["readiness"], "unavailable")
        self.assertEqual(view["next_action"], {"kind": "reevaluate", "task_id": "local"})

    def test_scoped_context_keeps_constraint_and_decision_correction_meanings_and_sources(self):
        self.request()
        self.request("unrelated")
        for sid in ("initial", "revision", "retirement", "move", "answer-a", "answer-b", "supersession"):
            self.source(sid)
        for tid in ("local", "unrelated"):
            self.command("record_request", dict(goal=self.store.read()["goals"]["goal-" + tid], tasks=[], criteria=[],
                                                 constraints=[dict(id="bounded-" + tid, statement="Keep monitoring",
                                                                   applies_to=[tid], source_refs=["initial"],
                                                                   disposition="active")]))
        self.correction("bounded-local", {"statement": "Keep monitoring and alerts"},
                        collection="constraints", source="revision")
        self.correction("bounded-local", {"disposition": "retired"},
                        collection="constraints", kind="retire", source="retirement")
        self.correction("bounded-local", {"applies_to": ["unrelated"]},
                        collection="constraints", source="move")
        for did, answer, sid in (("old", "A", "answer-a"), ("new", "B", "answer-b")):
            self.command("record_question", dict(id=did, question="Choose behavior", alternatives=["A", "B"],
                                                 affected=["local"], source_refs=["owner"],
                                                 resolution=None, resolution_sources=[]))
            self.command("resolve_decision", dict(id=did, resolution=answer, source_refs=[sid]))
        self.command("supersede_decision", dict(id="old", replacement="new", source_refs=["supersession"]))
        state = self.store.read()
        view = snapshot(state, now=NOW, task_ids=["local"])
        self.assertEqual([c["id"] for c in view["constraints"]], ["bounded-local"])
        self.assertEqual(view["constraints"][0]["disposition"], "retired")
        self.assertEqual(view["tasks"][0]["constraints"], [])
        changes = [c for c in view["corrections"] if c["collection"] == "constraints"]
        self.assertEqual([c["kind"] for c in changes], ["revise", "retire", "revise"])
        self.assertEqual(changes[0]["before"]["statement"], "Keep monitoring")
        self.assertEqual(changes[0]["after"]["statement"], "Keep monitoring and alerts")
        self.assertEqual(changes[1]["before"]["disposition"], "active")
        self.assertEqual(changes[1]["after"]["disposition"], "retired")
        supersession = next(c for c in view["corrections"] if c["kind"] == "supersede")
        self.assertEqual(supersession["before"]["resolution"], "A")
        self.assertEqual(supersession["after"]["resolution"], "B")
        for sid in ("initial", "revision", "retirement", "move", "answer-a", "answer-b", "supersession"):
            self.assertIn(sid, view["sources"])
            self.assertNotIn("excerpt", view["sources"][sid])
        self.assertEqual(view["decisions"][0]["superseded_by"], "new")
        view["constraints"][0]["statement"] = "Changed returned context"
        self.assertEqual(state["constraints"]["bounded-local"]["statement"], "Keep monitoring and alerts")

    def test_renderer_deterministic_escaped_unknown_and_stale(self):
        self.request()
        self.correction("local", {"title": "<script>alert(1)</script>"})
        data = {"lifecycle": snapshot(self.store.read(), now=NOW), "title": "<owner>", "refresh": 30}
        before = copy.deepcopy(data)
        first = program_board.render(data)
        self.assertEqual(first, program_board.render(data))
        self.assertEqual(before, data)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", first)
        self.assertNotIn("<script>alert(1)", first)
        self.assertIn("unknown", first)
        failed = program_board.render(dict(data, refresh_error="<invalid store>"))
        self.assertIn("Refresh failed; STALE", failed)
        self.assertIn("refresh overdue", first)
        self.assertIn("Stopped watcher", program_board.render(dict(data, stopped=True)))

    def test_read_snapshot_does_not_mutate_canonical_inputs(self):
        self.request()
        self.source("extra")
        self.command("record_request", dict(goal=self.store.read()["goals"]["goal-local"], tasks=[], criteria=[],
                                             constraints=[dict(id="bounded", statement="Keep monitoring",
                                                               applies_to=["local"], source_refs=["extra"], disposition="active")]))
        state = self.store.read()
        before = copy.deepcopy(state)
        snapshot(state, now=NOW)
        self.assertEqual(before, state)

    def test_migration_ids_original_sources_dual_write_and_no_spec_fallback(self):
        root = self.root / "migration"
        root.mkdir()
        original = "| Task | Status |\n| --- | --- |\n| First | Code ready |\n| Second | |\n"
        (root / "tasks.md").write_text(original)
        (root / "SPEC.md").write_text("Obsolete")
        store = StateStore(root)
        state = store.initialize("migration", import_tasks=True)
        self.assertEqual(len(state["tasks"]), 2)
        self.assertEqual(state["sources"]["source-tasks-import"]["excerpt"], original)
        self.assertEqual(state["evidence"], {})
        self.assertEqual(state["attempts"], {})
        self.assertEqual(store.read(), state)
        (root / "tasks.md").write_text(task_projection(state))
        self.assertEqual(store.read(), state)
        (root / "tasks.md").write_text(original + "| Hidden write | Code ready |\n")
        with self.assertRaisesRegex(StateError, "DUAL_WRITE"):
            store.read()
        with self.assertRaisesRegex(StateError, "DUAL_WRITE"):
            program_board.build(root, "11111111-1111-1111-1111-111111111111")

    def test_moved_state_requires_reconciliation_not_ownership_release(self):
        self.request()
        self.claim()
        other = self.root / "other"
        (other / ".architrave").mkdir(parents=True)
        (other / ".architrave/state.yaml").write_bytes(self.store.path.read_bytes())
        moved = StateStore(other)
        state = moved.read()
        command = dict(project_id="project", command_id="move", expected_revision=state["revision"],
                       operation="set_phase", payload={"phase": "review"})
        with self.assertRaisesRegex(StateError, "LOCATION_RECONCILIATION"):
            moved.apply(command)
        command.update(operation="reconcile_location", payload={"reference": "host:handoff"})
        with self.assertRaisesRegex(StateError, "OWNERSHIP"):
            moved.apply(command)

    def test_explicit_handoff_can_record_finished_read_only_observations(self):
        self.request()
        self.claim(read_only=True)
        other = self.root / "other"
        (other / ".architrave").mkdir(parents=True)
        (other / ".architrave/state.yaml").write_bytes(self.store.path.read_bytes())
        moved = StateStore(other)
        state = moved.read()
        result = moved.apply(dict(project_id="project", command_id="handoff", expected_revision=state["revision"],
                                  operation="reconcile_location", payload={"reference": "host:verified-handoff",
                                  "read_only_observations": [dict(attempt_id="attempt", activity="completed",
                                                                  reference="host:completed-review", observed_at=NOW)]}))
        self.assertEqual(result["revision"], state["revision"] + 1)
        self.assertEqual(moved.read()["attempts"]["attempt"]["activity"], "completed")
        self.assertEqual(moved.read()["location"]["repository"], str(other.resolve()))

    def test_handoff_cannot_release_mutable_or_unknown_scope_by_observation(self):
        self.request()
        self.claim()
        before = self.store.path.read_bytes()
        payload = {"reference": "host:handoff",
                   "read_only_observations": [dict(attempt_id="attempt", activity="completed",
                                                   reference="host:claimed-terminal", observed_at=NOW)]}
        with self.assertRaisesRegex(StateError, "OWNERSHIP"):
            self.command("reconcile_location", payload)
        self.assertEqual(self.store.path.read_bytes(), before)
        older = self.store.read()
        older["attempts"]["attempt"].pop("scope")
        self.store._write(older)
        before = self.store.path.read_bytes()
        with self.assertRaisesRegex(StateError, "OWNERSHIP"):
            self.command("reconcile_location", payload)
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_read_only_handoff_does_not_clear_uncertain_external_operations(self):
        self.request()
        self.claim()
        self.operation()
        self.observation("completed")
        self.request("review")
        self.claim("review", "review-attempt", read_only=True)
        before = self.store.path.read_bytes()
        with self.assertRaisesRegex(StateError, "OWNERSHIP"):
            self.command("reconcile_location", {"reference": "host:handoff",
                "read_only_observations": [dict(attempt_id="review-attempt", activity="completed",
                                                reference="host:completed-review", observed_at=NOW)]})
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_macos_binding_uses_configured_name_not_network_node(self):
        reported_machine.cache_clear()
        self.addCleanup(reported_machine.cache_clear)
        completed = subprocess.CompletedProcess([], 0, stdout="configured-host\n", stderr="")
        with patch("lifecycle.sys.platform", "darwin"), patch("lifecycle.subprocess.run", return_value=completed) as command:
            with patch("lifecycle.platform.node", return_value="network-one"):
                first = reported_machine()
            with patch("lifecycle.platform.node", return_value="network-two"):
                self.assertEqual(reported_machine(), first)
            self.assertEqual(first, "macos:configured-host")
            self.assertEqual(command.call_count, 1)

    def test_macos_missing_host_identity_does_not_silently_fall_back(self):
        reported_machine.cache_clear()
        self.addCleanup(reported_machine.cache_clear)
        with patch("lifecycle.sys.platform", "darwin"), patch("lifecycle.subprocess.run", side_effect=OSError("unavailable")):
            with self.assertRaisesRegex(StateError, "HOST_IDENTITY_UNAVAILABLE"):
                reported_machine()

    def test_unavailable_source_holds_work_without_fabricated_answer(self):
        self.request()
        self.command("observe_source", {"id": "owner", "available": False})
        self.assertIn("source unavailable: owner", snapshot(self.store.read(), now=NOW)["tasks"][0]["holds"])

    def test_cli_round_trip_real_import_context_and_board(self):
        root = self.root / "cli"
        root.mkdir()
        (root / "tasks.md").write_text("| Task | Status |\n| --- | --- |\n| CLI behavior | |\n")
        command = [sys.executable, str(ROOT / "harness/architrave_cli.py"), "state", "--repo", str(root)]
        result = subprocess.run(command + ["init", "--project", "cli", "--import-tasks"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run(command + ["context", "--now", NOW], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["generated_at"], NOW)
        board = root / "board.html"
        result = subprocess.run([sys.executable, str(ROOT / "harness/program_board.py"), "--ledger", str(root),
                                 "--session", "11111111-1111-1111-1111-111111111111", "--output", str(board)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("CLI behavior", board.read_text())
        self.assertIn("revision 0", board.read_text())

    def test_cli_apply_enforces_frozen_scope_and_exposes_stale_readiness(self):
        self.request(paths=["src/original"])
        self.request("overlap", paths=["src/original/child.py"])
        command = [sys.executable, str(ROOT / "harness/architrave_cli.py"), "state", "--repo", str(self.root)]
        def apply(operation, payload):
            self.sequence += 1
            envelope = dict(project_id="project", command_id=f"cli-{self.sequence}",
                            expected_revision=self.store.read()["revision"], operation=operation, payload=payload)
            return subprocess.run(command + ["apply", "--command", "-"], input=encode(envelope).decode(),
                                  capture_output=True, text=True)
        result = apply("claim_task", dict(id="cli-attempt", task_id="local", worker="worker", host="session:cli"))
        self.assertEqual(result.returncode, 0, result.stderr)
        result = apply("apply_correction", dict(collection="tasks", target="local", changes={"paths": ["src/new"]},
                                                source_refs=["owner"], kind="revise"))
        self.assertEqual(result.returncode, 0, result.stderr)
        result = apply("claim_task", dict(id="overlap-attempt", task_id="overlap", worker="other", host="session:other"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("HELD", result.stderr)
        result = apply("observe_attempt", dict(attempt_id="cli-attempt", activity="completed", stop_acknowledged=False,
                                               reference="host:terminal", observed_at=NOW))
        self.assertEqual(result.returncode, 0, result.stderr)
        result = apply("record_progress", dict(task_id="local", progress="Code ready"))
        self.assertEqual(result.returncode, 0, result.stderr)
        result = apply("apply_correction", dict(collection="criteria", target="criterion-local",
                                                changes={"expected": "The corrected actual result"},
                                                source_refs=["owner"], kind="revise"))
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run(command + ["context", "--tasks", "local", "--now", NOW], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        view = json.loads(result.stdout)
        self.assertEqual(view["attempts"][0]["scope"]["paths"], ["src/original"])
        self.assertEqual(view["tasks"][0]["readiness"], "stale")
        self.assertEqual(view["next_action"], {"kind": "reevaluate", "task_id": "local"})

    def test_scoped_context_keeps_obligations_without_replaying_originals(self):
        self.request()
        self.request("unrelated")
        self.source("irrelevant", "document")
        state = self.store.read()
        view = snapshot(state, now=NOW, task_ids=["local"])
        self.assertEqual([g["id"] for g in view["goals"]], ["goal-local"])
        self.assertNotIn("irrelevant", view["sources"])
        self.assertNotIn("excerpt", view["sources"]["owner"])
        self.assertIn("inputs", view["tasks"][0]["acceptance"][0])
        self.assertIn("<script>", StateStore(self.root).read()["sources"]["owner"]["excerpt"])
        data = program_board.build(self.root, "11111111-1111-1111-1111-111111111111", task_ids=["local"])
        self.assertNotIn("Implement unrelated", program_board.render(data))

    def test_explicit_decision_supersession_keeps_original_and_current_answer(self):
        self.request()
        for did in ("old", "new"):
            self.command("record_question", dict(id=did, question="Choose behavior", alternatives=["A", "B"],
                                                 affected=["local"], source_refs=["owner"],
                                                 resolution=None, resolution_sources=[]))
        self.command("resolve_decision", dict(id="old", resolution="A", source_refs=["owner"]))
        self.command("resolve_decision", dict(id="new", resolution="B", source_refs=["owner"]))
        self.command("supersede_decision", dict(id="old", replacement="new", source_refs=["owner"]))
        state = self.store.read()
        self.assertEqual(state["decisions"]["old"]["resolution"], "A")
        self.assertEqual(state["decisions"]["old"]["superseded_by"], "new")
        self.assertEqual(snapshot(state, now=NOW)["next_action"]["task_id"], "local")

    def test_read_only_attempt_preserves_current_and_stale_written_readiness(self):
        self.request()
        self.request("dependent")
        self.correction("dependent", {"depends_on": ["local"]})
        self.command("record_progress", dict(task_id="local", progress="Code ready"))
        ready_inputs = self.store.read()["tasks"]["local"]["ready_inputs"]
        self.claim(read_only=True)
        view = snapshot(self.store.read(), now=NOW)
        self.assertEqual(view["tasks"][0]["readiness"], "current")
        self.assertFalse(view["tasks"][1]["holds"])
        self.observation("completed")
        view = snapshot(self.store.read(), now=NOW)
        self.assertEqual(view["tasks"][0]["readiness"], "current")
        self.assertEqual(view["next_action"]["task_id"], "dependent")
        self.correction("criterion-local", {"expected": "Changed required behavior"}, collection="criteria")
        self.claim(aid="stale-review", read_only=True)
        self.observation("completed", aid="stale-review")
        view = snapshot(self.store.read(), now=NOW)
        self.assertEqual(self.store.read()["tasks"]["local"]["ready_inputs"], ready_inputs)
        self.assertEqual(view["tasks"][0]["readiness"], "stale")
        self.assertEqual(view["next_action"], {"kind": "reevaluate", "task_id": "local"})

    def test_generated_compatibility_view_survives_canonical_updates(self):
        root = self.root / "projection"
        root.mkdir()
        (root / "tasks.md").write_text("| Task | Status |\n| --- | --- |\n| First | |\n")
        store = StateStore(root)
        original = store.initialize("projection", import_tasks=True)
        (root / "tasks.md").write_text(task_projection(original))
        store.apply(dict(project_id="projection", command_id="progress", expected_revision=0,
                         operation="record_progress", payload={"task_id": next(iter(original["tasks"])),
                                                               "progress": "In progress"}))
        self.assertEqual(store.read()["revision"], 1)

    def test_imported_in_progress_keeps_scoped_unknown_ownership_hold(self):
        root = self.root / "ownership"
        root.mkdir()
        (root / "tasks.md").write_text("| Task | Status |\n| --- | --- |\n| Live? | In progress |\n| New | |\n")
        state = StateStore(root).initialize("ownership", import_tasks=True)
        view = snapshot(state, now=NOW)
        self.assertIn("migration conflict", view["tasks"][0]["holds"][0])
        self.assertFalse(view["tasks"][1]["holds"])

    def test_legacy_import_preserves_conflict_and_rejects_competing_run_mutations(self):
        repo = self.root / "legacy"
        repo.mkdir()
        for args in (("init", "-q"), ("config", "user.email", "test@example.invalid"),
                     ("config", "user.name", "Test"), ("commit", "--allow-empty", "-qm", "baseline")):
            subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
        runtime = RunStore(repo)
        legacy = runtime.create(goal="Legacy", outcome="Legacy outcome", criteria=[])
        store = StateStore(repo)
        state = store.initialize("legacy", legacy_runs=[f".architrave/runs/{legacy['runId']}"])
        self.assertEqual(state["imports"][0]["state"]["runId"], legacy["runId"])
        self.assertIsNone(state["conflicts"][0]["resolution"])
        with self.assertRaisesRegex(RuntimeFailure, "compete"):
            runtime._transaction(legacy["runId"], lambda s: None, event_type="test.no-dual-write")
        with self.assertRaisesRegex(RuntimeFailure, "competing"):
            runtime.create(goal="New competing run", outcome="no", criteria=[])

    def test_malformed_commands_are_explicit_and_never_replace_snapshot(self):
        before = self.store.path.read_bytes()
        for op, payload in (("set_phase", {"phase": []}), ("record_request", {"goal": [],
                            "tasks": [], "criteria": [], "constraints": []}),
                            ("record_progress", {"task_id": [], "progress": "Code ready"})):
            with self.subTest(op=op), self.assertRaises(StateError):
                self.command(op, payload)
            self.assertEqual(before, self.store.path.read_bytes())

    def test_real_watcher_refresh_failure_preserves_revision_with_error(self):
        self.request()
        output = self.root / "watch.html"
        process = subprocess.Popen([sys.executable, str(ROOT / "harness/program_board.py"), "--ledger", str(self.root),
                                    "--session", "11111111-1111-1111-1111-111111111111",
                                    "--output", str(output), "--watch", "30"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertIn("program-board:", process.stdout.readline())
            self.assertIsNone(process.poll(), "lifecycle watcher must not exit merely because session logs are absent")
            revision = self.store.read()["revision"]
            self.store.path.write_text("invalid YAML")
            deadline = time.monotonic() + 40
            while time.monotonic() < deadline and "Refresh failed; STALE" not in output.read_text():
                time.sleep(.2)
            page = output.read_text()
            self.assertIn("Refresh failed; STALE", page)
            self.assertIn(f"revision {revision}", page)
        finally:
            process.terminate()
            process.communicate(timeout=10)
        self.assertIn("Stopped watcher", output.read_text())


if __name__ == "__main__":
    unittest.main()
