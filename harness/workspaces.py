#!/usr/bin/env python3
"""Isolated WorkPacket workspaces and coordinator integration."""

from __future__ import annotations

import argparse
import contextlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
from typing import Any, Sequence

from architrave_runtime import RunStore, RuntimeFailure, find_task, redact
from worker_adapters import git_status, path_allowed


def git(repository: Path, arguments: Sequence[str], *, input_text: str | None = None) -> str:
    process = subprocess.run(
        ["git", *arguments],
        cwd=repository,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeFailure(
            "GIT_WORKSPACE",
            process.stderr.strip() or process.stdout.strip() or f"git {' '.join(arguments)} failed",
        )
    return process.stdout


def load_worker_config(repository: Path) -> dict[str, Any]:
    path = repository / "architrave.config.json"
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeFailure("CONFIG_INVALID", f"invalid JSON config: {exc}") from exc
    return value.get("workers") or {}


class WorkspaceManager:
    def __init__(self, repository: Path | str):
        self.repository = Path(repository).resolve()
        self.store = RunStore(self.repository)
        workers = load_worker_config(self.repository)
        configured = Path(workers.get("worktreeRoot") or ".architrave/worktrees")
        if configured.is_absolute() or ".." in configured.parts:
            raise RuntimeFailure("PATH_ESCAPE", "workers.worktreeRoot must stay inside the repository")
        self.worktree_root = (self.repository / configured).resolve()
        try:
            self.worktree_root.relative_to(self.repository)
        except ValueError as exc:
            raise RuntimeFailure("PATH_ESCAPE", "workers.worktreeRoot escapes the repository") from exc

    def create(self, run_id: str, task_id: str) -> dict[str, Any]:
        state = self.store.load(run_id)
        task = find_task(state, task_id)
        if task["status"] not in {"NOT_READY", "READY"}:
            raise RuntimeFailure("WORKSPACE_LATE_ASSIGNMENT", "workspace must be created before task start")
        # Every task -- mutating or read-only -- executes untrusted worker code against a
        # disposable detached worktree, never the live checkout. Read-only tasks still need
        # isolation: a worker may forge canonical Run state or read secrets (e.g. the runtime
        # signing key) if it can reach the coordinator's real working tree.
        path = (self.worktree_root / run_id / task_id).resolve()
        try:
            path.relative_to(self.worktree_root)
        except ValueError as exc:
            raise RuntimeFailure("PATH_ESCAPE", "worktree path escapes configured root") from exc
        if path.exists():
            raise RuntimeFailure("WORKSPACE_EXISTS", f"workspace already exists: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        git(self.repository, ["worktree", "add", "--detach", str(path), state["baseline"]["commit"]])
        self.store.assign_workspace(run_id, task_id, str(path))
        status = "created" if task["mutablePaths"] else "created-disposable"
        return {"status": status, "workspace": str(path), "taskId": task_id, "commit": state["baseline"]["commit"]}

    def collect(self, run_id: str, task_id: str) -> dict[str, Any]:
        state = self.store.load(run_id)
        task = find_task(state, task_id)
        if not task.get("workspace"):
            raise RuntimeFailure("WORKSPACE_NOT_ASSIGNED", "task has no assigned workspace")
        workspace = Path(task["workspace"]).resolve()
        if workspace == self.repository:
            raise RuntimeFailure("WORKSPACE_NOT_ISOLATED", "candidate collection requires an isolated worktree")
        changed = sorted(git_status(workspace))
        escaped = [path for path in changed if not path_allowed(path, task["mutablePaths"])]
        if escaped:
            raise RuntimeFailure(
                "MUTABLE_PATH_ESCAPE",
                "workspace contains out-of-scope changes",
                details={"paths": escaped},
            )
        git(workspace, ["add", "-N", "."])
        # Diff against HEAD (not the index) so changes already staged by the worker -- not just
        # the working-tree-vs-index delta -- are captured in the candidate patch.
        patch = git(workspace, ["diff", "HEAD", "--binary"])
        redacted_patch = redact(patch)
        if redacted_patch != patch:
            raise RuntimeFailure("SECRET_IN_PATCH", "candidate patch appears to contain secret material")
        run_dir = self.store.run_dir(run_id)
        artifact_dir = run_dir / "workspaces" / task_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        patch_path = artifact_dir / "candidate.patch"
        status_path = artifact_dir / "status.json"
        patch_path.write_text(patch, encoding="utf-8")
        status_path.write_text(json.dumps({"changedPaths": changed}, indent=2) + "\n", encoding="utf-8")
        suffix = uuid.uuid4().hex[:10]
        patch_artifact_id = f"workspace-patch-{task_id}-{suffix}"
        self.store._record_workspace_artifact(
            run_id,
            artifact_id=patch_artifact_id,
            kind="candidate-patch",
            path=patch_path.relative_to(self.repository).as_posix(),
            evidence_refs=[f"task:{task_id}"],
        )
        self.store._record_workspace_artifact(
            run_id,
            artifact_id=f"workspace-status-{task_id}-{suffix}",
            kind="workspace-status",
            path=status_path.relative_to(self.repository).as_posix(),
            evidence_refs=[f"task:{task_id}"],
        )
        return {
            "status": "candidate",
            "taskId": task_id,
            "workspace": str(workspace),
            "changedPaths": changed,
            "patch": patch_path.relative_to(self.repository).as_posix(),
            "patchArtifactRef": f"artifact:{patch_artifact_id}",
            "statusArtifact": status_path.relative_to(self.repository).as_posix(),
        }

    def integrate(self, run_id: str, task_id: str, *, confirmed: bool = False) -> dict[str, Any]:
        state = self.store.load(run_id)
        task = find_task(state, task_id)
        decision = self.store.policy_check(run_id, "repository", "edit", confirmed=confirmed)
        if decision["status"] != "allowed":
            raise RuntimeFailure("MUTATION_DENIED", f"workspace integration is {decision['status']}", details=decision)
        dirty_main = git_status(self.repository)
        overlap = sorted(path for path in dirty_main if path_allowed(path, task["mutablePaths"]))
        if overlap:
            raise RuntimeFailure(
                "INTEGRATION_COLLISION",
                "main workspace already has changes in mutable paths",
                details={"paths": overlap},
            )
        candidate = self.collect(run_id, task_id)
        patch_path = self.repository / candidate["patch"]
        patch = patch_path.read_text(encoding="utf-8")
        if not patch.strip():
            raise RuntimeFailure("EMPTY_CANDIDATE", "candidate patch is empty")
        git(self.repository, ["apply", "--check", "--binary", str(patch_path)])
        self.store.prepare_side_effect(
            run_id,
            task_id,
            operation="edit",
            target="repository",
            confirmed=confirmed,
        )
        git(self.repository, ["apply", "--binary", str(patch_path)])
        self.store.reconcile_side_effect(
            run_id,
            task_id,
            result="applied",
            evidence_ref=candidate["patchArtifactRef"],
        )

        def mark_integrated(run: dict[str, Any]) -> dict[str, Any]:
            current = find_task(run, task_id)
            return {"taskId": task_id, "workspace": current["workspace"], "patch": candidate["patch"]}

        self.store._transaction(
            run_id,
            mark_integrated,
            event_type="workspace.integrated",
            actor="coordinator",
            task_id=task_id,
            evidence_refs=[candidate["patchArtifactRef"]],
        )
        return {**candidate, "status": "integrated"}

    def cleanup(self, run_id: str, task_id: str, *, force: bool = False) -> dict[str, Any]:
        state = self.store.load(run_id)
        task = find_task(state, task_id)
        workspace_value = task.get("workspace")
        if not workspace_value:
            return {"status": "absent", "taskId": task_id}
        workspace = Path(workspace_value).resolve()
        if workspace == self.repository:
            return {"status": "shared", "taskId": task_id}
        if task["status"] not in {"COMPLETED", "FAILED", "SKIPPED", "CANCELLED"} and not force:
            raise RuntimeFailure("WORKSPACE_ACTIVE", "refusing to remove a workspace for an active task")
        if workspace.exists() and git_status(workspace) and not force:
            raise RuntimeFailure("WORKSPACE_DIRTY", "refusing to remove a dirty workspace without --force")
        git(self.repository, ["worktree", "remove", "--force" if force else str(workspace), *([str(workspace)] if force else [])])
        with contextlib.suppress(OSError):
            workspace.parent.rmdir()
        return {"status": "removed", "taskId": task_id, "workspace": str(workspace)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage isolated Architrave WorkPacket workspaces")
    parser.add_argument("--repo", default=".")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("create", "collect", "integrate", "cleanup"):
        current = subparsers.add_parser(command)
        current.add_argument("run_id")
        current.add_argument("task_id")
        if command == "integrate":
            current.add_argument("--confirmed", action="store_true")
        if command == "cleanup":
            current.add_argument("--force", action="store_true")
    return parser


def cli(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manager = WorkspaceManager(args.repo)
        if args.command == "create":
            result = manager.create(args.run_id, args.task_id)
        elif args.command == "collect":
            result = manager.collect(args.run_id, args.task_id)
        elif args.command == "integrate":
            result = manager.integrate(args.run_id, args.task_id, confirmed=args.confirmed)
        else:
            result = manager.cleanup(args.run_id, args.task_id, force=args.force)
        print(json.dumps({"status": "ok", "result": redact(result)}, indent=2))
        return 0
    except RuntimeFailure as exc:
        print(
            json.dumps(
                {"status": "failed", "error": {"code": exc.code, "message": exc.message, "details": redact(exc.details)}},
                indent=2,
            ),
            file=sys.stderr,
        )
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(cli())