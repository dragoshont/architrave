#!/usr/bin/env python3
"""Architrave durable Run v2 runtime.

The runtime deliberately uses only the Python standard library. Repository-local
JSON is canonical state; JSONL is a hash-chained audit log. Human-readable run
artifacts are projections and never drive state transitions.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import datetime as dt
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import uuid
import secrets
import stat
from typing import Any, Callable, Iterable, Iterator, Sequence


ZERO_HASH = "0" * 64
SCHEMA = "architrave.run.v2"
RUN_STATUSES = {
    "CREATED",
    "PLANNING",
    "RUNNING",
    "WAITING_EXTERNAL",
    "WAITING_RESOURCE",
    "WAITING_WORKER",
    "PAUSED",
    "RECOVERING",
    "VERIFYING",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
}
TASK_STATUSES = {
    "NOT_READY",
    "READY",
    "RUNNING",
    "WAITING_EXTERNAL",
    "WAITING_RESOURCE",
    "COMPLETED",
    "FAILED",
    "SKIPPED",
    "CANCELLED",
}
TERMINAL_TASK_STATUSES = {"COMPLETED", "FAILED", "SKIPPED", "CANCELLED"}
CRITERION_STATUSES = {"UNTESTED", "PASS", "FAIL", "BLOCKED_EXTERNAL", "NOT_APPLICABLE"}
RISK_CLASSES = {"R0", "R1", "R2", "R3", "R4"}
EXTERNAL_TYPES = {
    "AUTH_REQUIRED",
    "MFA_REQUIRED",
    "CONSENT_REQUIRED",
    "SAFE_WRITE_TARGET_REQUIRED",
    "SIGNING_REQUIRED",
    "HUMAN_JUDGMENT_REQUIRED",
}
EVENT_TYPE_RE = re.compile(r"^[a-z][a-z0-9_.-]+$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
SENSITIVE_KEY_RE = re.compile(
    r"(?:authorization|cookie|password|passwd|secret|token|api[_-]?key|private[_-]?key|session)",
    re.IGNORECASE,
)
SENSITIVE_VALUE_RES = (
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE),
    re.compile(r"\b(?:gh[pousr]_|github_pat_|sk-|cfut_)[A-Za-z0-9._-]{8,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)
ARTIFACT_PRODUCERS = {
    "coordinator",
    "deterministic",
    "invariant",
    "workspace",
    "worker",
    "legibility",
    "mutation",
    "reconciliation",
    "semantic-judge",
    "security-review",
    "policy-engine",
    "external-proof",
}
GATE_EVIDENCE_PRODUCERS = {
    "deterministic": {"deterministic", "invariant"},
    "e2e": {"legibility"},
    "reality": {"legibility", "mutation", "external-proof"},
    "semantic": {"semantic-judge"},
    "policy": {"policy-engine"},
    "security": {"security-review"},
}
PRODUCER_ARTIFACT_KINDS = {
    "deterministic": {"deterministic-result"},
    "invariant": {"invariant-result"},
    "workspace": {"candidate-patch", "workspace-status"},
    "worker": {"worker-result"},
    "mutation": {"mutation-receipt"},
    "reconciliation": {"reconciliation-receipt"},
    "semantic-judge": {"semantic-verdict"},
    "security-review": {"security-verdict"},
    "policy-engine": {"policy-decision"},
    "external-proof": {"external-proof"},
}
# Acceptance criteria declare a `verificationType`; this reconciles it with which gate `type`s
# may legitimately satisfy it (e2e and reality are treated as mutually satisfying, mirroring the
# "e2e-or-reality" bucket already used by DEFAULT_RISK_GATES) so a criterion cannot be marked PASS
# on the strength of a gate that never ran the kind of verification it claims.
CRITERION_GATE_TYPES = {
    "deterministic": {"deterministic"},
    "e2e": {"e2e", "reality"},
    "reality": {"e2e", "reality"},
    "semantic": {"semantic"},
}
# A reality/e2e criterion must own the exact product surface it verifies so a gate can never
# borrow one surface's evidence to satisfy a different surface's criterion. "deployment" and
# "runtime" cover the non-legibility reality producers (mutation, external-proof) below.
SURFACE_VALUES = {"web", "electron", "ios", "deployment", "runtime"}
SURFACE_VERIFICATION_TYPES = {"reality", "e2e"}


class RuntimeFailure(Exception):
    """A bounded runtime error suitable for structured CLI output."""

    def __init__(self, code: str, message: str, *, details: Any = None, exit_code: int = 1):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
        self.exit_code = exit_code


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_iso(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def redact(value: Any, key: str = "") -> Any:
    if key and SENSITIVE_KEY_RE.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(item_key): redact(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        redacted = value
        for pattern in SENSITIVE_VALUE_RES:
            redacted = pattern.sub("[REDACTED]", redacted)
        return redacted
    return value


def require_id(value: str, label: str) -> str:
    if not ID_RE.fullmatch(value):
        raise RuntimeFailure("INVALID_ID", f"{label} must match {ID_RE.pattern}")
    return value


def safe_relative_path(value: str, label: str = "path") -> str:
    path = Path(value)
    if not value or path.is_absolute() or ".." in path.parts:
        raise RuntimeFailure("PATH_ESCAPE", f"{label} must be a non-escaping repository-relative path")
    normalized = path.as_posix()
    if normalized in {".", ""}:
        raise RuntimeFailure("PATH_ESCAPE", f"{label} must identify a path below the repository root")
    return normalized


def run_command(args: Sequence[str], cwd: Path) -> str:
    try:
        completed = subprocess.run(
            list(args),
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeFailure("REPOSITORY_IDENTITY", f"failed to inspect repository: {' '.join(args)}") from exc
    return completed.stdout.strip()


class FileLock:
    def __init__(self, path: Path):
        self.path = path
        self.handle: Any = None

    def __enter__(self) -> "FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        if self.handle.tell() == 0:
            self.handle.write(b"0")
            self.handle.flush()
        self.handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(self.handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self.handle is None:
            return
        self.handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        self.handle.close()


class RunStore:
    def __init__(self, repository: Path | str):
        self.repository = Path(repository).resolve()
        self.runs_root = self.repository / ".architrave" / "runs"
        self.key_path = self.repository / ".architrave" / "runtime.key"

    def _runtime_key(self, *, create: bool = False) -> bytes:
        if create and not self.key_path.exists():
            self.key_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                descriptor = os.open(self.key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                pass
            else:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(secrets.token_bytes(32))
                    handle.flush()
                    os.fsync(handle.fileno())
        try:
            key_stat = self.key_path.lstat()
            if not stat.S_ISREG(key_stat.st_mode) or self.key_path.is_symlink():
                raise RuntimeFailure("RUNTIME_KEY_INVALID", "durable Run authentication key must be a regular file")
            if os.name != "nt" and ((key_stat.st_mode & 0o077) != 0 or key_stat.st_uid != os.getuid()):
                raise RuntimeFailure("RUNTIME_KEY_PERMISSIONS", "durable Run authentication key permissions or owner are unsafe")
            key = self.key_path.read_bytes()
        except OSError as exc:
            raise RuntimeFailure("RUNTIME_KEY_MISSING", "durable Run authentication key is unavailable") from exc
        if len(key) != 32:
            raise RuntimeFailure("RUNTIME_KEY_INVALID", "durable Run authentication key is invalid")
        return key

    def _state_hash(self, state: dict[str, Any]) -> str:
        semantic = {
            key: value
            for key, value in state.items()
            if key not in {"eventCursor", "pendingEvent"}
        }
        return hmac.new(self._runtime_key(), canonical_json(semantic).encode("utf-8"), hashlib.sha256).hexdigest()

    def _artifact_attestation(self, artifact: dict[str, Any]) -> str:
        unsigned = {key: value for key, value in artifact.items() if key != "attestation"}
        return hmac.new(self._runtime_key(), canonical_json(unsigned).encode("utf-8"), hashlib.sha256).hexdigest()

    def _verify_artifacts(self, state: dict[str, Any]) -> None:
        for artifact in state["artifacts"]:
            if artifact.get("producer") not in ARTIFACT_PRODUCERS:
                raise RuntimeFailure("ARTIFACT_TAMPERED", f"artifact producer is invalid: {artifact.get('id')}")
            if not hmac.compare_digest(str(artifact.get("attestation", "")), self._artifact_attestation(artifact)):
                raise RuntimeFailure("ARTIFACT_TAMPERED", f"artifact attestation failed: {artifact.get('id')}")
            relative = safe_relative_path(str(artifact.get("path", "")), "artifact path")
            path = (self.repository / relative).resolve()
            try:
                path.relative_to(self.repository)
            except ValueError as exc:
                raise RuntimeFailure("ARTIFACT_TAMPERED", "artifact path escapes repository") from exc
            if not path.is_file() or sha256_file(path) != artifact.get("sha256"):
                raise RuntimeFailure("ARTIFACT_TAMPERED", f"artifact content digest failed: {artifact.get('id')}")
            if artifact["producer"] == "legibility":
                receipt = self._read_json_receipt(artifact["path"], "legibility")
                for result in receipt.get("results") or []:
                    for source in result.get("artifacts") or []:
                        source_path = (self.repository / safe_relative_path(str(source.get("path", "")), "legibility source path")).resolve()
                        if not source_path.is_file() or sha256_file(source_path) != source.get("sha256"):
                            raise RuntimeFailure("ARTIFACT_TAMPERED", "legibility source artifact digest failed")

    def repository_identity(self) -> dict[str, Any]:
        root = Path(run_command(["git", "rev-parse", "--show-toplevel"], self.repository)).resolve()
        if root != self.repository:
            raise RuntimeFailure(
                "REPOSITORY_IDENTITY",
                "runtime must be invoked at the repository root",
                details={"expected": str(self.repository), "actual": str(root)},
            )
        commit = run_command(["git", "rev-parse", "HEAD"], self.repository)
        branch = run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"], self.repository)
        return {
            "repository": str(root),
            "commit": commit,
            "branch": branch,
            "deployment": None,
        }

    def _assert_repository_baseline(self, state: dict[str, Any]) -> None:
        identity = self.repository_identity()
        drift = {
            key: {"expected": state["baseline"].get(key), "actual": identity.get(key)}
            for key in ("repository", "commit", "branch")
            if state["baseline"].get(key) != identity.get(key)
        }
        if drift:
            raise RuntimeFailure("STALE_REPOSITORY", "repository baseline drift requires resume reconciliation", details=drift)

    def run_dir(self, run_id: str) -> Path:
        require_id(run_id, "run id")
        path = (self.runs_root / run_id).resolve()
        if path.parent != self.runs_root.resolve():
            raise RuntimeFailure("PATH_ESCAPE", "run id escapes the run root")
        return path

    def latest_run_id(self) -> str:
        if not self.runs_root.is_dir():
            raise RuntimeFailure("RUN_NOT_FOUND", "no durable runs exist", exit_code=2)
        candidates = [path for path in self.runs_root.iterdir() if path.is_dir() and (path / "run.json").is_file()]
        if not candidates:
            raise RuntimeFailure("RUN_NOT_FOUND", "no durable runs exist", exit_code=2)
        return max(candidates, key=lambda path: path.stat().st_mtime).name

    def _resolve_run_id(self, run_id: str | None) -> str:
        return run_id or self.latest_run_id()

    def _atomic_write(self, path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(value, handle, indent=2, sort_keys=False, ensure_ascii=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
            if os.name != "nt":
                directory_fd = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temp_name)

    def _write_snapshot(self, run_dir: Path, state: dict[str, Any]) -> None:
        snapshot_dir = run_dir / "snapshots"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        self._atomic_write(snapshot_dir / f"{state['revision']:012d}.json", state)

    def _restore_snapshot(
        self,
        run_dir: Path,
        run_id: str,
        events: Sequence[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if not events:
            return None
        expected_hash = events[-1]["payload"].get("stateHash")
        snapshot_dir = run_dir / "snapshots"
        for path in sorted(snapshot_dir.glob("*.json"), reverse=True) if snapshot_dir.is_dir() else []:
            try:
                candidate = json.loads(path.read_text(encoding="utf-8"))
                validate_run(candidate)
            except (OSError, json.JSONDecodeError, RuntimeFailure):
                continue
            if candidate.get("runId") != run_id:
                continue
            if candidate.get("eventCursor") != {"sequence": len(events), "lastHash": events[-1]["hash"]}:
                continue
            if self._state_hash(candidate) != expected_hash:
                continue
            self._atomic_write(run_dir / "run.json", candidate)
            return candidate
        return None

    def _read_state(self, run_dir: Path) -> dict[str, Any]:
        path = run_dir / "run.json"
        try:
            with path.open("r", encoding="utf-8") as handle:
                state = json.load(handle)
        except FileNotFoundError as exc:
            raise RuntimeFailure("RUN_NOT_FOUND", f"run state not found: {path}", exit_code=2) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeFailure("RUN_CORRUPT", f"run state is unreadable: {path}") from exc
        if not isinstance(state, dict):
            raise RuntimeFailure("RUN_CORRUPT", "run state must be a JSON object")
        return state

    def _event_hash(self, event: dict[str, Any]) -> str:
        unsigned = {key: value for key, value in event.items() if key != "hash"}
        return hmac.new(self._runtime_key(), canonical_json(unsigned).encode("utf-8"), hashlib.sha256).hexdigest()

    def _read_events(self, run_dir: Path) -> list[dict[str, Any]]:
        path = run_dir / "events.jsonl"
        if not path.exists():
            return []
        events: list[dict[str, Any]] = []
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if len(line) > 1024 * 1024:
                        raise RuntimeFailure("EVENT_LOG_CORRUPT", f"event line {line_number} exceeds 1 MiB")
                    if not line.strip():
                        raise RuntimeFailure("EVENT_LOG_CORRUPT", f"event line {line_number} is empty")
                    event = json.loads(line)
                    if not isinstance(event, dict):
                        raise RuntimeFailure("EVENT_LOG_CORRUPT", f"event line {line_number} is not an object")
                    events.append(event)
        except json.JSONDecodeError as exc:
            raise RuntimeFailure("EVENT_LOG_CORRUPT", f"invalid JSONL event at line {exc.lineno}") from exc
        except OSError as exc:
            raise RuntimeFailure("EVENT_LOG_CORRUPT", f"cannot read event log: {path}") from exc
        return events

    def _verify_events(
        self,
        run_id: str,
        events: Sequence[dict[str, Any]],
        expected_cursor: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        previous_hash = ZERO_HASH
        for sequence, event in enumerate(events, start=1):
            required = {
                "eventId",
                "runId",
                "taskId",
                "timestamp",
                "type",
                "actor",
                "payload",
                "evidenceRefs",
                "sequence",
                "previousHash",
                "hash",
            }
            if set(event) != required:
                raise RuntimeFailure("EVENT_LOG_TAMPERED", f"event {sequence} has an invalid shape")
            if event["runId"] != run_id or event["sequence"] != sequence:
                raise RuntimeFailure("EVENT_LOG_TAMPERED", f"event {sequence} identity or sequence mismatch")
            if event["previousHash"] != previous_hash or event["hash"] != self._event_hash(event):
                raise RuntimeFailure("EVENT_LOG_TAMPERED", f"event {sequence} hash chain mismatch")
            if not isinstance(event["type"], str) or not EVENT_TYPE_RE.fullmatch(event["type"]):
                raise RuntimeFailure("EVENT_LOG_TAMPERED", f"event {sequence} type is invalid")
            previous_hash = event["hash"]
        cursor = {"sequence": len(events), "lastHash": previous_hash}
        if expected_cursor is not None and cursor != expected_cursor:
            raise RuntimeFailure(
                "EVENT_LOG_TAMPERED",
                "event log does not match the Run cursor",
                details={"expected": expected_cursor, "actual": cursor},
            )
        return cursor

    def _append_event(self, run_dir: Path, event: dict[str, Any]) -> None:
        path = run_dir / "events.jsonl"
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical_json(event))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _recover_pending(self, run_dir: Path, state: dict[str, Any]) -> dict[str, Any]:
        pending = state.get("pendingEvent")
        events = self._read_events(run_dir)
        cursor = self._verify_events(state.get("runId", ""), events)
        if pending is None:
            self._verify_events(state.get("runId", ""), events, state.get("eventCursor"))
            return state

        expected_previous = state.get("eventCursor")
        if not isinstance(expected_previous, dict):
            raise RuntimeFailure("RUN_CORRUPT", "pending event has no prior event cursor")
        if pending.get("sequence") != expected_previous.get("sequence", -1) + 1:
            raise RuntimeFailure("RUN_CORRUPT", "pending event sequence is invalid")
        if pending.get("previousHash") != expected_previous.get("lastHash"):
            raise RuntimeFailure("RUN_CORRUPT", "pending event previous hash is invalid")
        if pending.get("hash") != self._event_hash(pending):
            raise RuntimeFailure("RUN_CORRUPT", "pending event hash is invalid")

        pending_cursor = {"sequence": pending["sequence"], "lastHash": pending["hash"]}
        if cursor == expected_previous:
            self._append_event(run_dir, pending)
        elif cursor != pending_cursor:
            raise RuntimeFailure("EVENT_LOG_TAMPERED", "event log diverged while a transition was pending")

        state["eventCursor"] = pending_cursor
        state["pendingEvent"] = None
        self._atomic_write(run_dir / "run.json", state)
        self._verify_events(state["runId"], self._read_events(run_dir), pending_cursor)
        return state

    def _load_locked(self, run_id: str) -> tuple[Path, dict[str, Any]]:
        run_dir = self.run_dir(run_id)
        state = self._recover_pending(run_dir, self._read_state(run_dir))
        validate_run(state)
        self._verify_artifacts(state)
        events = self._read_events(run_dir)
        self._verify_events(run_id, events, state["eventCursor"])
        if events and events[-1]["payload"].get("stateHash") != self._state_hash(state):
            recovered = self._restore_snapshot(run_dir, run_id, events)
            if recovered is not None:
                raise RuntimeFailure("RUN_STATE_TAMPERED_RECOVERED", "canonical Run state was restored from its latest valid snapshot")
            raise RuntimeFailure("RUN_STATE_TAMPERED", "canonical Run state does not match the latest event")
        return run_dir, state

    def load(self, run_id: str | None = None) -> dict[str, Any]:
        resolved = self._resolve_run_id(run_id)
        run_dir = self.run_dir(resolved)
        with FileLock(run_dir / ".run.lock"):
            _, state = self._load_locked(resolved)
            return copy.deepcopy(state)

    def events(self, run_id: str | None = None) -> list[dict[str, Any]]:
        resolved = self._resolve_run_id(run_id)
        run_dir = self.run_dir(resolved)
        with FileLock(run_dir / ".run.lock"):
            _, state = self._load_locked(resolved)
            events = self._read_events(run_dir)
            self._verify_events(resolved, events, state["eventCursor"])
            return events

    def _new_event(
        self,
        state: dict[str, Any],
        event_type: str,
        actor: str,
        task_id: str | None,
        payload: dict[str, Any] | None,
        evidence_refs: Sequence[str],
    ) -> dict[str, Any]:
        if not EVENT_TYPE_RE.fullmatch(event_type):
            raise RuntimeFailure("INVALID_EVENT", f"invalid event type: {event_type}")
        cursor = state["eventCursor"]
        event = {
            "eventId": f"evt-{uuid.uuid4().hex}",
            "runId": state["runId"],
            "taskId": task_id,
            "timestamp": utc_now(),
            "type": event_type,
            "actor": actor,
            "payload": redact(
                {
                    **(payload or {}),
                    "stateRevision": state["revision"],
                    "stateHash": self._state_hash(state),
                }
            ),
            "evidenceRefs": list(dict.fromkeys(evidence_refs)),
            "sequence": cursor["sequence"] + 1,
            "previousHash": cursor["lastHash"],
        }
        event["hash"] = self._event_hash(event)
        return event

    def _commit_locked(
        self,
        run_dir: Path,
        state: dict[str, Any],
        *,
        event_type: str,
        actor: str,
        task_id: str | None = None,
        payload: dict[str, Any] | None = None,
        evidence_refs: Sequence[str] = (),
    ) -> dict[str, Any]:
        sanitized = redact(state)
        state.clear()
        state.update(sanitized)
        state["revision"] += 1
        state["updatedAt"] = utc_now()
        event = self._new_event(state, event_type, actor, task_id, payload, evidence_refs)
        state["pendingEvent"] = event
        validate_run(state)
        self._atomic_write(run_dir / "run.json", state)
        self._append_event(run_dir, event)
        state["eventCursor"] = {"sequence": event["sequence"], "lastHash": event["hash"]}
        state["pendingEvent"] = None
        self._atomic_write(run_dir / "run.json", state)
        self._write_snapshot(run_dir, state)
        self._project(run_dir, state)
        return copy.deepcopy(state)

    def _transaction(
        self,
        run_id: str,
        mutate: Callable[[dict[str, Any]], dict[str, Any] | None],
        *,
        event_type: str,
        actor: str = "coordinator",
        task_id: str | None = None,
        evidence_refs: Sequence[str] = (),
    ) -> dict[str, Any]:
        run_dir = self.run_dir(run_id)
        with FileLock(run_dir / ".run.lock"):
            _, state = self._load_locked(run_id)
            before_policy = copy.deepcopy(state["policy"])
            payload = mutate(state) or {}
            if actor.startswith("worker:") and state["policy"] != before_policy:
                raise RuntimeFailure("POLICY_ESCALATION", "workers cannot modify Run policy")
            return self._commit_locked(
                run_dir,
                state,
                event_type=event_type,
                actor=actor,
                task_id=task_id,
                payload=payload,
                evidence_refs=evidence_refs,
            )

    def create(
        self,
        *,
        goal: str,
        outcome: str,
        criteria: Sequence[dict[str, Any]],
        autonomy_scope: str | None = None,
        policy_allow: Sequence[dict[str, Any]] | None = None,
        confirmation_required: Sequence[str] | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        # Explicit arguments always win; an omitted (None) argument falls back to the
        # repository's configured `autonomy` defaults, and only then to the built-in default.
        configured_autonomy = repository_config(str(self.repository)).get("autonomy") or {}
        configured_policy = configured_autonomy.get("mutationPolicy") or {}
        if autonomy_scope is None:
            autonomy_scope = configured_autonomy.get("scope") or "current-task"
        if policy_allow is None:
            policy_allow = configured_policy.get("allow") or []
        if confirmation_required is None:
            confirmation_required = configured_policy.get("confirmationRequired") or []
        if autonomy_scope not in {"current-task", "approved-program", "advisory-only"}:
            raise RuntimeFailure("INVALID_AUTONOMY", f"invalid autonomy scope: {autonomy_scope}")
        if not goal.strip() or not outcome.strip():
            raise RuntimeFailure("INVALID_RUN", "goal and outcome are required")
        run_id = run_id or f"run-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
        require_id(run_id, "run id")
        run_dir = self.run_dir(run_id)
        with FileLock(run_dir / ".run.lock"):
            if (run_dir / "run.json").exists():
                raise RuntimeFailure("RUN_EXISTS", f"run already exists: {run_id}")
            run_dir.mkdir(parents=True, exist_ok=True)
            self._runtime_key(create=True)
            normalized_criteria = normalize_criteria(criteria, outcome)
            now = utc_now()
            state: dict[str, Any] = {
                "schema": SCHEMA,
                "revision": -1,
                "runId": run_id,
                "createdAt": now,
                "updatedAt": now,
                "goal": goal.strip(),
                "status": "CREATED",
                "autonomy": {"scope": autonomy_scope},
                "policy": {
                    "default": "deny",
                    "allow": normalize_policy_allow(policy_allow),
                    "confirmationRequired": list(dict.fromkeys(confirmation_required)),
                },
                "outcome": {
                    "description": outcome.strip(),
                    "requiredCriteria": [
                        {
                            "id": criterion["id"],
                            "description": criterion["description"],
                            "verification": criterion["verificationType"],
                            "required": criterion["blocking"],
                        }
                        for criterion in normalized_criteria
                    ],
                },
                "acceptanceCriteria": normalized_criteria,
                "baseline": self.repository_identity(),
                "tasks": [],
                "checkpoints": [],
                "externalCheckpoints": [],
                "artifacts": [],
                "workers": [],
                "gateResults": [],
                "eventLog": f".architrave/runs/{run_id}/events.jsonl",
                "eventCursor": {"sequence": 0, "lastHash": ZERO_HASH},
                "pendingEvent": None,
            }
            self._create_human_artifacts(run_dir, state)
            return self._commit_locked(
                run_dir,
                state,
                event_type="run.created",
                actor="coordinator",
                payload={"goal": goal.strip(), "autonomyScope": autonomy_scope},
            )

    def _create_human_artifacts(self, run_dir: Path, state: dict[str, Any]) -> None:
        templates = {
            "intake.md": "# Intake\n\n## Understanding\n\n## Acceptance Criteria\n\n## Grounding Sources\n\n## Assumptions\n\n## Blocking Questions\n",
            "tournament.md": "# Tournament of Options\n\n## Decision Matrix\n\n## Winner\n",
            "recommended-plan.md": "# Recommended Plan\n\n## Implementation Sequence\n\n## Test Strategy\n\n## Rollback / Recovery\n",
            "deterministic-gates.md": "# Deterministic Gates\n\n",
            "judge-pre.md": "# Judge Gate 1\n\n## Verdict\n\n## Findings\n",
            "judge-post.md": "# Judge Gate 2\n\n## Verdict\n\n## Findings\n",
            "runtime-observer.md": "# Runtime Observer\n\n## Sources Used\n\n## Observed State\n\n## Mismatches\n",
        }
        for name, content in templates.items():
            path = run_dir / name
            if not path.exists():
                path.write_text(content, encoding="utf-8")

    def _project(self, run_dir: Path, state: dict[str, Any]) -> None:
        rows = [
            "# Phase Ledger",
            "",
            "> Projection of `run.json`; phase labels are observational and do not authorize or block work.",
            "",
            "| Phase | Name | Status | Scope | Gate | Result |",
            "|---:|---|---|---|---|---|",
        ]
        status_map = {
            "NOT_READY": "not-started",
            "READY": "not-started",
            "RUNNING": "in-progress",
            "WAITING_EXTERNAL": "blocked",
            "WAITING_RESOURCE": "blocked",
            "COMPLETED": "completed",
            "FAILED": "blocked",
            "SKIPPED": "skipped",
            "CANCELLED": "skipped",
        }
        for index, task in enumerate(state["tasks"], start=1):
            result = "pass" if task["status"] == "COMPLETED" else "pending"
            if task["status"] == "FAILED":
                result = "fail"
            values = [
                str(index),
                task["title"],
                status_map[task["status"]],
                task["objective"],
                task.get("gate") or "runtime task gate",
                result,
            ]
            escaped = [value.replace("|", "\\|").replace("\n", " ") for value in values]
            rows.append("| " + " | ".join(escaped) + " |")
        if not state["tasks"]:
            rows.append("| 0 | Planning | in-progress | Build the TaskGraph. | TaskGraph accepted | pending |")
        rows.extend(["", "## Phase Transition Log", "", f"Last projected from Run revision {state['revision']}.", ""])
        (run_dir / "phase-ledger.md").write_text("\n".join(rows), encoding="utf-8")

        required = [criterion for criterion in state["acceptanceCriteria"] if criterion["blocking"]]
        summary = {
            "schema": SCHEMA,
            "runId": state["runId"],
            "status": state["status"],
            "updatedAt": state["updatedAt"],
            "canonicalState": f".architrave/runs/{state['runId']}/run.json",
            "eventLog": state["eventLog"],
            "outcome": state["outcome"]["description"],
            "acceptance": {
                "required": len(required),
                "passed": sum(item["status"] in {"PASS", "NOT_APPLICABLE"} for item in required),
                "failed": sum(item["status"] == "FAIL" for item in required),
                "blockedExternal": sum(item["status"] == "BLOCKED_EXTERNAL" for item in required),
            },
            "readyTasks": [task["id"] for task in state["tasks"] if task["status"] == "READY"],
            "pendingExternalCheckpoints": [
                checkpoint["id"]
                for checkpoint in state["externalCheckpoints"]
                if checkpoint["status"] == "PENDING"
            ],
        }
        self._atomic_write(run_dir / "summary.json", summary)

    def add_task(self, run_id: str, task: dict[str, Any], actor: str = "coordinator") -> dict[str, Any]:
        task_id = require_id(str(task.get("id", "")), "task id")

        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            if state["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
                raise RuntimeFailure("RUN_TERMINAL", "cannot add a task to a terminal Run")
            if any(existing["id"] == task_id for existing in state["tasks"]):
                raise RuntimeFailure("TASK_EXISTS", f"task already exists: {task_id}")
            criterion_ids = {criterion["id"] for criterion in state["acceptanceCriteria"]}
            acceptance = list(dict.fromkeys(task.get("acceptanceCriteria") or []))
            if not acceptance or not set(acceptance).issubset(criterion_ids):
                raise RuntimeFailure("INVALID_TASK", "task must reference existing acceptance criteria")
            dependencies = list(dict.fromkeys(task.get("dependencies") or []))
            existing_ids = {existing["id"] for existing in state["tasks"]}
            if not set(dependencies).issubset(existing_ids):
                raise RuntimeFailure("INVALID_TASK", "task dependencies must already exist")
            mutable_paths = [safe_relative_path(path, "mutable path") for path in task.get("mutablePaths", [])]
            side_effect = task.get("sideEffect")
            if side_effect is not None:
                side_effect = {
                    "operation": str(side_effect["operation"]),
                    "target": str(side_effect["target"]),
                    "state": "NONE",
                    "reconciliation": None,
                }
            config = repository_config(str(self.repository))
            workers_config = config.get("workers") or {}
            evaluation_block = config.get("evaluation") or {}
            worker_profile = str(task.get("workerProfile") or workers_config.get("defaultAdapter") or "shell")
            enabled_adapters = workers_config.get("enabledAdapters")
            if enabled_adapters and worker_profile not in enabled_adapters:
                raise RuntimeFailure(
                    "INVALID_TASK",
                    f"worker adapter is not enabled for this repository: {worker_profile}",
                    details={"enabledAdapters": list(enabled_adapters)},
                )
            risk = str(task.get("risk") or evaluation_block.get("defaultRisk") or "R1")
            if risk not in RISK_CLASSES:
                raise RuntimeFailure("INVALID_TASK", f"invalid risk: {risk}")
            normalized = {
                "id": task_id,
                "title": str(task.get("title") or task_id),
                "objective": str(task.get("objective") or "").strip(),
                "status": "NOT_READY" if dependencies else "READY",
                "dependencies": dependencies,
                "workerProfile": worker_profile,
                "workspace": task.get("workspace"),
                "mutablePaths": mutable_paths,
                "tools": list(dict.fromkeys(task.get("tools") or [])),
                "risk": risk,
                "acceptanceCriteria": acceptance,
                "requiredArtifacts": list(dict.fromkeys(task.get("requiredArtifacts") or [])),
                "gate": task.get("gate"),
                "retryPolicy": {
                    "maxAttempts": int(task.get("maxAttempts", 1)),
                    "backoffSeconds": float(task.get("backoffSeconds", 0)),
                    "retryable": list(dict.fromkeys(task.get("retryable") or [])),
                },
                "checkpointPolicy": {
                    "beforeSideEffect": bool(task.get("beforeSideEffect", side_effect is not None)),
                    "afterCompletion": bool(task.get("afterCompletion", True)),
                },
                "attempts": 0,
                "lease": None,
                "retryNotBefore": None,
                "workPacket": normalize_work_packet(task.get("workPacket"), task_id, normalized_defaults={
                    "objective": str(task.get("objective") or "").strip(),
                    "acceptanceCriteria": acceptance,
                    "repoScope": str(self.repository),
                    "mutablePaths": mutable_paths,
                    "tools": list(dict.fromkeys(task.get("tools") or [])),
                    "worker": worker_profile,
                    "risk": risk,
                    "expectedArtifacts": list(dict.fromkeys(task.get("requiredArtifacts") or [])),
                }),
                "sideEffect": side_effect,
            }
            if not normalized["objective"]:
                raise RuntimeFailure("INVALID_TASK", "task objective is required")
            state["tasks"].append(normalized)
            validate_task_graph(state["tasks"])
            state["status"] = "PLANNING" if state["status"] == "CREATED" else state["status"]
            return {"taskId": task_id, "status": normalized["status"]}

        return self._transaction(run_id, mutate, event_type="task.created", actor=actor, task_id=task_id)

    def ready_tasks(self, run_id: str | None = None) -> list[dict[str, Any]]:
        state = self.load(run_id)
        return [copy.deepcopy(task) for task in state["tasks"] if task["status"] == "READY"]

    def assign_workspace(
        self,
        run_id: str,
        task_id: str,
        workspace: str,
        *,
        actor: str = "coordinator",
    ) -> dict[str, Any]:
        workspace_path = Path(workspace).resolve()

        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            self._assert_repository_baseline(state)
            task = find_task(state, task_id)
            if task["status"] not in {"NOT_READY", "READY"}:
                raise RuntimeFailure("WORKSPACE_LATE_ASSIGNMENT", "workspace must be assigned before task start")
            if any(
                other["id"] != task_id
                and other.get("workspace")
                and Path(other["workspace"]).resolve() == workspace_path
                and task["mutablePaths"]
                and other["mutablePaths"]
                and other["status"] not in TERMINAL_TASK_STATUSES
                for other in state["tasks"]
            ):
                raise RuntimeFailure("WORKSPACE_COLLISION", "workspace is already assigned to another active task")
            task["workspace"] = str(workspace_path)
            task["workPacket"]["repoScope"] = str(workspace_path)
            return {"taskId": task_id, "workspace": str(workspace_path)}

        return self._transaction(
            run_id,
            mutate,
            event_type="workspace.created",
            actor=actor,
            task_id=task_id,
        )

    def record_artifact(
        self,
        run_id: str,
        *,
        artifact_id: str,
        kind: str,
        path: str,
        evidence_refs: Sequence[str] = (),
        actor: str = "coordinator",
    ) -> dict[str, Any]:
        return self._record_artifact(
            run_id,
            artifact_id=artifact_id,
            kind=kind,
            path=path,
            evidence_refs=evidence_refs,
            actor=actor,
            producer="coordinator",
        )

    def _record_artifact(
        self,
        run_id: str,
        *,
        artifact_id: str,
        kind: str,
        path: str,
        evidence_refs: Sequence[str],
        actor: str,
        producer: str,
    ) -> dict[str, Any]:
        require_id(artifact_id, "artifact id")
        relative = safe_relative_path(path, "artifact path")
        absolute = (self.repository / relative).resolve()
        try:
            absolute.relative_to(self.repository)
        except ValueError as exc:
            raise RuntimeFailure("PATH_ESCAPE", "artifact path escapes repository") from exc
        if not absolute.is_file():
            raise RuntimeFailure("ARTIFACT_NOT_FOUND", f"artifact not found: {relative}")
        if producer not in ARTIFACT_PRODUCERS:
            raise RuntimeFailure("ARTIFACT_PRODUCER", f"invalid artifact producer: {producer}")
        allowed_kinds = PRODUCER_ARTIFACT_KINDS.get(producer)
        if producer == "legibility":
            if not kind.endswith("-legibility"):
                raise RuntimeFailure("ARTIFACT_KIND", "legibility artifact kind must end in -legibility")
        elif allowed_kinds is not None and kind not in allowed_kinds:
            raise RuntimeFailure("ARTIFACT_KIND", f"artifact kind {kind} is invalid for {producer}")
        if absolute.stat().st_size <= 2 * 1024 * 1024:
            content = absolute.read_bytes()
            if b"\x00" not in content:
                text = content.decode("utf-8", "replace")
                if redact(text) != text:
                    raise RuntimeFailure("ARTIFACT_SENSITIVE", "artifact appears to contain secret material")

        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            if any(item["id"] == artifact_id for item in state["artifacts"]):
                raise RuntimeFailure("ARTIFACT_EXISTS", f"artifact already exists: {artifact_id}")
            content_sha256 = sha256_file(absolute)
            if producer in {"mutation", "reconciliation"} and any(
                item["producer"] in {"mutation", "reconciliation"}
                and item["sha256"] == content_sha256
                for item in state["artifacts"]
            ):
                raise RuntimeFailure("EVIDENCE_REPLAY", "mutation reconciliation receipt content is already registered")
            artifact = {
                "id": artifact_id,
                "kind": kind,
                "producer": producer,
                "path": relative,
                "createdAt": utc_now(),
                "sha256": content_sha256,
                "evidenceRefs": list(dict.fromkeys(evidence_refs)),
                "consumedByTask": None,
            }
            artifact["attestation"] = self._artifact_attestation(artifact)
            state["artifacts"].append(artifact)
            return {"artifactId": artifact_id, "kind": kind, "path": relative}

        return self._transaction(
            run_id,
            mutate,
            event_type="artifact.recorded",
            actor=actor,
            evidence_refs=evidence_refs,
        )

    def _record_deterministic_result(self, run_id: str, **kwargs: Any) -> dict[str, Any]:
        receipt = self._read_json_receipt(kwargs["path"], "deterministic")
        if receipt.get("status") != "pass" or receipt.get("exitCode") != 0 or not receipt.get("command"):
            raise RuntimeFailure("DETERMINISTIC_RECEIPT", "deterministic receipt does not prove a passing command")
        return self._record_artifact(run_id, kind="deterministic-result", actor="deterministic-executor", producer="deterministic", **kwargs)

    def _record_invariant_result(self, run_id: str, **kwargs: Any) -> dict[str, Any]:
        path = (self.repository / safe_relative_path(str(kwargs["path"]), "invariant result path")).resolve()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeFailure("INVARIANT_RECEIPT", "invariant result is unreadable") from exc
        from invariant_engine import evaluate, load_config

        expected = evaluate(self.repository, load_config(self.repository))
        if payload != expected:
            raise RuntimeFailure("INVARIANT_RECEIPT", "invariant result does not match a fresh engine evaluation")
        return self._record_artifact(run_id, kind="invariant-result", actor="invariant-engine", producer="invariant", **kwargs)

    def _record_legibility_result(self, run_id: str, *, kind: str, **kwargs: Any) -> dict[str, Any]:
        receipt = self._read_json_receipt(kwargs["path"], "legibility")
        surface = kind.removesuffix("-legibility")
        required_names = {
            "web": {"runtime.health", "web.e2e"},
            "electron": {"electron.launch", "electron.health", "electron.screenshot"},
            "ios": {"ios.build", "ios.install", "ios.launch", "ios.screenshot", "ios.blank-screen"},
        }.get(surface)
        results = receipt.get("results") or []
        result_names = {item.get("name") for item in results if isinstance(item, dict) and item.get("status") == "pass"}
        if (
            required_names is None
            or receipt.get("surface") != surface
            or receipt.get("status") != "pass"
            or receipt.get("failed") != []
            or not required_names.issubset(result_names)
        ):
            raise RuntimeFailure("LEGIBILITY_RECEIPT", "legibility receipt does not prove the required surface checks")
        return self._record_artifact(run_id, kind=kind, actor="legibility-runner", producer="legibility", **kwargs)

    def _record_mutation_receipt(self, run_id: str, **kwargs: Any) -> dict[str, Any]:
        path = (self.repository / safe_relative_path(str(kwargs["path"]), "mutation receipt path")).resolve()
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeFailure("MUTATION_RECEIPT", "mutation receipt is unreadable") from exc
        result = receipt.get("result") or {}
        verification = receipt.get("verification") or {}
        expected = receipt.get("expected") or {}
        task_id = receipt.get("taskId")
        operation = receipt.get("operation")
        target = receipt.get("target")
        if not task_id or not operation or not target:
            raise RuntimeFailure("MUTATION_RECEIPT", "mutation receipt lacks task, operation, or target binding")
        if (result.get("apply") or {}).get("status") != "pass":
            raise RuntimeFailure("MUTATION_RECEIPT", "mutation receipt does not prove the apply occurred")
        if not (verification.get("version") or {}).get("stdout") or not (verification.get("digest") or {}).get("stdout"):
            raise RuntimeFailure("MUTATION_RECEIPT", "mutation receipt lacks version or digest evidence")
        if not expected.get("version") or not expected.get("digest"):
            raise RuntimeFailure("MUTATION_RECEIPT", "mutation receipt lacks intended version or digest")
        if (verification.get("health") or {}).get("status") != "pass":
            raise RuntimeFailure("MUTATION_RECEIPT", "mutation receipt health verification did not pass")
        if (verification.get("version") or {}).get("stdout", "").strip() != expected["version"]:
            raise RuntimeFailure("MUTATION_RECEIPT", "mutation receipt observed version does not match intended version")
        if (verification.get("digest") or {}).get("stdout", "").strip() != expected["digest"]:
            raise RuntimeFailure("MUTATION_RECEIPT", "mutation receipt observed digest does not match intended digest")
        state = self.load(run_id)
        task = find_task(state, task_id)
        side_effect = task.get("sideEffect")
        if side_effect is None or side_effect["operation"] != operation or side_effect["target"] != target:
            raise RuntimeFailure("MUTATION_RECEIPT", "mutation receipt does not match the bound task side effect")
        return self._record_artifact(run_id, kind="mutation-receipt", actor="mutation-runner", producer="mutation", **kwargs)

    def _record_reconciliation_receipt(self, run_id: str, **kwargs: Any) -> dict[str, Any]:
        receipt = self._read_json_receipt(kwargs["path"], "reconciliation")
        required = ("taskId", "operation", "target")
        if any(not receipt.get(field) for field in required) or receipt.get("outcome") != "not-applied":
            raise RuntimeFailure("RECONCILIATION_RECEIPT", "not-applied receipt lacks task/operation/target/outcome")
        if not receipt.get("observation") or not receipt.get("observedAt"):
            raise RuntimeFailure("RECONCILIATION_RECEIPT", "not-applied receipt lacks observation evidence")
        state = self.load(run_id)
        task = find_task(state, receipt["taskId"])
        side_effect = task.get("sideEffect")
        if side_effect is None or side_effect["operation"] != receipt["operation"] or side_effect["target"] != receipt["target"]:
            raise RuntimeFailure("RECONCILIATION_RECEIPT", "not-applied receipt does not match task side effect")
        return self._record_artifact(
            run_id,
            kind="reconciliation-receipt",
            actor="reconciliation-runner",
            producer="reconciliation",
            **kwargs,
        )

    def _record_workspace_artifact(self, run_id: str, *, kind: str, **kwargs: Any) -> dict[str, Any]:
        return self._record_artifact(run_id, kind=kind, actor="workspace-manager", producer="workspace", **kwargs)

    def _record_worker_result(self, run_id: str, **kwargs: Any) -> dict[str, Any]:
        return self._record_artifact(run_id, kind="worker-result", actor="worker-adapter", producer="worker", **kwargs)

    def _record_semantic_verdict(self, run_id: str, **kwargs: Any) -> dict[str, Any]:
        verdict = self._read_json_receipt(kwargs["path"], "semantic")
        if verdict.get("verdict") != "PASS" or verdict.get("family") not in {"gpt", "claude"} or not verdict.get("criteria"):
            raise RuntimeFailure("SEMANTIC_RECEIPT", "semantic verdict receipt is invalid")
        return self._record_artifact(run_id, kind="semantic-verdict", actor="semantic-review", producer="semantic-judge", **kwargs)

    def _record_security_verdict(self, run_id: str, **kwargs: Any) -> dict[str, Any]:
        return self._record_artifact(run_id, kind="security-verdict", actor="security-review", producer="security-review", **kwargs)

    def _record_policy_decision(self, run_id: str, **kwargs: Any) -> dict[str, Any]:
        return self._record_artifact(run_id, kind="policy-decision", actor="policy-engine", producer="policy-engine", **kwargs)

    def _record_external_proof(self, run_id: str, **kwargs: Any) -> dict[str, Any]:
        proof = self._read_json_receipt(kwargs["path"], "external")
        state = self.load(run_id)
        checkpoint = next((item for item in state["externalCheckpoints"] if item["id"] == proof.get("checkpointId")), None)
        if (
            checkpoint is None
            or checkpoint["status"] != "PENDING"
            or proof.get("principal") != checkpoint["principal"]
            or proof.get("provider") != checkpoint["provider"]
        ):
            raise RuntimeFailure("EXTERNAL_PROOF", "external proof does not match a pending checkpoint")
        return self._record_artifact(run_id, kind="external-proof", actor="external-checkpoint", producer="external-proof", **kwargs)

    def _read_json_receipt(self, path_value: str, label: str) -> dict[str, Any]:
        path = (self.repository / safe_relative_path(str(path_value), f"{label} receipt path")).resolve()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeFailure("EVIDENCE_RECEIPT", f"{label} receipt is unreadable") from exc
        if not isinstance(payload, dict):
            raise RuntimeFailure("EVIDENCE_RECEIPT", f"{label} receipt must be an object")
        return payload

    def start_task(
        self,
        run_id: str,
        task_id: str,
        *,
        worker_id: str,
        lease_seconds: int = 3600,
        confirmed: bool = False,
        actor: str = "coordinator",
    ) -> dict[str, Any]:
        require_id(worker_id, "worker id")

        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            self._assert_repository_baseline(state)
            if state["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
                raise RuntimeFailure("RUN_TERMINAL", "cannot start a task on a terminal Run")
            if state["status"] == "PAUSED":
                raise RuntimeFailure(
                    "RUN_PAUSED",
                    "cannot start a task while the Run is paused; call resume() explicitly first",
                )
            task = find_task(state, task_id)
            if task["status"] != "READY":
                raise RuntimeFailure("TASK_NOT_READY", f"task {task_id} is {task['status']}")
            if task["attempts"] >= task["retryPolicy"]["maxAttempts"]:
                raise RuntimeFailure("RETRY_EXHAUSTED", f"task {task_id} exhausted its retry policy")
            if task.get("retryNotBefore") and parse_iso(task["retryNotBefore"]) > dt.datetime.now(dt.timezone.utc):
                raise RuntimeFailure(
                    "RETRY_BACKOFF",
                    f"task {task_id} is within its declared retry backoff window",
                    details={"retryNotBefore": task["retryNotBefore"]},
                )
            max_parallel = (repository_config(str(self.repository)).get("workers") or {}).get("maxParallel")
            if max_parallel is not None:
                running = sum(1 for other in state["tasks"] if other["id"] != task_id and other["status"] == "RUNNING")
                if running >= int(max_parallel):
                    raise RuntimeFailure(
                        "PARALLELISM_EXCEEDED",
                        f"configured workers.maxParallel={max_parallel} concurrent task limit reached",
                    )
            if task["mutablePaths"]:
                active_mutating = [
                    other
                    for other in state["tasks"]
                    if other["id"] != task_id and other["status"] == "RUNNING" and other["mutablePaths"]
                ]
                if active_mutating and not task.get("workspace"):
                    raise RuntimeFailure(
                        "WORKSPACE_ISOLATION_REQUIRED",
                        "concurrent mutating tasks require isolated assigned workspaces",
                    )
                conflicting = [
                    other["id"]
                    for other in active_mutating
                    if mutable_scopes_overlap(task["mutablePaths"], other["mutablePaths"])
                ]
                if conflicting:
                    raise RuntimeFailure(
                        "RESOURCE_CONFLICT",
                        "concurrent mutating tasks have overlapping mutable paths",
                        details={"tasks": conflicting},
                    )
                cross_run_conflicts = self._cross_run_mutation_conflicts(state["runId"], task["mutablePaths"])
                if cross_run_conflicts:
                    raise RuntimeFailure(
                        "RESOURCE_CONFLICT",
                        "another Run has an active overlapping mutable scope",
                        details={"tasks": cross_run_conflicts},
                    )
                if task.get("workspace") and any(
                    other.get("workspace")
                    and Path(other["workspace"]).resolve() == Path(task["workspace"]).resolve()
                    for other in active_mutating
                ):
                    raise RuntimeFailure("WORKSPACE_COLLISION", "concurrent mutating tasks cannot share a workspace")
            if task["mutablePaths"]:
                require_mutation_allowed(state, "repository", "edit", confirmed=confirmed)
            if task["sideEffect"] is not None:
                require_mutation_allowed(
                    state,
                    task["sideEffect"]["target"],
                    task["sideEffect"]["operation"],
                    confirmed=confirmed,
                )
                task["sideEffect"]["state"] = "PENDING"
            if task["checkpointPolicy"]["beforeSideEffect"]:
                append_checkpoint(state, task_id, "TASK_START")
            acquired = dt.datetime.now(dt.timezone.utc)
            expires = acquired + dt.timedelta(seconds=max(1, lease_seconds))
            task["lease"] = {
                "owner": worker_id,
                "acquiredAt": acquired.isoformat(timespec="seconds").replace("+00:00", "Z"),
                "expiresAt": expires.isoformat(timespec="seconds").replace("+00:00", "Z"),
            }
            task["attempts"] += 1
            task["status"] = "RUNNING"
            worker = next((item for item in state["workers"] if item["id"] == worker_id), None)
            if worker is None:
                adapter = task["workerProfile"] if task["workerProfile"] in {"copilot", "claude", "codex", "shell"} else "shell"
                state["workers"].append(
                    {
                        "id": worker_id,
                        "adapter": adapter,
                        "status": "RUNNING",
                        "workspace": task["workspace"],
                        "mutablePaths": task["mutablePaths"],
                    }
                )
            else:
                if worker["status"] == "RUNNING":
                    raise RuntimeFailure("WORKER_BUSY", f"worker is already running: {worker_id}")
                worker["status"] = "RUNNING"
                worker["workspace"] = task["workspace"]
                worker["mutablePaths"] = task["mutablePaths"]
            state["status"] = "RUNNING"
            return {"taskId": task_id, "workerId": worker_id, "attempt": task["attempts"]}

        with FileLock(self.repository / ".architrave" / "resources.lock"):
            return self._transaction(run_id, mutate, event_type="task.started", actor=actor, task_id=task_id)

    def _cross_run_mutation_conflicts(self, current_run_id: str, mutable_paths: Sequence[str]) -> list[str]:
        conflicts: list[str] = []
        if not self.runs_root.is_dir():
            return conflicts
        for run_dir in self.runs_root.iterdir():
            if run_dir.name == current_run_id or not (run_dir / "run.json").is_file():
                continue
            try:
                other = self.load(run_dir.name)
            except RuntimeFailure as exc:
                raise RuntimeFailure(
                    "RESOURCE_STATE_UNREADABLE",
                    f"cannot validate active resource leases for Run {run_dir.name}",
                    details={"cause": exc.code},
                ) from exc
            for task in other["tasks"]:
                if task["status"] == "RUNNING" and task["mutablePaths"] and mutable_scopes_overlap(mutable_paths, task["mutablePaths"]):
                    conflicts.append(f"{run_dir.name}:{task['id']}")
        return conflicts

    def _apply_task_retry_or_terminate(self, state: dict[str, Any], task: dict[str, Any], reason: str) -> None:
        """Honor a task's declared retryPolicy on failure instead of always terminating it.

        A failure is retried (task returns to READY/NOT_READY, subject to backoffSeconds) only
        when attempts remain and the reason is retryable (an empty `retryable` list means every
        reason is retryable, matching the permissive default already produced by add_task).
        Otherwise the task becomes terminally FAILED, exactly as before this fix.
        """
        policy = task["retryPolicy"]
        retryable = not policy["retryable"] or reason in policy["retryable"]
        if retryable and task["attempts"] < policy["maxAttempts"]:
            task["status"] = "READY" if dependencies_completed(state, task) else "NOT_READY"
            backoff = max(0.0, float(policy["backoffSeconds"]))
            if backoff:
                retry_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=backoff)
                # isoformat(timespec="seconds") truncates sub-second precision, which could
                # round the persisted deadline *down* to a moment at or before "now" and let
                # start_task's RETRY_BACKOFF check pass immediately -- bypassing the declared
                # backoff window. Ceil to the next whole second instead, so the stored
                # retryNotBefore is never earlier than the true intended deadline.
                if retry_at.microsecond:
                    retry_at = (retry_at + dt.timedelta(seconds=1)).replace(microsecond=0)
                task["retryNotBefore"] = retry_at.isoformat(timespec="seconds").replace("+00:00", "Z")
            else:
                task["retryNotBefore"] = None
        else:
            task["status"] = "FAILED"
            task["retryNotBefore"] = None

    def finish_worker(
        self,
        run_id: str,
        task_id: str,
        *,
        worker_id: str,
        status: str,
        artifact_refs: Sequence[str] = (),
    ) -> dict[str, Any]:
        if status not in {"FINISHED", "FAILED"}:
            raise RuntimeFailure("INVALID_WORKER_RESULT", "worker status must be FINISHED or FAILED")

        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            self._assert_repository_baseline(state)
            task = find_task(state, task_id)
            if task["status"] != "RUNNING" or not task["lease"] or task["lease"]["owner"] != worker_id:
                raise RuntimeFailure("WORKER_OWNERSHIP", "worker does not own the running task")
            if parse_iso(task["lease"]["expiresAt"]) <= dt.datetime.now(dt.timezone.utc):
                raise RuntimeFailure(
                    "WORKER_LEASE_EXPIRED",
                    "worker completion reported after its lease expired",
                    details={"taskId": task_id, "workerId": worker_id},
                )
            worker = next((item for item in state["workers"] if item["id"] == worker_id), None)
            if worker is None:
                raise RuntimeFailure("WORKER_OWNERSHIP", "worker is not registered")
            worker["status"] = status
            task["lease"] = None
            if status == "FAILED":
                if task["sideEffect"] and task["sideEffect"]["state"] == "PENDING":
                    task["sideEffect"]["state"] = "UNCERTAIN"
                    task["status"] = "WAITING_RESOURCE"
                    append_checkpoint(state, task_id, "SIDE_EFFECT_AMBIGUITY")
                else:
                    self._apply_task_retry_or_terminate(state, task, "WORKER_FAILURE")
            else:
                task["status"] = "WAITING_RESOURCE"
                append_checkpoint(state, task_id, "WORKER_COMPLETION")
            state["status"] = derive_run_status(state)
            return {
                "taskId": task_id,
                "workerId": worker_id,
                "candidateStatus": status,
                "taskStatus": task["status"],
            }

        return self._transaction(
            run_id,
            mutate,
            event_type="worker.finished",
            actor=f"worker:{worker_id}",
            task_id=task_id,
            evidence_refs=artifact_refs,
        )

    def complete_task(
        self,
        run_id: str,
        task_id: str,
        *,
        evidence_refs: Sequence[str],
        actor: str = "coordinator",
    ) -> dict[str, Any]:
        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            self._assert_repository_baseline(state)
            task = find_task(state, task_id)
            # A task may only be completed once its owning worker has actually reported
            # finishing (finish_worker transitions it to WAITING_RESOURCE and releases the
            # lease) or it has otherwise reached that same legal waiting state through
            # reconciliation. Accepting completion while still RUNNING would let anyone with
            # runtime access -- including the worker itself, e.g. via the CLI -- complete a
            # task out from under its own in-flight execution, bypassing every post-execution
            # validation execute_work_packet performs.
            if task["status"] != "WAITING_RESOURCE":
                raise RuntimeFailure("TASK_NOT_COMPLETABLE", f"task {task_id} is {task['status']}")
            if task["sideEffect"] is not None and task["sideEffect"]["state"] != "CONFIRMED":
                raise RuntimeFailure("RECONCILIATION_REQUIRED", "task side effect must be confirmed before completion")
            if any(result["taskId"] == task_id and result["status"] == "FAIL" for result in state["gateResults"]):
                raise RuntimeFailure("DETERMINISTIC_FAILURE", "a failed gate blocks task completion")
            referenced_gates = [
                result
                for result in state["gateResults"]
                if f"gate:{result['id']}" in evidence_refs
            ]
            if not referenced_gates or any(
                result["status"] != "PASS"
                or result["taskId"] != task_id
                or not set(task["acceptanceCriteria"]).intersection(result["criteria"])
                for result in referenced_gates
            ):
                raise RuntimeFailure("GATE_REQUIRED", "task completion requires a task-bound PASS gate reference")
            missing_artifacts = [
                requirement
                for requirement in task["requiredArtifacts"]
                if not any(
                    (artifact["id"] == requirement or artifact["kind"] == requirement)
                    and f"task:{task_id}" in artifact["evidenceRefs"]
                    for artifact in state["artifacts"]
                )
            ]
            if missing_artifacts:
                raise RuntimeFailure(
                    "ARTIFACT_REQUIRED",
                    "task required artifacts are missing",
                    details={"requirements": missing_artifacts},
                )
            task["status"] = "COMPLETED"
            task["lease"] = None
            if task["checkpointPolicy"]["afterCompletion"]:
                append_checkpoint(state, task_id, "TASK_COMPLETION")
            newly_ready = refresh_task_readiness(state)
            if state["autonomy"]["scope"] == "current-task" and newly_ready:
                state["status"] = "PAUSED"
            else:
                state["status"] = derive_run_status(state)
            return {
                "taskId": task_id,
                "newlyReady": newly_ready,
                "automaticTransition": state["autonomy"]["scope"] == "approved-program",
            }

        return self._transaction(
            run_id,
            mutate,
            event_type="task.completed",
            actor=actor,
            task_id=task_id,
            evidence_refs=evidence_refs,
        )

    def fail_task(self, run_id: str, task_id: str, reason: str, actor: str = "coordinator") -> dict[str, Any]:
        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            self._assert_repository_baseline(state)
            task = find_task(state, task_id)
            if task["status"] in TERMINAL_TASK_STATUSES:
                raise RuntimeFailure("TASK_TERMINAL", f"task {task_id} is already terminal")
            task["lease"] = None
            if task["sideEffect"] and task["sideEffect"]["state"] == "PENDING":
                task["sideEffect"]["state"] = "UNCERTAIN"
                task["status"] = "WAITING_RESOURCE"
                append_checkpoint(state, task_id, "SIDE_EFFECT_AMBIGUITY")
            else:
                self._apply_task_retry_or_terminate(state, task, reason)
            state["status"] = derive_run_status(state)
            return {"taskId": task_id, "reason": reason, "taskStatus": task["status"]}

        return self._transaction(run_id, mutate, event_type="task.failed", actor=actor, task_id=task_id)

    def record_gate(
        self,
        run_id: str,
        *,
        gate_id: str,
        task_id: str | None,
        gate_type: str,
        status: str,
        evidence_refs: Sequence[str],
        family: str | None = None,
        criteria: Sequence[str] | None = None,
        surface: str | None = None,
        actor: str = "coordinator",
    ) -> dict[str, Any]:
        require_id(gate_id, "gate id")
        if gate_type not in {"deterministic", "e2e", "semantic", "reality", "policy", "security"}:
            raise RuntimeFailure("INVALID_GATE", f"invalid gate type: {gate_type}")
        if family not in {None, "gpt", "claude", "security"}:
            raise RuntimeFailure("INVALID_GATE", f"invalid gate family: {family}")
        if gate_type == "semantic" and family not in {"gpt", "claude"}:
            raise RuntimeFailure("INVALID_GATE", "semantic gates require gpt or claude family")
        if gate_type == "security" and family not in {None, "security"}:
            raise RuntimeFailure("INVALID_GATE", "security gate family must be security")
        if status not in {"PASS", "FAIL", "BLOCKED", "SKIPPED"}:
            raise RuntimeFailure("INVALID_GATE", f"invalid gate status: {status}")

        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            if any(result["id"] == gate_id for result in state["gateResults"]):
                raise RuntimeFailure("GATE_EXISTS", f"gate result already exists: {gate_id}")
            if task_id is not None:
                task = find_task(state, task_id)
                bound_criteria = list(criteria or task["acceptanceCriteria"])
            else:
                blocking_criteria = [item["id"] for item in state["acceptanceCriteria"] if item["blocking"]]
                # A taskless reality/e2e gate has no task to inherit its acceptance criteria
                # from. Defaulting to "every currently blocking criterion" is only unambiguous
                # when there is a single blocking criterion; with more than one, it silently let
                # one surface's legibility run stand in as proof for criteria it never
                # exercised. Require the caller to name exactly which criteria this gate proves
                # whenever that default would otherwise be ambiguous.
                if gate_type in {"reality", "e2e"} and not criteria and len(blocking_criteria) > 1:
                    raise RuntimeFailure(
                        "GATE_BINDING_REQUIRED",
                        "a taskless reality/e2e gate must explicitly bind to specific acceptance "
                        "criteria when more than one blocking criterion exists",
                    )
                bound_criteria = list(criteria or blocking_criteria)
            known_criteria = {item["id"] for item in state["acceptanceCriteria"]}
            if not bound_criteria or not set(bound_criteria).issubset(known_criteria):
                raise RuntimeFailure("INVALID_GATE", "gate must bind to known acceptance criteria")
            if status == "PASS":
                require_evidence_refs(state, evidence_refs, allowed={"artifact", "external"})
                artifact_ids = [reference.split(":", 1)[1] for reference in evidence_refs if reference.startswith("artifact:")]
                if task_id is not None and any(
                    f"task:{task_id}" not in artifact["evidenceRefs"]
                    for artifact in state["artifacts"]
                    if artifact["id"] in artifact_ids
                ):
                    raise RuntimeFailure("EVIDENCE_REPLAY", "PASS gate artifact is not bound to this task")
                producers = {
                    artifact["producer"]
                    for artifact in state["artifacts"]
                    if artifact["id"] in artifact_ids
                }
                if not producers or not producers.issubset(GATE_EVIDENCE_PRODUCERS[gate_type]):
                    raise RuntimeFailure(
                        "EVIDENCE_PROVENANCE",
                        "PASS gate evidence has an untrusted producer",
                        details={"gateType": gate_type, "producers": sorted(producers)},
                    )
                if gate_type == "semantic":
                    for artifact in state["artifacts"]:
                        if artifact["id"] not in artifact_ids:
                            continue
                        verdict = self._read_json_receipt(artifact["path"], "semantic")
                        if verdict.get("family") != family or not set(bound_criteria).issubset(set(verdict.get("criteria") or [])):
                            raise RuntimeFailure("SEMANTIC_RECEIPT", "semantic gate does not match verdict family/criteria")
                if gate_type in {"reality", "e2e"}:
                    # A reality/e2e PASS gate proves exactly one verification surface (web,
                    # electron, ios, deployment, runtime). Evidence spanning zero or more than
                    # one surface is ambiguous about what was actually verified and must be
                    # rejected rather than silently accepted as proof for whichever criteria the
                    # caller named. `producers` is already validated above to be a subset of
                    # GATE_EVIDENCE_PRODUCERS[gate_type], so every producer here is trusted.
                    def evidence_surface_of(artifact: dict[str, Any]) -> str | None:
                        producer = artifact["producer"]
                        if producer == "legibility":
                            return self._read_json_receipt(artifact["path"], "legibility").get("surface")
                        if producer == "mutation":
                            return "deployment"
                        if producer == "external-proof":
                            return "runtime"
                        return None

                    evidence_surfaces = {
                        evidence_surface_of(artifact)
                        for artifact in state["artifacts"]
                        if artifact["id"] in artifact_ids
                    }
                    if len(evidence_surfaces) != 1 or None in evidence_surfaces:
                        raise RuntimeFailure(
                            "EVIDENCE_SURFACE_AMBIGUOUS",
                            "reality/e2e PASS gate must be backed by evidence for exactly one verification surface",
                        )
                    (evidence_surface,) = evidence_surfaces
                    if surface is not None and surface != evidence_surface:
                        raise RuntimeFailure(
                            "EVIDENCE_SURFACE_MISMATCH",
                            "declared verification surface does not match the evidence",
                            details={"declared": surface, "evidence": evidence_surface},
                        )
                    # The criterion -- not the caller, and not the producer type -- is the
                    # authoritative source of the expected surface here: a caller can simply
                    # omit `surface` to dodge the declared-vs-evidence check above, and a
                    # mutation/external-proof producer is just as capable of being bound to the
                    # wrong criterion as a legibility one. Every derived reality/e2e evidence
                    # surface (web/electron/ios via legibility, deployment via mutation, runtime
                    # via external-proof) must match whatever surface every bound reality/e2e
                    # criterion owns, regardless of which producer backed it.
                    owned_surfaces = {
                        criterion.get("surface")
                        for criterion in state["acceptanceCriteria"]
                        if criterion["id"] in bound_criteria
                        and criterion["verificationType"] in SURFACE_VERIFICATION_TYPES
                        and criterion.get("surface")
                    }
                    if len(owned_surfaces) > 1:
                        raise RuntimeFailure(
                            "EVIDENCE_SURFACE_MISMATCH",
                            "gate is bound to criteria that expect conflicting verification surfaces",
                            details={"surfaces": sorted(owned_surfaces)},
                        )
                    if owned_surfaces:
                        (owned_surface,) = owned_surfaces
                        if owned_surface != evidence_surface:
                            raise RuntimeFailure(
                                "EVIDENCE_SURFACE_MISMATCH",
                                "evidence surface does not match the criterion-owned verification surface",
                                details={"criterion": owned_surface, "evidence": evidence_surface},
                            )
                elif surface is not None:
                    raise RuntimeFailure(
                        "EVIDENCE_SURFACE_MISMATCH",
                        "a verification surface was declared but no matching reality/e2e evidence was supplied",
                    )
                if "mutation" in producers:
                    for artifact in state["artifacts"]:
                        if artifact["id"] not in artifact_ids or artifact["producer"] != "mutation":
                            continue
                        receipt = self._read_json_receipt(artifact["path"], "mutation")
                        if task_id is None or receipt.get("taskId") != task_id or artifact.get("consumedByTask") != task_id:
                            raise RuntimeFailure("EVIDENCE_REPLAY", "mutation PASS gate receipt is not consumed by this task")
                        if receipt.get("result", {}).get("status") != "pass" or receipt.get("result", {}).get("mismatches") != []:
                            raise RuntimeFailure("MUTATION_RECEIPT", "mutation PASS gate requires a fully matching receipt")
            now = utc_now()
            state["gateResults"].append(
                {
                    "id": gate_id,
                    "taskId": task_id,
                    "criteria": list(dict.fromkeys(bound_criteria)),
                    "type": gate_type,
                    "family": family,
                    "status": status,
                    "startedAt": now,
                    "finishedAt": now,
                    "evidenceRefs": list(dict.fromkeys(evidence_refs)),
                }
            )
            append_checkpoint(state, task_id, "GATE_COMPLETION")
            if status == "FAIL" and gate_type in {"deterministic", "e2e", "reality", "policy", "security"}:
                state["status"] = "FAILED"
            return {"gateId": gate_id, "gateType": gate_type, "family": family, "status": status}

        return self._transaction(
            run_id,
            mutate,
            event_type="gate.passed" if status == "PASS" else "gate.failed" if status == "FAIL" else "gate.recorded",
            actor=actor,
            task_id=task_id,
            evidence_refs=evidence_refs,
        )

    def set_criterion(
        self,
        run_id: str,
        criterion_id: str,
        status: str,
        evidence_refs: Sequence[str],
        actor: str = "coordinator",
    ) -> dict[str, Any]:
        if status not in CRITERION_STATUSES:
            raise RuntimeFailure("INVALID_CRITERION", f"invalid criterion status: {status}")
        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            criterion = next((item for item in state["acceptanceCriteria"] if item["id"] == criterion_id), None)
            if criterion is None:
                raise RuntimeFailure("CRITERION_NOT_FOUND", f"criterion not found: {criterion_id}")
            if status in {"PASS", "NOT_APPLICABLE"}:
                require_evidence_refs(state, evidence_refs, allowed={"gate", "external"})
                for reference in evidence_refs:
                    kind, identifier = reference.split(":", 1)
                    if kind == "gate":
                        gate = next(item for item in state["gateResults"] if item["id"] == identifier)
                        if criterion_id not in gate["criteria"]:
                            raise RuntimeFailure(
                                "EVIDENCE_INVALID",
                                "gate evidence is not bound to this criterion",
                                details={"criterionId": criterion_id, "gateId": identifier},
                            )
                        allowed_gate_types = CRITERION_GATE_TYPES.get(criterion["verificationType"], set())
                        if gate["type"] not in allowed_gate_types:
                            raise RuntimeFailure(
                                "VERIFICATION_TYPE_MISMATCH",
                                "gate type does not satisfy the criterion's declared verificationType",
                                details={
                                    "criterionId": criterion_id,
                                    "verificationType": criterion["verificationType"],
                                    "gateType": gate["type"],
                                },
                            )
                    elif kind == "external":
                        if criterion["verificationType"] != "external":
                            raise RuntimeFailure(
                                "VERIFICATION_TYPE_MISMATCH",
                                "external evidence requires a criterion with verificationType 'external'",
                                details={"criterionId": criterion_id, "verificationType": criterion["verificationType"]},
                            )
                        checkpoint = next(item for item in state["externalCheckpoints"] if item["id"] == identifier)
                        bound_task = find_task(state, checkpoint["taskId"])
                        if criterion_id not in bound_task["acceptanceCriteria"]:
                            raise RuntimeFailure(
                                "EVIDENCE_INVALID",
                                "external checkpoint evidence is not bound to this criterion",
                                details={"criterionId": criterion_id, "checkpointId": identifier},
                            )
            criterion["status"] = status
            criterion["evidenceRefs"] = list(dict.fromkeys(evidence_refs))
            state["status"] = derive_run_status(state)
            return {"criterionId": criterion_id, "status": status}

        return self._transaction(
            run_id,
            mutate,
            event_type="acceptance.updated",
            actor=actor,
            evidence_refs=evidence_refs,
        )

    def wait_external(
        self,
        run_id: str,
        *,
        checkpoint_id: str,
        task_id: str,
        checkpoint_type: str,
        principal: str,
        provider: str,
        reason: str,
        actor: str = "coordinator",
    ) -> tuple[dict[str, Any], str]:
        require_id(checkpoint_id, "external checkpoint id")
        if checkpoint_type not in EXTERNAL_TYPES:
            raise RuntimeFailure("INVALID_EXTERNAL_CHECKPOINT", f"invalid external checkpoint type: {checkpoint_type}")
        challenge = secrets.token_urlsafe(32)
        challenge_hash = hashlib.sha256(challenge.encode("utf-8")).hexdigest()

        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            task = find_task(state, task_id)
            if task["status"] in TERMINAL_TASK_STATUSES:
                raise RuntimeFailure("TASK_TERMINAL", "terminal tasks cannot wait externally")
            if any(item["id"] == checkpoint_id for item in state["externalCheckpoints"]):
                raise RuntimeFailure("EXTERNAL_CHECKPOINT_EXISTS", f"checkpoint already exists: {checkpoint_id}")
            lease = task.get("lease")
            if lease:
                worker = next((item for item in state["workers"] if item["id"] == lease["owner"]), None)
                if worker is not None:
                    worker["status"] = "FINISHED"
            task["status"] = "WAITING_EXTERNAL"
            task["lease"] = None
            state["externalCheckpoints"].append(
                {
                    "id": checkpoint_id,
                    "taskId": task_id,
                    "type": checkpoint_type,
                    "principal": principal,
                    "provider": provider,
                    "reason": reason,
                    "createdAt": utc_now(),
                    "status": "PENDING",
                    "resumeTask": task_id,
                    "challengeHash": challenge_hash,
                    "resolutionRef": None,
                }
            )
            append_checkpoint(state, task_id, "EXTERNAL_WAIT")
            state["status"] = derive_run_status(state)
            return {
                "checkpointId": checkpoint_id,
                "type": checkpoint_type,
                "principal": principal,
                "provider": provider,
            }

        state = self._transaction(
            run_id,
            mutate,
            event_type="external.wait_started",
            actor=actor,
            task_id=task_id,
        )
        return state, challenge

    def resolve_external(
        self,
        run_id: str,
        *,
        checkpoint_id: str,
        resolution_ref: str,
        challenge: str,
        actor: str,
    ) -> dict[str, Any]:
        if actor != "coordinator" and not actor.startswith("human:"):
            raise RuntimeFailure("UNTRUSTED_RESOLUTION", "external checkpoints require a human or coordinator actor")
        if redact(resolution_ref) != resolution_ref:
            raise RuntimeFailure("SENSITIVE_RESOLUTION", "resolution reference appears to contain secret material")

        task_holder: dict[str, str] = {}

        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            checkpoint = next(
                (item for item in state["externalCheckpoints"] if item["id"] == checkpoint_id),
                None,
            )
            if checkpoint is None:
                raise RuntimeFailure("EXTERNAL_CHECKPOINT_NOT_FOUND", f"checkpoint not found: {checkpoint_id}")
            if checkpoint["status"] != "PENDING":
                raise RuntimeFailure("EXTERNAL_CHECKPOINT_TERMINAL", "checkpoint is not pending")
            supplied_hash = hashlib.sha256(challenge.encode("utf-8")).hexdigest()
            if not hmac.compare_digest(checkpoint["challengeHash"], supplied_hash):
                raise RuntimeFailure("UNTRUSTED_RESOLUTION", "external checkpoint challenge is invalid")
            require_evidence_refs(state, [resolution_ref], allowed={"artifact"})
            resolution_id = resolution_ref.split(":", 1)[1]
            resolution_artifact = next(item for item in state["artifacts"] if item["id"] == resolution_id)
            if resolution_artifact["producer"] != "external-proof":
                raise RuntimeFailure("UNTRUSTED_RESOLUTION", "external checkpoint evidence is not externally attested")
            if resolution_artifact.get("consumedByTask") is not None:
                raise RuntimeFailure("EVIDENCE_REPLAY", "external proof was already consumed")
            proof = self._read_json_receipt(resolution_artifact["path"], "external")
            if (
                proof.get("checkpointId") != checkpoint_id
                or proof.get("principal") != checkpoint["principal"]
                or proof.get("provider") != checkpoint["provider"]
            ):
                raise RuntimeFailure(
                    "EXTERNAL_PROOF_MISMATCH",
                    "external proof does not bind to this checkpoint's id, principal, and provider",
                )
            checkpoint["status"] = "RESOLVED"
            checkpoint["resolvedAt"] = utc_now()
            checkpoint["resolvedBy"] = actor
            checkpoint["resolutionRef"] = resolution_ref
            resolution_artifact["consumedByTask"] = checkpoint["resumeTask"]
            resolution_artifact["attestation"] = self._artifact_attestation(resolution_artifact)
            task = find_task(state, checkpoint["resumeTask"])
            outstanding = any(
                other["resumeTask"] == checkpoint["resumeTask"] and other["status"] == "PENDING"
                for other in state["externalCheckpoints"]
                if other["id"] != checkpoint_id
            )
            if not outstanding:
                task["status"] = "READY" if dependencies_completed(state, task) else "NOT_READY"
            task_holder["id"] = task["id"]
            state["status"] = derive_run_status(state)
            return {"checkpointId": checkpoint_id, "resumeTask": task["id"]}

        state = self._transaction(
            run_id,
            mutate,
            event_type="external.wait_resolved",
            actor=actor,
            evidence_refs=[resolution_ref],
        )
        return state

    def reconcile_side_effect(
        self,
        run_id: str,
        task_id: str,
        *,
        result: str,
        evidence_ref: str,
        actor: str = "coordinator",
    ) -> dict[str, Any]:
        if result not in {"applied", "not-applied"}:
            raise RuntimeFailure("INVALID_RECONCILIATION", "result must be applied or not-applied")

        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            task = find_task(state, task_id)
            side_effect = task["sideEffect"]
            if side_effect is None or side_effect["state"] != "UNCERTAIN":
                raise RuntimeFailure("RECONCILIATION_NOT_REQUIRED", "task has no uncertain side effect")
            require_evidence_refs(state, [evidence_ref], allowed={"artifact"})
            evidence_id = evidence_ref.split(":", 1)[1]
            artifact = next(item for item in state["artifacts"] if item["id"] == evidence_id)
            expected_producers = (
                {"reconciliation"}
                if result == "not-applied"
                else {"mutation"} if side_effect["operation"] != "edit" else {"workspace"}
            )
            if artifact["producer"] not in expected_producers:
                raise RuntimeFailure("EVIDENCE_PROVENANCE", "side-effect reconciliation evidence has the wrong producer")
            if artifact.get("consumedByTask") is not None:
                raise RuntimeFailure("EVIDENCE_REPLAY", "side-effect receipt was already consumed")
            if artifact["producer"] == "mutation":
                receipt = self._read_json_receipt(artifact["path"], "mutation")
                if (
                    receipt.get("taskId") != task_id
                    or receipt.get("operation") != side_effect["operation"]
                    or receipt.get("target") != side_effect["target"]
                ):
                    raise RuntimeFailure("EVIDENCE_REPLAY", "mutation receipt does not bind to this task side effect")
                if result != "applied":
                    raise RuntimeFailure("RECONCILIATION_CONTRADICTION", "applied mutation receipt cannot prove not-applied")
            elif artifact["producer"] == "reconciliation":
                receipt = self._read_json_receipt(artifact["path"], "reconciliation")
                if (
                    receipt.get("taskId") != task_id
                    or receipt.get("operation") != side_effect["operation"]
                    or receipt.get("target") != side_effect["target"]
                    or receipt.get("outcome") != "not-applied"
                ):
                    raise RuntimeFailure("EVIDENCE_REPLAY", "reconciliation receipt does not bind to this task/outcome")
            elif f"task:{task_id}" not in artifact["evidenceRefs"]:
                raise RuntimeFailure("EVIDENCE_REPLAY", "workspace receipt does not bind to this task")
            elif result != "applied":
                raise RuntimeFailure("RECONCILIATION_CONTRADICTION", "applied workspace receipt cannot prove not-applied")
            artifact["consumedByTask"] = task_id
            artifact["attestation"] = self._artifact_attestation(artifact)
            side_effect["state"] = "CONFIRMED" if result == "applied" else "NONE"
            side_effect["reconciliation"] = evidence_ref
            task["status"] = "WAITING_RESOURCE" if result == "applied" else "READY"
            state["status"] = derive_run_status(state)
            return {"taskId": task_id, "result": result}

        return self._transaction(
            run_id,
            mutate,
            event_type="mutation.reconciled",
            actor=actor,
            task_id=task_id,
            evidence_refs=[evidence_ref],
        )

    def prepare_side_effect(
        self,
        run_id: str,
        task_id: str,
        *,
        operation: str,
        target: str,
        confirmed: bool = False,
        actor: str = "coordinator",
    ) -> dict[str, Any]:
        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            self._assert_repository_baseline(state)
            task = find_task(state, task_id)
            if task["status"] not in {"RUNNING", "WAITING_RESOURCE"}:
                raise RuntimeFailure("SIDE_EFFECT_NOT_READY", "side effect task must be running or awaiting coordinator validation")
            require_mutation_allowed(state, target, operation, confirmed=confirmed)
            side_effect = task.get("sideEffect")
            if side_effect is None:
                side_effect = {
                    "operation": operation,
                    "target": target,
                    "state": "NONE",
                    "reconciliation": None,
                }
                task["sideEffect"] = side_effect
            if side_effect["operation"] != operation or side_effect["target"] != target:
                raise RuntimeFailure("SIDE_EFFECT_SCOPE", "side effect differs from the task's authorized operation/target")
            if side_effect["state"] not in {"NONE", "PENDING"}:
                raise RuntimeFailure("RECONCILIATION_REQUIRED", "side effect is already uncertain or confirmed")
            side_effect["state"] = "UNCERTAIN"
            append_checkpoint(state, task_id, "SIDE_EFFECT_AMBIGUITY")
            return {"taskId": task_id, "operation": operation, "target": target}

        return self._transaction(
            run_id,
            mutate,
            event_type="mutation.started",
            actor=actor,
            task_id=task_id,
        )

    def policy_check(
        self,
        run_id: str,
        scope: str,
        operation: str,
        *,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        state = self.load(run_id)
        decision = mutation_decision(state, scope, operation, confirmed=confirmed)
        event_type = "mutation.allowed" if decision["status"] == "allowed" else "mutation.denied"

        def no_mutation(run: dict[str, Any]) -> dict[str, Any]:
            return decision

        self._transaction(run_id, no_mutation, event_type=event_type, actor="coordinator")
        return decision

    def resume(self, run_id: str, *, accept_commit: bool = False, actor: str = "coordinator") -> dict[str, Any]:
        identity = self.repository_identity()

        current = self.load(run_id)
        drift = {
            key: {"expected": current["baseline"].get(key), "actual": identity.get(key)}
            for key in ("commit", "branch")
            if current["baseline"].get(key) != identity.get(key)
        }
        if drift and not accept_commit:
            def pause(state: dict[str, Any]) -> dict[str, Any]:
                state["status"] = "PAUSED"
                return {"reason": "stale-repository", "drift": drift}

            self._transaction(run_id, pause, event_type="run.paused", actor=actor)
            raise RuntimeFailure("STALE_REPOSITORY", "repository baseline drift requires reconciliation", details=drift)

        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            if Path(state["baseline"]["repository"]).resolve() != self.repository:
                raise RuntimeFailure("STALE_REPOSITORY", "Run belongs to a different repository")
            if drift:
                state["baseline"]["commit"] = identity["commit"]
                state["baseline"]["branch"] = identity["branch"]
            recovered: list[str] = []
            uncertain: list[str] = []
            for task in state["tasks"]:
                if task["status"] != "RUNNING":
                    continue
                lease = task.get("lease")
                if lease:
                    worker = next((item for item in state["workers"] if item["id"] == lease["owner"]), None)
                    if worker is not None:
                        worker["status"] = "FAILED"
                task["lease"] = None
                if task["sideEffect"] and task["sideEffect"]["state"] in {"PENDING", "UNCERTAIN"}:
                    task["sideEffect"]["state"] = "UNCERTAIN"
                    task["status"] = "WAITING_RESOURCE"
                    append_checkpoint(state, task["id"], "SIDE_EFFECT_AMBIGUITY")
                    uncertain.append(task["id"])
                else:
                    task["status"] = "READY" if dependencies_completed(state, task) else "NOT_READY"
                    recovered.append(task["id"])
            refresh_task_readiness(state)
            state["status"] = derive_run_status(state)
            if state["status"] == "PAUSED" and state["autonomy"]["scope"] == "current-task":
                state["status"] = "RUNNING" if any(task["status"] == "READY" for task in state["tasks"]) else state["status"]
            return {"recoveredTasks": recovered, "uncertainSideEffects": uncertain, "baselineDriftAccepted": bool(drift)}

        return self._transaction(run_id, mutate, event_type="run.resumed", actor=actor)

    def verify(self, run_id: str, actor: str = "coordinator") -> tuple[dict[str, Any], bool]:
        outcome: dict[str, Any] = {}

        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            required = [criterion for criterion in state["acceptanceCriteria"] if criterion["blocking"]]
            deterministic_failures = [
                gate["id"]
                for gate in state["gateResults"]
                if gate["status"] == "FAIL" and gate["type"] in {"deterministic", "e2e", "reality", "policy", "security"}
            ]
            failed = [criterion["id"] for criterion in required if criterion["status"] == "FAIL"]
            untested = [criterion["id"] for criterion in required if criterion["status"] == "UNTESTED"]
            blocked = [criterion["id"] for criterion in required if criterion["status"] == "BLOCKED_EXTERNAL"]
            missing_evidence = [
                criterion["id"]
                for criterion in required
                if criterion["status"] in {"PASS", "NOT_APPLICABLE"}
                and (
                    not criterion["evidenceRefs"]
                    or any(evidence_ref_kind(state, reference) is None for reference in criterion["evidenceRefs"])
                )
            ]
            incomplete_tasks = [
                task["id"] for task in state["tasks"] if task["status"] not in {"COMPLETED", "SKIPPED"}
            ]
            pending_external = [
                checkpoint["id"]
                for checkpoint in state["externalCheckpoints"]
                if checkpoint["status"] == "PENDING"
            ]
            high_risk = [criterion for criterion in required if criterion["risk"] in {"R3", "R4"}]
            passed_real_gates = {
                gate["type"]
                for gate in state["gateResults"]
                if gate["status"] == "PASS" and gate["type"] in {"e2e", "reality"}
            }
            missing_reality = bool(high_risk and not passed_real_gates)
            missing_risk_gates = missing_gate_requirements(state, required)

            if deterministic_failures or failed or missing_evidence:
                state["status"] = "FAILED"
            elif blocked or pending_external:
                state["status"] = "WAITING_EXTERNAL"
            elif untested or incomplete_tasks or missing_reality or missing_risk_gates:
                state["status"] = "VERIFYING"
            else:
                state["status"] = "COMPLETED"
            outcome.update(
                {
                    "status": state["status"],
                    "deterministicFailures": deterministic_failures,
                    "failedCriteria": failed,
                    "untestedCriteria": untested,
                    "blockedExternalCriteria": blocked,
                    "missingEvidence": missing_evidence,
                    "incompleteTasks": incomplete_tasks,
                    "pendingExternalCheckpoints": pending_external,
                    "missingRealityGate": missing_reality,
                    "missingRiskGates": missing_risk_gates,
                }
            )
            return outcome

        state = self._transaction(
            run_id,
            mutate,
            event_type="run.verifying",
            actor=actor,
        )
        completed = state["status"] == "COMPLETED"
        if completed:
            state = self._transaction(
                run_id,
                lambda _: {"outcome": "satisfied"},
                event_type="run.completed",
                actor=actor,
            )
        return state, completed

    def migrate_v1(self, summary_path: Path, *, run_id: str | None = None) -> dict[str, Any]:
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeFailure("V1_INVALID", f"cannot read v1 summary: {summary_path}") from exc
        if summary.get("schema") != "architrave.run.v1":
            raise RuntimeFailure("V1_INVALID", "input is not an architrave.run.v1 summary")
        migrated_id = run_id or f"{summary.get('runId', 'run')}-v2"
        state = self.create(
            goal=f"Migrated v1 Run {summary.get('runId', 'unknown')}",
            outcome="Preserve the legacy Run as durable v2 state without claiming new verification.",
            criteria=[
                {
                    "id": "MIGRATION-001",
                    "description": "Legacy phases are represented in Run v2.",
                    "scope": "migration",
                    "risk": "R0",
                    "verificationType": "deterministic",
                    "status": "UNTESTED",
                    "evidenceRefs": [],
                    "blocking": True,
                }
            ],
            autonomy_scope="advisory-only",
            run_id=migrated_id,
        )
        previous_task: str | None = None
        legacy_statuses: dict[str, str] = {}
        for index, phase in enumerate(summary.get("phases") or [], start=1):
            task_id = f"legacy-{index}"
            state = self.add_task(
                migrated_id,
                {
                    "id": task_id,
                    "title": str(phase.get("name") or f"Legacy phase {index}"),
                    "objective": str(phase.get("scope") or "Preserve legacy phase state."),
                    "dependencies": [previous_task] if previous_task else [],
                    "workerProfile": "shell",
                    "risk": "R0",
                    "acceptanceCriteria": ["MIGRATION-001"],
                    "requiredArtifacts": [],
                    "gate": str(phase.get("gate") or "legacy projection"),
                },
            )
            legacy_statuses[task_id] = str(phase.get("status") or "not-started")
            previous_task = task_id

        status_map = {
            "not-started": "NOT_READY",
            "in-progress": "READY",
            "blocked": "WAITING_RESOURCE",
            "completed": "COMPLETED",
            "skipped": "SKIPPED",
        }

        def preserve_statuses(run: dict[str, Any]) -> dict[str, Any]:
            for task in run["tasks"]:
                task["status"] = status_map.get(legacy_statuses[task["id"]], "NOT_READY")
            run["status"] = derive_run_status(run)
            return {"sourceSchema": "architrave.run.v1", "phaseStatuses": legacy_statuses}

        return self._transaction(
            migrated_id,
            preserve_statuses,
            event_type="run.migrated",
            actor="coordinator",
        )


def normalize_policy_allow(entries: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for entry in entries:
        scope = str(entry.get("scope") or "").strip()
        operations = tuple(dict.fromkeys(str(item).strip() for item in entry.get("operations", []) if str(item).strip()))
        if not scope or not operations:
            raise RuntimeFailure("INVALID_POLICY", "policy allows require scope and operations")
        key = (scope, operations)
        if key not in seen:
            result.append({"scope": scope, "operations": list(operations)})
            seen.add(key)
    return result


def normalize_criteria(criteria: Sequence[dict[str, Any]], outcome: str) -> list[dict[str, Any]]:
    if not criteria:
        criteria = [
            {
                "id": "OUTCOME-001",
                "description": outcome.strip(),
                "scope": "program",
                "risk": "R1",
                "verificationType": "deterministic",
                "status": "UNTESTED",
                "evidenceRefs": [],
                "blocking": True,
            }
        ]
    normalized: list[dict[str, Any]] = []
    ids: set[str] = set()
    for raw in criteria:
        criterion_id = require_id(str(raw.get("id") or ""), "criterion id")
        if criterion_id in ids:
            raise RuntimeFailure("INVALID_CRITERION", f"duplicate criterion id: {criterion_id}")
        risk = str(raw.get("risk") or "R1")
        if risk not in RISK_CLASSES:
            raise RuntimeFailure("INVALID_CRITERION", f"invalid risk: {risk}")
        verification = str(raw.get("verificationType") or "deterministic")
        if verification not in {"deterministic", "e2e", "semantic", "reality", "external"}:
            raise RuntimeFailure("INVALID_CRITERION", f"invalid verification type: {verification}")
        surface_raw = raw.get("surface")
        surface = str(surface_raw) if surface_raw not in (None, "") else None
        if verification in SURFACE_VERIFICATION_TYPES:
            if surface is None:
                raise RuntimeFailure(
                    "INVALID_CRITERION",
                    f"criterion {criterion_id} has verificationType '{verification}' and must "
                    "declare the product surface it verifies",
                )
            if surface not in SURFACE_VALUES:
                raise RuntimeFailure("INVALID_CRITERION", f"invalid verification surface: {surface}")
        elif surface is not None:
            raise RuntimeFailure(
                "INVALID_CRITERION",
                f"criterion {criterion_id} has verificationType '{verification}' and must not "
                "declare a verification surface",
            )
        normalized.append(
            {
                "id": criterion_id,
                "description": str(raw.get("description") or "").strip(),
                "scope": str(raw.get("scope") or "program"),
                "risk": risk,
                "verificationType": verification,
                "surface": surface,
                "status": str(raw.get("status") or "UNTESTED"),
                "evidenceRefs": list(dict.fromkeys(raw.get("evidenceRefs") or [])),
                "blocking": bool(raw.get("blocking", True)),
            }
        )
        ids.add(criterion_id)
    return normalized


def normalize_work_packet(
    value: dict[str, Any] | None,
    task_id: str,
    *,
    normalized_defaults: dict[str, Any],
) -> dict[str, Any]:
    value = value or {}
    packet_id = require_id(str(value.get("workPacketId") or f"wp-{task_id}"), "work packet id")
    return {
        "workPacketId": packet_id,
        "taskId": task_id,
        "objective": str(value.get("objective") or normalized_defaults["objective"]),
        "acceptanceCriteria": list(value.get("acceptanceCriteria") or normalized_defaults["acceptanceCriteria"]),
        "contextBundle": [safe_relative_path(path, "context path") for path in value.get("contextBundle", [])],
        "repoScope": str(value.get("repoScope") or normalized_defaults["repoScope"]),
        "mutablePaths": [safe_relative_path(path, "mutable path") for path in value.get("mutablePaths", normalized_defaults["mutablePaths"])],
        "tools": list(dict.fromkeys(value.get("tools") or normalized_defaults["tools"])),
        "worker": str(value.get("worker") or normalized_defaults["worker"]),
        "model": value.get("model"),
        "risk": str(value.get("risk") or normalized_defaults["risk"]),
        "expectedArtifacts": list(value.get("expectedArtifacts") or normalized_defaults["expectedArtifacts"]),
        "budget": {
            "timeoutSeconds": int((value.get("budget") or {}).get("timeoutSeconds", 3600)),
            "maxOutputBytes": int((value.get("budget") or {}).get("maxOutputBytes", 1024 * 1024)),
        },
        "execution": normalize_execution(value.get("execution")),
    }


def normalize_execution(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    command = value.get("command") or []
    if not isinstance(command, list) or not command or not all(isinstance(item, str) and item for item in command):
        raise RuntimeFailure("INVALID_EXECUTION", "execution command must be a non-empty argv array")
    cwd = value.get("cwd")
    if cwd is not None:
        cwd = safe_relative_path(str(cwd), "execution cwd")
    environment = list(dict.fromkeys(value.get("environment") or []))
    if any(not re.fullmatch(r"[A-Z_][A-Z0-9_]*", str(name)) for name in environment):
        raise RuntimeFailure("INVALID_EXECUTION", "execution environment contains an invalid variable name")
    return {"command": list(command), "cwd": cwd, "environment": environment}


def validate_run(state: dict[str, Any]) -> None:
    required = {
        "schema",
        "revision",
        "runId",
        "createdAt",
        "updatedAt",
        "goal",
        "status",
        "autonomy",
        "policy",
        "outcome",
        "acceptanceCriteria",
        "baseline",
        "tasks",
        "checkpoints",
        "externalCheckpoints",
        "artifacts",
        "workers",
        "gateResults",
        "eventLog",
        "eventCursor",
        "pendingEvent",
    }
    if set(state) != required:
        raise RuntimeFailure("RUN_INVALID", "Run has missing or unknown top-level fields")
    if state["schema"] != SCHEMA or state["status"] not in RUN_STATUSES:
        raise RuntimeFailure("RUN_INVALID", "Run schema or status is invalid")
    require_id(str(state["runId"]), "run id")
    if not isinstance(state["revision"], int) or state["revision"] < -1:
        raise RuntimeFailure("RUN_INVALID", "Run revision is invalid")
    if state["autonomy"].get("scope") not in {"current-task", "approved-program", "advisory-only"}:
        raise RuntimeFailure("RUN_INVALID", "Run autonomy scope is invalid")
    if state["policy"].get("default") != "deny":
        raise RuntimeFailure("RUN_INVALID", "mutation policy must default to deny")
    normalize_policy_allow(state["policy"].get("allow") or [])
    criteria_ids: set[str] = set()
    for criterion in state["acceptanceCriteria"]:
        criterion_id = require_id(str(criterion.get("id") or ""), "criterion id")
        if criterion_id in criteria_ids or criterion.get("risk") not in RISK_CLASSES:
            raise RuntimeFailure("RUN_INVALID", "acceptance criteria are invalid")
        if criterion.get("status") not in CRITERION_STATUSES:
            raise RuntimeFailure("RUN_INVALID", "acceptance criterion status is invalid")
        surface = criterion.get("surface")
        if surface is not None and surface not in SURFACE_VALUES:
            raise RuntimeFailure("RUN_INVALID", "acceptance criterion surface is invalid")
        criteria_ids.add(criterion_id)
    outcome_ids = {item.get("id") for item in state["outcome"].get("requiredCriteria", [])}
    if not outcome_ids or not outcome_ids.issubset(criteria_ids):
        raise RuntimeFailure("RUN_INVALID", "Outcome references unknown acceptance criteria")
    validate_task_graph(state["tasks"])
    for task in state["tasks"]:
        if task["risk"] not in RISK_CLASSES or task["status"] not in TASK_STATUSES:
            raise RuntimeFailure("RUN_INVALID", f"task {task['id']} risk or status is invalid")
        if not set(task["acceptanceCriteria"]).issubset(criteria_ids):
            raise RuntimeFailure("RUN_INVALID", f"task {task['id']} references unknown criteria")
        for path in task["mutablePaths"]:
            safe_relative_path(path, "mutable path")
        for path in task["workPacket"]["contextBundle"]:
            safe_relative_path(path, "context path")
    checkpoint_ids = [item.get("id") for item in state["checkpoints"]]
    external_ids = [item.get("id") for item in state["externalCheckpoints"]]
    if len(checkpoint_ids) != len(set(checkpoint_ids)) or len(external_ids) != len(set(external_ids)):
        raise RuntimeFailure("RUN_INVALID", "checkpoint ids must be unique")
    for checkpoint in state["externalCheckpoints"]:
        if not re.fullmatch(r"[0-9a-f]{64}", str(checkpoint.get("challengeHash", ""))):
            raise RuntimeFailure("RUN_INVALID", "external checkpoint challenge hash is invalid")
    gate_ids: set[str] = set()
    for gate in state["gateResults"]:
        gate_id = require_id(str(gate.get("id") or ""), "gate id")
        if gate_id in gate_ids or not gate.get("criteria") or not set(gate["criteria"]).issubset(criteria_ids):
            raise RuntimeFailure("RUN_INVALID", "gate ids and criterion bindings must be valid")
        gate_ids.add(gate_id)
    cursor = state["eventCursor"]
    if not isinstance(cursor.get("sequence"), int) or cursor["sequence"] < 0:
        raise RuntimeFailure("RUN_INVALID", "event cursor sequence is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", str(cursor.get("lastHash", ""))):
        raise RuntimeFailure("RUN_INVALID", "event cursor hash is invalid")


def validate_task_graph(tasks: Sequence[dict[str, Any]]) -> None:
    task_ids = [require_id(str(task.get("id") or ""), "task id") for task in tasks]
    if len(task_ids) != len(set(task_ids)):
        raise RuntimeFailure("TASK_GRAPH_INVALID", "task ids must be unique")
    known = set(task_ids)
    graph: dict[str, list[str]] = {}
    for task in tasks:
        dependencies = list(task.get("dependencies") or [])
        if task["id"] in dependencies or not set(dependencies).issubset(known):
            raise RuntimeFailure("TASK_GRAPH_INVALID", f"task {task['id']} has invalid dependencies")
        graph[task["id"]] = dependencies

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise RuntimeFailure("TASK_GRAPH_CYCLE", f"task graph cycle includes {task_id}")
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in graph[task_id]:
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in task_ids:
        visit(task_id)


def find_task(state: dict[str, Any], task_id: str) -> dict[str, Any]:
    require_id(task_id, "task id")
    task = next((item for item in state["tasks"] if item["id"] == task_id), None)
    if task is None:
        raise RuntimeFailure("TASK_NOT_FOUND", f"task not found: {task_id}")
    return task


def dependencies_completed(state: dict[str, Any], task: dict[str, Any]) -> bool:
    statuses = {item["id"]: item["status"] for item in state["tasks"]}
    return all(statuses.get(dependency) in {"COMPLETED", "SKIPPED"} for dependency in task["dependencies"])


def mutable_scopes_overlap(left: Sequence[str], right: Sequence[str]) -> bool:
    def prefix(pattern: str) -> str:
        wildcard = min(
            [position for token in "*?[" if (position := pattern.find(token)) >= 0]
            or [len(pattern)]
        )
        return pattern[:wildcard].rstrip("/")

    for left_pattern in left:
        for right_pattern in right:
            if left_pattern == right_pattern:
                return True
            left_prefix = prefix(left_pattern)
            right_prefix = prefix(right_pattern)
            if not left_prefix or not right_prefix:
                return True
            if (
                left_prefix == right_prefix
                or left_prefix.startswith(right_prefix + "/")
                or right_prefix.startswith(left_prefix + "/")
            ):
                return True
    return False


def refresh_task_readiness(state: dict[str, Any]) -> list[str]:
    newly_ready: list[str] = []
    for task in state["tasks"]:
        if task["status"] == "NOT_READY" and dependencies_completed(state, task):
            task["status"] = "READY"
            newly_ready.append(task["id"])
    return newly_ready


def derive_run_status(state: dict[str, Any]) -> str:
    if state["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
        return state["status"]
    statuses = {task["status"] for task in state["tasks"]}
    if "RUNNING" in statuses:
        return "RUNNING"
    if "READY" in statuses:
        return "RUNNING"
    pending_external = any(item["status"] == "PENDING" for item in state["externalCheckpoints"])
    if pending_external or "WAITING_EXTERNAL" in statuses:
        return "WAITING_EXTERNAL"
    if "WAITING_RESOURCE" in statuses:
        return "WAITING_RESOURCE"
    if statuses and statuses.issubset({"COMPLETED", "SKIPPED"}):
        return "VERIFYING"
    if "FAILED" in statuses:
        return "FAILED"
    return "PLANNING" if state["tasks"] else "CREATED"


def append_checkpoint(state: dict[str, Any], task_id: str | None, kind: str) -> None:
    snapshot = copy.deepcopy(state)
    snapshot["pendingEvent"] = None
    checkpoint = {
        "id": f"cp-{uuid.uuid4().hex}",
        "taskId": task_id,
        "kind": kind,
        "createdAt": utc_now(),
        "revision": state["revision"],
        "stateHash": sha256_value(snapshot),
    }
    state["checkpoints"].append(checkpoint)


def evidence_ref_kind(state: dict[str, Any], reference: str) -> str | None:
    if ":" not in reference:
        return None
    kind, identifier = reference.split(":", 1)
    if kind == "artifact" and any(item["id"] == identifier for item in state["artifacts"]):
        return kind
    if kind == "gate" and any(item["id"] == identifier and item["status"] == "PASS" for item in state["gateResults"]):
        return kind
    if kind == "external" and any(item["id"] == identifier and item["status"] == "RESOLVED" for item in state["externalCheckpoints"]):
        return kind
    return None


def require_evidence_refs(state: dict[str, Any], references: Sequence[str], *, allowed: set[str]) -> None:
    if not references:
        raise RuntimeFailure("EVIDENCE_REQUIRED", "registered evidence is required")
    invalid = [
        reference
        for reference in references
        if evidence_ref_kind(state, reference) not in allowed
    ]
    if invalid:
        raise RuntimeFailure(
            "EVIDENCE_INVALID",
            "evidence references must resolve to registered Run evidence",
            details={"references": invalid, "allowed": sorted(allowed)},
        )


DEFAULT_RISK_GATES = {
    "R0": ["deterministic"],
    "R1": ["deterministic"],
    "R2": ["deterministic", "semantic-any"],
    "R3": ["deterministic", "e2e-or-reality", "semantic-gpt", "semantic-claude"],
    "R4": ["deterministic", "e2e-or-reality", "semantic-gpt", "semantic-claude", "security", "policy"],
}


def evaluation_config(repository: str) -> dict[str, Any]:
    path = Path(repository) / "architrave.config.json"
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value.get("evaluation") or {} if isinstance(value, dict) else {}


def repository_config(repository: str) -> dict[str, Any]:
    path = Path(repository) / "architrave.config.json"
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def missing_gate_requirements(state: dict[str, Any], criteria: Sequence[dict[str, Any]]) -> list[str]:
    repo_config = repository_config(state["baseline"]["repository"])
    configured = repo_config.get("evaluation") or {}
    risk_policy = configured.get("riskPolicy") or {}
    missing: list[str] = []
    for criterion in criteria:
        requirements = list(
            dict.fromkeys(
                [
                    *DEFAULT_RISK_GATES[criterion["risk"]],
                    *(risk_policy.get(criterion["risk"]) or []),
                ]
            )
        )
        if configured.get("realityGate") and criterion["risk"] in {"R2", "R3", "R4"}:
            requirements = [*requirements, "reality"]
        if repo_config.get("invariants"):
            requirements = [*requirements, "invariant"]
        passed = [
            gate
            for gate in state["gateResults"]
            if gate["status"] == "PASS" and criterion["id"] in gate["criteria"]
        ]
        capabilities: set[str] = {gate["type"] for gate in passed}
        if any(gate["type"] == "semantic" for gate in passed):
            capabilities.add("semantic-any")
        if any(gate["type"] == "semantic" and gate.get("family") == "gpt" for gate in passed):
            capabilities.add("semantic-gpt")
        if any(gate["type"] == "semantic" and gate.get("family") == "claude" for gate in passed):
            capabilities.add("semantic-claude")
        if any(gate["type"] in {"e2e", "reality"} for gate in passed):
            capabilities.add("e2e-or-reality")
        if any(
            gate["type"] == "deterministic"
            and gate["id"].startswith("invariants-")
            and any(
                artifact["producer"] == "invariant"
                and f"artifact:{artifact['id']}" in gate["evidenceRefs"]
                for artifact in state["artifacts"]
            )
            for gate in passed
        ):
            capabilities.add("invariant")
        missing.extend(
            f"{criterion['id']}:{requirement}"
            for requirement in requirements
            if requirement not in capabilities
        )
    return sorted(set(missing))


def mutation_decision(state: dict[str, Any], scope: str, operation: str, *, confirmed: bool) -> dict[str, Any]:
    if state["autonomy"]["scope"] == "advisory-only":
        return {"status": "denied", "reason": "advisory-only", "scope": scope, "operation": operation}
    allowed = any(
        (entry["scope"] == scope or entry["scope"] == "*")
        and (operation in entry["operations"] or "*" in entry["operations"])
        for entry in state["policy"]["allow"]
    )
    if not allowed:
        return {"status": "denied", "reason": "default-deny", "scope": scope, "operation": operation}
    if operation in state["policy"]["confirmationRequired"] and not confirmed:
        return {
            "status": "confirmation-required",
            "reason": "operation-requires-confirmation",
            "scope": scope,
            "operation": operation,
        }
    return {"status": "allowed", "reason": "scoped-policy", "scope": scope, "operation": operation}


def require_mutation_allowed(state: dict[str, Any], scope: str, operation: str, *, confirmed: bool) -> None:
    decision = mutation_decision(state, scope, operation, confirmed=confirmed)
    if decision["status"] != "allowed":
        raise RuntimeFailure(
            "MUTATION_DENIED",
            f"mutation {scope}:{operation} is {decision['status']} ({decision['reason']})",
            details=decision,
        )


def parse_criterion(value: str) -> dict[str, Any]:
    parts = value.split("|", 5)
    if len(parts) not in (5, 6):
        raise RuntimeFailure(
            "INVALID_ARGUMENT",
            "criterion must be ID|description|scope|R0-R4|deterministic|e2e|semantic|reality|external"
            "[|web|electron|ios|deployment|runtime] (surface is required for reality/e2e)",
            exit_code=2,
        )
    criterion_id, description, scope, risk, verification, *rest = parts
    surface = rest[0] if rest and rest[0] else None
    return {
        "id": criterion_id,
        "description": description,
        "scope": scope,
        "risk": risk,
        "verificationType": verification,
        "surface": surface,
        "status": "UNTESTED",
        "evidenceRefs": [],
        "blocking": True,
    }


def parse_policy_allow(value: str) -> dict[str, Any]:
    if ":" not in value:
        raise RuntimeFailure("INVALID_ARGUMENT", "allow must be SCOPE:operation[,operation]", exit_code=2)
    scope, operations = value.rsplit(":", 1)
    return {"scope": scope, "operations": [item for item in operations.split(",") if item]}


def split_csv(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def state_summary(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "runId": state["runId"],
        "status": state["status"],
        "revision": state["revision"],
        "autonomy": state["autonomy"]["scope"],
        "readyTasks": [task["id"] for task in state["tasks"] if task["status"] == "READY"],
        "runningTasks": [task["id"] for task in state["tasks"] if task["status"] == "RUNNING"],
        "pendingExternal": [
            checkpoint["id"] for checkpoint in state["externalCheckpoints"] if checkpoint["status"] == "PENDING"
        ],
        "acceptance": {criterion["id"]: criterion["status"] for criterion in state["acceptanceCriteria"]},
        "eventCursor": state["eventCursor"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Architrave durable Run v2 control plane")
    parser.add_argument("--repo", default=".", help="repository root (default: current directory)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("run", aliases=["create"], help="create a durable Run")
    create.add_argument("--goal", required=True)
    create.add_argument("--outcome", required=True)
    create.add_argument("--criterion", action="append", default=[])
    create.add_argument("--autonomy", choices=["current-task", "approved-program", "advisory-only"], default="current-task")
    create.add_argument("--allow", action="append", default=[])
    create.add_argument("--confirmation-required", action="append", default=[])
    create.add_argument("--run-id")

    for command in ("status", "inspect", "events", "ready", "resume", "verify"):
        current = subparsers.add_parser(command)
        current.add_argument("run_id", nargs="?")
        if command == "resume":
            current.add_argument("--accept-commit", action="store_true")

    task_add = subparsers.add_parser("task-add")
    task_add.add_argument("run_id")
    task_add.add_argument("--id", required=True)
    task_add.add_argument("--title", required=True)
    task_add.add_argument("--objective", required=True)
    task_add.add_argument("--depends-on")
    task_add.add_argument("--worker", choices=["copilot", "claude", "codex", "shell"], default="shell")
    task_add.add_argument("--workspace")
    task_add.add_argument("--mutable-path", action="append", default=[])
    task_add.add_argument("--tool", action="append", default=[])
    task_add.add_argument("--risk", choices=sorted(RISK_CLASSES), default="R1")
    task_add.add_argument("--criteria", required=True)
    task_add.add_argument("--artifact", action="append", default=[])
    task_add.add_argument("--gate")
    task_add.add_argument("--max-attempts", type=int, default=1)
    task_add.add_argument("--side-effect", help="OPERATION@TARGET")
    task_add.add_argument("--command", nargs=argparse.REMAINDER, help="deterministic shell argv (must be last)")

    task_start = subparsers.add_parser("task-start")
    task_start.add_argument("run_id")
    task_start.add_argument("task_id")
    task_start.add_argument("--worker-id", required=True)
    task_start.add_argument("--lease-seconds", type=int, default=3600)
    task_start.add_argument("--confirmed", action="store_true")

    worker_finish = subparsers.add_parser("worker-finish")
    worker_finish.add_argument("run_id")
    worker_finish.add_argument("task_id")
    worker_finish.add_argument("--worker-id", required=True)
    worker_finish.add_argument("--status", choices=["FINISHED", "FAILED"], required=True)
    worker_finish.add_argument("--evidence", action="append", default=[])

    task_complete = subparsers.add_parser("task-complete")
    task_complete.add_argument("run_id")
    task_complete.add_argument("task_id")
    task_complete.add_argument("--evidence", action="append", required=True)

    task_fail = subparsers.add_parser("task-fail")
    task_fail.add_argument("run_id")
    task_fail.add_argument("task_id")
    task_fail.add_argument("--reason", required=True)

    gate = subparsers.add_parser("gate-record")
    gate.add_argument("run_id")
    gate.add_argument("--id", required=True)
    gate.add_argument("--task-id")
    gate.add_argument("--type", choices=["deterministic", "e2e", "semantic", "reality", "policy", "security"], required=True)
    gate.add_argument("--family", choices=["gpt", "claude", "security"])
    gate.add_argument("--criteria", help="comma-separated acceptance criterion ids")
    gate.add_argument("--surface", help="verification surface this reality/e2e gate proves (e.g. web, ios, electron)")
    gate.add_argument("--status", choices=["PASS", "FAIL", "BLOCKED", "SKIPPED"], required=True)
    gate.add_argument("--evidence", action="append", default=[])

    criterion = subparsers.add_parser("criterion-set")
    criterion.add_argument("run_id")
    criterion.add_argument("criterion_id")
    criterion.add_argument("--status", choices=sorted(CRITERION_STATUSES), required=True)
    criterion.add_argument("--evidence", action="append", default=[])

    wait = subparsers.add_parser("external-wait")
    wait.add_argument("run_id")
    wait.add_argument("--id", required=True)
    wait.add_argument("--task-id", required=True)
    wait.add_argument("--type", choices=sorted(EXTERNAL_TYPES), required=True)
    wait.add_argument("--principal", required=True)
    wait.add_argument("--provider", required=True)
    wait.add_argument("--reason", required=True)

    resolve = subparsers.add_parser("external-resolve")
    resolve.add_argument("run_id")
    resolve.add_argument("checkpoint_id")
    resolve.add_argument("--resolution-ref", required=True)
    resolve.add_argument("--challenge", required=True)
    resolve.add_argument("--actor", required=True, help="human:<name> or coordinator")

    reconcile = subparsers.add_parser("reconcile-side-effect")
    reconcile.add_argument("run_id")
    reconcile.add_argument("task_id")
    reconcile.add_argument("--result", choices=["applied", "not-applied"], required=True)
    reconcile.add_argument("--evidence", required=True)

    policy = subparsers.add_parser("policy-check")
    policy.add_argument("run_id")
    policy.add_argument("--scope", required=True)
    policy.add_argument("--operation", required=True)
    policy.add_argument("--confirmed", action="store_true")

    migrate = subparsers.add_parser("migrate-v1")
    migrate.add_argument("summary")
    migrate.add_argument("--run-id")
    return parser


def cli(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    store = RunStore(args.repo)
    try:
        command = args.command
        if command in {"run", "create"}:
            state = store.create(
                goal=args.goal,
                outcome=args.outcome,
                criteria=[parse_criterion(item) for item in args.criterion],
                autonomy_scope=args.autonomy,
                policy_allow=[parse_policy_allow(item) for item in args.allow],
                confirmation_required=args.confirmation_required,
                run_id=args.run_id,
            )
            output = state_summary(state)
        elif command == "status":
            output = state_summary(store.load(args.run_id))
        elif command == "inspect":
            output = store.load(args.run_id)
        elif command == "events":
            output = store.events(args.run_id)
        elif command == "ready":
            output = {"tasks": store.ready_tasks(args.run_id)}
        elif command == "resume":
            run_id = args.run_id or store.latest_run_id()
            output = state_summary(store.resume(run_id, accept_commit=args.accept_commit))
        elif command == "verify":
            run_id = args.run_id or store.latest_run_id()
            state, completed = store.verify(run_id)
            output = state_summary(state)
            if not completed:
                print(json.dumps({"status": "incomplete", "result": output}, indent=2))
                return 1
        elif command == "task-add":
            side_effect = None
            if args.side_effect:
                if "@" not in args.side_effect:
                    raise RuntimeFailure("INVALID_ARGUMENT", "side-effect must be OPERATION@TARGET", exit_code=2)
                operation, target = args.side_effect.split("@", 1)
                side_effect = {"operation": operation, "target": target}
            state = store.add_task(
                args.run_id,
                {
                    "id": args.id,
                    "title": args.title,
                    "objective": args.objective,
                    "dependencies": split_csv(args.depends_on),
                    "workerProfile": args.worker,
                    "workspace": args.workspace,
                    "mutablePaths": args.mutable_path,
                    "tools": args.tool,
                    "risk": args.risk,
                    "acceptanceCriteria": split_csv(args.criteria),
                    "requiredArtifacts": args.artifact,
                    "gate": args.gate,
                    "maxAttempts": args.max_attempts,
                    "sideEffect": side_effect,
                    "workPacket": {
                        "execution": {
                            "command": args.command,
                            "cwd": None,
                            "environment": [],
                        }
                    } if args.command else None,
                },
            )
            output = state_summary(state)
        elif command == "task-start":
            output = state_summary(
                store.start_task(
                    args.run_id,
                    args.task_id,
                    worker_id=args.worker_id,
                    lease_seconds=args.lease_seconds,
                    confirmed=args.confirmed,
                )
            )
        elif command == "worker-finish":
            output = state_summary(
                store.finish_worker(
                    args.run_id,
                    args.task_id,
                    worker_id=args.worker_id,
                    status=args.status,
                    artifact_refs=args.evidence,
                )
            )
        elif command == "task-complete":
            output = state_summary(store.complete_task(args.run_id, args.task_id, evidence_refs=args.evidence))
        elif command == "task-fail":
            output = state_summary(store.fail_task(args.run_id, args.task_id, args.reason))
        elif command == "gate-record":
            output = state_summary(
                store.record_gate(
                    args.run_id,
                    gate_id=args.id,
                    task_id=args.task_id,
                    gate_type=args.type,
                    status=args.status,
                    evidence_refs=args.evidence,
                    family=args.family,
                    criteria=split_csv(args.criteria) if args.criteria else None,
                    surface=args.surface,
                )
            )
        elif command == "criterion-set":
            output = state_summary(
                store.set_criterion(args.run_id, args.criterion_id, args.status, args.evidence)
            )
        elif command == "external-wait":
            state, challenge = store.wait_external(
                args.run_id,
                checkpoint_id=args.id,
                task_id=args.task_id,
                checkpoint_type=args.type,
                principal=args.principal,
                provider=args.provider,
                reason=args.reason,
            )
            output = {**state_summary(state), "resolutionChallenge": challenge}
        elif command == "external-resolve":
            output = state_summary(
                store.resolve_external(
                    args.run_id,
                    checkpoint_id=args.checkpoint_id,
                    resolution_ref=args.resolution_ref,
                    challenge=args.challenge,
                    actor=args.actor,
                )
            )
        elif command == "reconcile-side-effect":
            output = state_summary(
                store.reconcile_side_effect(
                    args.run_id,
                    args.task_id,
                    result=args.result,
                    evidence_ref=args.evidence,
                )
            )
        elif command == "policy-check":
            output = store.policy_check(
                args.run_id,
                args.scope,
                args.operation,
                confirmed=args.confirmed,
            )
            if output["status"] != "allowed":
                print(json.dumps({"status": "denied", "result": output}, indent=2))
                return 3
        elif command == "migrate-v1":
            output = state_summary(store.migrate_v1(Path(args.summary), run_id=args.run_id))
        else:
            parser.error(f"unsupported command: {command}")
            return 2
        print(json.dumps({"status": "ok", "result": output}, indent=2))
        return 0
    except RuntimeFailure as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error": {"code": exc.code, "message": exc.message, "details": redact(exc.details)},
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(cli())