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
    "DEFERRED",
    "SKIPPED",
    "CANCELLED",
}
TERMINAL_TASK_STATUSES = {"COMPLETED", "FAILED", "DEFERRED", "SKIPPED", "CANCELLED"}
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
    "deterministic": {"deterministic-result", "reuse-baseline"},
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
WORK_KINDS = {"product", "diagnostic", "infrastructure", "review", "research", "communications"}
TARGET_OPERATIONS = {"launch", "test", "install"}


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


def sha256_path(path: Path) -> str:
    if path.is_file():
        return sha256_file(path)
    if not path.is_dir():
        raise RuntimeFailure("EVIDENCE_RECEIPT", f"evidence path does not exist: {path}")
    digest = hashlib.sha256()
    for child in sorted(item for item in path.rglob("*") if item.is_file()):
        digest.update(child.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(child).encode("ascii"))
        digest.update(b"\n")
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


class _ObjectiveAuthorization:
    __slots__ = ("issuer", "from_version", "to_version", "checkpoint_id")

    def __init__(self, issuer: object, from_version: int, to_version: int, checkpoint_id: str):
        self.issuer = issuer
        self.from_version = from_version
        self.to_version = to_version
        self.checkpoint_id = checkpoint_id


class _PolicyAuthorization:
    __slots__ = ("issuer", "objective_version", "revision", "checkpoint_id", "challenge")

    def __init__(
        self,
        issuer: object,
        objective_version: int,
        revision: int,
        checkpoint_id: str,
        challenge: str,
    ):
        self.issuer = issuer
        self.objective_version = objective_version
        self.revision = revision
        self.checkpoint_id = checkpoint_id
        self.challenge = challenge


