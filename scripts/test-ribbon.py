from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
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
                self.store.set_criterion(run_id, "PRODUCT", "PASS", ["gate:positive"])
                self.store.complete_task(run_id, "delivery", evidence_refs=["gate:positive"])
                self.store.advance_milestone(run_id, "delivery", criterion_id="PRODUCT",
                    milestone="Fixture observation", gate_ref="gate:positive")
                positive = ribbon_snapshot(self.store, run_id)
                self.assertEqual("verified", positive["steps"][0]["state"])
                self.assertIsNotNone(positive["milestone"])
                self.store.record_gate(run_id, gate_id="negative", task_id=owner, gate_type="reality",
                    status="FAIL", evidence_refs=[], criteria=["PRODUCT"], surface="web")
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
        self.git("add", ".")
        self.git("commit", "-qm", "new source")
        self.assertEqual("stale", ribbon_snapshot(self.store, "run")["source"]["freshness"])

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


if __name__ == "__main__":
    unittest.main()
