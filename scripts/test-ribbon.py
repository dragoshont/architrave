from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import shlex
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from architrave_runtime import RunStore, RuntimeFailure
from ribbon import ribbon_snapshot
from worker_adapters import workspace_fingerprint

spec = importlib.util.spec_from_file_location("ribbon_installer", ROOT / "tools" / "install_update.py")
installer = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = installer
spec.loader.exec_module(installer)


class RibbonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        for args in [("init", "-q"), ("config", "user.email", "fixture@example.invalid"),
                     ("config", "user.name", "Fixture")]:
            self.git(*args)
        (self.repo / "fixture.txt").write_text("generic fixture\n", encoding="utf-8")
        (self.repo / ".gitignore").write_text(".architrave/\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        self.store = RunStore(self.repo)
        self.store.create(goal="Generic fixture", outcome="Observed outcome", run_id="run", criteria=[])

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, capture_output=True, text=True, check=True).stdout.strip()

    def task(self, identifier, dependencies=(), **options):
        self.store.add_task("run", {
            "id": identifier, "title": identifier, "objective": "Observe fixture",
            "acceptanceCriteria": ["OUTCOME-001"], "dependencies": list(dependencies),
            "pushback": "KEEP:generic fixture", "maxAttempts": 3,
            **options,
        })

    def test_projection_read_only_and_dependencies(self):
        self.task("first")
        self.task("next", ["first"])
        run_dir = self.store.run_dir("run")
        before = {name: (run_dir / name).read_bytes() for name in ["run.json", "events.jsonl"]}
        result = ribbon_snapshot(self.store, "run")
        self.assertEqual(["planned", "blocked"], [step["state"] for step in result["steps"]])
        self.assertEqual("dependency", result["steps"][1]["blocker"])
        self.assertEqual(["first"], result["steps"][1]["dependencies"])
        self.assertIsNone(result["milestone"])
        self.assertIsNone(result["deadline"])
        self.assertEqual(before, {name: (run_dir / name).read_bytes() for name in before})
        self.assertNotIn("tokens", result)
        self.assertNotIn("policy", result)

    def test_taskless_current_product_observation_verifies_completed_delivery(self):
        from legibility import LegibilityRunner
        command = ("& '" + sys.executable.replace("'", "''") + "' -c \"print('observed')\""
                   if os.name == "nt" else shlex.join([sys.executable, "-c", "print('observed')"]))
        (self.repo / "architrave.config.json").write_text(json.dumps({
            "kind": "knowledge", "build": command, "test": command}), encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "product observation fixture")
        run_id = "taskless"
        self.store.create(run_id=run_id, goal="Observed fixture", outcome="Observed web",
            criteria=[{"id": "PRODUCT", "description": "Observed fixture", "scope": "fixture",
                       "risk": "R1", "verificationType": "reality", "surface": "web", "blocking": True}])
        for identifier in ("delivery", "foreign"):
            self.store.add_task(run_id, {"id": identifier, "objective": "Observed fixture",
                "acceptanceCriteria": ["PRODUCT"], "workerProfile": "shell", "risk": "R1",
                "pushback": "KEEP:fixture"})
            self.store.start_task(run_id, identifier, worker_id="worker-" + identifier)
            self.store.finish_worker(run_id, identifier, worker_id="worker-" + identifier, status="FINISHED")
        scoped = self.store.execute_gate(run_id, "delivery")
        self.store.complete_task(run_id, "delivery", evidence_refs=[scoped["gateRef"]])
        runner = LegibilityRunner(self.repo, run_id)
        observed = runner._finalize_gate("web", [
            runner.recipe("runtime.health", command), runner.recipe("web.e2e", command)], task_id=None)
        ref = "gate:" + observed["gateId"]
        self.store.set_criterion(run_id, "PRODUCT", "PASS", [ref])
        self.assertEqual("verified", ribbon_snapshot(self.store, run_id)["steps"][0]["state"])
        runner = LegibilityRunner(self.repo, run_id)
        foreign = runner._finalize_gate("web", [
            runner.recipe("runtime.health", command), runner.recipe("web.e2e", command)], task_id="foreign")
        self.store.set_criterion(run_id, "PRODUCT", "PASS", ["gate:" + foreign["gateId"]])
        self.assertEqual("done", ribbon_snapshot(self.store, run_id)["steps"][0]["state"])
        self.store.set_criterion(run_id, "PRODUCT", "PASS", [ref])
        (self.repo / "fixture.txt").write_text("Uncommitted source correction\n", encoding="utf-8")
        self.assertEqual("done", ribbon_snapshot(self.store, run_id)["steps"][0]["state"])

    def test_explicit_loop_stop_not_attempt_count(self):
        self.task("retry")
        self.store.start_task("run", "retry", worker_id="worker-one")
        self.store.fail_task("run", "retry", "generic repeat")
        first = ribbon_snapshot(self.store, "run")["steps"][0]
        self.assertEqual("planned", first["state"])
        self.assertEqual(1, first["retry"]["repeated"])
        self.store.start_task("run", "retry", worker_id="worker-two", retry_hypothesis="Probe a distinct cause")
        self.store.fail_task("run", "retry", "generic repeat")
        second = ribbon_snapshot(self.store, "run")["steps"][0]
        self.assertEqual("stopped", second["state"])
        self.assertTrue(second["retry"]["stopped"])
        self.assertEqual(first["retry"]["fingerprint"], second["retry"]["fingerprint"])

    def test_governing_failure_revokes_verified_display_and_milestone_not_completion_history(self):
        for owner in ("delivery", None):
            with self.subTest(failure_task=owner):
                run_id = "negative-" + ("task" if owner else "criterion")
                self.store.create(run_id=run_id, goal="Public verification fixture", outcome="Observed surface",
                    criteria=[{"id": "PRODUCT", "description": "Observed fixture", "scope": "fixture",
                               "risk": "R1", "verificationType": "reality", "surface": "web", "blocking": True}])
                self.store.add_task(run_id, {"id": "delivery", "objective": "Public fixture",
                    "acceptanceCriteria": ["PRODUCT"], "workerProfile": "shell", "risk": "R1",
                    "pushback": "KEEP:fixture"})
                self.store.start_task(run_id, "delivery", worker_id="fixture-worker")
                self.store.finish_worker(run_id, "delivery", worker_id="fixture-worker", status="FINISHED")
                path = self.store.run_dir(run_id) / "fixture-receipt.json"
                path.write_text(json.dumps({"surface": "web", "status": "pass", "failed": [],
                    "binding": {"runId": run_id, "taskId": "delivery", "objectiveVersion": 1, "criteria": ["PRODUCT"]},
                    "source": {"commit": self.git("rev-parse", "HEAD"),
                               "sha256": workspace_fingerprint(self.repo, include_ignored=False)},
                    "results": [{"name": name, "status": "pass"} for name in ("runtime.health", "web.e2e")]}))
                self.store._record_legibility_result(run_id, kind="web-legibility", artifact_id="observed",
                    path=path.relative_to(self.store.repository).as_posix(), evidence_refs=["task:delivery"])
                self.store.record_gate(run_id, gate_id="positive", task_id="delivery", gate_type="reality",
                    status="PASS", evidence_refs=["artifact:observed"], criteria=["PRODUCT"], surface="web")
                self.store.advance_milestone(run_id, "delivery", criterion_id="PRODUCT",
                    milestone="Intermediate observation", gate_ref="gate:positive")
                self.assertIsNotNone(ribbon_snapshot(self.store, run_id)["milestone"])
                self.assertEqual("UNTESTED", self.store.load(run_id)["acceptanceCriteria"][0]["status"])
                self.store.set_criterion(run_id, "PRODUCT", "PASS", ["gate:positive"])
                self.store.complete_task(run_id, "delivery", evidence_refs=["gate:positive"])
                positive = ribbon_snapshot(self.store, run_id)
                self.assertEqual("verified", positive["steps"][0]["state"])
                self.assertIsNotNone(positive["milestone"])
                for status in ("UNTESTED", "FAIL"):
                    self.store.set_criterion(run_id, "PRODUCT", status, [])
                    withdrawn = ribbon_snapshot(self.store, run_id)
                    self.assertIsNone(withdrawn["milestone"])
                    self.assertNotEqual("verified", withdrawn["steps"][0]["state"])
                    fresh_id = "after-" + status.lower()
                    fresh_path = path.with_name(fresh_id + ".json")
                    fresh = json.loads(path.read_text())
                    fresh["results"][0]["observation"] = fresh_id
                    fresh_path.write_text(json.dumps(fresh))
                    self.store._record_legibility_result(run_id, kind="web-legibility", artifact_id=fresh_id,
                        path=fresh_path.relative_to(self.store.repository).as_posix(), evidence_refs=["task:delivery"])
                    self.store.record_gate(run_id, gate_id=fresh_id, task_id="delivery", gate_type="reality",
                        status="PASS", evidence_refs=["artifact:" + fresh_id], criteria=["PRODUCT"], surface="web")
                    self.store.set_criterion(run_id, "PRODUCT", "PASS", ["gate:" + fresh_id])
                    self.store.advance_milestone(run_id, "delivery", criterion_id="PRODUCT",
                        milestone="New verified observation", gate_ref="gate:" + fresh_id)
                failed_path = path.with_name("negative.json")
                failed_receipt = json.loads(path.read_text())
                failed_receipt.update({"status": "fail", "failed": ["runtime.health"]})
                failed_receipt["binding"]["taskId"] = owner
                failed_receipt["results"][0]["status"] = "fail"
                failed_path.write_text(json.dumps(failed_receipt), encoding="utf-8")
                self.store._record_legibility_result(run_id, kind="web-legibility", artifact_id="negative",
                    path=failed_path.relative_to(self.store.repository).as_posix(),
                    evidence_refs=["task:delivery"] if owner else [])
                self.store.record_gate(run_id, gate_id="negative", task_id=owner, gate_type="reality",
                    status="FAIL", evidence_refs=["artifact:negative"], criteria=["PRODUCT"], surface="web")
                negative = ribbon_snapshot(self.store, run_id)
                self.assertEqual("stopped", negative["steps"][0]["state"])
                self.assertIn("negative", negative["steps"][0]["reason"])
                self.assertIn("gate:positive", negative["steps"][0]["evidence"])
                self.assertIn("gate:negative", negative["steps"][0]["evidence"])
                self.assertIsNone(negative["milestone"])
                self.assertEqual("COMPLETED", self.store.load(run_id)["tasks"][0]["status"])

    def test_source_drift_and_no_synthetic_product_pass(self):
        self.task("scoped")
        result = ribbon_snapshot(self.store, "run")
        self.assertEqual("current", result["source"]["freshness"])
        self.assertNotEqual("verified", result["steps"][0]["state"])
        (self.repo / "fixture.txt").write_text("changed\n", encoding="utf-8")
        self.assertEqual("stale", ribbon_snapshot(self.store, "run")["source"]["freshness"])
        self.git("add", ".")
        self.git("commit", "-qm", "new source")
        self.assertEqual("stale", ribbon_snapshot(self.store, "run")["source"]["freshness"])

    def test_old_source_failures_remain_history_after_resume_not_governing(self):
        self.task("delivery")
        path = self.store.run_dir("run") / "old-failure.json"
        path.write_text(json.dumps({"surface": "web", "status": "fail", "failed": ["runtime.health"],
            "binding": {"runId": "run", "taskId": "delivery", "objectiveVersion": 1,
                        "criteria": ["OUTCOME-001"]},
            "source": {"commit": self.git("rev-parse", "HEAD"),
                       "sha256": workspace_fingerprint(self.repo, include_ignored=False)},
            "results": [{"name": "runtime.health", "status": "fail"},
                        {"name": "web.e2e", "status": "pass"}]}), encoding="utf-8")
        self.store._record_legibility_result("run", kind="web-legibility", artifact_id="old-failure",
            path=path.relative_to(self.store.repository).as_posix(), evidence_refs=["task:delivery"])
        self.store.record_gate("run", gate_id="negative", task_id="delivery", gate_type="reality",
            status="FAIL", evidence_refs=["artifact:old-failure"], criteria=["OUTCOME-001"], surface="web")
        self.assertEqual("stopped", ribbon_snapshot(self.store, "run")["steps"][0]["state"])
        self.assertEqual("FAILED", self.store.verify("run")[0]["status"])
        authenticated = path.read_bytes()
        path.write_bytes(b"tampered retained failure")
        with self.assertRaises(RuntimeFailure):
            ribbon_snapshot(self.store, "run")
        path.write_bytes(authenticated)
        (self.repo / "fixture.txt").write_text("New source after failure\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "new source")
        self.store.resume("run", accept_commit=True)
        step = ribbon_snapshot(self.store, "run")["steps"][0]
        self.assertNotEqual("stopped", step["state"])
        self.assertIn("historical", step["reason"].lower())
        self.assertTrue(any("gate:negative" in ref for ref in step["evidence"]))
        retained = self.store.load("run")["gateResults"][0]
        self.assertEqual("FAIL", retained["status"])
        self.assertNotEqual("FAILED", self.store.verify("run")[0]["status"])

    def test_private_control_metadata_drift_is_not_public_source_drift(self):
        private = self.repo / ".architrave" / "private-history.txt"
        private.write_text("Private fixture history\n", encoding="utf-8")
        self.git("add", "-f", ".architrave/private-history.txt")
        self.git("commit", "-qm", "private metadata fixture")
        self.store.resume("run", accept_commit=True)
        private.write_text("Private metadata update\n", encoding="utf-8")
        self.assertEqual("current", ribbon_snapshot(self.store, "run")["source"]["freshness"])

    def test_current_policy_and_security_failures_govern_even_without_code_binding(self):
        for gate_type in ("policy", "security"):
            with self.subTest(gate_type=gate_type):
                run_id = gate_type
                self.store.create(run_id=run_id, goal="Fail-closed fixture", outcome="Protected fixture", criteria=[])
                self.store.add_task(run_id, {"id": "delivery", "objective": "Protected fixture",
                    "acceptanceCriteria": ["OUTCOME-001"], "pushback": "KEEP:fixture"})
                path = self.store.run_dir(run_id) / "negative.json"
                path.write_text(json.dumps({"verdict": "FAIL", "reason": "Current authenticated decision"}))
                record = (self.store._record_policy_decision if gate_type == "policy"
                          else self.store._record_security_verdict)
                record(run_id, artifact_id="negative", path=path.relative_to(self.store.repository).as_posix(),
                       evidence_refs=["task:delivery"])
                self.store.record_gate(run_id, gate_id="negative", task_id="delivery", gate_type=gate_type,
                    status="FAIL", evidence_refs=["artifact:negative"], criteria=["OUTCOME-001"])
                self.assertEqual("stopped", ribbon_snapshot(self.store, run_id)["steps"][0]["state"])
                self.assertEqual("FAILED", self.store.verify(run_id)[0]["status"])
                original = path.read_bytes()
                path.write_bytes(b"tampered")
                with self.assertRaises(RuntimeFailure):
                    ribbon_snapshot(self.store, run_id)
                path.write_bytes(original)

    def test_malformed_policy_and_security_identity_never_counts_as_staleness(self):
        malformed = [
            {"source": {"sha256": []}}, {"source": {"commit": []}},
            {"source": {"sha256": None}}, {"source": {"commit": "not-a-commit"}},
            {"binding": {"runId": None}}, {"binding": {"objectiveVersion": True}},
            {"binding": {"objectiveVersion": -1}}, {"binding": None},
            {"binding": {"taskId": []}}, {"binding": {"revision": True}},
            {"binding": {"criteria": [None]}}, {"source": None},
        ]
        for gate_type in ("policy", "security"):
            run_id = "malformed-" + gate_type
            self.store.create(run_id=run_id, goal="Protected identity", outcome="Valid evidence", criteria=[])
            record = self.store._record_policy_decision if gate_type == "policy" else self.store._record_security_verdict
            for index, fields in enumerate(malformed):
                with self.subTest(gate_type=gate_type, fields=fields):
                    identifier = "negative-" + str(index)
                    path = self.store.run_dir(run_id) / (identifier + ".json")
                    path.write_text(json.dumps({"verdict": "FAIL", **fields}), encoding="utf-8")
                    record(run_id, artifact_id=identifier, path=path.relative_to(self.store.repository).as_posix(),
                           evidence_refs=[])
                    self.store.record_gate(run_id, gate_id=identifier, task_id=None, gate_type=gate_type,
                        status="FAIL", evidence_refs=["artifact:" + identifier], criteria=["OUTCOME-001"])
                    state = self.store.load(run_id)
                    gate = next(item for item in state["gateResults"] if item["id"] == identifier)
                    with self.assertRaises(RuntimeFailure) as invalid:
                        self.store.failure_source_status(state, gate)
                    self.assertEqual("EVIDENCE_BINDING_INVALID", invalid.exception.code)

    def test_source_bound_policy_and_security_failures_become_historical_only_with_real_drift(self):
        for gate_type in ("policy", "security"):
            with self.subTest(gate_type=gate_type):
                run_id = gate_type + "-source"
                self.store.create(run_id=run_id, goal="Protected source fixture", outcome="Safe source", criteria=[])
                self.store.add_task(run_id, {"id": "delivery", "objective": "Protected fixture",
                    "acceptanceCriteria": ["OUTCOME-001"], "pushback": "KEEP:fixture"})
                path = self.store.run_dir(run_id) / "bound-negative.json"
                path.write_text(json.dumps({"verdict": "FAIL",
                    "binding": {"runId": run_id, "objectiveVersion": 1},
                    "source": {"commit": self.git("rev-parse", "HEAD"),
                               "sha256": workspace_fingerprint(self.repo, include_ignored=False)}}))
                record = self.store._record_policy_decision if gate_type == "policy" else self.store._record_security_verdict
                record(run_id, artifact_id="negative", path=path.relative_to(self.store.repository).as_posix(),
                       evidence_refs=["task:delivery"])
                self.store.record_gate(run_id, gate_id="negative", task_id="delivery", gate_type=gate_type,
                    status="FAIL", evidence_refs=["artifact:negative"], criteria=["OUTCOME-001"])
                self.assertEqual("stopped", ribbon_snapshot(self.store, run_id)["steps"][0]["state"])
                self.assertEqual("FAILED", self.store.verify(run_id)[0]["status"])
                (self.repo / "fixture.txt").write_text("Corrected " + gate_type + " source\n", encoding="utf-8")
                self.git("add", ".")
                self.git("commit", "-qm", "source correction")
                self.store.resume(run_id, accept_commit=True)
                step = ribbon_snapshot(self.store, run_id)["steps"][0]
                self.assertNotEqual("stopped", step["state"])
                self.assertIn("historical", step["reason"].lower())
                self.assertNotEqual("FAILED", self.store.verify(run_id)[0]["status"])

    def test_old_deterministic_failure_is_historical_after_source_resume(self):
        command = ("& '" + sys.executable.replace("'", "''") + "' -c \"raise SystemExit(1)\""
                   if os.name == "nt" else shlex.join([sys.executable, "-c", "raise SystemExit(1)"]))
        (self.repo / "architrave.config.json").write_text(json.dumps({
            "kind": "knowledge", "build": command, "test": command}), encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "configured observed failure")
        self.store.resume("run", accept_commit=True)
        self.task("delivery")
        self.store.start_task("run", "delivery", worker_id="deterministic-fixture")
        self.store.finish_worker("run", "delivery", worker_id="deterministic-fixture", status="FINISHED")
        result = self.store.execute_gate("run", "delivery")
        self.assertEqual("FAIL", result["status"])
        self.assertEqual("stopped", ribbon_snapshot(self.store, "run")["steps"][0]["state"])
        self.assertEqual("FAILED", self.store.verify("run")[0]["status"])
        (self.repo / "fixture.txt").write_text("Source correction\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "source correction")
        self.store.resume("run", accept_commit=True)
        step = ribbon_snapshot(self.store, "run")["steps"][0]
        self.assertNotEqual("stopped", step["state"])
        self.assertIn("historical", step["reason"].lower())
        self.assertTrue(any(result["gateRef"] in ref for ref in step["evidence"]))
        self.assertNotEqual("FAILED", self.store.verify("run")[0]["status"])

    def test_cli_projection_envelope(self):
        self.task("scoped")
        result = subprocess.run([sys.executable, str(ROOT / "harness" / "architrave_runtime.py"),
                                 "--repo", str(self.repo), "ribbon-snapshot", "run"],
                                capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("architrave.ribbon.v1", json.loads(result.stdout)["result"]["schema"])

    def test_maximum_run_id_projects_complete_safe_domain_identity(self):
        run_id = "r" * 128
        self.store.create(run_id=run_id, goal="Maximum public fixture ID", outcome="Source", criteria=[])
        result = ribbon_snapshot(self.store, run_id)
        self.assertEqual(153, len(result["domainKey"]))
        self.assertEqual(run_id, result["runId"])

    def test_empty_event_history_has_explicit_projection_error(self):
        with patch.object(self.store, "events", return_value=[]):
            with self.assertRaises(RuntimeFailure) as failure:
                ribbon_snapshot(self.store, "run")
        self.assertEqual("RIBBON_HISTORY_EMPTY", failure.exception.code)

    def test_superseded_blocker_is_history_not_current(self):
        self.task("prerequisite")
        self.task("old-blocker", ["prerequisite"])
        historical = self.store.load("run")
        historical["objective"]["version"] = 2
        with patch.object(self.store, "load", return_value=historical):
            result = ribbon_snapshot(self.store, "run")
        self.assertTrue(all(not step["current"] for step in result["steps"]))
        self.assertEqual("deferred", result["steps"][1]["state"])
        self.assertIsNone(result["steps"][1]["blocker"])
        self.assertIn("not a current blocker", result["steps"][1]["reason"])

    def test_human_hold_remains_visible_with_explicit_stop(self):
        self.task("held")
        self.store.wait_external("run", checkpoint_id="approval", task_id="held",
                                 checkpoint_type="HUMAN_JUDGMENT_REQUIRED", principal="human",
                                 provider="manual", reason="Fixture approval")
        self.store.fail_task("run", "held", "same cause")
        self.store.fail_task("run", "held", "same cause")
        step = ribbon_snapshot(self.store, "run")["steps"][0]
        self.assertEqual("stopped", step["state"])
        self.assertEqual("human", step["blocker"])
        self.assertIn("Pending human checkpoint", step["reason"])

    def test_parallel_work_kind_lanes_keep_independent_states_and_owners(self):
        self.task("prerequisite")
        self.task("delivery", ["prerequisite"])
        self.task("feasibility", workKind="diagnostic", lane="feasibility", isMinimalAcceptanceTest=True)
        self.store.start_task("run", "feasibility", worker_id="research-owner")
        result = ribbon_snapshot(self.store, "run")
        indexed = {step["id"]: step for step in result["steps"]}
        self.assertEqual("blocked", indexed["delivery"]["state"])
        self.assertEqual("active", indexed["feasibility"]["state"])
        self.assertEqual("research-owner", indexed["feasibility"]["owner"])
        self.assertNotEqual(indexed["delivery"]["streamId"], indexed["feasibility"]["streamId"])
        stream = next(item for item in result["streams"] if item["id"] == indexed["feasibility"]["streamId"])
        self.assertEqual("exploratory", stream["kind"])
        self.assertIn("not product shipped", stream["outcome"])
        self.assertEqual(result["revision"], stream["sourceRef"]["revision"])
        self.assertEqual([], result["relations"])

    def test_cross_stream_prerequisite_is_blocks_not_inferred_informs(self):
        self.task("research", workKind="research", lane="research")
        self.task("implementation", ["research"])
        result = ribbon_snapshot(self.store, "run")
        self.assertEqual(1, len(result["relations"]))
        relation = result["relations"][0]
        self.assertEqual(("research", "implementation", "blocks", "canonical dependency"),
                         (relation["fromStep"], relation["toStep"], relation["type"], relation["provenance"]))

    def test_completed_research_is_scoped_not_product_verified_and_unknown_lane_is_labelled(self):
        self.task("research", workKind="research")
        state = self.store.load("run")
        state["tasks"][0]["status"] = "COMPLETED"
        state["tasks"][0]["lane"] = "unknown-lane"
        with patch.object(self.store, "load", return_value=state):
            result = ribbon_snapshot(self.store, "run")
        self.assertEqual("done", result["steps"][0]["state"])
        self.assertIsNone(result["steps"][0]["owner"])
        self.assertIn("Unassigned lane", result["streams"][0]["label"])
        self.assertEqual("exploratory", result["streams"][0]["kind"])

    def test_installer_opt_in_exact_bytes_and_refresh(self):
        manifest = json.loads((ROOT / "plugin.json").read_text())
        self.assertEqual(".github/extensions/architrave-ribbon", manifest["extensions"])
        self.assertEqual(["architrave-ribbon"],
                         sorted(path.name for path in (ROOT / ".github" / "extensions").iterdir() if path.is_dir()))
        target = Path(self.temp.name) / "consumer"
        target.mkdir()
        (target / "product.txt").write_text("preserve", encoding="utf-8")
        installer.install_canvas(ROOT, target)
        installed = target / ".github" / "extensions" / "architrave-ribbon" / "extension.mjs"
        source = ROOT / ".github" / "extensions" / "architrave-ribbon" / "extension.mjs"
        self.assertEqual(source.read_bytes(), installed.read_bytes())
        installed.write_text("old version", encoding="utf-8")
        installer.install_canvas(ROOT, target)
        self.assertEqual(source.read_bytes(), installed.read_bytes())
        self.assertEqual("preserve", (target / "product.txt").read_text(encoding="utf-8"))
        self.assertFalse((target / "architrave.config.json").exists())

    def test_installer_refuses_unsafe_destination(self):
        target = Path(self.temp.name) / "consumer"
        target.mkdir()
        (target / ".github").write_text("not a directory", encoding="utf-8")
        with self.assertRaises(installer.InstallerError):
            installer.install_canvas(ROOT, target)
        self.assertEqual("not a directory", (target / ".github").read_text(encoding="utf-8"))

    def test_companion_install_is_one_file_and_preserves_durable_opt_out(self):
        home = Path(self.temp.name) / "copilot-home"
        artifacts = home / "extensions" / "architrave-ribbon" / "artifacts"
        artifacts.mkdir(parents=True)
        preferences = artifacts / "preferences.json"
        preferences.write_text('{"enabled":false}', encoding="utf-8")
        installer.install_companion(ROOT, home)
        entry = artifacts.parent / "extension.mjs"
        source = ROOT / ".github" / "extensions" / "architrave-ribbon" / "extension.mjs"
        self.assertEqual(source.read_bytes(), entry.read_bytes())
        self.assertEqual('{"enabled":false}', preferences.read_text(encoding="utf-8"))
        self.assertEqual({"extensions/architrave-ribbon/extension.mjs",
                          "extensions/architrave-ribbon/artifacts/preferences.json"},
                         {path.relative_to(home).as_posix() for path in home.rglob("*") if path.is_file()})
        entry.write_text("old renderer", encoding="utf-8")
        installer.install_companion(ROOT, home)
        self.assertEqual(source.read_bytes(), entry.read_bytes())
        self.assertEqual('{"enabled":false}', preferences.read_text(encoding="utf-8"))

    def test_companion_install_requires_explicit_existing_home_and_safe_paths(self):
        missing = Path(self.temp.name) / "missing"
        with self.assertRaises(installer.InstallerError):
            installer.install_companion(ROOT, missing)
        self.assertFalse(missing.exists())
        home = Path(self.temp.name) / "copilot-home"
        home.mkdir()
        (home / "extensions").write_text("preserve", encoding="utf-8")
        with self.assertRaises(installer.InstallerError):
            installer.install_companion(ROOT, home)
        self.assertEqual("preserve", (home / "extensions").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
