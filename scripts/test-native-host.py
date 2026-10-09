#!/usr/bin/env python3
"""Installed adoption and host-native lifecycle regressions; live smoke is separate."""

from __future__ import annotations

import json
import hashlib
import datetime as dt
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from architrave_runtime import RunStore, RuntimeFailure, effective_work_budget, feasibility_status, primary_failures, primary_criterion_status, state_summary
from worker_adapters import workspace_fingerprint

_fixture_add_task = RunStore.add_task
RunStore.add_task = lambda self, run_id, task, actor="coordinator": _fixture_add_task(
    self, run_id, {"pushback": "KEEP:test fixture", **task}, actor)
from worker_adapters import command_for, execute_work_packet
from workspaces import WorkspaceManager
from native_host import routing_observation


class NativeHostTests(unittest.TestCase):
    def test_host_visibility_is_unknown_not_idle_and_stale_source_is_not_current_stall(self):
        run_id, task_id = self.task("shell")
        summary = state_summary(self.store.load(run_id))
        self.assertEqual([], summary["activeWorkers"])
        self.assertEqual("UNKNOWN", summary["hostWorkers"]["visibility"])
        self.assertFalse(summary["hostWorkers"]["idleProven"])
        self.assertEqual("UNKNOWN", summary["runtime"]["sessionLoadedInstructions"])
        self.assertIn("fingerprint", summary["runtime"])
        (self.repo / "new.txt").write_text("new source", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "source changed"], cwd=self.repo, check=True, capture_output=True)
        summary = state_summary(self.store.load(run_id))
        self.assertTrue(summary["reconciliation"]["required"])
        self.assertFalse(summary["reconciliation"]["automaticRepair"])
        self.assertEqual("UNTESTED", summary["acceptance"]["FIX"])

    def test_adoption_status_is_read_only_and_installed_is_not_loaded(self):
        run, task = self.task("shell")
        before = (self.store.run_dir(run) / "run.json").read_bytes()
        result = subprocess.run([sys.executable, str(ROOT / "tools/install_update.py"), "adoption-status", str(self.repo)],
                                 capture_output=True, text=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report["mutationPerformed"])
        self.assertIn("UNKNOWN", report["sessionLoadedInstructions"])
        self.assertIsNone(report["adoptedKitVersion"])
        self.assertEqual(before, (self.store.run_dir(run) / "run.json").read_bytes())

    def test_owner_message_bound_keeps_machine_evidence_out_of_owner_wall(self):
        from architrave_runtime import owner_message_lint
        self.assertIsNotNone(owner_message_lint("evidence " * 400))
        self.assertIsNone(owner_message_lint("Objective: actual product flow. Blocker: unknown mechanism. Next: one parity probe."))

    def product_task(self):
        run = self.store.create(
            run_id="milestone", goal="Actual product progress", outcome="Product flow works",
            autonomy_scope="approved-program", primary_criterion="FLOW", primary_paths=["README.md"],
            criteria=[{"id": "FLOW", "description": "Observed product flow", "scope": "product",
                       "risk": "R1", "verificationType": "reality", "surface": "web", "blocking": True}])
        self.store.add_task("milestone", {"id": "flow", "objective": "Verify actual product",
                                        "acceptanceCriteria": ["FLOW"], "risk": "R1", "workerProfile": "shell"})
        return "milestone", "flow"

    def product_gate(self, run, task, suffix):
        state = self.store.load(run)
        path = self.store.run_dir(run) / f"web-{suffix}.json"
        receipt = {
            "surface": "web", "status": "pass", "failed": [],
            "binding": {"runId": run, "taskId": task, "objectiveVersion": state["objective"]["version"],
                        "criteria": ["FLOW"]},
            "source": {"commit": state["baseline"]["commit"], "sha256": workspace_fingerprint(self.repo, include_ignored=False)},
            "results": [{"name": "runtime.health", "status": "pass"}, {"name": "web.e2e", "status": "pass"}],
        }
        path.write_text(json.dumps(receipt), encoding="utf-8")
        self.store._record_legibility_result(run, artifact_id=f"product-{suffix}", kind="web-legibility",
            path=path.relative_to(self.store.repository).as_posix(), evidence_refs=[f"task:{task}"])
        self.store.record_gate(run, gate_id=f"gate-{suffix}", task_id=task, gate_type="reality", status="PASS",
                               evidence_refs=[f"artifact:product-{suffix}"], criteria=["FLOW"])
        return f"gate:gate-{suffix}"

    def test_exact_milestone_does_not_complete_criterion_or_recount_identical_observation(self):
        run, task = self.product_task()
        gate = self.product_gate(run, task, "first")
        state = self.store.advance_milestone(run, task, criterion_id="FLOW", milestone="Observed intermediate flow", gate_ref=gate)
        self.assertEqual("UNTESTED", state["acceptanceCriteria"][0]["status"])
        self.assertEqual(1, primary_criterion_status(state, self.store.events(run), self.repo)["verifiedMilestones"])
        duplicate = self.product_gate(run, task, "second")
        with self.assertRaises(RuntimeFailure) as error:
            self.store.advance_milestone(run, task, criterion_id="FLOW", milestone="New label same evidence", gate_ref=duplicate)
        self.assertEqual("MILESTONE_REPLAY", error.exception.code)
        (self.repo / "README.md").write_text("stale product source", encoding="utf-8")
        with self.assertRaises(RuntimeFailure) as error:
            self.store.advance_milestone(run, task, criterion_id="FLOW", milestone="Stale flow", gate_ref=gate)
        self.assertEqual("MILESTONE_SOURCE_STALE", error.exception.code)
        fresh_same_result = self.product_gate(run, task, "source-churn")
        with self.assertRaises(RuntimeFailure) as error:
            self.store.advance_milestone(run, task, criterion_id="FLOW", milestone="Same observed flow after patch", gate_ref=fresh_same_result)
        self.assertEqual("MILESTONE_REPLAY", error.exception.code)

    def test_control_gate_cannot_become_product_milestone(self):
        run, task = self.product_task()
        (self.repo / "architrave.config.json").write_text(json.dumps({"kind": "knowledge","test":"echo control","build":"echo control"}))
        self.store.start_task(run, task, worker_id="direct")
        self.store.finish_worker(run, task, worker_id="direct", status="FINISHED")
        gate = self.store.execute_gate(run, task)
        with self.assertRaises(RuntimeFailure) as error:
            self.store.advance_milestone(run, task, criterion_id="FLOW", milestone="control tests", gate_ref=gate["gateRef"])
        self.assertEqual("MILESTONE_BINDING", error.exception.code)

    def test_path_touch_activity_cannot_reset_product_milestone_and_live_bound_work_is_not_stalled(self):
        run, task = self.product_task()
        for number in range(3):
            (self.repo / "README.md").write_text(f"compatibility patch {number}", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=self.repo, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-qm", f"patch {number}"], cwd=self.repo, check=True, capture_output=True)
        state = self.store.load(run)
        summary = state_summary(state)
        self.assertEqual("STALE_SOURCE", summary["primaryCriterion"]["freshness"])
        self.assertNotIn("escalation", summary)
        self.store.resume(run, accept_commit=True)
        state = self.store.load(run)
        primary = primary_criterion_status(state, self.store.events(run), self.repo)
        self.assertEqual(0, primary["verifiedMilestones"])
        self.assertTrue(primary["milestoneReviewNeeded"])
        self.assertFalse(primary["pathTouchIsProductEvidence"])
        self.store.start_task(run, task, worker_id="exploring-bounded")
        state = self.store.load(run)
        self.assertFalse(primary_criterion_status(state, self.store.events(run), self.repo)["milestoneReviewNeeded"])

    def test_owner_path_correction_is_exact_and_preserves_auth_holds_budget_and_source_history(self):
        run, task = self.product_task()
        (self.repo / "Swift").mkdir()
        (self.repo / "Swift" / "flow.swift").write_text("source", encoding="utf-8")
        self.store.wait_external(run, checkpoint_id="auth", task_id=task, checkpoint_type="AUTH_REQUIRED",
                                  principal="owner", provider="product", reason="Human sign in still needed")
        before = self.store.load(run)
        _, challenge = self.store.request_focus_correction(run, task, paths=["Swift"], principal="owner",
                                                        actor="human:owner", checkpoint_id="correct-path")
        after = self.store.apply_focus_correction(run, "correct-path", challenge=challenge, actor="human:owner")
        self.assertEqual(["Swift"], after["focus"]["primaryCriterion"]["paths"])
        for key in ("baseline", "acceptanceCriteria", "policy", "workers"):
            self.assertEqual(before[key], after[key])
        self.assertEqual("PENDING", after["externalCheckpoints"][0]["status"])
        self.assertEqual(before["tasks"], after["tasks"])
        with self.assertRaises(RuntimeFailure):
            self.store.apply_focus_correction(run, "correct-path", challenge=challenge, actor="human:owner")

    def test_owner_path_correction_cannot_cross_revision_source_or_principal(self):
        run, task = self.product_task()
        _, challenge = self.store.request_focus_correction(run, task, paths=["README.md"], principal="owner",
                                                        actor="human:owner", checkpoint_id="correct-path")
        with self.assertRaises(RuntimeFailure):
            self.store.apply_focus_correction(run, "correct-path", challenge=challenge, actor="human:other")
        self.store.policy_check(run, "repository", "edit")
        with self.assertRaises(RuntimeFailure):
            self.store.apply_focus_correction(run, "correct-path", challenge=challenge, actor="human:owner")
        self.assertEqual(["README.md"], self.store.load(run)["focus"]["primaryCriterion"]["paths"])

    def test_focus_correction_rejects_external_link_or_reparse_ancestor(self):
        run, task = self.product_task()
        outside = Path(self.temp.name) / "outside-repo"
        outside.mkdir()
        link = self.repo / "linked"
        if sys.platform == "win32":
            created = subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True)
            if created.returncode:
                self.skipTest("Windows junction creation unavailable")
        else:
            link.symlink_to(outside, target_is_directory=True)
        try:
            with self.assertRaises(RuntimeFailure) as error:
                self.store.request_focus_correction(run, task, paths=["linked"], principal="owner",
                                                    actor="human:owner", checkpoint_id="invalid-link")
            self.assertEqual("FOCUS_CORRECTION_PATH", error.exception.code)
        finally:
            if sys.platform == "win32":
                link.rmdir()
            else:
                link.unlink()

    def test_frozen_product_gate_rejects_objective_change_between_observation_and_registration(self):
        run, task = self.product_task()
        gate = self.product_gate(run, task, "before-correction")
        _, challenge = self.store.wait_external(run, checkpoint_id="change", task_id=task,
            checkpoint_type="HUMAN_JUDGMENT_REQUIRED", principal="owner", provider="owner",
            reason="Explicit owner objective change")
        self.store.replace_objective(run, outcome="A new objective using the same surface", criteria=[{
            "id": "FLOW", "description": "Different actual outcome", "scope": "product",
            "risk": "R1", "verificationType": "reality", "surface": "web", "blocking": True}],
            correction="New authorized strategy.", next_cheapest_test="Observe new behavior.",
            checkpoint_id="change", challenge=challenge, actor="human:owner")
        with self.assertRaises(RuntimeFailure) as error:
            self.store.record_gate(run, gate_id="new-objective-gate", task_id=task, gate_type="reality",
                status="PASS", evidence_refs=["artifact:product-before-correction"], criteria=["FLOW"])
        self.assertEqual("EVIDENCE_SOURCE_STALE", error.exception.code)
        with self.assertRaises(RuntimeFailure):
            self.store.set_criterion(run, "FLOW", "PASS", [gate])
        self.assertEqual("UNTESTED", self.store.load(run)["acceptanceCriteria"][0]["status"])

    def feasibility(self, run_id, task_id, **overrides):
        values = {
            "trigger": "user", "decision": "BOUNDED_GO",
            "window": {"timeoutSeconds": 120, "maxTurns": 8, "maxOutputBytes": 2000},
            "rationale": "A cheap discriminating check can resolve the remaining uncertainty.",
            "next_step": "Run the exact existing acceptance test.",
            "revisit": "Revisit only after new discriminating evidence.",
            "uncertainty": "Runtime hypothesis is unproven.",
            "product_delta": "No product outcome has yet been observed.",
            "blocker": "The failing mechanism is not yet discriminated.",
        }
        return self.store.record_feasibility(run_id, task_id, **{**values, **overrides})

    def test_feasibility_small_complex_and_explicit_owner_windows(self):
        run_id, task_id = self.task("shell")
        state = self.feasibility(run_id, task_id)
        small = state["tasks"][0]["feasibility"]["window"]
        self.assertLessEqual(small["timeoutSeconds"], 120)
        self.store.add_task(run_id, {"id": "complex", "objective": "Trace a deeper independent dependency",
                                   "workerProfile": "shell", "acceptanceCriteria": ["FIX"], "risk": "R2",
                                   "lane": "second", "workPacket": {"budget": {
                                       "timeoutSeconds": 1800, "maxTurns": 30, "maxOutputBytes": 8000}}})
        state = self.feasibility(run_id, "complex",
                                 window={"timeoutSeconds": 900, "maxTurns": 20, "maxOutputBytes": 6000},
                                 rationale="Uncertain dependency chain needs one bounded longer discriminating test.")
        complex_window = state["tasks"][1]["feasibility"]["window"]
        self.assertGreater(complex_window["timeoutSeconds"], small["timeoutSeconds"])
        self.store.add_task(run_id, {"id": "owner-capped", "objective": "Evaluate explicit owner ceiling",
                                   "workerProfile": "shell", "acceptanceCriteria": ["FIX"], "risk": "R1"})
        (self.repo / "README.md").write_text("new scoped evidence", encoding="utf-8")
        self.store.add_task(run_id, {"id": "capped-independent", "objective": "Owner ceiling",
                                   "workerProfile": "shell", "acceptanceCriteria": ["FIX"], "risk": "R1",
                                   "workPacket": {"contextBundle": ["README.md"]}})
        state = self.feasibility(run_id, "capped-independent",
                                 owner_ceiling={"timeoutSeconds": 45, "maxTurns": 3, "maxOutputBytes": 1000})
        capped = state["tasks"][-1]["feasibility"]["window"]
        self.assertLessEqual(capped["timeoutSeconds"], 45)
        self.assertEqual(3, capped["maxTurns"])
        self.assertEqual(1000, capped["maxOutputBytes"])

    def test_feasibility_global_owner_deadline_and_task_budget_precedence(self):
        run_id, task_id = self.task("shell")
        (self.repo / "architrave.config.json").write_text(json.dumps({
            "evaluation": {"budget": {"maxMinutes": 1, "maxTurns": 8}},
        }), encoding="utf-8")
        deadline = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=20)).isoformat()
        state = self.feasibility(run_id, task_id,
                                 owner_ceiling={"timeoutSeconds": 50, "maxTurns": 20},
                                 owner_deadline=deadline,
                                 window={"timeoutSeconds": 10000, "maxTurns": 200, "maxOutputBytes": 100000})
        chosen = state["tasks"][0]["feasibility"]["window"]
        self.assertLessEqual(chosen["timeoutSeconds"], 20)
        self.assertLessEqual(chosen["maxTurns"], 6)
        self.assertLessEqual(chosen["maxOutputBytes"], 4096)
        task_budget = effective_work_budget(state, state["tasks"][0])
        self.assertLessEqual(task_budget["timeoutSeconds"], chosen["timeoutSeconds"])

    def test_feasibility_no_fixed_duration_cli_and_unknown_signals(self):
        run_id, task_id = self.task("shell")
        result = subprocess.run([
            sys.executable, str(ROOT / "harness/architrave_runtime.py"), "--repo", str(self.repo),
            "feasibility-record", run_id, task_id, "--trigger", "user", "--decision", "CONTINUE",
            "--seconds", "25", "--turns", "4", "--output-bytes", "800",
            "--rationale", "A small known-path test needs only this finite window.",
            "--next-step", "Run focused acceptance.", "--revisit", "New observed mechanism.",
            "--uncertainty", "Runtime behavior remains unproven.", "--product-delta", "Not yet observed.",
            "--blocker", "Mechanism not established.",
        ], capture_output=True, text=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stderr)
        state = self.store.load(run_id)
        reset = state["tasks"][0]["feasibility"]
        self.assertLessEqual(reset["window"]["timeoutSeconds"], 25)
        self.assertIsNone(reset["snapshot"]["availableBudget"]["hostCredits"])
        self.assertIsNone(reset["snapshot"]["availableBudget"]["taskTurnsObserved"])
        self.assertIsNone(reset["snapshot"]["availableBudget"]["globalSeconds"])
        self.assertEqual([], state["workers"])
        schema = json.loads((ROOT / "harness/schemas/run-v2.schema.json").read_text())
        properties = schema["definitions"]["task"]["properties"]["feasibility"]
        self.assertFalse(set(reset) - set(properties["properties"]))
        self.assertFalse(set(properties["required"]) - set(reset))
        cto = (ROOT / "skills/architrave-cto/SKILL.md").read_text()
        self.assertNotIn("5400", cto)
        self.assertIn("Neither is mandatory", cto)
        self.assertIn("Quiet parent activity", cto)

    def test_feasibility_counts_spent_clock_and_budget_exhaustion(self):
        run_id, task_id = self.task("shell")
        self.store.start_task(run_id, task_id, worker_id="initial")
        self.store.finish_worker(run_id, task_id, worker_id="initial", status="FINISHED")
        future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=700)

        class Clock(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return future if tz else future.replace(tzinfo=None)

        with mock.patch("architrave_runtime.dt.datetime", Clock):
            state = self.feasibility(run_id, task_id)
        reset = state["tasks"][0]["feasibility"]
        self.assertEqual("PARK", reset["decision"])
        self.assertTrue(reset["partial"])
        self.assertEqual(0, reset["window"]["timeoutSeconds"])

    def test_feasibility_global_dispatch_budget_blocks_new_work(self):
        run_id, task_id = self.task("shell")
        (self.repo / "architrave.config.json").write_text(
            json.dumps({"evaluation": {"budget": {"maxDispatches": 1}}}), encoding="utf-8")
        self.store.start_task(run_id, task_id, worker_id="first")
        self.store.finish_worker(run_id, task_id, worker_id="first", status="FINISHED")
        state = self.feasibility(run_id, task_id, trigger="budget")
        self.assertEqual("PARK", state["tasks"][0]["feasibility"]["decision"])
        self.assertTrue(feasibility_status(state, state["tasks"][0])["partial"])

    def test_feasibility_park_pauses_only_implicated_lane_and_preserves_uncertain_effect(self):
        state = self.store.create(
            run_id="uncertain", goal="Preserve scoped recovery", outcome="No side-effect replay",
            autonomy_scope="approved-program", policy_allow=[{"scope": "sandbox", "operations": ["write"]}],
            criteria=[{"id": "FIX", "description": "Recovery remains safe", "scope": "fixture",
                       "risk": "R1", "verificationType": "deterministic", "blocking": True}],
        )
        for name, extra in (("effect", {"sideEffect": {"operation": "write", "target": "sandbox"}}),
                            ("independent", {"lane": "second"})):
            self.store.add_task("uncertain", {"id": name, "objective": name, "workerProfile": "shell",
                                             "risk": "R1", "acceptanceCriteria": ["FIX"], **extra})
        self.store.start_task("uncertain", "effect", worker_id="effect-owner")
        self.store.fail_task("uncertain", "effect", "external result unknown")
        before = self.store.load("uncertain")
        after = self.feasibility("uncertain", "effect", decision="PARK")
        self.assertEqual(before["tasks"][0]["sideEffect"], after["tasks"][0]["sideEffect"])
        self.assertEqual("UNCERTAIN", after["tasks"][0]["sideEffect"]["state"])
        self.assertEqual(["independent"], [task["id"] for task in self.store.ready_tasks("uncertain")])
        self.store.start_task("uncertain", "independent", worker_id="unrelated")
        with self.assertRaises(RuntimeFailure):
            self.store.start_task("uncertain", "effect", worker_id="must-not-replay")

    def test_feasibility_unchanged_evidence_no_clock_reset_and_expiry_is_partial(self):
        run_id, task_id = self.task("shell")
        self.store.add_task(run_id, {"id": "scoped", "objective": "Read scoped evidence",
                                   "workerProfile": "shell", "acceptanceCriteria": ["FIX"], "risk": "R1",
                                   "workPacket": {"contextBundle": ["README.md"]}})
        first = self.feasibility(run_id, "scoped")["tasks"][1]["feasibility"]
        with self.assertRaises(RuntimeFailure) as error:
            self.feasibility(run_id, "scoped", rationale="Longer window would be convenient.")
        self.assertEqual("FEASIBILITY_UNCHANGED", error.exception.code)
        (self.repo / "README.md").write_text("new real mechanism evidence", encoding="utf-8")
        second = self.feasibility(run_id, "scoped",
                                  window={"timeoutSeconds": 1000, "maxTurns": 20, "maxOutputBytes": 99999})["tasks"][1]["feasibility"]
        self.assertEqual(first["startedAt"], second["startedAt"])
        self.assertEqual(first["startSequence"], second["startSequence"])
        self.assertLessEqual(second["expiresAt"], first["expiresAt"])
        future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10)

        class Clock(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return future if tz else future.replace(tzinfo=None)

        with mock.patch("architrave_runtime.dt.datetime", Clock):
            state = self.store.load(run_id)
            status = feasibility_status(state, state["tasks"][1])
            self.assertTrue(status["partial"])
            self.assertEqual("PARK", status["decision"])
            self.assertEqual("Revisit only after new discriminating evidence.", status["revisit"])
            with self.assertRaises(RuntimeFailure):
                self.store.start_task(run_id, "scoped", worker_id="expired")
            with self.assertRaises(RuntimeFailure) as error:
                self.feasibility(run_id, "scoped")
            self.assertEqual("FEASIBILITY_EXPIRED", error.exception.code)

    def test_feasibility_requires_actual_pause_and_preserves_holds_and_candidates(self):
        run_id, task_id = self.task()
        ticket = self.store.begin_native_worker(run_id, task_id, host_owner="host")
        self.store.bind_native_owner(ticket, "real-owner")
        with self.assertRaises(RuntimeFailure) as error:
            self.feasibility(run_id, task_id)
        self.assertEqual("HOST_PAUSE_REQUIRED", error.exception.code)
        self.store.accept_native_candidate(ticket, host_task_id="real-owner", host_status="completed", text="retained candidate")
        self.store.wait_external(run_id, checkpoint_id="auth", task_id=task_id,
                                 checkpoint_type="AUTH_REQUIRED", principal="owner", provider="product",
                                 reason="Human sign-in is still required")
        before = self.store.load(run_id)
        after = self.feasibility(run_id, task_id, decision="PARK")
        for key in ("artifacts", "workers", "policy", "externalCheckpoints"):
            self.assertEqual(before[key], after[key])
        self.assertEqual(before["tasks"][0]["workspace"], after["tasks"][0]["workspace"])
        self.assertEqual(before["tasks"][0]["sideEffect"], after["tasks"][0]["sideEffect"])
        self.assertEqual(1, after["tasks"][0]["attempts"])
        self.assertEqual(0, len(list(self.store.run_dir(run_id).glob("*.md"))))

    def test_feasibility_does_not_force_reviewer_poc_or_bypass_loop_stop(self):
        run_id, task_id = self.task("native")
        with self.assertRaises(RuntimeFailure) as error:
            self.feasibility(run_id, task_id, trigger="stall")
        self.assertEqual("FEASIBILITY_TRIGGER_UNPROVEN", error.exception.code)
        first = self.feasibility(run_id, task_id)
        self.assertEqual(1, len(first["tasks"]))
        self.assertEqual([], first["workers"])
        self.assertEqual([], first["artifacts"])
        ticket = self.store.begin_native_worker(run_id, task_id, host_owner="host")
        self.store.bind_native_owner(ticket, "first")
        self.store.accept_native_candidate(ticket, host_task_id="first", host_status="cancelled", text="same failure",
                                          host_observation={"turnsObserved": 1})
        self.store.recover_workers(run_id, task_id=task_id)
        ticket = self.store.begin_native_worker(run_id, task_id, host_owner="host",
                                              retry_hypothesis="Try exact new discriminating check")
        self.store.bind_native_owner(ticket, "second")
        self.store.accept_native_candidate(ticket, host_task_id="second", host_status="cancelled", text="same failure",
                                          host_observation={"turnsObserved": 1})
        self.feasibility(run_id, task_id, trigger="repeated-failure", decision="PARK")
        with self.assertRaises(RuntimeFailure):
            self.store.recover_workers(run_id, task_id=task_id)

    def test_feasibility_cumulative_host_turns_and_output_honor_owner_ceiling(self):
        run_id, task_id = self.task(budget={"timeoutSeconds": 600, "maxTurns": 30, "maxOutputBytes": 4096})
        self.store.add_task(run_id, {"id": "second", "objective": "Sequential discriminating test",
                                   "workerProfile": "native", "risk": "R0", "acceptanceCriteria": ["FIX"],
                                   "workPacket": {"budget": {"timeoutSeconds": 600, "maxTurns": 30, "maxOutputBytes": 4096}}})
        self.feasibility(run_id, task_id, window={"timeoutSeconds": 120, "maxTurns": 20, "maxOutputBytes": 800},
                         owner_ceiling={"maxTurns": 20, "maxOutputBytes": 800})
        ticket = self.store.begin_native_worker(run_id, task_id, host_owner="host")
        self.store.bind_native_owner(ticket, "first")
        with self.assertRaises(RuntimeFailure) as error:
            self.store.begin_native_worker(run_id, "second", host_owner="host")
        self.assertEqual("FEASIBILITY_LANE_BUSY", error.exception.code)
        candidate = self.store.accept_native_candidate(ticket, host_task_id="first", host_status="completed",
                                                       text="x" * 100, host_observation={"turnsObserved": 17})
        state = self.store.load(run_id)
        budget = effective_work_budget(state, state["tasks"][1])
        self.assertEqual(3, budget["maxTurns"])
        self.assertEqual(700, budget["maxOutputBytes"])
        ticket = self.store.begin_native_worker(run_id, "second", host_owner="host")
        self.store.bind_native_owner(ticket, "second")
        candidate = self.store.accept_native_candidate(ticket, host_task_id="second", host_status="completed",
                                                       text="\u2603" * 2000, host_observation={"turnsObserved": 3})
        self.assertLessEqual(len(candidate["summary"].encode()), 700)
        self.assertTrue(candidate["truncated"])
        state = self.store.load(run_id)
        self.assertTrue(feasibility_status(state, state["tasks"][1])["partial"])
        with self.assertRaises(RuntimeFailure):
            effective_work_budget(state, state["tasks"][1])

    def test_feasibility_one_host_turn_is_not_spent_by_metadata(self):
        run_id, task_id = self.task()
        self.feasibility(run_id, task_id, window={"timeoutSeconds": 120, "maxTurns": 1, "maxOutputBytes": 800})
        ticket = self.store.begin_native_worker(run_id, task_id, host_owner="host")
        self.store.bind_native_owner(ticket, "first")
        state = self.store.load(run_id)
        self.assertFalse(feasibility_status(state, state["tasks"][0])["expired"])
        self.assertEqual(1, ticket.snapshot["budget"]["maxTurns"])
        self.store.accept_native_candidate(ticket, host_task_id="first", host_status="completed", text="candidate",
                                          host_observation={"turnsObserved": 1})
        state = self.store.load(run_id)
        self.assertTrue(feasibility_status(state, state["tasks"][0])["expired"])

    def test_feasibility_native_ticket_uses_atomic_admission_budget_after_interleaving(self):
        run_id, first_id = self.task(budget={"timeoutSeconds": 600, "maxTurns": 30, "maxOutputBytes": 4096})
        self.store.add_task(run_id, {"id": "second", "objective": "Next discriminating test",
                                   "workerProfile": "native", "risk": "R0", "acceptanceCriteria": ["FIX"],
                                   "workPacket": {"budget": {"timeoutSeconds": 600, "maxTurns": 30, "maxOutputBytes": 4096}}})
        self.feasibility(run_id, first_id, window={"timeoutSeconds": 120, "maxTurns": 20, "maxOutputBytes": 800},
                         owner_ceiling={"maxTurns": 20, "maxOutputBytes": 800})
        start = self.store.start_task
        interleaved = False

        def before_admission(run, task_id, **kwargs):
            nonlocal interleaved
            if task_id == "second" and not interleaved:
                interleaved = True
                first = self.store.begin_native_worker(run, first_id, host_owner="host")
                self.store.bind_native_owner(first, "first")
                self.store.accept_native_candidate(first, host_task_id="first", host_status="completed",
                                                  text="x" * 100, host_observation={"turnsObserved": 17})
            return start(run, task_id, **kwargs)

        with mock.patch.object(self.store, "start_task", side_effect=before_admission):
            ticket = self.store.begin_native_worker(run_id, "second", host_owner="host")
        self.assertEqual(3, ticket.snapshot["budget"]["maxTurns"])
        self.assertEqual(700, ticket.snapshot["budget"]["maxOutputBytes"])
        state = self.store.load(run_id)
        worker = next(item for item in state["workers"] if item["id"] == ticket.binding["workerId"])
        self.assertEqual(ticket.snapshot["budget"], worker["admittedBudget"])
        self.store.bind_native_owner(ticket, "second")
        candidate = self.store.accept_native_candidate(ticket, host_task_id="second", host_status="completed",
                                                       text="y" * 2000, host_observation={"turnsObserved": 3})
        self.assertEqual(700, len(candidate["summary"].encode()))
        self.assertTrue(candidate["truncated"])

    def test_feasibility_unreported_finished_turns_are_unknown_not_zero(self):
        run_id, task_id = self.task()
        self.feasibility(run_id, task_id)
        ticket = self.store.begin_native_worker(run_id, task_id, host_owner="host")
        self.store.bind_native_owner(ticket, "first")
        self.store.accept_native_candidate(ticket, host_task_id="first", host_status="completed", text="candidate")
        state = self.store.load(run_id)
        status = feasibility_status(state, state["tasks"][0])
        self.assertIsNone(status["remainingHostTurns"])
        self.assertTrue(status["hostTurnsUnknown"])
        with self.assertRaises(RuntimeFailure) as error:
            effective_work_budget(state, state["tasks"][0])
        self.assertEqual("FEASIBILITY_BUDGET_UNKNOWN", error.exception.code)

    def test_feasibility_historical_objective_does_not_break_status(self):
        run_id, task_id = self.task("shell")
        self.feasibility(run_id, task_id, decision="PARK")
        _, challenge = self.store.wait_external(
            run_id, checkpoint_id="owner-correction", task_id=task_id,
            checkpoint_type="HUMAN_JUDGMENT_REQUIRED", principal="owner", provider="owner",
            reason="Owner explicitly changed the objective")
        state = self.store.replace_objective(
            run_id, outcome="A different authorized objective", criteria=[{
                "id": "NEW", "description": "New acceptance", "scope": "fixture",
                "risk": "R1", "verificationType": "deterministic", "blocking": True}],
            correction="Owner strategy changed.", next_cheapest_test="Prove the newly scoped slice.",
            checkpoint_id="owner-correction", challenge=challenge, actor="human:owner")
        self.assertIn("feasibility", state["tasks"][0])
        self.assertNotIn("feasibility", state_summary(state))
        self.assertEqual([], self.store.ready_tasks(run_id))

    def test_feasibility_shell_output_is_one_combined_ceiling(self):
        run_id, task_id = self.task("shell", {
            "command": [sys.executable, "-c", "import sys; sys.stdout.write('o'*1000); sys.stderr.write('e'*1000)"],
            "cwd": None, "environment": [],
        })
        self.feasibility(run_id, task_id, window={"timeoutSeconds": 120, "maxTurns": 8, "maxOutputBytes": 800})
        WorkspaceManager(self.repo).create(run_id, task_id)
        self.store.start_task(run_id, task_id, worker_id="bounded-shell")
        result = execute_work_packet(self.store, run_id, task_id, "bounded-shell")
        self.assertEqual("candidate", result["status"])
        self.assertLessEqual(len(result["stdout"].encode()) + len(result["stderr"].encode()), 800)
        self.assertTrue(result["outputTruncated"])

    def test_model_observation_never_claims_an_unreported_or_ignored_override(self):
        self.assertIsNone(routing_observation(None, "host-reported-model")["fallback"])
        self.assertIn("did not report", routing_observation("user-pin", None)["fallback"])
        self.assertIn("different effective", routing_observation("user-pin", "inherited-model")["fallback"])
        self.assertIn("no per-turn", routing_observation("user-pin", "user-pin", True)["fallback"])

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

    def task(self, adapter="native", execution=None, budget=None):
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
            "workPacket": {"execution": execution, **({"budget": budget} if budget else {})},
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

    def test_sibling_native_lifecycle_commutes_but_human_hold_does_not(self):
        run_id, task_id = self.task()
        self.store.add_task(run_id, {"id": "sibling", "objective": "Independent read",
                                   "workerProfile": "native", "acceptanceCriteria": ["FIX"], "risk": "R0"})
        first = self.store.begin_native_worker(run_id, task_id, host_owner="fixture-host")
        self.store.bind_native_owner(first, "host-first")
        second = self.store.begin_native_worker(run_id, "sibling", host_owner="fixture-host")
        self.store.bind_native_owner(second, "host-second")
        self.assertEqual("candidate", self.store.accept_native_candidate(
            second, host_task_id="host-second", host_status="completed", text="second")["status"])
        self.assertEqual("candidate", self.store.accept_native_candidate(
            first, host_task_id="host-first", host_status="completed", text="first")["status"])

    def test_global_hold_invalidates_parallel_ticket(self):
        run_id, task_id = self.task()
        self.store.add_task(run_id, {"id": "sibling", "objective": "Independent read",
                                   "workerProfile": "native", "acceptanceCriteria": ["FIX"], "risk": "R0"})
        ticket = self.store.begin_native_worker(run_id, task_id, host_owner="fixture-host")
        self.store.bind_native_owner(ticket, "host-first")
        self.store.wait_external(run_id, checkpoint_id="human-hold", task_id="sibling",
                                 checkpoint_type="AUTH_REQUIRED", principal="owner", provider="fixture",
                                 reason="Human authentication is still required")
        with self.assertRaises(RuntimeFailure) as error:
            self.store.accept_native_candidate(ticket, host_task_id="host-first", host_status="completed", text="candidate")
        self.assertEqual("NATIVE_RESULT_STALE", error.exception.code)

    def test_idle_owner_cannot_be_repurposed_without_same_task_binding(self):
        run_id, task_id = self.task()
        before = self.store.load(run_id)
        with self.assertRaises(RuntimeFailure) as error:
            self.store.begin_native_worker(run_id, task_id, host_owner="fixture-host", owner_handle="unrelated-idle")
        self.assertEqual("NATIVE_OWNER_TASK_MISMATCH", error.exception.code)
        self.assertEqual(before["revision"], self.store.load(run_id)["revision"])

    def test_owned_task_and_source_changes_still_invalidate_candidate(self):
        run_id, task_id = self.task()
        ticket = self.store.begin_native_worker(run_id, task_id, host_owner="fixture-host")
        self.store.bind_native_owner(ticket, "host-first")
        (self.repo / "README.md").write_text("changed source", encoding="utf-8")
        result = self.store.accept_native_candidate(ticket, host_task_id="host-first", host_status="completed", text="candidate")
        self.assertEqual("failed", result["status"])
        self.assertIn("worker changed the coordinator workspace", result["errors"])
        with self.assertRaises(RuntimeFailure):
            self.store.accept_native_candidate(ticket, host_task_id="host-first", host_status="completed", text="replay")

    def test_two_identical_failures_stop_and_recovery_cannot_reset_them(self):
        run_id, task_id = self.task("shell")
        self.store.start_task(run_id, task_id, worker_id="first")
        self.store.fail_task(run_id, task_id, "same missing dependency")
        self.store.recover_workers(run_id, task_id=task_id)
        with self.assertRaises(RuntimeFailure) as error:
            self.store.start_task(run_id, task_id, worker_id="second")
        self.assertEqual("RETRY_REASON_REQUIRED", error.exception.code)
        self.store.start_task(run_id, task_id, worker_id="second", retry_hypothesis="Check declared dependency path")
        state = self.store.fail_task(run_id, task_id, "same missing dependency")
        self.assertTrue(state["tasks"][0]["loop"]["stopped"])
        with self.assertRaises(RuntimeFailure) as error:
            self.store.recover_workers(run_id, task_id=task_id)
        self.assertEqual("REPEATED_FAILURE", error.exception.code)

    def test_new_relevant_source_evidence_resets_failure_streak(self):
        run_id, task_id = self.task("shell")
        # Read-only context is still relevant new evidence, not an unrelated artifact.
        state = self.store.load(run_id)
        self.store.add_task(run_id, {"id": "bounded", "objective": "Read README", "workerProfile": "shell",
                                   "acceptanceCriteria": ["FIX"], "risk": "R0", "maxAttempts": 3,
                                   "workPacket": {"contextBundle": ["README.md"]}})
        self.store.start_task(run_id, "bounded", worker_id="first")
        self.store.fail_task(run_id, "bounded", "same failure")
        (self.repo / "README.md").write_text("new evidence", encoding="utf-8")
        self.store.start_task(run_id, "bounded", worker_id="second")
        state = self.store.fail_task(run_id, "bounded", "same failure")
        self.assertFalse(state["tasks"][1]["loop"]["stopped"])
        self.assertEqual(1, state["tasks"][1]["loop"]["count"])

    def test_equivalent_receipt_provenance_cannot_reset_failure_streak(self):
        run_id, _ = self.task("shell")
        self.store.add_task(run_id, {"id": "bounded", "objective": "Bounded diagnostic",
                                   "workerProfile": "shell", "acceptanceCriteria": ["FIX"],
                                   "risk": "R0", "maxAttempts": 3})

        def observation(number):
            path = self.store.run_dir(run_id) / f"observation-{number}.json"
            path.write_text(json.dumps({"status": "pass", "exitCode": 0,
                                        "command": ["diagnostic"], "stdout": "same missing dependency",
                                        "observedAt": str(number), "durationMs": number,
                                        "binding": {"revision": number}}), encoding="utf-8")
            self.store._record_deterministic_result(
                run_id, artifact_id=f"observation-{number}", path=path.relative_to(self.store.repository).as_posix(),
                evidence_refs=["task:bounded"])

        observation(1)
        self.store.start_task(run_id, "bounded", worker_id="first")
        self.store.fail_task(run_id, "bounded", "same missing dependency")
        observation(2)
        with self.assertRaises(RuntimeFailure) as error:
            self.store.start_task(run_id, "bounded", worker_id="second")
        self.assertEqual("RETRY_REASON_REQUIRED", error.exception.code)
        self.store.start_task(run_id, "bounded", worker_id="second", retry_hypothesis="Check a different dependency location")
        state = self.store.fail_task(run_id, "bounded", "same missing dependency")
        self.assertTrue(state["tasks"][1]["loop"]["stopped"])

    def test_distinct_native_failure_causes_do_not_share_a_fingerprint(self):
        run_id, task_id = self.task()
        ticket = self.store.begin_native_worker(run_id, task_id, host_owner="fixture-host")
        self.store.bind_native_owner(ticket, "first")
        self.store.accept_native_candidate(ticket, host_task_id="first", host_status="cancelled", text="cancelled")
        original = self.store.load(run_id)["tasks"][0]["loop"]["fingerprint"]
        self.store.recover_workers(run_id, task_id=task_id)
        ticket = self.store.begin_native_worker(run_id, task_id, host_owner="fixture-host",
                                              retry_hypothesis="Investigate workspace scope rather than host cancellation")
        self.store.bind_native_owner(ticket, "second")
        (Path(ticket.snapshot["workspace"]) / "outside.txt").write_text("out of scope", encoding="utf-8")
        self.store.accept_native_candidate(ticket, host_task_id="second", host_status="completed", text="candidate")
        loop = self.store.load(run_id)["tasks"][0]["loop"]
        self.assertNotEqual(original, loop["fingerprint"])
        self.assertFalse(loop["stopped"])
        failures = primary_failures(self.store.load(run_id), self.store.events(run_id), "FIX")
        self.assertEqual(2, len(failures))
        self.assertNotEqual(failures[0]["reason"], failures[1]["reason"])
        self.assertIn("cancelled", failures[0]["reason"])
        self.assertIn("outside", failures[1]["reason"])

    def test_default_active_child_cap_is_three(self):
        run_id, task_id = self.task("shell")
        for number in range(3):
            self.store.add_task(run_id, {"id": f"child-{number}", "objective": "Bounded read",
                                       "workerProfile": "shell", "acceptanceCriteria": ["FIX"], "risk": "R0"})
        self.store.start_task(run_id, task_id, worker_id="first")
        for number in range(2):
            self.store.start_task(run_id, f"child-{number}", worker_id=f"worker-{number}")
        with self.assertRaises(RuntimeFailure) as error:
            self.store.start_task(run_id, "child-2", worker_id="fourth")
        self.assertEqual("PARALLELISM_EXCEEDED", error.exception.code)

    @unittest.skipUnless(shutil.which("node"), "Node required only for the SDK transport contract fixture")
    def test_sdk_fixture_event_wait_hookless_and_concurrent_admission(self):
        """Mock SDK contract test, deliberately NOT native-host execution evidence."""
        root = Path(self.temp.name) / "transport"
        root.mkdir()
        source = (ROOT / "extensions/architrave-native/bridge.mjs").read_text(encoding="utf-8")
        source = source.replace('"@github/copilot-sdk/extension"',
                                '"data:text/javascript,export const joinSession=globalThis.joinSession;"')
        entry = root / "extension.mjs"
        entry.write_text(source + "\nexport { observeTask };\n", encoding="utf-8")
        python = Path(sys.executable).resolve()
        (root / "installation.json").write_text(json.dumps({
            "root": str(root), "python": str(python),
            "pythonSha256": hashlib.sha256(python.read_bytes()).hexdigest(),
            "extensionSha256": hashlib.sha256(entry.read_bytes()).hexdigest(), "files": {},
        }), encoding="utf-8")
        script = r'''
import assert from "node:assert/strict";
import {pathToFileURL} from "node:url";
let options, callback, reads=0, unsubscribed=false;
let tasks=[{id:"test",type:"agent",status:"running"}];
const host={sessionId:"root",on(fn){callback=fn;return ()=>{unsubscribed=true;}},
  rpc:{tasks:{startAgent(){throw Error("fixture must not launch a worker");},
    list:async()=>{reads++;return {tasks};},cancel:async()=>({cancelled:true})}}};
globalThis.joinSession=async value=>{options=value;return host;};
const module=await import(pathToFileURL(process.argv[1]));
assert.equal(Object.hasOwn(options,"hooks"),false);
const observer=module.observeTask(12);
const waiting=observer.wait("test",Date.now()+1000,()=>true);
await new Promise(resolve=>setImmediate(resolve));
assert.equal(reads,1);
tasks=[{id:"test",type:"agent",status:"completed"}];
callback({type:"session.background_tasks_changed"});
assert.equal((await waiting).status,"completed");
assert.equal(reads,2);
assert.equal(unsubscribed,true);
for(const owner of ["early-admission","retained-delivery"]) {
  let cancelled=false;
  tasks=[{id:owner,type:"agent",status:"running"}];
  host.rpc.tasks.cancel=async({id})=>{
    assert.equal(id,owner);cancelled=true;tasks[0].status="cancelled";
    callback({type:"session.background_tasks_changed"});return {cancelled:true};
  };
  const early=module.observeTask(2);
  // Both events arrive before startAgent/sendMessage returns the owner handle.
  callback({agentId:owner,type:"assistant.turn_start"});
  callback({agentId:owner,type:"assistant.turn_start"});
  const observed=await early.wait(owner,Date.now()+1000,()=>true);
  assert.equal(cancelled,true);
  assert.equal(observed.turnsObserved,2);
  assert.equal(observed.budgetStop,"turns");
}
host.rpc.tasks.list=()=>new Promise(()=>{});
const dispatch=options.tools.find(tool=>tool.name==="architrave_native_dispatch");
for(let i=0;i<3;i++) void dispatch.handler({repo:"unused",run_id:"r",task_id:String(i)},{sessionId:"root"});
assert.equal(Object.hasOwn(options,"hooks"),false);
await assert.rejects(dispatch.handler({},{sessionId:"root"}),/CHILD_LIMIT/);
console.log("SDK event/hookless/admission fixture: PASS (not native evidence)");
'''
        result = subprocess.run(["node", "--input-type=module", "-e", script, str(entry)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_benchmark_report_cannot_turn_failed_or_missing_native_execution_into_success(self):
        output = Path(self.temp.name) / "measurement"
        for arm in ("baseline", "candidate"):
            (output / arm).mkdir(parents=True)
        for acceptance, execution in (("FAIL", "FAILED"), ("UNOBSERVED", "NOT_DISPATCHED"),
                                      ("PASS", "OBSERVED")):
            measurement = {
                "frozenFixtureSha256": "same-fixture", "sourceCommit": "fixture", "exactTelemetry": {},
                "tasks": {
                    "A": {"acceptance": "PASS", "childCount": 0},
                    "B": {"acceptance": acceptance, "execution": execution, "childCount": 0,
                          "nativeOwnersObserved": 0, "maxConcurrency": 0, "workerStatuses": []},
                },
            }
            for arm in ("baseline", "candidate"):
                (output / arm / "measurement.json").write_text(json.dumps(measurement), encoding="utf-8")
            record = output / "record.json"
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/bench-thin-supervisor.py"), "report",
                 "--source", str(ROOT), "--baseline-source", str(ROOT), "--output", str(output),
                 "--arm", "candidate", "--record", str(record)], capture_output=True, text=True, timeout=15)
            self.assertEqual(0, result.returncode, result.stderr)
            data = json.loads(record.read_text(encoding="utf-8"))
            self.assertEqual(0, data["windowsCopilotApp"]["candidateNativeOwnerCountObserved"])
            self.assertFalse(data["hostMatrix"]["windowsCopilotApp"]["nativeParallelBVerified"])
            self.assertNotEqual("PASS", data["hostMatrix"]["windowsCopilotApp"]["B"])
            self.assertEqual("UNVERIFIED", data["acceptance"]["5"])
            self.assertIsNone(data["windowsCopilotApp"]["installedVersion"])
            self.assertEqual("UNOBSERVED", data["review"]["status"])

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
