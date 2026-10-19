#!/usr/bin/env python3
"""Authenticated Run relocation fixtures; never uses an installed/product Run."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))

from architrave_runtime import RunStore, RuntimeFailure


class ReconciliationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name).resolve() / "source"
        self.target = Path(self.temp.name).resolve() / "verified"
        self.source.mkdir()
        self.git(self.source, "init", "-q")
        self.git(self.source, "config", "user.name", "Fixture")
        self.git(self.source, "config", "user.email", "fixture@example.invalid")
        self.git(self.source, "config", "core.autocrlf", "false")
        (self.source / ".gitignore").write_text(".architrave/\nignored-output\n")
        (self.source / "product").write_text("baseline\n")
        self.git(self.source, "add", ".")
        self.git(self.source, "commit", "-qm", "baseline")
        self.baseline = self.git(self.source, "rev-parse", "HEAD")
        self.store = RunStore(self.source)
        state = self.store.create(goal="fixture", outcome="fixture", criteria=[
            {"id": "FIXTURE", "description": "fixture", "scope": "fixture", "risk": "R1",
             "verificationType": "deterministic", "status": "UNTESTED", "evidenceRefs": [], "blocking": True},
        ], run_id="canonical",
                                  policy_allow=[{"scope": "repository", "operations": ["edit"]}])
        self.run_id = state["runId"]
        # A verified product commit exists in a linked worktree, while source HEAD
        # and the authenticated Run baseline independently lag behind.
        (self.source / "product").write_text("old source HEAD\n")
        self.git(self.source, "commit", "-qam", "source HEAD")
        self.source_commit = self.git(self.source, "rev-parse", "HEAD")
        self.git(self.source, "worktree", "add", "-q", "-b", "verified", str(self.target))
        (self.target / "product").write_text("verified product\n")
        self.git(self.target, "commit", "-qam", "verified")
        self.target_commit = self.git(self.target, "rev-parse", "HEAD")
        (self.source / "product").write_bytes(b"dirty staged\0bytes\n")
        self.git(self.source, "add", "product")
        (self.source / "product").write_bytes(b"dirty unstaged\0bytes\n")
        (self.source / "untracked").write_bytes(b"keep exactly\n")
        (self.source / "ignored-output").write_bytes(b"keep ignored too\n")
        evidence = self.store.run_dir(self.run_id) / "evidence.json"
        evidence.write_text('{"status":"fixture"}\n')
        self.store.record_artifact(self.run_id, artifact_id="history", kind="note",
                                   path=evidence.relative_to(self.source).as_posix())

    @staticmethod
    def git(repo: Path, *args: str) -> str:
        return subprocess.run(["git", "--no-optional-locks", *args], cwd=repo, capture_output=True,
                              text=True, check=True).stdout.strip()

    def options(self) -> dict:
        return dict(destination=self.target, source_commit=self.source_commit, baseline_commit=self.baseline,
                    destination_commit=self.target_commit, revision=self.store.load(self.run_id)["revision"],
                    principal="owner", provider="user-direction", actor="human:owner")

    def request(self) -> dict:
        options = self.options()
        state, challenge = self.store.request_worktree_reconciliation(self.run_id, **options, reason="Use verified worktree")
        return {**options, "revision": state["revision"], "challenge": challenge}

    def source_bytes(self) -> dict:
        result = {}
        for path in self.source.rglob("*"):
            relative = path.relative_to(self.source)
            if relative.parts[0] == ".architrave":
                continue
            if path.is_symlink():
                result[relative.as_posix()] = ("link", os.readlink(path))
            elif path.is_file():
                result[relative.as_posix()] = (path.stat().st_mode, path.read_bytes())
        return result

    def assert_code(self, code: str, call, *args, **kwargs) -> None:
        with self.assertRaises(RuntimeFailure) as caught:
            call(*args, **kwargs)
        self.assertEqual(code, caught.exception.code, str(caught.exception))

    def test_same_run_clean_binding_authenticated_history_and_source_bytes(self) -> None:
        # Pending human holds must survive migration, not turn into approval.
        self.store.add_task(self.run_id, {
            "id": "hold", "title": "hold", "objective": "human hold", "pushback": "KEEP:fixture",
            "dependencies": [], "workerProfile": "shell", "mutablePaths": [], "tools": [],
            "risk": "R1", "acceptanceCriteria": ["FIXTURE"], "requiredArtifacts": [], "gate": "fixture", "maxAttempts": 1,
        })
        self.store.wait_external(self.run_id, checkpoint_id="human", task_id="hold",
                                 checkpoint_type="HUMAN_JUDGMENT_REQUIRED", principal="owner",
                                 provider="user-direction", reason="Actual approval remains outstanding")
        self.store.add_task(self.run_id, {
            "id": "policy", "title": "policy", "objective": "policy hold", "pushback": "KEEP:fixture",
            "dependencies": [], "workerProfile": "shell", "mutablePaths": ["product"], "tools": [],
            "risk": "R1", "acceptanceCriteria": ["FIXTURE"], "requiredArtifacts": [], "gate": "fixture", "maxAttempts": 1,
        })
        self.store.request_policy_amendment(
            self.run_id, checkpoint_id="pending-policy", task_id="policy", principal="owner",
            provider="user-direction", delta={"addConfirmationRequired": ["edit"]},
            reason="Actual policy decision remains outstanding", actor="human:owner",
        )
        original = self.store.load(self.run_id)
        original_bytes = self.source_bytes()
        original_events = (self.store.run_dir(self.run_id) / "events.jsonl").read_bytes()
        key_bytes = self.store.key_path.read_bytes()
        options = self.request()
        reconciled = self.store.reconcile_worktree(self.run_id, **options)
        target_store = RunStore(self.target)
        self.assertEqual(original_bytes, self.source_bytes())
        self.assertEqual(key_bytes, self.store.key_path.read_bytes())
        self.assertFalse(target_store.key_path.exists())
        self.assertFalse((self.store.runs_root / self.run_id).exists())
        self.assertEqual(self.target_commit, reconciled["baseline"]["commit"])
        self.assertEqual(str(self.target.resolve()), reconciled["baseline"]["repository"])
        self.assertEqual("verified", reconciled["baseline"]["branch"])
        self.assertEqual("", self.git(self.target, "status", "--porcelain"))
        for task in original["tasks"]:
            task["workPacket"]["repoScope"] = str(self.target)
        for field in original:
            if field not in {"baseline", "revision", "updatedAt", "eventCursor"}:
                self.assertEqual(original[field], reconciled[field], field)
        events_path = target_store.run_dir(self.run_id) / "events.jsonl"
        self.assertTrue(events_path.read_bytes().startswith(original_events))
        events = target_store.events(self.run_id)
        self.assertEqual(["run.reconciliation_requested", "run.reconciled"], [event["type"] for event in events[-2:]])
        self.assertEqual(events[-2]["hash"], events[-1]["previousHash"])
        # Full state, artifact attestations and old/new events validate under the
        # original authority; further transitions continue that exact chain.
        self.assertEqual(reconciled, target_store.load(self.run_id))
        target_store.policy_check(self.run_id, "repository", "deploy")
        self.assertEqual(events[-1]["hash"], target_store.events(self.run_id)[-1]["previousHash"])
        self.assertEqual(original["policy"], target_store.load(self.run_id)["policy"])
        self.assertEqual(original["externalCheckpoints"], target_store.load(self.run_id)["externalCheckpoints"])
        self.assert_code("RUN_NOT_FOUND", self.store.load, self.run_id)
        self.assert_code("RUNTIME_CONTEXT_READ_ONLY", target_store.create, goal="no fork", outcome="no fork", criteria=[])

    def test_cli_request_apply_and_target_resume(self) -> None:
        def cli(repo: Path, command: str, *extra: str) -> dict:
            result = subprocess.run([sys.executable, str(ROOT / "harness/architrave_runtime.py"),
                                     "--repo", str(repo), command, self.run_id, *extra],
                                    capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            return json.loads(result.stdout)["result"]
        options = self.options()
        common = ["--destination", str(self.target), "--source-commit", self.source_commit,
                  "--baseline-commit", self.baseline, "--destination-commit", self.target_commit,
                  "--principal", "owner", "--provider", "user-direction", "--actor", "human:owner"]
        requested = cli(self.source, "reconcile-worktree-request", *common,
                        "--revision", str(options["revision"]), "--reason", "owner directed")
        cli(self.source, "reconcile-worktree", *common, "--revision", str(requested["revision"]),
            "--challenge", requested["resolutionChallenge"])
        cli(self.target, "resume")
        self.assertEqual(self.target_commit, RunStore(self.target).load(self.run_id)["baseline"]["commit"])

    def test_wrong_commits_repositories_revision_and_dirty_target_rejected(self) -> None:
        options = self.options()
        for field in ("source_commit", "baseline_commit", "destination_commit"):
            with self.subTest(field=field):
                bad = {**options, field: "0" * 40}
                self.assert_code("RECONCILIATION_STALE", self.store.request_worktree_reconciliation,
                                 self.run_id, **bad, reason="fixture")
        self.assert_code("RECONCILIATION_COMMIT", self.store.request_worktree_reconciliation,
                         self.run_id, **{**options, "destination_commit": self.target_commit[:8]}, reason="fixture")
        self.assert_code("RECONCILIATION_STALE", self.store.request_worktree_reconciliation,
                         self.run_id, **{**options, "revision": options["revision"] - 1}, reason="fixture")
        for name in ("product", "untracked", "ignored-output"):
            with self.subTest(name=name):
                path = self.target / name
                before = path.read_bytes() if path.exists() else None
                path.write_bytes(b"not the verified commit\n")
                self.assert_code("RECONCILIATION_DIRTY", self.store.request_worktree_reconciliation,
                                 self.run_id, **options, reason="fixture")
                if before is None:
                    path.unlink()
                else:
                    path.write_bytes(before)
        clone = Path(self.temp.name) / "clone"
        self.git(self.source, "clone", "-q", "--no-hardlinks", str(self.source), str(clone))
        self.git(clone, "checkout", "-q", self.target_commit)
        self.assert_code("RECONCILIATION_REPOSITORY", self.store.request_worktree_reconciliation,
                         self.run_id, **{**options, "destination": clone}, reason="fixture")

    def test_status_hidden_dirty_bytes_rejected(self) -> None:
        self.git(self.target, "update-index", "--assume-unchanged", "product")
        (self.target / "product").write_bytes(b"hidden dirty bytes\n")
        self.assertEqual("", self.git(self.target, "status", "--porcelain"))
        self.assert_code("RECONCILIATION_DIRTY", self.store.request_worktree_reconciliation,
                         self.run_id, **self.options(), reason="fixture")

    def test_authority_identity_staleness_and_replay_rejected(self) -> None:
        options = self.request()
        original = self.source_bytes()
        for field, value in (("challenge", "wrong"), ("principal", "other"), ("provider", "other"),
                             ("actor", "coordinator"), ("revision", options["revision"] - 1)):
            with self.subTest(field=field):
                self.assert_code("RECONCILIATION_AUTHORITY", self.store.reconcile_worktree,
                                 self.run_id, **{**options, field: value})
        self.git(self.target, "checkout", "-qb", "renamed-identity")
        self.assert_code("RECONCILIATION_STALE", self.store.reconcile_worktree, self.run_id, **options)
        self.git(self.target, "checkout", "-q", "verified")
        (self.source / "untracked").write_bytes(b"changed after owner confirmation\n")
        self.assert_code("RECONCILIATION_STALE", self.store.reconcile_worktree, self.run_id, **options)
        (self.source / "untracked").write_bytes(original["untracked"][1])
        self.store.policy_check(self.run_id, "repository", "observe")
        self.assert_code("RECONCILIATION_AUTHORITY", self.store.reconcile_worktree, self.run_id, **options)
        options = self.request()
        self.store.reconcile_worktree(self.run_id, **options)
        self.assert_code("RUN_NOT_FOUND", self.store.reconcile_worktree, self.run_id, **options)

    def test_key_run_event_artifact_and_context_tampering_fail_closed(self) -> None:
        options = self.request()
        key = self.store.key_path.read_bytes()
        self.store.key_path.write_bytes(b"x" * 32)
        self.assert_code("EVENT_LOG_TAMPERED", self.store.reconcile_worktree, self.run_id, **options)
        self.store.key_path.write_bytes(key)
        self.store.reconcile_worktree(self.run_id, **options)
        target = RunStore(self.target)
        descriptor = self.target / ".architrave/runtime-context.json"
        context = json.loads(descriptor.read_text())
        for field, value in (("transitionHash", "0" * 64), ("runId", "other"), ("repository", str(self.source))):
            descriptor.write_text(json.dumps({**context, field: value}))
            self.assert_code("RUNTIME_CONTEXT_INVALID", target.load, self.run_id)
        descriptor.write_text(json.dumps(context))
        artifact = target.run_dir(self.run_id) / "evidence.json"
        artifact.write_text("tampered\n")
        self.assert_code("ARTIFACT_TAMPERED", target.load, self.run_id)

    def test_active_or_uncertain_work_and_existing_target_context_rejected(self) -> None:
        original = self.store.load(self.run_id)
        # Exercise every rejected state without persisting fabricated runtime
        # transitions: the guard is also called on each authenticated loaded Run.
        for task in (
            {"id": "active", "status": "RUNNING"},
            {"id": "leased", "status": "READY", "lease": {"owner": "worker"}},
            {"id": "pending", "status": "READY", "sideEffect": {"state": "PENDING"}},
            {"id": "uncertain", "status": "FAILED", "sideEffect": {"state": "UNCERTAIN"}},
            {"id": "workspace", "status": "READY", "workspace": "/old/workspace"},
        ):
            candidate = copy.deepcopy(original)
            candidate["tasks"] = [task]
            self.assert_code("RECONCILIATION_UNSAFE", self.store._assert_reconciliation_quiescent, candidate)
        candidate = copy.deepcopy(original)
        candidate["workers"] = [{"id": "orphan", "status": "RUNNING"}]
        self.assert_code("RECONCILIATION_UNSAFE", self.store._assert_reconciliation_quiescent, candidate)
        (self.target / ".architrave").mkdir()
        self.assert_code("RECONCILIATION_CONTEXT", self.store.request_worktree_reconciliation,
                         self.run_id, **self.options(), reason="fixture")

    def test_interrupted_rename_retries_without_new_approval_or_source_execution(self) -> None:
        options = self.request()
        original = self.source_bytes()
        with mock.patch("architrave_runtime.os.rename", side_effect=OSError("fixture interruption")):
            self.assert_code("RECONCILIATION_PENDING", self.store.reconcile_worktree, self.run_id, **options)
        self.assertEqual(original, self.source_bytes())
        self.assert_code("STALE_REPOSITORY", self.store.policy_check, self.run_id, "repository", "edit")
        state = self.store.reconcile_worktree(self.run_id, **options)
        self.assertEqual(self.target_commit, state["baseline"]["commit"])
        events = RunStore(self.target).events(self.run_id)
        self.assertEqual(1, sum(event["type"] == "run.reconciled" for event in events))

    def test_interrupted_run_move_reuses_authenticated_destination_reservation(self) -> None:
        options = self.request()
        rename = os.rename

        def interrupt_run_move(source, destination):
            if Path(source).name == self.run_id:
                raise OSError("interrupted after atomic context reservation")
            return rename(source, destination)

        with mock.patch("architrave_runtime.os.rename", side_effect=interrupt_run_move):
            self.assert_code("RECONCILIATION_PENDING", self.store.reconcile_worktree, self.run_id, **options)
        self.assertTrue((self.target / ".architrave/runtime-context.json").is_file())
        self.store.reconcile_worktree(self.run_id, **options)
        self.assertEqual(self.target_commit, RunStore(self.target).load(self.run_id)["baseline"]["commit"])

    def test_target_and_source_drift_after_request_are_not_accepted(self) -> None:
        options = self.request()
        (self.target / "product").write_bytes(b"dirty after request\n")
        self.assert_code("RECONCILIATION_DIRTY", self.store.reconcile_worktree, self.run_id, **options)
        (self.target / "product").write_bytes(b"verified product\n")
        (self.source / "ignored-output").write_bytes(b"ignored source bytes also bound\n")
        self.assert_code("RECONCILIATION_STALE", self.store.reconcile_worktree, self.run_id, **options)
        self.assertFalse((self.target / ".architrave").exists())

    def test_historical_external_evidence_must_match_without_copying(self) -> None:
        evidence = self.source / "untracked"
        self.store.record_artifact(self.run_id, artifact_id="external", kind="note", path="untracked")
        self.assert_code("RECONCILIATION_EVIDENCE", self.store.request_worktree_reconciliation,
                         self.run_id, **self.options(), reason="fixture")
        self.assertEqual(b"keep exactly\n", evidence.read_bytes())

    def test_unrelated_history_in_same_git_repository_rejected(self) -> None:
        self.git(self.target, "checkout", "-q", "--orphan", "unrelated")
        self.git(self.target, "add", ".")
        self.git(self.target, "commit", "-qm", "unrelated root")
        options = {**self.options(), "destination_commit": self.git(self.target, "rev-parse", "HEAD")}
        self.assert_code("RECONCILIATION_REPOSITORY", self.store.request_worktree_reconciliation,
                         self.run_id, **options, reason="fixture")

    def test_original_key_missing_or_replaced_remains_fail_closed_at_destination(self) -> None:
        options = self.request()
        self.store.reconcile_worktree(self.run_id, **options)
        key = self.store.key_path.read_bytes()
        self.store.key_path.unlink()
        self.assert_code("RUNTIME_KEY_MISSING", RunStore(self.target).load, self.run_id)
        self.store.key_path.write_bytes(b"z" * 32)
        self.store.key_path.chmod(0o600)
        self.assert_code("EVENT_LOG_TAMPERED", RunStore(self.target).load, self.run_id)
        self.store.key_path.write_bytes(key)
        self.assertEqual(self.run_id, RunStore(self.target).load(self.run_id)["runId"])

    def test_request_tampering_is_detected_before_any_target_change(self) -> None:
        options = self.request()
        events_path = self.store.run_dir(self.run_id) / "events.jsonl"
        events = [json.loads(line) for line in events_path.read_text().splitlines()]
        events[-1]["payload"]["binding"]["destination"]["commit"] = "0" * 40
        events_path.write_text("\n".join(json.dumps(event) for event in events) + "\n")
        self.assert_code("EVENT_LOG_TAMPERED", self.store.reconcile_worktree, self.run_id, **options)
        self.assertFalse((self.target / ".architrave").exists())

    def test_reconciled_worker_and_observed_gate_execute_verified_bytes(self) -> None:
        from worker_adapters import execute_work_packet
        from workspaces import WorkspaceManager

        self.store.add_task(self.run_id, {
            "id": "product", "title": "verify product", "objective": "verify bytes", "pushback": "KEEP:fixture",
            "dependencies": [], "workerProfile": "shell", "mutablePaths": [], "tools": [],
            "risk": "R1", "acceptanceCriteria": ["FIXTURE"], "requiredArtifacts": [], "gate": "fixture", "maxAttempts": 1,
            "workPacket": {"execution": {"command": [
                sys.executable, "-c",
                "from pathlib import Path; assert Path('product').read_bytes() == b'verified product\\n'",
            ]}},
        })
        self.store.reconcile_worktree(self.run_id, **self.request())
        target = RunStore(self.target)
        WorkspaceManager(self.target).create(self.run_id, "product")
        target.start_task(self.run_id, "product", worker_id="fixture-worker")
        result = execute_work_packet(target, self.run_id, "product", "fixture-worker")
        self.assertEqual("candidate", result["status"])
        gate = target.execute_gate(self.run_id, "product", recipe="task")
        self.assertEqual("PASS", gate["status"])
        self.assertEqual(self.target_commit, gate["source"]["commit"])
        target.assert_gate_sources_current(target.load(self.run_id), [gate["gateRef"]])
        (self.target / "product").write_bytes(b"changed after gate\n")
        self.assert_code("EVIDENCE_SOURCE_STALE", target.assert_gate_sources_current,
                         target.load(self.run_id), [gate["gateRef"]])

    def test_failed_workspace_recovery_rebinds_packet_to_destination(self) -> None:
        from worker_adapters import execute_work_packet
        from workspaces import WorkspaceManager

        self.store.resume(self.run_id, accept_commit=True)
        self.baseline = self.source_commit
        self.store.add_task(self.run_id, {
            "id": "failed", "title": "failed fixture", "objective": "recover candidate", "pushback": "KEEP:fixture",
            "dependencies": [], "workerProfile": "shell", "mutablePaths": [], "tools": [],
            "risk": "R1", "acceptanceCriteria": ["FIXTURE"], "requiredArtifacts": [], "gate": "fixture", "maxAttempts": 1,
            "workPacket": {"execution": {"command": [sys.executable, "-c", "raise SystemExit(1)"]}},
        })
        WorkspaceManager(self.source).create(self.run_id, "failed")
        self.store.start_task(self.run_id, "failed", worker_id="failed-worker")
        self.assert_code("RECONCILIATION_UNSAFE", self.store.request_worktree_reconciliation,
                         self.run_id, **self.options(), reason="active workers cannot relocate")
        execute_work_packet(self.store, self.run_id, "failed", "failed-worker")
        self.store.reconcile_worktree(self.run_id, **self.request())
        recovered = RunStore(self.target).recover_workers(self.run_id, task_id="failed")
        task = recovered["tasks"][0]
        self.assertEqual("READY", task["status"])
        self.assertIsNone(task["workspace"])
        self.assertEqual(str(self.target), task["workPacket"]["repoScope"])

    def test_destination_drift_during_signing_does_not_report_success(self) -> None:
        options = self.request()
        commit = self.store._commit_locked

        def drift(*args, **kwargs):
            state = commit(*args, **kwargs)
            (self.target / "product").write_bytes(b"changed during transition\n")
            return state

        with mock.patch.object(self.store, "_commit_locked", side_effect=drift):
            self.assert_code("RECONCILIATION_STALE", self.store.reconcile_worktree, self.run_id, **options)
        self.assertFalse((self.target / ".architrave").exists())
        self.assert_code("STALE_REPOSITORY", self.store.policy_check, self.run_id, "repository", "edit")
        (self.target / "product").write_bytes(b"verified product\n")
        self.store.reconcile_worktree(self.run_id, **options)


if __name__ == "__main__":
    unittest.main(verbosity=2)