class RunStore:
    def __init__(self, repository: Path | str):
        self.repository = Path(repository).resolve()
        self.runs_root = self.repository / ".architrave" / "runs"
        self.key_path = self.repository / ".architrave" / "runtime.key"
        self.__objective_capability = object()
        self.__policy_capability = object()

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
                json.dump(value, handle, separators=(",", ":"), sort_keys=False, ensure_ascii=True)
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
        self._atomic_write(run_dir / "recovery.json", state)

    def _restore_snapshot(
        self,
        run_dir: Path,
        run_id: str,
        events: Sequence[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if not events:
            return None
        expected_hash = events[-1]["payload"].get("stateHash")
        path = run_dir / "recovery.json"
        try:
            candidate = json.loads(path.read_text(encoding="utf-8"))
            validate_run(candidate)
        except (OSError, json.JSONDecodeError, RuntimeFailure):
            return None
        if candidate.get("runId") != run_id:
            return None
        if candidate.get("eventCursor") != {"sequence": len(events), "lastHash": events[-1]["hash"]}:
            return None
        if self._state_hash(candidate) != expected_hash:
            return None
        self._atomic_write(run_dir / "run.json", candidate)
        return candidate

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
        if state.get("schema") == SCHEMA and "objective" not in state:
            events = self._read_events(run_dir)
            self._verify_events(run_id, events, state.get("eventCursor"))
            if events and events[-1]["payload"].get("stateHash") != self._state_hash(state):
                raise RuntimeFailure("RUN_STATE_TAMPERED", "legacy Run state does not match its event log")
            now = utc_now()
            criterion_ids = [item["id"] for item in state.get("acceptanceCriteria", [])]
            state["objective"] = {
                "version": 1,
                "description": state["outcome"]["description"],
                "acceptanceCriteria": criterion_ids,
                "updatedAt": now,
                "correctionReason": None,
            }
            state["reuseBaseline"] = None
            state["focus"] = {
                "nextCheapestTest": None,
                "lastResetReason": None,
                "minimalSliceProven": any(
                    item.get("status") == "PASS" for item in state.get("acceptanceCriteria", [])
                ),
                "reviewReopens": 0,
            }
            state["lanes"] = {
                "maxActive": 2,
                "active": [{"id": "product", "kind": "product", "objectiveVersion": 1}],
                "deferred": [],
            }
            state["targetIdentity"] = None
            for task in state.get("tasks", []):
                task.setdefault("objectiveVersion", 1)
                task.setdefault("lane", "product")
                task.setdefault("workKind", "product")
                task.setdefault("changeKind", "normal")
                task.setdefault("operations", [])
                task.setdefault("targetIdentity", None)
                task.setdefault("isMinimalAcceptanceTest", False)
                task.setdefault("largeChange", False)
                task.setdefault("deferredReason", None)
                task.get("workPacket", {}).pop("model", None)
            for gate in state.get("gateResults", []):
                gate.setdefault("objectiveVersion", 1)
            for checkpoint in state.get("externalCheckpoints", []):
                checkpoint.setdefault("objectiveVersion", 1)
                checkpoint.setdefault("targetBindingHash", None)
                checkpoint.setdefault("policyAmendment", None)
            state = self._commit_locked(
                run_dir,
                state,
                event_type="run.migrated",
                actor="runtime",
                payload={"from": "architrave.run.v2-pre-focus", "to": SCHEMA},
            )
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

    def _batch_review_reset(self, state: dict[str, Any], reason: str) -> list[str]:
        deferred: list[str] = []
        for task in state["tasks"]:
            if (
                task.get("objectiveVersion", state["objective"]["version"]) == state["objective"]["version"]
                and task["status"] not in TERMINAL_TASK_STATUSES
                and task.get("workKind") == "review"
            ):
                task["status"] = "DEFERRED"
                task["lease"] = None
                task["deferredReason"] = reason
                deferred.append(task["id"])
        state["focus"]["reviewReopens"] = 0
        state["focus"]["lastResetReason"] = reason
        state["status"] = derive_run_status(state)
        return deferred

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
            before_state = copy.deepcopy(state)
            before_policy = copy.deepcopy(state["policy"])
            before_objective = copy.deepcopy(state["objective"])
            payload = mutate(state) or {}
            objective_authorization = payload.pop("_objectiveAuthorization", None)
            policy_authorization = payload.pop("_policyAuthorization", None)
            if event_type == "policy.amended" or state["policy"] != before_policy:
                before_checkpoint = next(
                    (
                        checkpoint
                        for checkpoint in before_state["externalCheckpoints"]
                        if isinstance(policy_authorization, _PolicyAuthorization)
                        and checkpoint["id"] == policy_authorization.checkpoint_id
                    ),
                    None,
                )
                after_checkpoint = next(
                    (
                        checkpoint
                        for checkpoint in state["externalCheckpoints"]
                        if isinstance(policy_authorization, _PolicyAuthorization)
                        and checkpoint["id"] == policy_authorization.checkpoint_id
                    ),
                    None,
                )
                expected_policy = copy.deepcopy(before_policy)
                if before_checkpoint is not None and before_checkpoint.get("policyAmendment") is not None:
                    delta = before_checkpoint["policyAmendment"]["delta"]
                    expected_policy["allow"] = merge_policy_allow(expected_policy["allow"], delta["addAllow"])
                    expected_policy["confirmationRequired"] = list(
                        dict.fromkeys(
                            expected_policy["confirmationRequired"] + delta["addConfirmationRequired"]
                        )
                    )
                authorized = (
                    isinstance(policy_authorization, _PolicyAuthorization)
                    and policy_authorization.issuer is self.__policy_capability
                    and policy_authorization.objective_version == before_objective["version"]
                    and policy_authorization.revision == before_state["revision"]
                    and bool(policy_authorization.checkpoint_id)
                    and before_checkpoint is not None
                    and before_checkpoint["type"] == "HUMAN_JUDGMENT_REQUIRED"
                    and before_checkpoint["status"] == "PENDING"
                    and before_checkpoint["objectiveVersion"] == before_objective["version"]
                    and before_checkpoint.get("policyAmendment") is not None
                    and hmac.compare_digest(
                        before_checkpoint["challengeHash"],
                        hashlib.sha256(policy_authorization.challenge.encode("utf-8")).hexdigest(),
                    )
                    and after_checkpoint is not None
                    and after_checkpoint["status"] == "RESOLVED"
                    and after_checkpoint["resolvedBy"] == actor
                    and actor == f"human:{before_checkpoint['principal']}"
                    and state["policy"] == expected_policy
                    and policy_amendment_state_isolated(
                        before_state,
                        state,
                        policy_authorization.checkpoint_id,
                    )
                )
                if not authorized:
                    raise RuntimeFailure(
                        "POLICY_AUTHORITY",
                        "policy transitions require a consumed policy-amendment checkpoint",
                    )
            if (
                event_type == "objective.replaced"
                or state["objective"] != before_objective
            ):
                authorized = (
                    isinstance(objective_authorization, _ObjectiveAuthorization)
                    and objective_authorization.issuer is self.__objective_capability
                    and objective_authorization.from_version == before_objective["version"]
                    and objective_authorization.to_version == state["objective"]["version"]
                    and bool(objective_authorization.checkpoint_id)
                    and any(
                        checkpoint["id"] == objective_authorization.checkpoint_id
                        and checkpoint["type"] == "HUMAN_JUDGMENT_REQUIRED"
                        and checkpoint["status"] == "RESOLVED"
                        and checkpoint["resolvedBy"] == actor
                        and checkpoint["objectiveVersion"] == before_objective["version"]
                        for checkpoint in state["externalCheckpoints"]
                    )
                )
                if not authorized:
                    raise RuntimeFailure(
                        "OBJECTIVE_AUTHORITY",
                        "objective transitions require a consumed trusted checkpoint",
                    )
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
                "objective": {
                    "version": 1,
                    "description": outcome.strip(),
                    "acceptanceCriteria": [criterion["id"] for criterion in normalized_criteria],
                    "updatedAt": now,
                    "correctionReason": None,
                },
                "autonomy": {"scope": autonomy_scope},
                "policy": {
                    "default": "deny",
                    "allow": normalize_policy_allow(policy_allow),
                    "confirmationRequired": normalize_confirmation_required(confirmation_required),
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
                "reuseBaseline": None,
                "focus": {
                    "nextCheapestTest": None,
                    "lastResetReason": None,
                    "minimalSliceProven": False,
                    "reviewReopens": 0,
                },
                "lanes": {
                    "maxActive": 2,
                    "active": [{"id": "product", "kind": "product", "objectiveVersion": 1}],
                    "deferred": [],
                },
                "targetIdentity": None,
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
        # Canonical state and the authenticated event ledger are the durable artifacts.
        # Human-readable views are rendered on demand by CLI commands.
        return None

    def _project(self, run_dir: Path, state: dict[str, Any]) -> None:
        return None

    def replace_objective(
        self,
        run_id: str,
        *,
        outcome: str,
        criteria: Sequence[dict[str, Any]],
        correction: str,
        next_cheapest_test: str,
        checkpoint_id: str,
        challenge: str,
        actor: str = "user",
    ) -> dict[str, Any]:
        if not outcome.strip() or not correction.strip() or not next_cheapest_test.strip():
            raise RuntimeFailure("INVALID_OBJECTIVE", "replacement outcome, correction, and next test are required")
        normalized = normalize_criteria(criteria, outcome)

        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            checkpoint = next(
                (item for item in state["externalCheckpoints"] if item["id"] == checkpoint_id),
                None,
            )
            if (
                checkpoint is None
                or checkpoint["status"] != "PENDING"
                or checkpoint["type"] != "HUMAN_JUDGMENT_REQUIRED"
                or checkpoint.get("policyAmendment") is not None
                or checkpoint["objectiveVersion"] != state["objective"]["version"]
                or hashlib.sha256(str(challenge).encode("utf-8")).hexdigest() != checkpoint["challengeHash"]
                or actor != f"human:{checkpoint['principal']}"
            ):
                raise RuntimeFailure("OBJECTIVE_AUTHORITY", "objective replacement checkpoint is invalid")
            checkpoint["status"] = "RESOLVED"
            checkpoint["resolvedAt"] = utc_now()
            checkpoint["resolvedBy"] = actor
            checkpoint["resolutionRef"] = f"objective:{state['objective']['version'] + 1}"
            prior_version = state["objective"]["version"]
            new_version = prior_version + 1
            new_ids = {item["id"] for item in normalized}
            for criterion in state["acceptanceCriteria"]:
                if criterion["id"] in state["objective"]["acceptanceCriteria"] and criterion["id"] not in new_ids:
                    criterion["status"] = "NOT_APPLICABLE"
                    criterion["blocking"] = False
                    criterion["evidenceRefs"] = []
            by_id = {item["id"]: item for item in state["acceptanceCriteria"]}
            for criterion in normalized:
                if criterion["id"] in by_id:
                    by_id[criterion["id"]].update(criterion)
                else:
                    state["acceptanceCriteria"].append(criterion)
            deferred_tasks: list[str] = []
            cancelled_workers: list[str] = []
            uncertain_tasks: list[str] = []
            old_workspaces: set[str] = set()
            old_worker_ids: set[str] = set()
            for task in state["tasks"]:
                if task.get("objectiveVersion", prior_version) != prior_version:
                    continue
                if task["status"] not in TERMINAL_TASK_STATUSES:
                    if task.get("lease"):
                        old_worker_ids.add(task["lease"]["owner"])
                    if task.get("sideEffect") and task["sideEffect"]["state"] in {"PENDING", "UNCERTAIN"}:
                        task["sideEffect"]["state"] = "UNCERTAIN"
                        task["status"] = "WAITING_RESOURCE"
                        task["deferredReason"] = "objective replaced; side effect requires reconciliation"
                        append_checkpoint(state, task["id"], "SIDE_EFFECT_AMBIGUITY")
                        uncertain_tasks.append(task["id"])
                    else:
                        task["status"] = "DEFERRED"
                        task["deferredReason"] = f"objective replaced by version {new_version}"
                        deferred_tasks.append(task["id"])
                    task["lease"] = None
                    if task.get("workspace"):
                        old_workspaces.add(str(Path(task["workspace"]).resolve()))
            for checkpoint in state["externalCheckpoints"]:
                if checkpoint["status"] != "PENDING" or checkpoint["taskId"] in uncertain_tasks:
                    continue
                task = find_task(state, checkpoint["taskId"])
                if task.get("objectiveVersion", prior_version) == prior_version:
                    checkpoint["status"] = "CANCELLED"
                    checkpoint["resolvedAt"] = utc_now()
                    checkpoint["resolvedBy"] = "objective-replacement"
            for worker in state["workers"]:
                if worker["status"] == "RUNNING" and (
                    worker["id"] in old_worker_ids or worker.get("workspace") in old_workspaces
                ):
                    worker["status"] = "FAILED"
                    cancelled_workers.append(worker["id"])
            state["objective"] = {
                "version": new_version,
                "description": outcome.strip(),
                "acceptanceCriteria": [item["id"] for item in normalized],
                "updatedAt": utc_now(),
                "correctionReason": correction.strip(),
            }
            state["goal"] = outcome.strip()
            state["outcome"] = {
                "description": outcome.strip(),
                "requiredCriteria": [
                    {
                        "id": criterion["id"],
                        "description": criterion["description"],
                        "verification": criterion["verificationType"],
                        "required": criterion["blocking"],
                    }
                    for criterion in normalized
                ],
            }
            state["focus"]["reviewReopens"] = 0
            state["focus"]["minimalSliceProven"] = False
            state["focus"]["nextCheapestTest"] = next_cheapest_test.strip()
            state["focus"]["lastResetReason"] = correction.strip()
            state["lanes"]["deferred"].extend(
                lane for lane in state["lanes"]["active"] if lane["id"] != "product"
            )
            state["lanes"]["active"] = [{"id": "product", "kind": "product", "objectiveVersion": new_version}]
            state["reuseBaseline"] = None
            state["targetIdentity"] = None
            state["status"] = "WAITING_RESOURCE" if uncertain_tasks else "PLANNING"
            return {
                "priorVersion": prior_version,
                "objectiveVersion": new_version,
                "correction": correction.strip(),
                "deferredTasks": deferred_tasks,
                "cancelledWorkers": cancelled_workers,
                "uncertainTasks": uncertain_tasks,
                "nextCheapestTest": next_cheapest_test.strip(),
                "_objectiveAuthorization": _ObjectiveAuthorization(
                    self.__objective_capability,
                    prior_version,
                    new_version,
                    checkpoint_id,
                ),
            }

        return self._transaction(run_id, mutate, event_type="objective.replaced", actor=actor)

    def record_reuse_baseline(
        self,
        run_id: str,
        *,
        path: str,
        difference: str,
        evidence_refs: Sequence[str],
        actor: str = "coordinator",
    ) -> dict[str, Any]:
        relative = safe_relative_path(path, "reuse baseline path")
        if not difference.strip():
            raise RuntimeFailure("REUSE_EVIDENCE", "reuse baseline requires the specific difference being tested")
        baseline = self.repository / relative
        if not baseline.exists():
            raise RuntimeFailure("REUSE_EVIDENCE", f"reuse baseline does not exist: {relative}")

        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            require_evidence_refs(state, evidence_refs, allowed={"artifact"})
            artifacts = [
                artifact
                for artifact in state["artifacts"]
                if f"artifact:{artifact['id']}" in evidence_refs
                and artifact["kind"] == "reuse-baseline"
                and artifact["producer"] == "deterministic"
            ]
            if not artifacts:
                raise RuntimeFailure("REUSE_EVIDENCE", "dedicated reuse baseline evidence is required")
            receipt = self._read_json_receipt(artifacts[-1]["path"], "reuse baseline")
            if (
                receipt.get("baselinePath") != relative
                or receipt.get("difference") != difference.strip()
                or receipt.get("sha256") != sha256_path(baseline)
            ):
                raise RuntimeFailure("REUSE_EVIDENCE", "reuse receipt does not match the requested baseline")
            state["reuseBaseline"] = {
                "path": relative,
                "difference": difference.strip(),
                "evidenceRefs": list(dict.fromkeys(evidence_refs)),
                "status": "TESTED",
                "objectiveVersion": state["objective"]["version"],
                "recordedAt": utc_now(),
            }
            return copy.deepcopy(state["reuseBaseline"])

        return self._transaction(
            run_id,
            mutate,
            event_type="reuse.baseline_tested",
            actor=actor,
            evidence_refs=evidence_refs,
        )

    def verify_reuse_baseline(
        self,
        run_id: str,
        *,
        path: str,
        difference: str,
        test_command: Sequence[str],
        actor: str = "coordinator",
    ) -> dict[str, Any]:
        relative = safe_relative_path(path, "reuse baseline path")
        baseline = self.repository / relative
        if not baseline.exists() or not difference.strip() or not test_command:
            raise RuntimeFailure("REUSE_EVIDENCE", "existing baseline, difference, and test command are required")
        completed = subprocess.run(
            list(test_command),
            cwd=self.repository,
            text=True,
            capture_output=True,
            timeout=300,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeFailure(
                "REUSE_EVIDENCE",
                "reuse baseline test failed",
                details={"exitCode": completed.returncode, "stderr": completed.stderr[-1000:]},
            )
        artifact_id = f"reuse-{uuid.uuid4().hex}"
        receipt_path = self.run_dir(run_id) / "evidence" / f"{artifact_id}.json"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            json.dumps(
                {
                    "status": "pass",
                    "baselinePath": relative,
                    "difference": difference.strip(),
                    "test": list(test_command),
                    "sha256": sha256_path(baseline),
                    "stdout": completed.stdout[-2000:],
                },
                separators=(",", ":"),
            ) + "\n",
            encoding="utf-8",
        )
        self._record_reuse_result(
            run_id,
            artifact_id=artifact_id,
            path=receipt_path.relative_to(self.repository).as_posix(),
            evidence_refs=[],
        )
        return self.record_reuse_baseline(
            run_id,
            path=relative,
            difference=difference,
            evidence_refs=[f"artifact:{artifact_id}"],
            actor=actor,
        )

    def resolve_target_identity_checkpoint(
        self,
        run_id: str,
        *,
        checkpoint_id: str,
        challenge: str,
        intended: dict[str, str],
        evidence_ref: str,
        actor: str,
    ) -> dict[str, Any]:
        required = {"provider", "artifact", "version", "sha256", "environment", "workspace", "acceptanceTarget"}
        if set(intended) != required:
            raise RuntimeFailure("TARGET_IDENTITY_INVALID", "target identity requires provider, artifact, version, sha256, environment, workspace, and acceptanceTarget")

        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            checkpoint = next(
                (item for item in state["externalCheckpoints"] if item["id"] == checkpoint_id),
                None,
            )
            task = find_task(state, checkpoint["taskId"]) if checkpoint else None
            require_evidence_refs(state, [evidence_ref], allowed={"artifact"})
            artifact_id = evidence_ref.split(":", 1)[1]
            artifact = next(
                (item for item in state["artifacts"] if item["id"] == artifact_id),
                None,
            )
            if (
                artifact is None
                or artifact["producer"] != "external-proof"
                or artifact["kind"] != "external-proof"
                or artifact.get("consumedByTask") is not None
            ):
                raise RuntimeFailure("TARGET_IDENTITY_INVALID", "unconsumed external attestation is required")
            receipt = self._read_json_receipt(artifact["path"], "target identity")
            observed = receipt.get("observed") or {}
            expected_binding = sha256_value(
                {
                    "runId": state["runId"],
                    "objectiveVersion": state["objective"]["version"],
                    "taskId": checkpoint["taskId"] if checkpoint else "",
                    "provider": checkpoint["provider"] if checkpoint else "",
                    "principal": checkpoint["principal"] if checkpoint else "",
                    "intended": intended,
                    "challengeHash": checkpoint["challengeHash"] if checkpoint else "",
                }
            )
            if (
                checkpoint is None
                or task is None
                or checkpoint["status"] != "PENDING"
                or checkpoint["type"] != "SAFE_WRITE_TARGET_REQUIRED"
                or checkpoint["objectiveVersion"] != state["objective"]["version"]
                or hashlib.sha256(challenge.encode("utf-8")).hexdigest() != checkpoint["challengeHash"]
                or checkpoint.get("targetBindingHash") != expected_binding
                or task.get("targetIdentity") != intended
                or actor != f"human:{checkpoint['principal']}"
                or intended["provider"] != checkpoint["provider"]
                or receipt.get("checkpointId") != checkpoint_id
            ):
                raise RuntimeFailure("TARGET_IDENTITY_INVALID", "target identity checkpoint is invalid")
            mismatches = {
                key: {"intended": intended[key], "observed": observed[key]}
                for key in sorted(required)
                if intended[key] != observed[key]
            }
            checkpoint["status"] = "RESOLVED"
            checkpoint["resolvedAt"] = utc_now()
            checkpoint["resolvedBy"] = actor
            checkpoint["resolutionRef"] = f"target:{checkpoint_id}"
            artifact["consumedByTask"] = task["id"]
            artifact["attestation"] = self._artifact_attestation(artifact)
            if not any(
                item["taskId"] == task["id"] and item["status"] == "PENDING"
                for item in state["externalCheckpoints"]
            ):
                task["status"] = "READY" if dependencies_completed(state, task) else "NOT_READY"
            state["targetIdentity"] = {
                "checkpointId": checkpoint_id,
                "principal": checkpoint["principal"],
                "provider": checkpoint["provider"],
                "challengeHash": checkpoint["challengeHash"],
                "intended": dict(intended),
                "observed": dict(observed),
                "status": "MISMATCH" if mismatches else "VERIFIED",
                "mismatches": mismatches,
                "objectiveVersion": state["objective"]["version"],
                "verifiedAt": utc_now(),
                "evidenceRef": evidence_ref,
            }
            if mismatches:
                state["status"] = "PAUSED"
            else:
                state["status"] = derive_run_status(state)
            return copy.deepcopy(state["targetIdentity"])

        return self._transaction(
            run_id,
            mutate,
            event_type="target.preflight",
            actor=actor,
            evidence_refs=[evidence_ref],
        )

    def record_review_result(
        self,
        run_id: str,
        *,
        verdict: str,
        product_evidence_refs: Sequence[str] = (),
        actor: str = "coordinator",
    ) -> dict[str, Any]:
        if verdict not in {"PASS", "REVISE", "FAIL"}:
            raise RuntimeFailure("INVALID_REVIEW", "review verdict must be PASS, REVISE, or FAIL")
        before = self.load(run_id)
        will_reset = verdict != "PASS" and before["focus"]["reviewReopens"] + 1 >= 2

        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            if product_evidence_refs:
                require_evidence_refs(state, product_evidence_refs, allowed={"artifact", "gate"})
            if verdict == "PASS":
                state["focus"]["reviewReopens"] = 0
                return {"verdict": verdict, "batchRequired": False}
            state["focus"]["reviewReopens"] += 1
            deferred: list[str] = []
            if state["focus"]["reviewReopens"] >= 2:
                deferred = self._batch_review_reset(state, "repeated review without new product evidence")
            return {
                "verdict": verdict,
                "batchRequired": state["focus"]["lastResetReason"] == "repeated review without new product evidence",
                "deferredTasks": deferred,
            }

        return self._transaction(
            run_id,
            mutate,
            event_type="review.batch_required" if will_reset else "review.recorded",
            actor=actor,
            evidence_refs=product_evidence_refs,
        )

    def human_checkpoint(self, run_id: str | None = None) -> dict[str, Any]:
        state = self.load(run_id)
        current_ids = set(state["objective"]["acceptanceCriteria"])
        acceptance = [
            f"{item['id']}: {item['description']} [{item['status']}]"
            for item in state["acceptanceCriteria"]
            if item["id"] in current_ids
        ][:8]
        passed_evidence = [
            reference
            for item in state["acceptanceCriteria"]
            if item["id"] in current_ids and item["status"] == "PASS"
            for reference in item["evidenceRefs"]
        ]
        blocker = next(
            (
                checkpoint["reason"]
                for checkpoint in state["externalCheckpoints"]
                if checkpoint["status"] == "PENDING"
            ),
            state["focus"]["lastResetReason"],
        )
        return {
            "currentObjective": state["objective"]["description"],
            "objectiveVersion": state["objective"]["version"],
            "acceptanceCriteria": acceptance,
            "lastVerifiedProductEvidence": passed_evidence[-3:],
            "blocker": blocker,
            "nextCheapestTest": state["focus"]["nextCheapestTest"],
            "activeLanes": [item["id"] for item in state["lanes"]["active"]],
            "deferredWork": [
                {"task": task["id"], "reason": task.get("deferredReason")}
                for task in state["tasks"]
                if task["status"] == "DEFERRED"
            ][:8],
        }

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
            superseded_dependencies = [
                dependency
                for dependency in dependencies
                if find_task(state, dependency).get("objectiveVersion", state["objective"]["version"])
                != state["objective"]["version"]
            ]
            if superseded_dependencies:
                raise RuntimeFailure(
                    "OBJECTIVE_SUPERSEDED",
                    "new tasks cannot depend on superseded objective work",
                    details={"tasks": superseded_dependencies},
                )
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
            work_kind = str(task.get("workKind") or "product")
            if work_kind not in WORK_KINDS:
                raise RuntimeFailure("INVALID_TASK", f"invalid work kind: {work_kind}")
            change_kind = str(task.get("changeKind") or "normal")
            if change_kind not in {"normal", "replacement-architecture", "new-compatibility-constraint"}:
                raise RuntimeFailure("INVALID_TASK", f"invalid change kind: {change_kind}")
            if change_kind != "normal":
                reuse = state.get("reuseBaseline")
                if not reuse or reuse.get("status") != "TESTED" or not reuse.get("difference"):
                    raise RuntimeFailure(
                        "REUSE_FIRST_REQUIRED",
                        "existing working implementation must be inspected, diffed, and tested before replacement",
                    )
            lane = str(task.get("lane") or "product")
            active_lane_ids = {item["id"] for item in state["lanes"]["active"]}
            deferred_lane_ids = {item["id"] for item in state["lanes"]["deferred"]}
            deferred_reason = None
            unrelated = work_kind in {"communications", "research", "infrastructure"}
            if unrelated:
                deferred_reason = "unrelated lane deferred behind active product objective"
                if lane not in active_lane_ids and lane not in deferred_lane_ids:
                    state["lanes"]["deferred"].append(
                        {"id": lane, "kind": work_kind, "objectiveVersion": state["objective"]["version"]}
                    )
            elif lane not in active_lane_ids:
                if len(active_lane_ids) >= state["lanes"]["maxActive"]:
                    deferred_reason = "unrelated lane deferred behind active product objective"
                    if lane not in deferred_lane_ids:
                        state["lanes"]["deferred"].append(
                            {"id": lane, "kind": work_kind, "objectiveVersion": state["objective"]["version"]}
                        )
                else:
                    state["lanes"]["active"].append(
                        {"id": lane, "kind": work_kind, "objectiveVersion": state["objective"]["version"]}
                    )
            minimal_test = bool(task.get("isMinimalAcceptanceTest", False))
            large_change = bool(task.get("largeChange", False))
            if not state["focus"]["minimalSliceProven"] and risk != "R4":
                if work_kind in {"infrastructure", "review"}:
                    deferred_reason = "minimal vertical slice must be proven before hardening or review"
                elif work_kind == "diagnostic" and not minimal_test:
                    deferred_reason = "diagnosis must begin with the cheapest discriminating acceptance test"
                elif large_change:
                    deferred_reason = "large change is blocked until the minimal end-to-end path is reproduced"
            if work_kind == "review" and state["focus"]["reviewReopens"] >= 2:
                deferred_reason = "review findings must be batched before another review"
            operations = list(
                dict.fromkeys(
                    [
                        *(str(value) for value in task.get("operations") or []),
                        *([str(side_effect["operation"]).lower()] if side_effect else []),
                    ]
                )
            )
            normalized = {
                "id": task_id,
                "title": str(task.get("title") or task_id),
                "objective": str(task.get("objective") or "").strip(),
                "status": "DEFERRED" if deferred_reason else ("NOT_READY" if dependencies else "READY"),
                "dependencies": dependencies,
                "workerProfile": worker_profile,
                "workspace": task.get("workspace"),
                "mutablePaths": mutable_paths,
                "tools": list(dict.fromkeys(task.get("tools") or [])),
                "risk": risk,
                "objectiveVersion": state["objective"]["version"],
                "lane": lane,
                "workKind": work_kind,
                "changeKind": change_kind,
                "operations": operations,
                "targetIdentity": copy.deepcopy(task.get("targetIdentity")),
                "isMinimalAcceptanceTest": minimal_test,
                "largeChange": large_change,
                "deferredReason": deferred_reason,
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
            return {
                "taskId": task_id,
                "status": normalized["status"],
                "objectiveVersion": normalized["objectiveVersion"],
                "lane": lane,
                "deferredReason": deferred_reason,
            }

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

    def _record_reuse_result(self, run_id: str, **kwargs: Any) -> dict[str, Any]:
        receipt = self._read_json_receipt(kwargs["path"], "reuse baseline")
        baseline_path = safe_relative_path(str(receipt.get("baselinePath") or ""), "reuse baseline path")
        baseline = (self.repository / baseline_path).resolve()
        if (
            receipt.get("status") != "pass"
            or not str(receipt.get("difference") or "").strip()
            or not str(receipt.get("test") or "").strip()
            or receipt.get("sha256") != sha256_path(baseline)
        ):
            raise RuntimeFailure("REUSE_EVIDENCE", "reuse baseline receipt is invalid or stale")
        return self._record_artifact(
            run_id,
            kind="reuse-baseline",
            actor="deterministic-executor",
            producer="deterministic",
            **kwargs,
        )

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
        reviewer = verdict.get("reviewer") or verdict.get("family")
        if verdict.get("verdict") != "PASS" or not reviewer or not verdict.get("criteria"):
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
        if checkpoint["type"] == "SAFE_WRITE_TARGET_REQUIRED":
            task = find_task(state, checkpoint["taskId"])
            required = {"provider", "artifact", "version", "sha256", "environment", "workspace", "acceptanceTarget"}
            if (
                proof.get("runId") != run_id
                or proof.get("objectiveVersion") != state["objective"]["version"]
                or proof.get("taskId") != task["id"]
                or proof.get("challengeHash") != checkpoint["challengeHash"]
                or proof.get("provider") != checkpoint["provider"]
                or proof.get("principal") != checkpoint["principal"]
                or proof.get("actor") != checkpoint["principal"]
                or proof.get("intended") != task.get("targetIdentity")
                or set(proof.get("observed") or {}) != required
            ):
                raise RuntimeFailure("EXTERNAL_PROOF", "target identity proof is not bound to the pending checkpoint")
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
            if task.get("objectiveVersion", state["objective"]["version"]) != state["objective"]["version"]:
                raise RuntimeFailure("OBJECTIVE_SUPERSEDED", "task belongs to a superseded objective")
            if task.get("lane", "product") not in {item["id"] for item in state["lanes"]["active"]}:
                raise RuntimeFailure("LANE_DEFERRED", "task lane is not active")
            if task["status"] != "READY":
                raise RuntimeFailure("TASK_NOT_READY", f"task {task_id} is {task['status']}")
            if TARGET_OPERATIONS.intersection(task.get("operations") or []):
                identity = state.get("targetIdentity")
                if not identity or identity.get("status") != "VERIFIED":
                    raise RuntimeFailure("TARGET_IDENTITY_REQUIRED", "launch/test/install requires verified target identity")
                expected_identity = task.get("targetIdentity") or {}
                mismatches = {
                    key: {"expected": value, "actual": identity["observed"].get(key)}
                    for key, value in expected_identity.items()
                    if identity["observed"].get(key) != value
                }
                if mismatches:
                    raise RuntimeFailure("TARGET_IDENTITY_MISMATCH", "task target does not match verified identity", details=mismatches)
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
        if family is not None and not ID_RE.fullmatch(family):
            raise RuntimeFailure("INVALID_GATE", f"invalid gate reviewer identity: {family}")
        if gate_type == "semantic" and family is None:
            raise RuntimeFailure("INVALID_GATE", "semantic gates require an independent reviewer identity")
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
                    "objectiveVersion": state["objective"]["version"],
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
                        if gate.get("objectiveVersion", 1) != state["objective"]["version"]:
                            raise RuntimeFailure("EVIDENCE_SUPERSEDED", "gate evidence belongs to a superseded objective")
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
                        if checkpoint.get("objectiveVersion", 1) != state["objective"]["version"]:
                            raise RuntimeFailure("EVIDENCE_SUPERSEDED", "external evidence belongs to a superseded objective")
                        bound_task = find_task(state, checkpoint["taskId"])
                        if criterion_id not in bound_task["acceptanceCriteria"]:
                            raise RuntimeFailure(
                                "EVIDENCE_INVALID",
                                "external checkpoint evidence is not bound to this criterion",
                                details={"criterionId": criterion_id, "checkpointId": identifier},
                            )
            criterion["status"] = status
            criterion["evidenceRefs"] = list(dict.fromkeys(evidence_refs))
            if status == "PASS" and criterion_id in state["objective"]["acceptanceCriteria"]:
                state["focus"]["minimalSliceProven"] = True
                state["focus"]["reviewReopens"] = 0
            state["status"] = derive_run_status(state)
            return {"criterionId": criterion_id, "status": status}

        return self._transaction(
            run_id,
            mutate,
            event_type="product.progress" if status == "PASS" else "acceptance.updated",
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
        challenge = "arc_" + secrets.token_urlsafe(32)
        challenge_hash = hashlib.sha256(challenge.encode("utf-8")).hexdigest()

        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            task = find_task(state, task_id)
            if task["status"] in TERMINAL_TASK_STATUSES:
                raise RuntimeFailure("TASK_TERMINAL", "terminal tasks cannot wait externally")
            if any(item["id"] == checkpoint_id for item in state["externalCheckpoints"]):
                raise RuntimeFailure("EXTERNAL_CHECKPOINT_EXISTS", f"checkpoint already exists: {checkpoint_id}")
            target_binding = None
            if checkpoint_type == "SAFE_WRITE_TARGET_REQUIRED":
                declared = task.get("targetIdentity")
                required = {"provider", "artifact", "version", "sha256", "environment", "workspace", "acceptanceTarget"}
                if not isinstance(declared, dict) or set(declared) != required or declared["provider"] != provider:
                    raise RuntimeFailure(
                        "TARGET_IDENTITY_REQUIRED",
                        "SAFE_WRITE_TARGET_REQUIRED needs complete task target identity bound to the provider",
                    )
                target_binding = sha256_value(
                    {
                        "runId": state["runId"],
                        "objectiveVersion": state["objective"]["version"],
                        "taskId": task_id,
                        "provider": provider,
                        "principal": principal,
                        "intended": declared,
                        "challengeHash": challenge_hash,
                    }
                )
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
                    "objectiveVersion": state["objective"]["version"],
                    "targetBindingHash": target_binding,
                    "policyAmendment": None,
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
            if checkpoint.get("policyAmendment") is not None:
                raise RuntimeFailure(
                    "POLICY_AMENDMENT_REQUIRED",
                    "policy amendment checkpoints must be resolved by the policy-amend command",
                )
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

    def request_policy_amendment(
        self,
        run_id: str,
        *,
        checkpoint_id: str,
        task_id: str,
        principal: str,
        provider: str,
        delta: dict[str, Any],
        reason: str,
        actor: str,
    ) -> tuple[dict[str, Any], str]:
        require_id(checkpoint_id, "policy amendment checkpoint id")
        normalized_delta = normalize_policy_delta(delta)
        if not principal.strip() or not provider.strip() or not reason.strip():
            raise RuntimeFailure(
                "INVALID_POLICY_AMENDMENT",
                "policy amendment principal, provider, and reason are required",
            )
        if actor != f"human:{principal.strip()}":
            raise RuntimeFailure(
                "POLICY_AUTHORITY",
                "policy amendment requests require the authorized human principal",
            )
        challenge = "arc_" + secrets.token_urlsafe(32)
        challenge_hash = hashlib.sha256(challenge.encode("utf-8")).hexdigest()

        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            task = find_task(state, task_id)
            if task["status"] != "READY":
                raise RuntimeFailure(
                    "POLICY_AMENDMENT_NOT_READY",
                    "policy amendment requests require a ready task blocked by the requested policy delta",
                )
            if any(item["id"] == checkpoint_id for item in state["externalCheckpoints"]):
                raise RuntimeFailure("EXTERNAL_CHECKPOINT_EXISTS", f"checkpoint already exists: {checkpoint_id}")
            running_mutations, uncertain_side_effects = policy_amendment_unsafe_tasks(state)
            if running_mutations or uncertain_side_effects:
                raise RuntimeFailure(
                    "POLICY_AMENDMENT_UNSAFE",
                    "policy amendment requires no running mutation or unresolved side effect",
                    details={
                        "runningMutations": running_mutations,
                        "uncertainSideEffects": uncertain_side_effects,
                    },
                )
            requirements = task_policy_requirements(task)
            if not requirements:
                raise RuntimeFailure(
                    "POLICY_AMENDMENT_SCOPE",
                    "policy amendment task has no mutation requirement to authorize",
                )
            candidate = copy.deepcopy(state)
            candidate["policy"]["allow"] = merge_policy_allow(
                candidate["policy"]["allow"],
                normalized_delta["addAllow"],
            )
            candidate["policy"]["confirmationRequired"] = list(
                dict.fromkeys(
                    candidate["policy"]["confirmationRequired"]
                    + normalized_delta["addConfirmationRequired"]
                )
            )
            changed_requirements = [
                {"scope": scope, "operation": operation}
                for scope, operation in requirements
                if mutation_decision(state, scope, operation, confirmed=False)
                != mutation_decision(candidate, scope, operation, confirmed=False)
            ]
            if not changed_requirements:
                raise RuntimeFailure(
                    "POLICY_AMENDMENT_SCOPE",
                    "requested policy delta does not change this task's exact mutation requirements",
                )
            requested_revision = state["revision"] + 1
            binding = {
                "runId": state["runId"],
                "objectiveVersion": state["objective"]["version"],
                "revision": requested_revision,
                "principal": principal.strip(),
                "provider": provider.strip(),
                "delta": normalized_delta,
                "reason": reason.strip(),
                "challengeHash": challenge_hash,
            }
            task["status"] = "WAITING_EXTERNAL"
            state["externalCheckpoints"].append(
                {
                    "id": checkpoint_id,
                    "taskId": task_id,
                    "type": "HUMAN_JUDGMENT_REQUIRED",
                    "principal": principal.strip(),
                    "provider": provider.strip(),
                    "reason": reason.strip(),
                    "createdAt": utc_now(),
                    "status": "PENDING",
                    "resumeTask": task_id,
                    "objectiveVersion": state["objective"]["version"],
                    "targetBindingHash": None,
                    "policyAmendment": {
                        "revision": requested_revision,
                        "delta": normalized_delta,
                        "bindingHash": sha256_value(binding),
                    },
                    "challengeHash": challenge_hash,
                    "resolutionRef": None,
                }
            )
            append_checkpoint(state, task_id, "EXTERNAL_WAIT")
            state["status"] = derive_run_status(state)
            return {
                "checkpointId": checkpoint_id,
                "principal": principal.strip(),
                "provider": provider.strip(),
                "delta": normalized_delta,
                "reason": reason.strip(),
                "requirements": changed_requirements,
            }

        state = self._transaction(
            run_id,
            mutate,
            event_type="policy.amendment_requested",
            actor=actor,
            task_id=task_id,
        )
        return state, challenge

    def amend_policy(
        self,
        run_id: str,
        *,
        checkpoint_id: str,
        challenge: str,
        principal: str,
        provider: str,
        delta: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        normalized_delta = normalize_policy_delta(delta)

        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            checkpoint = next(
                (item for item in state["externalCheckpoints"] if item["id"] == checkpoint_id),
                None,
            )
            if checkpoint is None:
                raise RuntimeFailure("POLICY_CHECKPOINT_NOT_FOUND", f"checkpoint not found: {checkpoint_id}")
            amendment = checkpoint.get("policyAmendment")
            supplied_hash = hashlib.sha256(str(challenge).encode("utf-8")).hexdigest()
            if (
                checkpoint["status"] != "PENDING"
                or checkpoint["type"] != "HUMAN_JUDGMENT_REQUIRED"
                or amendment is None
                or checkpoint["objectiveVersion"] != state["objective"]["version"]
                or amendment["revision"] != state["revision"]
            ):
                raise RuntimeFailure("POLICY_AUTHORITY", "policy amendment checkpoint is stale or invalid")
            if (
                principal != checkpoint["principal"]
                or provider != checkpoint["provider"]
                or actor != f"human:{checkpoint['principal']}"
                or not hmac.compare_digest(checkpoint["challengeHash"], supplied_hash)
                or normalized_delta != amendment["delta"]
            ):
                raise RuntimeFailure("POLICY_AUTHORITY", "policy amendment authority or requested delta does not match")
            expected_binding = sha256_value(
                {
                    "runId": state["runId"],
                    "objectiveVersion": state["objective"]["version"],
                    "revision": state["revision"],
                    "principal": checkpoint["principal"],
                    "provider": checkpoint["provider"],
                    "delta": amendment["delta"],
                    "reason": checkpoint["reason"],
                    "challengeHash": checkpoint["challengeHash"],
                }
            )
            if not hmac.compare_digest(amendment["bindingHash"], expected_binding):
                raise RuntimeFailure("POLICY_AUTHORITY", "policy amendment checkpoint binding is invalid")
            running_mutations, uncertain_side_effects = policy_amendment_unsafe_tasks(state)
            if running_mutations or uncertain_side_effects:
                raise RuntimeFailure(
                    "POLICY_AMENDMENT_UNSAFE",
                    "policy amendment requires no running mutation or unresolved side effect",
                    details={
                        "runningMutations": running_mutations,
                        "uncertainSideEffects": uncertain_side_effects,
                    },
                )
            state["policy"]["allow"] = merge_policy_allow(
                state["policy"]["allow"],
                amendment["delta"]["addAllow"],
            )
            state["policy"]["confirmationRequired"] = list(
                dict.fromkeys(
                    state["policy"]["confirmationRequired"]
                    + amendment["delta"]["addConfirmationRequired"]
                )
            )
            checkpoint["status"] = "RESOLVED"
            checkpoint["resolvedAt"] = utc_now()
            checkpoint["resolvedBy"] = actor
            checkpoint["resolutionRef"] = f"policy:{state['revision'] + 1}"
            task = find_task(state, checkpoint["resumeTask"])
            outstanding = any(
                other["resumeTask"] == task["id"] and other["status"] == "PENDING"
                for other in state["externalCheckpoints"]
                if other["id"] != checkpoint_id
            )
            if not outstanding:
                task["status"] = "READY" if dependencies_completed(state, task) else "NOT_READY"
            state["status"] = derive_run_status(state)
            return {
                "checkpointId": checkpoint_id,
                "delta": amendment["delta"],
                "resumeTask": task["id"],
                "_policyAuthorization": _PolicyAuthorization(
                    self.__policy_capability,
                    state["objective"]["version"],
                    state["revision"],
                    checkpoint_id,
                    challenge,
                ),
            }

        return self._transaction(
            run_id,
            mutate,
            event_type="policy.amended",
            actor=actor,
        )

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
                if task.get("objectiveVersion", state["objective"]["version"]) != state["objective"]["version"]:
                    task["status"] = "DEFERRED"
                    task["lease"] = None
                    task["deferredReason"] = "superseded objective"
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
                task["id"]
                for task in state["tasks"]
                if task.get("objectiveVersion", state["objective"]["version"]) == state["objective"]["version"]
                and task["status"] not in {"COMPLETED", "SKIPPED", "DEFERRED", "CANCELLED"}
            ]
            pending_external = [
                checkpoint["id"]
                for checkpoint in state["externalCheckpoints"]
                if checkpoint["status"] == "PENDING"
            ]
            uncertain_side_effects = [
                task["id"]
                for task in state["tasks"]
                if task.get("sideEffect") and task["sideEffect"]["state"] == "UNCERTAIN"
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
            elif uncertain_side_effects:
                state["status"] = "WAITING_RESOURCE"
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
                    "uncertainSideEffects": uncertain_side_effects,
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
        if scope == "*" or "*" in operations:
            raise RuntimeFailure("INVALID_POLICY", "policy grants require exact scopes and operations")
        key = (scope, operations)
        if key not in seen:
            result.append({"scope": scope, "operations": list(operations)})
            seen.add(key)
    return result


def normalize_confirmation_required(operations: Sequence[Any]) -> list[str]:
    normalized = list(dict.fromkeys(str(item).strip() for item in operations if str(item).strip()))
    if "*" in normalized:
        raise RuntimeFailure("INVALID_POLICY", "confirmation-required operations must be exact")
    return normalized


def normalize_policy_delta(delta: dict[str, Any]) -> dict[str, Any]:
    if set(delta) - {"addAllow", "addConfirmationRequired"}:
        raise RuntimeFailure("INVALID_POLICY_AMENDMENT", "policy amendment contains unsupported fields")
    try:
        add_allow = normalize_policy_allow(delta.get("addAllow") or [])
        add_confirmation = normalize_confirmation_required(delta.get("addConfirmationRequired") or [])
    except RuntimeFailure as exc:
        raise RuntimeFailure("INVALID_POLICY_AMENDMENT", exc.message) from exc
    if not add_allow and not add_confirmation:
        raise RuntimeFailure("INVALID_POLICY_AMENDMENT", "policy amendment delta must add an exact grant")
    return {
        "addAllow": add_allow,
        "addConfirmationRequired": add_confirmation,
    }


def merge_policy_allow(
    existing: Sequence[dict[str, Any]],
    additions: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[str, list[str]] = {}
    order: list[str] = []
    for entry in [*existing, *additions]:
        scope = entry["scope"]
        if scope not in merged:
            merged[scope] = []
            order.append(scope)
        merged[scope] = list(dict.fromkeys(merged[scope] + list(entry["operations"])))
    return [{"scope": scope, "operations": merged[scope]} for scope in order]


def task_policy_requirements(task: dict[str, Any]) -> list[tuple[str, str]]:
    requirements: list[tuple[str, str]] = []
    if task.get("mutablePaths"):
        requirements.append(("repository", "edit"))
    side_effect = task.get("sideEffect")
    if side_effect is not None:
        requirements.append((side_effect["target"], side_effect["operation"]))
    return list(dict.fromkeys(requirements))


def policy_amendment_unsafe_tasks(state: dict[str, Any]) -> tuple[list[str], list[str]]:
    running_mutations = [
        task["id"]
        for task in state["tasks"]
        if task["status"] == "RUNNING" and task_policy_requirements(task)
    ]
    uncertain_side_effects = [
        task["id"]
        for task in state["tasks"]
        if task.get("sideEffect") is not None
        and task["sideEffect"]["state"] in {"PENDING", "UNCERTAIN"}
    ]
    return running_mutations, uncertain_side_effects


def policy_amendment_state_isolated(
    before: dict[str, Any],
    after: dict[str, Any],
    checkpoint_id: str,
) -> bool:
    expected = copy.deepcopy(before)
    candidate = copy.deepcopy(after)
    candidate["policy"] = copy.deepcopy(expected["policy"])
    candidate["status"] = expected["status"]
    before_checkpoint = next(
        (item for item in expected["externalCheckpoints"] if item["id"] == checkpoint_id),
        None,
    )
    after_checkpoint = next(
        (item for item in candidate["externalCheckpoints"] if item["id"] == checkpoint_id),
        None,
    )
    if before_checkpoint is None or after_checkpoint is None:
        return False
    resume_task = before_checkpoint["resumeTask"]
    before_task = next((item for item in expected["tasks"] if item["id"] == resume_task), None)
    after_task = next((item for item in candidate["tasks"] if item["id"] == resume_task), None)
    if before_task is None or after_task is None or after_task["status"] not in {"READY", "NOT_READY"}:
        return False
    after_task["status"] = before_task["status"]
    for field in ("resolvedAt", "resolvedBy"):
        after_checkpoint.pop(field, None)
    after_checkpoint["status"] = before_checkpoint["status"]
    after_checkpoint["resolutionRef"] = before_checkpoint["resolutionRef"]
    return candidate == expected


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
        "objective",
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
        "reuseBaseline",
        "focus",
        "lanes",
        "targetIdentity",
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
    normalize_confirmation_required(state["policy"].get("confirmationRequired") or [])
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
    objective = state["objective"]
    if (
        not isinstance(objective.get("version"), int)
        or objective["version"] < 1
        or not str(objective.get("description") or "").strip()
        or not set(objective.get("acceptanceCriteria") or []).issubset(criteria_ids)
    ):
        raise RuntimeFailure("RUN_INVALID", "canonical objective is invalid")
    if not isinstance(state["focus"].get("reviewReopens"), int):
        raise RuntimeFailure("RUN_INVALID", "focus state is invalid")
    lanes = state["lanes"]
    if int(lanes.get("maxActive", 0)) < 1 or len(lanes.get("active") or []) > lanes["maxActive"]:
        raise RuntimeFailure("RUN_INVALID", "active lane limit exceeded")
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
        if task.get("workKind", "product") not in WORK_KINDS:
            raise RuntimeFailure("RUN_INVALID", f"task {task['id']} work kind is invalid")
        if int(task.get("objectiveVersion", objective["version"])) < 1:
            raise RuntimeFailure("RUN_INVALID", f"task {task['id']} objective version is invalid")
    checkpoint_ids = [item.get("id") for item in state["checkpoints"]]
    external_ids = [item.get("id") for item in state["externalCheckpoints"]]
    if len(checkpoint_ids) != len(set(checkpoint_ids)) or len(external_ids) != len(set(external_ids)):
        raise RuntimeFailure("RUN_INVALID", "checkpoint ids must be unique")
    for checkpoint in state["externalCheckpoints"]:
        if not re.fullmatch(r"[0-9a-f]{64}", str(checkpoint.get("challengeHash", ""))):
            raise RuntimeFailure("RUN_INVALID", "external checkpoint challenge hash is invalid")
        if int(checkpoint.get("objectiveVersion", 0)) < 1:
            raise RuntimeFailure("RUN_INVALID", "external checkpoint objective version is invalid")
        binding = checkpoint.get("targetBindingHash")
        if binding is not None and not re.fullmatch(r"[0-9a-f]{64}", str(binding)):
            raise RuntimeFailure("RUN_INVALID", "external checkpoint target binding is invalid")
        amendment = checkpoint.get("policyAmendment")
        if amendment is not None:
            if (
                checkpoint.get("type") != "HUMAN_JUDGMENT_REQUIRED"
                or not isinstance(amendment.get("revision"), int)
                or amendment["revision"] < 0
                or not re.fullmatch(r"[0-9a-f]{64}", str(amendment.get("bindingHash", "")))
                or normalize_policy_delta(amendment.get("delta") or {}) != amendment.get("delta")
            ):
                raise RuntimeFailure("RUN_INVALID", "policy amendment checkpoint binding is invalid")
    gate_ids: set[str] = set()
    for gate in state["gateResults"]:
        gate_id = require_id(str(gate.get("id") or ""), "gate id")
        if gate_id in gate_ids or not gate.get("criteria") or not set(gate["criteria"]).issubset(criteria_ids):
            raise RuntimeFailure("RUN_INVALID", "gate ids and criterion bindings must be valid")
        if int(gate.get("objectiveVersion", 0)) < 1:
            raise RuntimeFailure("RUN_INVALID", "gate objective version is invalid")
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
    active_lanes = {item["id"] for item in state["lanes"]["active"]}
    for task in state["tasks"]:
        if (
            task["status"] == "NOT_READY"
            and task.get("objectiveVersion", state["objective"]["version"]) == state["objective"]["version"]
            and task.get("lane", "product") in active_lanes
            and dependencies_completed(state, task)
        ):
            task["status"] = "READY"
            newly_ready.append(task["id"])
    return newly_ready


def derive_run_status(state: dict[str, Any]) -> str:
    if state["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
        return state["status"]
    current_tasks = [
        task
        for task in state["tasks"]
        if task.get("objectiveVersion", state["objective"]["version"]) == state["objective"]["version"]
    ]
    statuses = {task["status"] for task in current_tasks}
    if "RUNNING" in statuses:
        return "RUNNING"
    if "READY" in statuses:
        return "RUNNING"
    pending_external = any(item["status"] == "PENDING" for item in state["externalCheckpoints"])
    if pending_external or "WAITING_EXTERNAL" in statuses:
        return "WAITING_EXTERNAL"
    if "WAITING_RESOURCE" in statuses:
        return "WAITING_RESOURCE"
    executable_statuses = statuses - {"DEFERRED", "CANCELLED"}
    if executable_statuses and executable_statuses.issubset({"COMPLETED", "SKIPPED"}):
        return "VERIFYING"
    if "FAILED" in statuses:
        return "FAILED"
    if statuses and statuses.issubset({"DEFERRED", "CANCELLED"}):
        return "PAUSED"
    return "PLANNING" if current_tasks else "CREATED"


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
    "R3": ["deterministic", "e2e-or-reality", "semantic-independent-2"],
    "R4": ["deterministic", "e2e-or-reality", "semantic-independent-2", "security", "policy"],
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
            if gate["status"] == "PASS"
            and gate.get("objectiveVersion", 1) == state["objective"]["version"]
            and criterion["id"] in gate["criteria"]
        ]
        capabilities: set[str] = {gate["type"] for gate in passed}
        if any(gate["type"] == "semantic" for gate in passed):
            capabilities.add("semantic-any")
        semantic_reviewers = {
            gate.get("family")
            for gate in passed
            if gate["type"] == "semantic" and gate.get("family")
        }
        if len(semantic_reviewers) >= 2:
            capabilities.add("semantic-independent-2")
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
        entry["scope"] == scope and operation in entry["operations"]
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
        "objectiveVersion": state["objective"]["version"],
        "objective": state["objective"]["description"],
        "autonomy": state["autonomy"]["scope"],
        "readyTasks": [task["id"] for task in state["tasks"] if task["status"] == "READY"],
        "runningTasks": [task["id"] for task in state["tasks"] if task["status"] == "RUNNING"],
        "pendingExternal": [
            checkpoint["id"] for checkpoint in state["externalCheckpoints"] if checkpoint["status"] == "PENDING"
        ],
        "acceptance": {criterion["id"]: criterion["status"] for criterion in state["acceptanceCriteria"]},
        "activeLanes": [lane["id"] for lane in state["lanes"]["active"]],
        "nextCheapestTest": state["focus"]["nextCheapestTest"],
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

    for command in ("status", "inspect", "events", "ready", "resume", "verify", "checkpoint"):
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
    task_add.add_argument("--lane", default="product")
    task_add.add_argument("--work-kind", choices=sorted(WORK_KINDS), default="product")
    task_add.add_argument("--change-kind", choices=["normal", "replacement-architecture", "new-compatibility-constraint"], default="normal")
    task_add.add_argument("--operation", action="append", default=[])
    task_add.add_argument("--target-json")
    task_add.add_argument("--minimal-test", action="store_true")
    task_add.add_argument("--large-change", action="store_true")
    task_add.add_argument("--criteria", required=True)
    task_add.add_argument("--artifact", action="append", default=[])
    task_add.add_argument("--gate")
    task_add.add_argument("--max-attempts", type=int, default=1)
    task_add.add_argument("--side-effect", help="OPERATION@TARGET")
    task_add.add_argument("--command", dest="execution_command", nargs=argparse.REMAINDER, help="deterministic shell argv (must be last)")

    objective = subparsers.add_parser("objective-replace")
    objective.add_argument("run_id")
    objective.add_argument("--outcome", required=True)
    objective.add_argument("--criterion", action="append", required=True)
    objective.add_argument("--correction", required=True)
    objective.add_argument("--next-test", required=True)
    objective.add_argument("--checkpoint-id", required=True)
    objective.add_argument("--challenge", required=True)
    objective.add_argument("--actor", required=True)

    reuse = subparsers.add_parser("reuse-verify")
    reuse.add_argument("run_id")
    reuse.add_argument("--path", required=True)
    reuse.add_argument("--difference", required=True)
    reuse.add_argument("--test-command", nargs=argparse.REMAINDER, required=True)

    target = subparsers.add_parser("target-resolve")
    target.add_argument("run_id")
    target.add_argument("--checkpoint-id", required=True)
    target.add_argument("--challenge", required=True)
    target.add_argument("--intended-json", required=True)
    target.add_argument("--evidence", required=True)
    target.add_argument("--actor", required=True)

    review = subparsers.add_parser("review-record")
    review.add_argument("run_id")
    review.add_argument("--verdict", choices=["PASS", "REVISE", "FAIL"], required=True)
    review.add_argument("--evidence", action="append", default=[])

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
    gate.add_argument("--family", help="independent reviewer identity; model selection remains host-owned")
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

    policy_request = subparsers.add_parser("policy-amend-request")
    policy_request.add_argument("run_id")
    policy_request.add_argument("--id", required=True)
    policy_request.add_argument("--task-id", required=True)
    policy_request.add_argument("--principal", required=True)
    policy_request.add_argument("--provider", required=True)
    policy_request.add_argument("--actor", required=True)
    policy_request.add_argument("--reason", required=True)
    policy_request.add_argument("--add-allow", action="append", default=[])
    policy_request.add_argument("--add-confirmation-required", action="append", default=[])

    policy_amend = subparsers.add_parser("policy-amend")
    policy_amend.add_argument("run_id")
    policy_amend.add_argument("checkpoint_id")
    policy_amend.add_argument("--challenge", required=True)
    policy_amend.add_argument("--principal", required=True)
    policy_amend.add_argument("--provider", required=True)
    policy_amend.add_argument("--actor", required=True)
    policy_amend.add_argument("--add-allow", action="append", default=[])
    policy_amend.add_argument("--add-confirmation-required", action="append", default=[])

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
        elif command == "checkpoint":
            output = store.human_checkpoint(args.run_id)
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
        elif command == "objective-replace":
            output = state_summary(
                store.replace_objective(
                    args.run_id,
                    outcome=args.outcome,
                    criteria=[parse_criterion(item) for item in args.criterion],
                    correction=args.correction,
                    next_cheapest_test=args.next_test,
                    checkpoint_id=args.checkpoint_id,
                    challenge=args.challenge,
                    actor=args.actor,
                )
            )
        elif command == "reuse-verify":
            output = state_summary(
                store.verify_reuse_baseline(
                    args.run_id,
                    path=args.path,
                    difference=args.difference,
                    test_command=args.test_command,
                )
            )
        elif command == "target-resolve":
            output = state_summary(
                store.resolve_target_identity_checkpoint(
                    args.run_id,
                    checkpoint_id=args.checkpoint_id,
                    challenge=args.challenge,
                    intended=json.loads(args.intended_json),
                    evidence_ref=args.evidence,
                    actor=args.actor,
                )
            )
        elif command == "review-record":
            output = state_summary(
                store.record_review_result(
                    args.run_id,
                    verdict=args.verdict,
                    product_evidence_refs=args.evidence,
                )
            )
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
                    "lane": args.lane,
                    "workKind": args.work_kind,
                    "changeKind": args.change_kind,
                    "operations": args.operation,
                    "targetIdentity": json.loads(args.target_json) if args.target_json else None,
                    "isMinimalAcceptanceTest": args.minimal_test,
                    "largeChange": args.large_change,
                    "acceptanceCriteria": split_csv(args.criteria),
                    "requiredArtifacts": args.artifact,
                    "gate": args.gate,
                    "maxAttempts": args.max_attempts,
                    "sideEffect": side_effect,
                    "workPacket": {
                        "execution": {
                            "command": args.execution_command,
                            "cwd": None,
                            "environment": [],
                        }
                    } if args.execution_command else None,
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
        elif command == "policy-amend-request":
            state, challenge = store.request_policy_amendment(
                args.run_id,
                checkpoint_id=args.id,
                task_id=args.task_id,
                principal=args.principal,
                provider=args.provider,
                delta={
                    "addAllow": [parse_policy_allow(item) for item in args.add_allow],
                    "addConfirmationRequired": args.add_confirmation_required,
                },
                reason=args.reason,
                actor=args.actor,
            )
            output = {**state_summary(state), "resolutionChallenge": challenge}
        elif command == "policy-amend":
            output = state_summary(
                store.amend_policy(
                    args.run_id,
                    checkpoint_id=args.checkpoint_id,
                    challenge=args.challenge,
                    principal=args.principal,
                    provider=args.provider,
                    delta={
                        "addAllow": [parse_policy_allow(item) for item in args.add_allow],
                        "addConfirmationRequired": args.add_confirmation_required,
                    },
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