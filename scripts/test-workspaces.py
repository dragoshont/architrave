#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))

from architrave_runtime import RunStore, RuntimeFailure
from workspaces import WorkspaceManager


class WorkspaceManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.email", "architrave@example.invalid")
        self.git("config", "user.name", "Architrave Test")
        (self.repo / ".gitignore").write_text(
            ".architrave/runs/\n.architrave/worktrees/\n",
            encoding="utf-8",
        )
        (self.repo / "architrave.config.json").write_text(
            json.dumps({"workers": {"worktreeRoot": ".architrave/worktrees"}}),
            encoding="utf-8",
        )
        (self.repo / "README.md").write_text("before\n", encoding="utf-8")
        (self.repo / "allowed").mkdir()
        (self.repo / "allowed/value.txt").write_text("before\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        self.store = RunStore(self.repo)
        self.manager = WorkspaceManager(self.repo)

    def tearDown(self) -> None:
        subprocess.run(["git", "worktree", "prune"], cwd=self.repo, capture_output=True)
        self.temp.cleanup()

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=self.repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def create_run(self) -> str:
        state = self.store.create(
            goal="Exercise isolated workspaces.",
            outcome="Candidate changes remain scoped and coordinator-integrated.",
            criteria=[
                {
                    "id": "WORKSPACE-001",
                    "description": "Workspace isolation is enforced.",
                    "scope": "workspace",
                    "risk": "R3",
                    "verificationType": "deterministic",
                    "status": "UNTESTED",
                    "evidenceRefs": [],
                    "blocking": True,
                }
            ],
            autonomy_scope="approved-program",
            policy_allow=[{"scope": "repository", "operations": ["edit"]}],
        )
        return state["runId"]

    def add_task(self, run_id: str, task_id: str, mutable_paths: list[str]) -> None:
        self.store.add_task(
            run_id,
            {
                "id": task_id,
                "title": task_id,
                "objective": f"Complete {task_id}.",
                "workerProfile": "shell",
                "mutablePaths": mutable_paths,
                "tools": [],
                "risk": "R3" if mutable_paths else "R0",
                "acceptanceCriteria": ["WORKSPACE-001"],
                "requiredArtifacts": [],
                "gate": "workspace fixture",
            },
        )

    def test_mutating_tasks_receive_unique_detached_worktrees(self) -> None:
        run_id = self.create_run()
        self.add_task(run_id, "one", ["README.md"])
        self.add_task(run_id, "two", ["allowed/**"])
        one = self.manager.create(run_id, "one")
        two = self.manager.create(run_id, "two")
        self.assertNotEqual(one["workspace"], two["workspace"])
        self.assertEqual(self.git("rev-parse", "HEAD"), one["commit"])
        self.assertTrue((Path(one["workspace"]) / ".git").is_file())
        state = self.store.load(run_id)
        self.assertEqual(2, len({task["workspace"] for task in state["tasks"]}))

    def test_read_only_tasks_receive_isolated_disposable_worktrees(self) -> None:
        run_id = self.create_run()
        self.add_task(run_id, "one", [])
        self.add_task(run_id, "two", [])
        one = self.manager.create(run_id, "one")
        two = self.manager.create(run_id, "two")
        self.assertEqual("created-disposable", one["status"])
        self.assertEqual("created-disposable", two["status"])
        self.assertNotEqual(one["workspace"], two["workspace"])
        self.assertNotEqual(str(self.repo), one["workspace"])
        self.assertTrue((Path(one["workspace"]) / ".git").is_file())
        state = self.store.load(run_id)
        self.assertEqual(2, len({task["workspace"] for task in state["tasks"]}))

    def test_collect_rejects_out_of_scope_change(self) -> None:
        run_id = self.create_run()
        self.add_task(run_id, "scoped", ["README.md"])
        created = self.manager.create(run_id, "scoped")
        (Path(created["workspace"]) / "outside.txt").write_text("escape\n", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeFailure, "out-of-scope"):
            self.manager.collect(run_id, "scoped")

    def test_collect_rejects_secret_looking_patch(self) -> None:
        run_id = self.create_run()
        self.add_task(run_id, "secret", ["README.md"])
        created = self.manager.create(run_id, "secret")
        (Path(created["workspace"]) / "README.md").write_text(
            "sk-1234567890ABCDEFGHIJKLMN\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(RuntimeFailure, "secret material"):
            self.manager.collect(run_id, "secret")

    def test_collect_captures_already_staged_changes(self) -> None:
        # Regression for Finding #7a: `git diff` (no ref) is empty whenever a change is fully
        # staged (working tree == index), so collecting a candidate patch from it silently
        # drops any content a worker already `git add`-ed. Diffing against HEAD instead must
        # capture staged content just as reliably as unstaged content.
        run_id = self.create_run()
        self.add_task(run_id, "staged", ["README.md"])
        created = self.manager.create(run_id, "staged")
        workspace = Path(created["workspace"])
        (workspace / "README.md").write_text("staged change\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=workspace, check=True, capture_output=True, text=True)
        candidate = self.manager.collect(run_id, "staged")
        patch_text = (self.repo / candidate["patch"]).read_text(encoding="utf-8")
        self.assertIn("staged change", patch_text)
        self.assertIn("README.md", candidate["changedPaths"])

    def test_coordinator_integration_applies_scoped_patch_and_records_artifact(self) -> None:
        run_id = self.create_run()
        self.add_task(run_id, "integrate", ["README.md"])
        created = self.manager.create(run_id, "integrate")
        (Path(created["workspace"]) / "README.md").write_text("after\n", encoding="utf-8")
        self.store.start_task(run_id, "integrate", worker_id="worker-integrate")
        self.store.finish_worker(run_id, "integrate", worker_id="worker-integrate", status="FINISHED")
        result = self.manager.integrate(run_id, "integrate", confirmed=True)
        self.assertEqual("integrated", result["status"])
        self.assertEqual("after\n", (self.repo / "README.md").read_text(encoding="utf-8"))
        state = self.store.load(run_id)
        self.assertGreaterEqual(len(state["artifacts"]), 2)
        self.assertEqual("workspace.integrated", self.store.events(run_id)[-1]["type"])

    def test_cleanup_refuses_active_or_dirty_workspace_without_force(self) -> None:
        run_id = self.create_run()
        self.add_task(run_id, "active", ["README.md"])
        created = self.manager.create(run_id, "active")
        (Path(created["workspace"]) / "README.md").write_text("dirty\n", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeFailure, "active task"):
            self.manager.cleanup(run_id, "active")
        removed = self.manager.cleanup(run_id, "active", force=True)
        self.assertEqual("removed", removed["status"])
        self.assertFalse(Path(created["workspace"]).exists())

    def test_concurrent_mutating_tasks_cannot_share_unassigned_source(self) -> None:
        run_id = self.create_run()
        self.add_task(run_id, "one", ["README.md"])
        self.add_task(run_id, "two", ["allowed/**"])
        self.store.start_task(run_id, "one", worker_id="worker-one")
        with self.assertRaisesRegex(RuntimeFailure, "isolated assigned workspaces"):
            self.store.start_task(run_id, "two", worker_id="worker-two")

    def test_concurrent_mutating_tasks_with_overlapping_scopes_are_serialized(self) -> None:
        run_id = self.create_run()
        self.add_task(run_id, "one", ["README.md"])
        self.add_task(run_id, "two", ["README.md"])
        self.manager.create(run_id, "one")
        self.manager.create(run_id, "two")
        self.store.start_task(run_id, "one", worker_id="worker-one")
        with self.assertRaisesRegex(RuntimeFailure, "overlapping mutable paths"):
            self.store.start_task(run_id, "two", worker_id="worker-two")

    def test_overlapping_mutable_scopes_are_serialized_across_runs(self) -> None:
        first_run = self.create_run()
        second_run = self.create_run()
        self.add_task(first_run, "one", ["README.md"])
        self.add_task(second_run, "two", ["README.md"])
        self.manager.create(first_run, "one")
        self.manager.create(second_run, "two")
        self.store.start_task(first_run, "one", worker_id="worker-one")
        with self.assertRaisesRegex(RuntimeFailure, "another Run"):
            self.store.start_task(second_run, "two", worker_id="worker-two")

    def test_concurrent_cross_run_starts_allow_exactly_one_overlap(self) -> None:
        first_run = self.create_run()
        second_run = self.create_run()
        self.add_task(first_run, "one", ["README.md"])
        self.add_task(second_run, "two", ["README.md"])
        self.manager.create(first_run, "one")
        self.manager.create(second_run, "two")
        barrier = threading.Barrier(2)
        outcomes: list[str] = []

        def start(run_id: str, task_id: str, worker_id: str) -> None:
            barrier.wait()
            try:
                self.store.start_task(run_id, task_id, worker_id=worker_id)
            except RuntimeFailure as exc:
                outcomes.append(exc.code)
            else:
                outcomes.append("STARTED")

        first = threading.Thread(target=start, args=(first_run, "one", "worker-one"))
        second = threading.Thread(target=start, args=(second_run, "two", "worker-two"))
        first.start()
        second.start()
        first.join(timeout=5)
        second.join(timeout=5)
        self.assertFalse(first.is_alive() or second.is_alive())
        self.assertEqual(["RESOURCE_CONFLICT", "STARTED"], sorted(outcomes))

    def test_uncertain_workspace_integration_cannot_replay(self) -> None:
        run_id = self.create_run()
        self.add_task(run_id, "integrate", ["README.md"])
        created = self.manager.create(run_id, "integrate")
        (Path(created["workspace"]) / "README.md").write_text("after\n", encoding="utf-8")
        self.store.start_task(run_id, "integrate", worker_id="worker-integrate")
        self.store.finish_worker(run_id, "integrate", worker_id="worker-integrate", status="FINISHED")
        candidate = self.manager.collect(run_id, "integrate")
        self.store.prepare_side_effect(
            run_id,
            "integrate",
            operation="edit",
            target="repository",
            confirmed=True,
        )
        with self.assertRaisesRegex(RuntimeFailure, "wrong producer"):
            self.store.reconcile_side_effect(
                run_id,
                "integrate",
                result="not-applied",
                evidence_ref=candidate["patchArtifactRef"],
            )
        with self.assertRaisesRegex(RuntimeFailure, "already uncertain"):
            self.manager.integrate(run_id, "integrate", confirmed=True)
        self.assertEqual("before\n", (self.repo / "README.md").read_text(encoding="utf-8"))
        self.assertTrue((self.repo / candidate["patch"]).is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)