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
import fnmatch
import hashlib
import hmac
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import shutil
import sys
import tempfile
import uuid
import secrets
import stat
import threading
import time
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
    "PRODUCT_OUTCOME_CONFIRMED",
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
PRIMARY_STALL_THRESHOLD = 3
PRIMARY_RESULT_EVENTS = {"worker.finished", "task.completed", "task.failed"}
PRIMARY_BOUND_EVENTS = PRIMARY_RESULT_EVENTS | {
    "gate.passed", "gate.failed", "gate.recorded", "acceptance.updated", "product.progress", "product.milestone",
}
OBSERVED_OUTCOME_TYPES = {"reality", "e2e", "external"}
PUSHBACK_VERDICTS = {"KEEP", "CUT", "DEFER"}
BUDGET_LIMITS = {"turns": "maxTurns", "commits": "maxCommits", "dispatches": "maxDispatches", "minutes": "maxMinutes"}
OWNER_MESSAGE_NOISE = (
    re.compile(r"\b[0-9a-f]{40}(?:[0-9a-f]{24})?\b", re.IGNORECASE),
    re.compile(r"\bpids?\s*[=:#]?\s*\d+", re.IGNORECASE),
    re.compile(r"\brun-[A-Za-z0-9][A-Za-z0-9._-]*"),
    re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE),
)
TARGET_IDENTITY_FIELDS = {
    "provider",
    "artifact",
    "version",
    "sha256",
    "environment",
    "workspace",
    "acceptanceTarget",
}
EXECUTOR_REGISTRY_SCHEMA = "architrave.executor-registry.v1"
EXACT_TARGET_REQUEST_SCHEMA = "architrave.exact-target-request.v1"
EXACT_TARGET_RESULT_SCHEMA = "architrave.exact-target-result.v1"
EXECUTOR_STDOUT_LIMIT = 64 * 1024
EXECUTOR_STDERR_LIMIT = 8 * 1024


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


def _is_reparse_point(info: os.stat_result) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & 0x400)


def trusted_user_state_root() -> Path:
    if os.name == "nt":
        import ctypes

        buffer = ctypes.create_unicode_buffer(32768)
        result = ctypes.windll.shell32.SHGetFolderPathW(None, 40, None, 0, buffer)
        if result != 0 or not buffer.value:
            raise RuntimeFailure("EXECUTOR_TRUST_ROOT_INVALID", "Windows user profile path is unavailable")
        home = Path(buffer.value)
    else:
        import pwd

        home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    if not home.is_absolute():
        raise RuntimeFailure("EXECUTOR_TRUST_ROOT_INVALID", "user profile path is not absolute")
    return home / ".architrave"


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise json.JSONDecodeError(f"duplicate key: {key}", key, 0)
        result[key] = value
    return result


def _verify_pinned_executable(path_value: Any, digest_value: Any, label: str) -> Path:
    if not isinstance(path_value, str) or not isinstance(digest_value, str):
        raise RuntimeFailure("EXECUTOR_REGISTRY_INVALID", f"trusted {label} path and digest are invalid")
    path = Path(path_value)
    if not path.is_absolute() or not re.fullmatch(r"[0-9a-f]{64}", digest_value):
        raise RuntimeFailure("EXECUTOR_REGISTRY_INVALID", f"trusted {label} path or digest is invalid")
    try:
        info = path.lstat()
    except OSError as exc:
        raise RuntimeFailure("EXECUTOR_PIN_MISMATCH", f"trusted {label} is unavailable") from exc
    if not stat.S_ISREG(info.st_mode) or path.is_symlink() or _is_reparse_point(info):
        raise RuntimeFailure("EXECUTOR_PIN_MISMATCH", f"trusted {label} must be a regular non-link file")
    if not hmac.compare_digest(sha256_file(path), digest_value):
        raise RuntimeFailure("EXECUTOR_PIN_MISMATCH", f"trusted {label} SHA-256 pin does not match")
    return path.resolve()


def _bounded_stream_reader(
    stream: Any,
    limit: int,
    output: bytearray,
    overflow: threading.Event,
) -> None:
    while True:
        chunk = stream.read(min(4096, limit + 1))
        if not chunk:
            return
        remaining = limit - len(output)
        if remaining > 0:
            output.extend(chunk[:remaining])
        if len(chunk) > remaining:
            overflow.set()
            return


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


class NativeWorkerTicket:
    """Process-local authority held by the trusted host bridge, never serialized."""

    def __init__(self, issuer: object, binding: dict[str, Any], snapshot: dict[str, Any]):
        self.issuer = issuer
        self.binding = binding
        self.snapshot = snapshot
        self.consumed = False


class NativeSemanticTicket:
    """Single-invocation authority; never a serialized verdict-import capability."""

    def __init__(self, issuer: object, binding: dict[str, Any], challenge: str, budget: dict[str, Any]):
        self.issuer = issuer
        self.binding = binding
        self.challenge = challenge
        self.budget = budget
        self.consumed = False
        self.receipt_sha256 = None


def native_review_family(model: str) -> str:
    if isinstance(model, str) and model.startswith(("gpt-", "o1", "o3", "o4")):
        return "openai"
    if isinstance(model, str) and model.startswith("claude-"):
        return "anthropic"
    raise RuntimeFailure("SEMANTIC_FAMILY_UNCONFIRMED", "host first-dispatched model has no supported family mapping")

def native_source_inventory(repository: Path) -> tuple[list[str], dict[str, Any]]:
    tracked = [path for path in run_command(["git", "ls-files", "-z"], repository).split("\0") if path]
    private = [path for path in tracked if path.split("/", 1)[0].casefold() in {".git", ".architrave"}]
    private_paths = set(private)
    implementation = [path for path in tracked if path not in private_paths]
    if len(implementation) > 4096:
        raise RuntimeFailure("SEMANTIC_SOURCE_TOO_LARGE", "bounded native implementation inventory exceeded")
    scope = {"kind": "implementation-source", "inventoryCount": len(implementation),
             "inventorySha256": sha256_value(implementation),
             "excludedCategory": "canonical-control-plane/history-and-private-trust-metadata",
             "excludedPrivateStateCount": len(private),
             "privateHistoryAcceptance": "not reviewed; supervisor audit remains separate"}
    return implementation, scope


class RunStore:
    def __init__(self, repository: Path | str):
        self.repository = Path(repository).resolve()
        self.runs_root = self.repository / ".architrave" / "runs"
        self.__native_issuer = object()
        self.__semantic_issuer = object()
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

    def _executor_registry_path(self) -> Path:
        return trusted_user_state_root() / "executors.json"

    def _read_executor_registry(self) -> dict[str, Any]:
        path = self._executor_registry_path()
        try:
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or path.is_symlink() or _is_reparse_point(info):
                raise RuntimeFailure("EXECUTOR_REGISTRY_INVALID", "trusted executor registry must be a regular file")
            if os.name != "nt" and (info.st_uid != os.getuid() or (info.st_mode & 0o077) != 0):
                raise RuntimeFailure("EXECUTOR_REGISTRY_PERMISSIONS", "trusted executor registry owner or permissions are unsafe")
            registry = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_json_keys)
        except RuntimeFailure:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeFailure("EXECUTOR_REGISTRY_INVALID", "trusted executor registry is unavailable or invalid") from exc
        if not isinstance(registry, dict) or set(registry) != {"schema", "exactTarget"}:
            raise RuntimeFailure("EXECUTOR_REGISTRY_INVALID", "trusted executor registry schema is invalid")
        if registry["schema"] != EXECUTOR_REGISTRY_SCHEMA or not isinstance(registry["exactTarget"], dict):
            raise RuntimeFailure("EXECUTOR_REGISTRY_INVALID", "trusted executor registry schema is unsupported")
        return registry

    def _trusted_exact_target_executor(
        self,
        checkpoint: dict[str, Any],
        intended: dict[str, str],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        executor = self._read_executor_registry()["exactTarget"]
        required = {
            "executable",
            "executableSha256",
            "adapter",
            "adapterSha256",
            "allowedProviders",
            "allowedCheckpointTypes",
            "timeoutSeconds",
            "targets",
        }
        if set(executor) != required:
            raise RuntimeFailure("EXECUTOR_REGISTRY_INVALID", "exact-target executor entry is invalid")
        if (
            not isinstance(executor["allowedProviders"], list)
            or checkpoint["provider"] not in executor["allowedProviders"]
            or not isinstance(executor["allowedCheckpointTypes"], list)
            or checkpoint["type"] not in executor["allowedCheckpointTypes"]
        ):
            raise RuntimeFailure("EXECUTOR_NOT_ALLOWED", "trusted executor is not allowed for this provider and checkpoint type")
        timeout = executor["timeoutSeconds"]
        if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout < 1 or timeout > 30:
            raise RuntimeFailure("EXECUTOR_REGISTRY_INVALID", "trusted executor timeout must be between 1 and 30 seconds")
        executable = _verify_pinned_executable(executor["executable"], executor["executableSha256"], "executor")
        adapter = _verify_pinned_executable(executor["adapter"], executor["adapterSha256"], "adapter")
        trust_root = trusted_user_state_root().resolve()
        registry_path = self._executor_registry_path().resolve()
        try:
            registry_path.relative_to(trust_root)
            adapter.relative_to(trust_root / "executors")
        except ValueError as exc:
            raise RuntimeFailure(
                "EXECUTOR_TRUST_ROOT_INVALID",
                "trusted executor registry and adapter must live in the private user executor tree",
            ) from exc
        for trusted_path, label in ((registry_path, "registry"), (adapter, "adapter")):
            try:
                trusted_path.relative_to(self.repository)
            except ValueError:
                pass
            else:
                raise RuntimeFailure("EXECUTOR_TRUST_ROOT_INVALID", f"trusted executor {label} cannot live inside the target repository")
        if os.name != "nt":
            for path in (trust_root, trust_root / "executors", adapter.parent):
                info = path.lstat()
                if not stat.S_ISDIR(info.st_mode) or path.is_symlink() or info.st_uid != os.getuid() or (info.st_mode & 0o077) != 0:
                    raise RuntimeFailure("EXECUTOR_TRUST_ROOT_INVALID", "trusted executor directory owner or permissions are unsafe")
        targets = executor["targets"]
        if not isinstance(targets, list):
            raise RuntimeFailure("EXECUTOR_REGISTRY_INVALID", "trusted executor targets must be a list")
        matches = [
            target
            for target in targets
            if isinstance(target, dict)
            and target.get("identity") == intended
        ]
        if len(matches) != 1:
            raise RuntimeFailure("EXECUTOR_TARGET_NOT_TRUSTED", "intended target is not uniquely enrolled in the trusted executor registry")
        target = matches[0]
        if set(target) not in (
            {"identity", "transport", "artifactPath", "workspaceMode", "ssh"},
            {"identity", "transport", "artifactPath", "workspaceMode", "ssh", "reconciliation"},
        ):
            raise RuntimeFailure("EXECUTOR_REGISTRY_INVALID", "trusted target entry is invalid")
        target.setdefault("reconciliation", None)
        workspace_mode = target["workspaceMode"]
        transport = target["transport"]
        artifact_path_value = str(target["artifactPath"])
        path_is_absolute = (
            Path(artifact_path_value).is_absolute()
            if transport == "local"
            else PurePosixPath(artifact_path_value).is_absolute()
        )
        if transport not in {"local", "ssh"} or not path_is_absolute or workspace_mode not in {"exact-directory", "absent-or-exact-directory"}:
            raise RuntimeFailure("EXECUTOR_REGISTRY_INVALID", "trusted target path or workspace mode is invalid")
        if transport == "local":
            if target["ssh"] is not None:
                raise RuntimeFailure("EXECUTOR_REGISTRY_INVALID", "local trusted target cannot declare SSH settings")
        else:
            ssh = target["ssh"]
            ssh_fields = {
                "executable",
                "executableSha256",
                "host",
                "hostKeyAlias",
                "port",
                "user",
                "identityFile",
                "identityFileSha256",
                "knownHosts",
                "knownHostsSha256",
                "remotePython",
                "remoteAdapter",
                "remoteAdapterSha256",
            }
            if not isinstance(ssh, dict) or set(ssh) != ssh_fields:
                raise RuntimeFailure("EXECUTOR_REGISTRY_INVALID", "trusted SSH target settings are invalid")
            _verify_pinned_executable(ssh["executable"], ssh["executableSha256"], "SSH executable")
            identity_file = _verify_pinned_executable(ssh["identityFile"], ssh["identityFileSha256"], "SSH identity")
            known_hosts = _verify_pinned_executable(ssh["knownHosts"], ssh["knownHostsSha256"], "SSH known-hosts")
            for trusted_path, label in ((identity_file, "SSH identity"), (known_hosts, "SSH known-hosts")):
                try:
                    trusted_path.relative_to(
                        trust_root.parent / ".ssh"
                        if os.name == "nt"
                        else trust_root
                    )
                except ValueError as exc:
                    raise RuntimeFailure(
                        "EXECUTOR_TRUST_ROOT_INVALID",
                        f"trusted {label} must live under the approved private user SSH trust root",
                    ) from exc
        return {
            **executor,
            "executable": str(executable),
            "adapter": str(adapter),
        }, target

    def _invoke_exact_target_executor(
        self,
        executor: dict[str, Any],
        request: dict[str, Any],
    ) -> dict[str, Any]:
        encoded = canonical_json(request).encode("utf-8")
        if len(encoded) > 32 * 1024:
            raise RuntimeFailure("EXECUTOR_REQUEST_OVERSIZE", "trusted executor request exceeds the size limit")
        registry_dir = self._executor_registry_path().parent.resolve()
        environment = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in {
                "SYSTEMROOT",
                "WINDIR",
                "TMP",
                "TEMP",
                "TMPDIR",
                "USERPROFILE",
                "HOMEDRIVE",
                "HOMEPATH",
                "PROGRAMDATA",
            }
        }
        try:
            process = subprocess.Popen(
                [executor["executable"], "-I", "-S", executor["adapter"]],
                cwd=registry_dir,
                env=environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
            )
        except OSError as exc:
            raise RuntimeFailure("EXECUTOR_LAUNCH_FAILED", "trusted executor could not be launched") from exc
        stdout_bytes = bytearray()
        stderr_bytes = bytearray()
        stdout_overflow = threading.Event()
        stderr_overflow = threading.Event()
        stdout_thread = threading.Thread(
            target=_bounded_stream_reader,
            args=(process.stdout, EXECUTOR_STDOUT_LIMIT, stdout_bytes, stdout_overflow),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=_bounded_stream_reader,
            args=(process.stderr, EXECUTOR_STDERR_LIMIT, stderr_bytes, stderr_overflow),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()
        try:
            assert process.stdin is not None
            process.stdin.write(encoded)
            process.stdin.close()
            deadline = time.monotonic() + executor["timeoutSeconds"]
            while process.poll() is None:
                if stdout_overflow.is_set() or stderr_overflow.is_set():
                    process.kill()
                    raise RuntimeFailure("EXECUTOR_OUTPUT_OVERSIZE", "trusted executor output exceeds the size limit")
                if time.monotonic() >= deadline:
                    process.kill()
                    raise RuntimeFailure("EXECUTOR_TIMEOUT", "trusted executor timed out")
                time.sleep(0.01)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            stdout_thread.join(timeout=1)
            stderr_thread.join(timeout=1)
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()
        if stdout_overflow.is_set() or stderr_overflow.is_set():
            raise RuntimeFailure("EXECUTOR_OUTPUT_OVERSIZE", "trusted executor output exceeds the size limit")
        stdout = bytes(stdout_bytes).decode("utf-8", "replace")
        stderr = bytes(stderr_bytes).decode("utf-8", "replace")
        if process.returncode != 0:
            raise RuntimeFailure(
                "EXECUTOR_FAILED",
                "trusted executor rejected the observation",
                details={"exitCode": process.returncode, "stderr": redact(stderr)[:2000]},
            )
        try:
            result = json.loads(stdout, object_pairs_hook=_reject_duplicate_json_keys)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeFailure("EXECUTOR_RESULT_INVALID", "trusted executor returned malformed JSON") from exc
        if (
            not isinstance(result, dict)
            or set(result) != {"schema", "status", "binding", "observed", "observation"}
            or result.get("schema") != EXACT_TARGET_RESULT_SCHEMA
            or result.get("status") != "observed"
            or result.get("binding") != request["binding"]
            or not isinstance(result.get("observed"), dict)
            or set(result["observed"]) != TARGET_IDENTITY_FIELDS
            or not isinstance(result.get("observation"), dict)
        ):
            raise RuntimeFailure("EXECUTOR_RESULT_INVALID", "trusted executor result schema or binding is invalid")
        observation = result["observation"]
        common_observation = {
            "artifactPath",
            "artifactSha256",
            "artifactSize",
            "workspacePath",
            "workspaceState",
            "observerSha256",
            "transport",
        }
        expected_observation = (
            common_observation
            if request["target"]["transport"] == "local"
            else common_observation | {"sshHost"}
        )
        reconciliation = request["target"].get("reconciliation")
        if reconciliation is not None:
            expected_observation |= {"processId", "processState", "reconciliationOutcome"}
        expected_observer_sha256 = (
            executor["adapterSha256"]
            if request["target"]["transport"] == "local"
            else request["target"]["ssh"]["remoteAdapterSha256"]
        )
        if (
            set(observation) != expected_observation
            or observation.get("transport") != request["target"]["transport"]
            or not isinstance(observation.get("artifactPath"), str)
            or not isinstance(observation.get("workspacePath"), str)
            or not isinstance(observation.get("artifactSize"), int)
            or isinstance(observation.get("artifactSize"), bool)
            or observation["artifactSize"] < 0
            or observation.get("workspaceState") not in {"absent", "directory"}
            or (
                request["target"]["workspaceMode"] == "exact-directory"
                and observation.get("workspaceState") != "directory"
            )
            or not re.fullmatch(r"[0-9a-f]{64}", str(observation.get("artifactSha256", "")))
            or not re.fullmatch(r"[0-9a-f]{64}", str(observation.get("observerSha256", "")))
            or (request["target"]["transport"] == "ssh" and observation.get("sshHost") != request["target"]["ssh"]["host"])
            or observation.get("artifactSha256") != request["intended"]["sha256"]
            or observation.get("artifactPath") != request["target"]["artifactPath"]
            or observation.get("workspacePath") != request["intended"]["workspace"]
            or observation.get("observerSha256") != expected_observer_sha256
            or (
                reconciliation is not None
                and (
                    observation.get("processId") != reconciliation["processId"]
                    or observation.get("processState") != "closed"
                    or observation.get("reconciliationOutcome") != reconciliation["outcome"]
                )
            )
            or redact(observation) != observation
        ):
            raise RuntimeFailure("EXECUTOR_RESULT_INVALID", "trusted executor observation schema is invalid")
        return result

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
        primary_criterion: str | None = None,
        primary_paths: Sequence[str] = (),
        primary_threshold: int = PRIMARY_STALL_THRESHOLD,
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
                    "pushbackRequired": True,
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
            if primary_criterion:
                state["focus"]["primaryCriterion"] = normalize_primary_criterion(
                    state, primary_criterion, primary_paths, primary_threshold, state["baseline"]["commit"],
                )
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
                or checkpoint.get("focusCorrection") is not None
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
            state["focus"].pop("primaryCriterion", None)
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

    def set_primary_criterion(
        self,
        run_id: str,
        *,
        criterion_id: str,
        paths: Sequence[str],
        threshold: int = PRIMARY_STALL_THRESHOLD,
        actor: str = "coordinator",
    ) -> dict[str, Any]:
        head = run_command(["git", "rev-parse", "HEAD"], self.repository)

        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            if state["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
                raise RuntimeFailure("RUN_TERMINAL", "cannot declare a primary criterion on a terminal Run")
            state["focus"]["primaryCriterion"] = normalize_primary_criterion(
                state, criterion_id, paths, threshold, head,
            )
            return copy.deepcopy(state["focus"]["primaryCriterion"])

        return self._transaction(run_id, mutate, event_type="focus.primary_declared", actor=actor)

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
        raise RuntimeFailure(
            "TRUSTED_EXECUTOR_REQUIRED",
            "SAFE_WRITE_TARGET_REQUIRED checkpoints must be resolved with target-attest",
        )

    def attest_target_identity_checkpoint(
        self,
        run_id: str,
        *,
        checkpoint_id: str,
        challenge: str,
        actor: str,
    ) -> dict[str, Any]:
        before = self.load(run_id)
        checkpoint = next((item for item in before["externalCheckpoints"] if item["id"] == checkpoint_id), None)
        task = find_task(before, checkpoint["taskId"]) if checkpoint else None
        supplied_hash = hashlib.sha256(challenge.encode("utf-8")).hexdigest()
        if (
            checkpoint is None
            or task is None
            or checkpoint["status"] != "PENDING"
            or checkpoint["type"] != "SAFE_WRITE_TARGET_REQUIRED"
            or checkpoint["objectiveVersion"] != before["objective"]["version"]
            or not hmac.compare_digest(checkpoint["challengeHash"], supplied_hash)
            or actor != f"human:{checkpoint['principal']}"
            or not isinstance(task.get("targetIdentity"), dict)
            or set(task["targetIdentity"]) != TARGET_IDENTITY_FIELDS
        ):
            raise RuntimeFailure("TARGET_IDENTITY_INVALID", "target identity checkpoint is invalid")
        intended = dict(task["targetIdentity"])
        expected_binding = sha256_value(
            {
                "runId": run_id,
                "objectiveVersion": before["objective"]["version"],
                "taskId": task["id"],
                "provider": checkpoint["provider"],
                "principal": checkpoint["principal"],
                "intended": intended,
                "challengeHash": checkpoint["challengeHash"],
            }
        )
        if checkpoint.get("targetBindingHash") != expected_binding:
            raise RuntimeFailure("TARGET_IDENTITY_INVALID", "target identity checkpoint binding is invalid")
        executor, trusted_target = self._trusted_exact_target_executor(checkpoint, intended)
        binding = {
            "runId": run_id,
            "objectiveVersion": before["objective"]["version"],
            "revision": before["revision"],
            "taskId": task["id"],
            "checkpointId": checkpoint_id,
            "checkpointType": checkpoint["type"],
            "provider": checkpoint["provider"],
            "principal": checkpoint["principal"],
            "challengeHash": checkpoint["challengeHash"],
        }
        request = {
            "schema": EXACT_TARGET_REQUEST_SCHEMA,
            "binding": binding,
            "intended": intended,
            "target": {
                "transport": trusted_target["transport"],
                "artifactPath": trusted_target["artifactPath"],
                "workspaceMode": trusted_target["workspaceMode"],
                "ssh": trusted_target["ssh"],
                "reconciliation": trusted_target.get("reconciliation"),
            },
        }
        result = self._invoke_exact_target_executor(executor, request)
        observed = result["observed"]
        mismatches = {
            key: {"intended": intended[key], "observed": observed[key]}
            for key in sorted(TARGET_IDENTITY_FIELDS)
            if intended[key] != observed[key]
        }
        if mismatches:
            raise RuntimeFailure(
                "TARGET_IDENTITY_MISMATCH",
                "trusted executor observed a different target identity",
                details=mismatches,
            )
        artifact_id = f"external-{uuid.uuid4().hex}"
        evidence_ref = f"artifact:{artifact_id}"
        receipt_relative = (Path(".architrave") / "runs" / run_id / "evidence" / f"{artifact_id}.json").as_posix()
        receipt_path = self.repository / receipt_relative
        receipt = {
            **binding,
            "actor": checkpoint["principal"],
            "intended": intended,
            "observed": observed,
            "adapter": {
                "executable": executor["executable"],
                "executableSha256": executor["executableSha256"],
                "adapter": executor["adapter"],
                "adapterSha256": executor["adapterSha256"],
            },
            "observation": result["observation"],
        }
        receipt_bytes = (canonical_json(receipt) + "\n").encode("utf-8")
        receipt_sha256 = hashlib.sha256(receipt_bytes).hexdigest()

        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            current_checkpoint = next(
                (item for item in state["externalCheckpoints"] if item["id"] == checkpoint_id),
                None,
            )
            current_task = find_task(state, current_checkpoint["taskId"]) if current_checkpoint else None
            if (
                state["revision"] != before["revision"]
                or state["objective"]["version"] != binding["objectiveVersion"]
                or current_checkpoint is None
                or current_task is None
                or current_checkpoint["status"] != "PENDING"
                or current_checkpoint["type"] != binding["checkpointType"]
                or current_checkpoint["taskId"] != binding["taskId"]
                or current_checkpoint["provider"] != binding["provider"]
                or current_checkpoint["principal"] != binding["principal"]
                or current_checkpoint["challengeHash"] != binding["challengeHash"]
                or current_checkpoint.get("targetBindingHash") != expected_binding
                or current_task.get("targetIdentity") != intended
                or actor != f"human:{current_checkpoint['principal']}"
            ):
                raise RuntimeFailure("TARGET_ATTESTATION_STALE", "target attestation became stale before commit")
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(prefix=f".{receipt_path.name}.", dir=receipt_path.parent)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(receipt_bytes)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, receipt_path)
            finally:
                with contextlib.suppress(FileNotFoundError):
                    os.unlink(temporary)
            if sha256_file(receipt_path) != receipt_sha256:
                raise RuntimeFailure("TARGET_ATTESTATION_RACE", "target proof receipt changed before registration")
            artifact = {
                "id": artifact_id,
                "kind": "external-proof",
                "producer": "external-proof",
                "path": receipt_relative,
                "createdAt": utc_now(),
                "sha256": receipt_sha256,
                "evidenceRefs": [f"task:{current_task['id']}"],
                "consumedByTask": current_task["id"],
            }
            artifact["attestation"] = self._artifact_attestation(artifact)
            state["artifacts"].append(artifact)
            current_checkpoint["status"] = "RESOLVED"
            current_checkpoint["resolvedAt"] = utc_now()
            current_checkpoint["resolvedBy"] = actor
            current_checkpoint["resolutionRef"] = f"target:{checkpoint_id}"
            if not any(
                item["taskId"] == current_task["id"] and item["status"] == "PENDING"
                for item in state["externalCheckpoints"]
            ):
                current_task["status"] = "READY" if dependencies_completed(state, current_task) else "NOT_READY"
            state["targetIdentity"] = {
                "taskId": current_task["id"],
                "checkpointId": checkpoint_id,
                "principal": current_checkpoint["principal"],
                "provider": current_checkpoint["provider"],
                "challengeHash": current_checkpoint["challengeHash"],
                "intended": intended,
                "observed": observed,
                "status": "VERIFIED",
                "mismatches": {},
                "objectiveVersion": state["objective"]["version"],
                "verifiedAt": utc_now(),
                "verifiedRevision": state["revision"] + 1,
                "artifactPath": result["observation"].get("artifactPath"),
                "transport": result["observation"].get("transport"),
                "evidenceRef": evidence_ref,
            }
            state["status"] = derive_run_status(state)
            return copy.deepcopy(state["targetIdentity"])

        return self._transaction(
            run_id,
            mutate,
            event_type="target.preflight",
            actor=actor,
            task_id=task["id"],
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

    def advance_milestone(self, run_id: str, task_id: str, *, criterion_id: str,
                          milestone: str, gate_ref: str) -> dict[str, Any]:
        """Record verified intermediate progress, never criterion completion."""
        from worker_adapters import workspace_fingerprint
        if not milestone.strip() or len(milestone) > 160:
            raise RuntimeFailure("MILESTONE_INVALID", "one compact milestone label is required")

        def mutate(state):
            self._assert_repository_baseline(state)
            task = find_task(state, task_id)
            if task["objectiveVersion"] != state["objective"]["version"] or criterion_id not in task["acceptanceCriteria"]:
                raise RuntimeFailure("MILESTONE_BINDING", "milestone must belong to the current task/criterion")
            require_evidence_refs(state, [gate_ref], allowed={"gate"})
            gate = next(item for item in state["gateResults"] if f"gate:{item['id']}" == gate_ref)
            if (gate["taskId"] != task_id or criterion_id not in gate["criteria"]
                    or gate["objectiveVersion"] != state["objective"]["version"]
                    or gate["type"] not in {"reality", "e2e"}):
                raise RuntimeFailure("MILESTONE_BINDING", "a matching current task product gate is required")
            refs = set(gate["evidenceRefs"])
            artifacts = [item for item in state["artifacts"] if f"artifact:{item['id']}" in refs]
            if not artifacts or any(item["producer"] != "legibility" for item in artifacts):
                raise RuntimeFailure("MILESTONE_PRODUCER", "only executor-produced product legibility observations advance milestones")
            current = workspace_fingerprint(self.repository, include_ignored=False)
            substantive = []
            for artifact in artifacts:
                receipt = self._read_json_receipt(artifact["path"], "milestone")
                binding = receipt.get("binding", {})
                source = receipt.get("source", {})
                if (binding.get("runId") != run_id or binding.get("taskId") != task_id
                        or binding.get("objectiveVersion") != state["objective"]["version"]
                        or criterion_id not in binding.get("criteria", [])
                        or source.get("commit") != state["baseline"]["commit"] or source.get("sha256") != current):
                    raise RuntimeFailure("MILESTONE_SOURCE_STALE", "product observation lacks exact current source/task/criterion binding")
                results = [{key: value for key, value in result.items() if key != "artifacts"}
                           | {"artifactDigests": sorted(item["sha256"] for item in result.get("artifacts", []))}
                           for result in receipt["results"]]
                substantive.append({"surface": receipt["surface"], "results": results})
            digest = sha256_value(substantive)
            events = self._read_events(self.run_dir(run_id))
            if any(event["type"] == "product.milestone" and event["payload"].get("criterionId") == criterion_id
                   and event["payload"].get("observationDigest") == digest for event in events):
                raise RuntimeFailure("MILESTONE_REPLAY", "identical product observation cannot count twice")
            return {"taskId": task_id, "criterionId": criterion_id, "milestone": milestone.strip(),
                    "observationDigest": digest, "source": {"commit": state["baseline"]["commit"], "sha256": current},
                    "criterionCompleted": False}

        return self._transaction(run_id, mutate, event_type="product.milestone",
                                 task_id=task_id, evidence_refs=[gate_ref])

    def request_focus_correction(self, run_id: str, task_id: str, *, paths: Sequence[str],
                                 principal: str, actor: str, checkpoint_id: str) -> tuple[dict[str, Any], str]:
        """Owner challenge for primary path facts only, not a generic repair grant."""
        from worker_adapters import workspace_fingerprint
        corrected = [safe_relative_path(path, "primary path") for path in paths]
        if not corrected or actor != f"human:{principal}":
            raise RuntimeFailure("FOCUS_CORRECTION_AUTHORITY", "owner principal and nonempty repository paths required")
        state = self.load(run_id)
        task = find_task(state, task_id)
        primary = state["focus"].get("primaryCriterion")
        if not primary or primary["id"] not in task["acceptanceCriteria"] or task["lease"] or task["status"] == "RUNNING":
            raise RuntimeFailure("FOCUS_CORRECTION_UNSAFE", "settled current primary-bound task required")
        for path in corrected:
            self._assert_focus_path(path)
        revision = state["revision"]
        source = workspace_fingerprint(self.repository, include_ignored=False)
        challenge = "arc_" + secrets.token_urlsafe(32)
        def mutate(current):
            if current["revision"] != revision or find_task(current, task_id)["objectiveVersion"] != current["objective"]["version"]:
                raise RuntimeFailure("FOCUS_CORRECTION_STALE", "task/objective changed before owner challenge")
            for path in corrected:
                self._assert_focus_path(path)
            if any(item["id"] == checkpoint_id for item in current["externalCheckpoints"]):
                raise RuntimeFailure("EXTERNAL_CHECKPOINT_EXISTS", "correction checkpoint already exists")
            current["externalCheckpoints"].append({
                "id": require_id(checkpoint_id, "checkpoint"), "taskId": task_id,
                "type": "HUMAN_JUDGMENT_REQUIRED", "principal": principal, "provider": "focus-correction",
                "reason": "Owner-bound factual primary-path correction only; no PASS, baseline, hold or budget repair.",
                "createdAt": utc_now(), "status": "PENDING", "resumeTask": task_id,
                "objectiveVersion": current["objective"]["version"], "targetBindingHash": None,
                "policyAmendment": None, "challengeHash": hashlib.sha256(challenge.encode()).hexdigest(),
                "resolutionRef": None, "focusCorrection": {"paths": corrected, "revision": revision + 1, "source": source},
            })
            return {"checkpointId": checkpoint_id, "paths": corrected, "taskId": task_id}
        return self._transaction(run_id, mutate, event_type="focus.correction_requested", actor=actor, task_id=task_id), challenge

    def _assert_focus_path(self, path: str) -> None:
        candidate = self.repository
        for component in Path(safe_relative_path(path, "primary path")).parts:
            candidate = candidate / component
            try:
                info = candidate.lstat()
            except OSError as exc:
                raise RuntimeFailure("FOCUS_CORRECTION_PATH", "corrected path must exist in this repository") from exc
            if stat.S_ISLNK(info.st_mode) or _is_reparse_point(info):
                raise RuntimeFailure("FOCUS_CORRECTION_PATH", "symlink/junction/reparse correction paths are not accepted")
        try:
            candidate.resolve().relative_to(self.repository)
        except ValueError as exc:
            raise RuntimeFailure("FOCUS_CORRECTION_PATH", "corrected path resolves outside this repository") from exc

    def apply_focus_correction(self, run_id: str, checkpoint_id: str, *, challenge: str, actor: str) -> dict[str, Any]:
        from worker_adapters import workspace_fingerprint
        def mutate(state):
            checkpoint = next((item for item in state["externalCheckpoints"] if item["id"] == checkpoint_id), None)
            correction = checkpoint.get("focusCorrection") if checkpoint else None
            if (not correction or checkpoint["status"] != "PENDING"
                    or actor != f"human:{checkpoint['principal']}"
                    or hashlib.sha256(challenge.encode()).hexdigest() != checkpoint["challengeHash"]
                    or state["revision"] != correction["revision"]
                    or checkpoint["objectiveVersion"] != state["objective"]["version"]
                    or workspace_fingerprint(self.repository, include_ignored=False) != correction["source"]):
                raise RuntimeFailure("FOCUS_CORRECTION_STALE", "owner challenge/source/revision/objective mismatch")
            task = find_task(state, checkpoint["taskId"])
            for path in correction["paths"]:
                self._assert_focus_path(path)
            if task.get("lease") or task["status"] == "RUNNING":
                raise RuntimeFailure("HOST_PAUSE_REQUIRED", "settle the actual owner before correction")
            state["focus"]["primaryCriterion"]["paths"] = correction["paths"]
            checkpoint.update(status="RESOLVED", resolvedAt=utc_now(), resolvedBy=actor,
                              resolutionRef=f"focus:{state['revision'] + 1}")
            return {"checkpointId": checkpoint_id, "correctedPaths": correction["paths"], "factsOnly": True}
        return self._transaction(run_id, mutate, event_type="focus.corrected", actor=actor)

    def record_feasibility(
        self, run_id: str, task_id: str, *, trigger: str, decision: str,
        window: dict[str, int], rationale: str, next_step: str, revisit: str,
        uncertainty: str, product_delta: str, blocker: str, failed_hypotheses: Sequence[str] = (),
        owner_ceiling: dict[str, int] | None = None, owner_deadline: str | None = None,
        actor: str = "coordinator",
    ) -> dict[str, Any]:
        """One on-demand decision in the existing task; never a worker or scheduler."""
        decisions = {"CONTINUE", "BOUNDED_GO", "PIVOT", "PARK"}
        if trigger not in {"user", "stall", "repeated-failure", "budget"} or decision not in decisions:
            raise RuntimeFailure("FEASIBILITY_INVALID", "reset needs an explicit supported trigger and decision")
        text = {"rationale": rationale, "nextStep": next_step, "revisit": revisit,
                "uncertainty": uncertainty, "reportedProductDelta": product_delta, "blocker": blocker}
        if any(not value.strip() or len(value) > 1000 for value in text.values()) or "\n" in rationale:
            raise RuntimeFailure("FEASIBILITY_INVALID", "compact decision fields and one-line rationale are required")
        if len(failed_hypotheses) > 8 or any(not item.strip() or len(item) > 500 for item in failed_hypotheses):
            raise RuntimeFailure("FEASIBILITY_INVALID", "at most eight compact failed hypotheses")
        keys = {"timeoutSeconds", "maxTurns", "maxOutputBytes"}
        for value in (window, owner_ceiling or {}):
            if (not isinstance(value, dict) or set(value) - keys
                    or any(type(item) is not int or item < 1 for item in value.values())):
                raise RuntimeFailure("FEASIBILITY_INVALID", "window/owner ceiling must contain positive integer WorkPacket bounds")
        if set(window) != keys:
            raise RuntimeFailure("FEASIBILITY_INVALID", "choose finite time, turn and output ceilings")
        try:
            deadline = parse_iso(owner_deadline) if owner_deadline else None
            if deadline and deadline.tzinfo is None:
                raise ValueError("timezone missing")
        except (ValueError, TypeError) as exc:
            raise RuntimeFailure("FEASIBILITY_INVALID", "owner deadline requires an absolute timezone-qualified timestamp") from exc

        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            task = find_task(state, task_id)
            if task["objectiveVersion"] != state["objective"]["version"]:
                raise RuntimeFailure("OBJECTIVE_SUPERSEDED", "feasibility reset must belong to the current objective")
            if state["status"] in {"COMPLETED", "CANCELLED"} or task["status"] in {"COMPLETED", "CANCELLED", "SKIPPED", "DEFERRED"}:
                raise RuntimeFailure("FEASIBILITY_TERMINAL", "do not reopen completed or superseded work")
            lane = task["lane"]
            if any(other["lane"] == lane and (other["status"] == "RUNNING" or other.get("lease"))
                   for other in state["tasks"]):
                raise RuntimeFailure("HOST_PAUSE_REQUIRED", "settle the actual host owner before recording this lane reset")
            events = self._read_events(self.run_dir(run_id))
            global_budget = budget_signal(state, events, self.repository)
            primary = primary_criterion_status(state, events, self.repository) if state["focus"].get("primaryCriterion") else None
            if trigger != "user" and not (
                trigger == "stall" and primary and primary["stalled"]
                or trigger == "repeated-failure" and task.get("loop", {}).get("stopped")
                or trigger == "budget" and global_budget and global_budget["signal"] in {"BUDGET_80", "BUDGET_100"}
            ):
                raise RuntimeFailure("FEASIBILITY_TRIGGER_UNPROVEN", "quiet/time alone is not an established reset signal")
            prior = lane_feasibility(state, task)
            evidence = feasibility_evidence(state, task, self.repository)
            now = dt.datetime.now(dt.timezone.utc)
            if prior:
                if feasibility_status(state, task)["expired"]:
                    raise RuntimeFailure("FEASIBILITY_EXPIRED", "window expired; preserve the partial decision, do not reset its clock")
                if prior["evidenceDigest"] == evidence:
                    raise RuntimeFailure("FEASIBILITY_UNCHANGED", "unchanged evidence cannot renew or reopen a decision")
            ceiling = dict(prior["ceiling"] if prior else task["workPacket"]["budget"])
            ceiling.setdefault("maxTurns", 12)
            for key, value in (owner_ceiling or {}).items():
                ceiling[key] = min(ceiling[key], value)
            remaining = feasibility_remaining(state, task, self.repository, events)
            chosen = {key: min(window[key], ceiling[key]) for key in keys}
            for key in ("timeoutSeconds", "maxTurns"):
                if remaining[key] is not None:
                    chosen[key] = min(chosen[key], remaining[key])
            end = now + dt.timedelta(seconds=chosen["timeoutSeconds"])
            if deadline:
                end = min(end, deadline)
            if prior:
                end = min(end, parse_iso(prior["expiresAt"]))
            chosen["timeoutSeconds"] = max(0, int((end - now).total_seconds()))
            if (chosen["timeoutSeconds"] < 1 or chosen["maxTurns"] < 1
                    or global_budget and global_budget["signal"] == "BUDGET_100"):
                decision_value, partial = "PARK", True
            else:
                decision_value, partial = decision, False
            dependencies = [find_task(state, item) for item in task["dependencies"]]
            task["feasibility"] = {
                **{key: redact(value.strip()) for key, value in text.items()},
                "trigger": trigger, "decision": decision_value, "partial": partial,
                "startedAt": prior["startedAt"] if prior else utc_now(),
                "expiresAt": end.isoformat(timespec="seconds").replace("+00:00", "Z"),
                "startSequence": prior["startSequence"] if prior else state["eventCursor"]["sequence"] + 1,
                "recordedSequence": state["eventCursor"]["sequence"] + 1,
                "window": chosen, "ceiling": ceiling, "evidenceDigest": evidence,
                "snapshot": {
                    "objective": state["objective"]["description"][:1000],
                    "risk": task["risk"],
                    "failedHypotheses": [redact(item) for item in failed_hypotheses],
                    "failures": primary_failures(state, events, task["acceptanceCriteria"][0])[-3:],
                    "dependencies": [{"id": item["id"], "status": item["status"]} for item in dependencies[:8]],
                    "pendingHumanHolds": [item["id"] for item in state["externalCheckpoints"] if item["status"] == "PENDING"][:8],
                    "sideEffect": copy.deepcopy(task["sideEffect"]),
                    "observedProductEvidence": [ref for criterion in state["acceptanceCriteria"]
                                               if criterion["id"] in task["acceptanceCriteria"]
                                               and criterion["status"] == "PASS" and criterion["verificationType"] in OBSERVED_OUTCOME_TYPES
                                               for ref in criterion["evidenceRefs"]][-3:],
                    "availableBudget": remaining,
                },
            }
            return {"taskId": task_id, "lane": lane, "decision": decision_value,
                    "partial": partial, "window": chosen, "rationale": text["rationale"]}

        return self._transaction(run_id, mutate, event_type="feasibility.recorded", actor=actor, task_id=task_id)

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
            **({"ownerMessageLint": lint} if (lint := owner_message_lint(" ".join(
                str(text) for text in (state["objective"]["description"], *acceptance, blocker,
                                       state["focus"]["nextCheapestTest"]) if text))) else {}),
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
            native_aliases = {"native", "copilot", "claude", "codex"}
            enabled_profiles = {"native" if item in native_aliases else item for item in enabled_adapters or []}
            routed_profile = "native" if worker_profile in native_aliases else worker_profile
            if enabled_adapters and routed_profile not in enabled_profiles:
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
            pushback = task.get("pushback")
            if pushback is not None:
                verdict, _, reason = str(pushback).partition(":")
                verdict, reason = verdict.strip().upper(), reason.strip()
                if verdict not in PUSHBACK_VERDICTS or not reason or "\n" in reason:
                    raise RuntimeFailure("INVALID_PUSHBACK", "push-back must be KEEP|CUT|DEFER:one-line reason")
                pushback = {"verdict": verdict, "reason": reason}
                if verdict != "KEEP":
                    deferred_reason = f"push-back {verdict}: {reason}"
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
            if pushback is not None:
                normalized["pushback"] = pushback
                if pushback["verdict"] == "CUT":
                    normalized["status"] = "SKIPPED"
            if task.get("effort") is not None:
                if task["effort"] not in {"low", "default", "high"}:
                    raise RuntimeFailure("INVALID_TASK", "effort must be low, default, or high")
                normalized["effort"] = task["effort"]
            if change_kind != "normal":
                # Reference parity is the first gate: the replacement is bound to the tested baseline.
                normalized["reference"] = {
                    "path": state["reuseBaseline"]["path"],
                    "difference": state["reuseBaseline"]["difference"],
                    "evidenceRefs": list(state["reuseBaseline"]["evidenceRefs"]),
                }
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
        ready = []
        for task in state["tasks"]:
            if task["status"] != "READY":
                continue
            reset = feasibility_status(state, task)
            if not reset or not reset["expired"] and not reset["hostTurnsUnknown"] and reset["decision"] in {"CONTINUE", "BOUNDED_GO"}:
                ready.append(copy.deepcopy(task))
        return ready

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
        failed_names = [item.get("name") for item in results
                        if isinstance(item, dict) and item.get("status") in {"fail", "missing"}]
        passing = receipt.get("status") == "pass" and receipt.get("failed") == [] and not failed_names
        failing = (receipt.get("status") == "fail" and bool(failed_names)
                   and receipt.get("failed") == failed_names)
        observed_names = {item.get("name") for item in results if isinstance(item, dict)}
        if (
            required_names is None
            or receipt.get("surface") != surface
            or not (passing or failing)
            or not required_names.issubset(result_names if passing else observed_names)
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
        retry_hypothesis: str | None = None,
        retry_evidence: Sequence[str] = (),
    ) -> dict[str, Any]:
        require_id(worker_id, "worker id")
        preflight_revision: int | None = None
        preflight_observation: dict[str, Any] | None = None
        snapshot = self.load(run_id)
        snapshot_task = find_task(snapshot, task_id)
        pushback = snapshot_task.get("pushback")
        if pushback is None and snapshot["focus"].get("pushbackRequired"):
            raise RuntimeFailure("PUSHBACK_MISSING", "record a KEEP/CUT/DEFER push-back verdict before starting this task")
        if pushback is not None and pushback["verdict"] != "KEEP":
            raise RuntimeFailure("PUSHBACK_NOT_KEPT", f"push-back verdict {pushback['verdict']} never dispatches")
        events = self.events(run_id)
        reset = feasibility_status(snapshot, snapshot_task)
        if reset and (reset["expired"] or reset["decision"] not in {"CONTINUE", "BOUNDED_GO"}):
            raise RuntimeFailure("FEASIBILITY_STOP", "lane is paused/expired; synthesize the retained partial decision", details=reset)
        budget = budget_signal(snapshot, events, self.repository)
        if budget and budget["signal"] == "BUDGET_100":
            raise RuntimeFailure("BUDGET_100", "Run budget is exhausted; no new worker dispatches", details=budget)
        primary = snapshot["focus"].get("primaryCriterion")
        if primary:
            stall = primary_criterion_status(snapshot, events, self.repository)
            bound = primary["id"] in snapshot_task["acceptanceCriteria"]
            if stall and bound and stall["loopCapped"]:
                escalation = primary_stalled_escalation(stall)
                raise RuntimeFailure(escalation["code"], escalation["message"], details=escalation)
            if stall and not bound and stall["stalled"]:
                escalation = stalled_primary_escalation(stall)
                raise RuntimeFailure(escalation["code"], escalation["message"], details=stall)
        if TARGET_OPERATIONS.intersection(snapshot_task.get("operations") or []):
            identity = snapshot.get("targetIdentity")
            if (
                not isinstance(identity, dict)
                or identity.get("status") != "VERIFIED"
                or identity.get("taskId") != task_id
                or identity.get("verifiedRevision") != snapshot["revision"]
            ):
                raise RuntimeFailure("TARGET_IDENTITY_REQUIRED", "launch/test/install requires current task-bound target identity")
            checkpoint = next(
                (
                    item
                    for item in snapshot["externalCheckpoints"]
                    if item["id"] == identity.get("checkpointId")
                ),
                None,
            )
            intended = snapshot_task.get("targetIdentity")
            if checkpoint is None or not isinstance(intended, dict):
                raise RuntimeFailure("TARGET_IDENTITY_REQUIRED", "verified target checkpoint is unavailable")
            executor, trusted_target = self._trusted_exact_target_executor(checkpoint, intended)
            binding = {
                "runId": run_id,
                "objectiveVersion": snapshot["objective"]["version"],
                "revision": snapshot["revision"],
                "taskId": task_id,
                "checkpointId": checkpoint["id"],
                "checkpointType": checkpoint["type"],
                "provider": checkpoint["provider"],
                "principal": checkpoint["principal"],
                "challengeHash": checkpoint["challengeHash"],
            }
            result = self._invoke_exact_target_executor(
                executor,
                {
                    "schema": EXACT_TARGET_REQUEST_SCHEMA,
                    "binding": binding,
                    "intended": intended,
                    "target": {
                        "transport": trusted_target["transport"],
                        "artifactPath": trusted_target["artifactPath"],
                        "workspaceMode": trusted_target["workspaceMode"],
                        "ssh": trusted_target["ssh"],
                        "reconciliation": trusted_target.get("reconciliation"),
                    },
                },
            )
            if result["observed"] != intended:
                raise RuntimeFailure("TARGET_IDENTITY_MISMATCH", "trusted executor observed a different target identity")
            preflight_revision = snapshot["revision"]
            preflight_observation = result["observation"]

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
            reset = feasibility_status(state, task)
            if reset and (reset["expired"] or reset["decision"] not in {"CONTINUE", "BOUNDED_GO"}):
                raise RuntimeFailure("FEASIBILITY_STOP", "lane reset prevents dispatch", details=reset)
            loop = task.get("loop")
            if loop and loop.get("stopped"):
                raise RuntimeFailure("REPEATED_FAILURE", "same failure twice without new evidence; this lane is stopped")
            if task["attempts"]:
                if retry_evidence:
                    require_evidence_refs(state, retry_evidence, allowed={"artifact", "gate"})
                evidence_changed = loop and loop["evidence"] != retry_evidence_digest(state, task, self.repository)
                if loop is None:
                    history = self._read_events(self.run_dir(run_id))
                    last_start = max((event["sequence"] for event in history
                                      if event["type"] == "task.started" and event.get("taskId") == task_id), default=0)
                    evidence_changed = any(
                        event["sequence"] > last_start and (
                            event["type"] == "external.wait_resolved"
                            and event["payload"].get("resumeTask") == task_id
                            or event["type"] == "mutation.reconciled"
                            and event.get("taskId") == task_id
                            and event["payload"].get("result") == "not-applied"
                        )
                        for event in history
                    )
                hypothesis_changed = bool(retry_hypothesis and retry_hypothesis.strip()
                                          and retry_hypothesis.strip() != (loop or {}).get("hypothesis"))
                if not evidence_changed and not hypothesis_changed:
                    raise RuntimeFailure("RETRY_REASON_REQUIRED", "a retry needs a new hypothesis or registered evidence")
                task["retryHypothesis"] = retry_hypothesis.strip() if retry_hypothesis else None
            if task.get("objectiveVersion", state["objective"]["version"]) != state["objective"]["version"]:
                raise RuntimeFailure("OBJECTIVE_SUPERSEDED", "task belongs to a superseded objective")
            if task.get("lane", "product") not in {item["id"] for item in state["lanes"]["active"]}:
                raise RuntimeFailure("LANE_DEFERRED", "task lane is not active")
            if task["status"] != "READY":
                raise RuntimeFailure("TASK_NOT_READY", f"task {task_id} is {task['status']}")
            if task_has_pending_checkpoint(state, task_id):
                raise RuntimeFailure("EXTERNAL_CHECKPOINT_PENDING", "task still has an unresolved external checkpoint")
            if TARGET_OPERATIONS.intersection(task.get("operations") or []):
                if preflight_revision != state["revision"] or preflight_observation is None:
                    raise RuntimeFailure("TARGET_IDENTITY_STALE", "target observation became stale before task start")
                identity = state.get("targetIdentity")
                if not identity or identity.get("status") != "VERIFIED":
                    raise RuntimeFailure("TARGET_IDENTITY_REQUIRED", "launch/test/install requires verified target identity")
                if identity.get("taskId") != task["id"]:
                    raise RuntimeFailure("TARGET_IDENTITY_REQUIRED", "verified target identity belongs to another task")
                if identity.get("verifiedRevision") != state["revision"]:
                    raise RuntimeFailure("TARGET_IDENTITY_STALE", "verified target identity is stale after an intervening Run transition")
                expected_identity = task.get("targetIdentity") or {}
                mismatches = {
                    key: {"expected": value, "actual": identity["observed"].get(key)}
                    for key, value in expected_identity.items()
                    if identity["observed"].get(key) != value
                }
                if mismatches:
                    raise RuntimeFailure("TARGET_IDENTITY_MISMATCH", "task target does not match verified identity", details=mismatches)
                artifact_path_value = identity.get("artifactPath")
                if identity.get("transport") == "local" and artifact_path_value:
                    artifact_path = Path(str(artifact_path_value))
                    try:
                        artifact_info = artifact_path.lstat()
                    except OSError as exc:
                        raise RuntimeFailure("TARGET_IDENTITY_STALE", "verified target artifact is unavailable") from exc
                    if (
                        not artifact_path.is_absolute()
                        or not stat.S_ISREG(artifact_info.st_mode)
                        or artifact_path.is_symlink()
                        or _is_reparse_point(artifact_info)
                        or sha256_file(artifact_path) != expected_identity.get("sha256")
                    ):
                        raise RuntimeFailure("TARGET_IDENTITY_STALE", "verified target artifact changed after attestation")
            if task["attempts"] >= task["retryPolicy"]["maxAttempts"]:
                raise RuntimeFailure("RETRY_EXHAUSTED", f"task {task_id} exhausted its retry policy")
            if task.get("retryNotBefore") and parse_iso(task["retryNotBefore"]) > dt.datetime.now(dt.timezone.utc):
                raise RuntimeFailure(
                    "RETRY_BACKOFF",
                    f"task {task_id} is within its declared retry backoff window",
                    details={"retryNotBefore": task["retryNotBefore"]},
                )
            max_parallel = min(3, int((repository_config(str(self.repository)).get("workers") or {}).get("maxParallel", 3)))
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
            admitted_budget = effective_work_budget(state, task) if reset else None
            if reset:
                lease_seconds_bound = min(lease_seconds, admitted_budget["timeoutSeconds"])
            else:
                lease_seconds_bound = lease_seconds
            expires = acquired + dt.timedelta(seconds=max(1, lease_seconds_bound))
            task["lease"] = {
                "owner": worker_id,
                "acquiredAt": acquired.isoformat(timespec="seconds").replace("+00:00", "Z"),
                "expiresAt": expires.isoformat(timespec="seconds").replace("+00:00", "Z"),
            }
            task["attempts"] += 1
            task["status"] = "RUNNING"
            worker = next((item for item in state["workers"] if item["id"] == worker_id), None)
            if worker is None:
                adapter = "shell" if task["workerProfile"] == "shell" else "native"
                state["workers"].append(
                    {
                        "id": worker_id,
                        "adapter": adapter,
                        "status": "RUNNING",
                        "workspace": task["workspace"],
                        "mutablePaths": task["mutablePaths"],
                        "taskId": task_id,
                    }
                )
            else:
                if worker["status"] == "RUNNING":
                    raise RuntimeFailure("WORKER_BUSY", f"worker is already running: {worker_id}")
                worker["status"] = "RUNNING"
                worker["workspace"] = task["workspace"]
                worker["mutablePaths"] = task["mutablePaths"]
                worker["taskId"] = task_id
            worker = next(item for item in state["workers"] if item["id"] == worker_id)
            if admitted_budget is not None:
                worker["admittedBudget"] = admitted_budget
            else:
                worker.pop("admittedBudget", None)
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

    def _apply_task_retry_or_terminate(self, state: dict[str, Any], task: dict[str, Any], reason: str,
                                     *, failure_cause: Any = None) -> None:
        """Honor a task's declared retryPolicy on failure instead of always terminating it.

        A failure is retried (task returns to READY/NOT_READY, subject to backoffSeconds) only
        when attempts remain and the reason is retryable (an empty `retryable` list means every
        reason is retryable, matching the permissive default already produced by add_task).
        Otherwise the task becomes terminally FAILED, exactly as before this fix.
        """
        policy = task["retryPolicy"]
        fingerprint = sha256_value(redact(failure_cause if failure_cause is not None else reason))
        evidence = retry_evidence_digest(state, task, self.repository)
        previous = task.get("loop") or {}
        repeated = previous.get("fingerprint") == fingerprint and previous.get("evidence") == evidence
        task["loop"] = {
            "fingerprint": fingerprint, "evidence": evidence,
            "count": previous.get("count", 0) + 1 if repeated else 1,
            "hypothesis": task.pop("retryHypothesis", None),
            "stopped": repeated and previous.get("count", 0) >= 1,
        }
        if task["loop"]["stopped"]:
            task["status"] = "FAILED"
            task["retryNotBefore"] = None
            return
        retryable = not policy["retryable"] or reason in policy["retryable"]
        if retryable and task["attempts"] < policy["maxAttempts"]:
            task["status"] = ("WAITING_EXTERNAL" if task_has_pending_checkpoint(state, task["id"])
                              else "READY" if dependencies_completed(state, task) else "NOT_READY")
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
        native_ticket: NativeWorkerTicket | None = None,
        failure_cause: Any = None,
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
            if worker["adapter"] == "native":
                self._require_native_ticket(native_ticket, state, task)
            worker["status"] = status
            task["lease"] = None
            if status == "FAILED":
                if task["sideEffect"] and task["sideEffect"]["state"] == "PENDING":
                    task["sideEffect"]["state"] = "UNCERTAIN"
                    task["status"] = "WAITING_RESOURCE"
                    append_checkpoint(state, task_id, "SIDE_EFFECT_AMBIGUITY")
                else:
                    self._apply_task_retry_or_terminate(state, task, "WORKER_FAILURE", failure_cause=failure_cause)
            else:
                task["status"] = "WAITING_RESOURCE"
                append_checkpoint(state, task_id, "WORKER_COMPLETION")
            state["status"] = derive_run_status(state)
            return {
                "taskId": task_id,
                "workerId": worker_id,
                "candidateStatus": status,
                "taskStatus": task["status"],
                "reason": (canonical_json(redact(failure_cause))[:2000] if failure_cause is not None
                           else "worker reported failure; executor cause unavailable") if status == "FAILED" else "candidate only",
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
            self.assert_gate_sources_current(state, evidence_refs)
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
            close_task_workers(state, task, reason)
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

    def _require_native_ticket(
        self, ticket: NativeWorkerTicket | None, state: dict[str, Any], task: dict[str, Any],
        *, allow_expired_failure: bool = False,
    ) -> None:
        if (
            not isinstance(ticket, NativeWorkerTicket)
            or ticket.issuer is not self.__native_issuer
            or ticket.consumed
        ):
            raise RuntimeFailure("NATIVE_RESULT_UNTRUSTED", "native results require a live host-owned bridge invocation")
        binding = ticket.binding
        lease = task.get("lease")
        revision_safe = state["revision"] == binding["revision"]
        if not revision_safe:
            # Only authenticated, task-scoped sibling lifecycle changes commute.
            # Policy/checkpoints/source and the owned task still bind the ticket.
            changes = [event for event in self._read_events(self.run_dir(state["runId"]))
                       if event["sequence"] > binding["revision"] + 1]
            revision_safe = bool(changes) and all(
                event.get("taskId") not in {None, task["id"]}
                and event["type"] in {
                    "workspace.created", "workspace.assigned", "task.started",
                    "worker.admitted", "worker.finished", "artifact.recorded",
                    "workspace.collected", "task.completed",
                }
                for event in changes
            )
        if (
            state["runId"] != binding["runId"]
            or state["objective"]["version"] != binding["objectiveVersion"]
            or not revision_safe
            or sha256_value({"policy": state["policy"], "autonomy": state["autonomy"],
                             "objective": state["objective"], "task": task,
                             "pending": [item for item in state["externalCheckpoints"] if item["status"] == "PENDING"]})
            != ticket.snapshot["authority"]
            or task["id"] != binding["taskId"]
            or task["workPacket"]["workPacketId"] != binding["workPacketId"]
            or task["status"] != "RUNNING"
            or not lease
            or lease["owner"] != binding["workerId"]
            or lease["acquiredAt"] != binding["acquiredAt"]
            or (not allow_expired_failure and parse_iso(lease["expiresAt"]) <= dt.datetime.now(dt.timezone.utc))
        ):
            raise RuntimeFailure("NATIVE_RESULT_STALE", "native objective/revision/lease binding is stale or replayed")

    def begin_native_worker(self, run_id: str, task_id: str, *, host_owner: str,
                            retry_hypothesis: str | None = None,
                            owner_handle: str | None = None) -> NativeWorkerTicket:
        """Admit one bounded task before the bridge invokes the current host."""
        from worker_adapters import git_status, ignored_fingerprint, workspace_fingerprint
        from workspaces import WorkspaceManager

        state = self.load(run_id)
        task = find_task(state, task_id)
        if task.get("loop", {}).get("stopped"):
            raise RuntimeFailure("REPEATED_FAILURE", "native admission cannot bypass a repeated-failure stop")
        if task["workerProfile"] not in {"native", "copilot", "claude", "codex"}:
            raise RuntimeFailure("NATIVE_PROFILE_REQUIRED", "task is not a native agent WorkPacket")
        if task["sideEffect"] is not None:
            raise RuntimeFailure("NATIVE_SIDE_EFFECT_DENIED", "native candidates cannot execute registered side effects")
        if task["workPacket"].get("execution"):
            raise RuntimeFailure("NATIVE_EXECUTION_DENIED", "agent WorkPackets cannot carry shell execution recipes")
        packet = task["workPacket"]
        effective_work_budget(state, task)
        if (
            packet["mutablePaths"] != task["mutablePaths"]
            or packet["acceptanceCriteria"] != task["acceptanceCriteria"]
            or packet["risk"] != task["risk"]
            or not 1 <= packet["budget"]["timeoutSeconds"] <= 3600
            or not 1 <= packet["budget"]["maxOutputBytes"] <= 1024 * 1024
            or not 1 <= packet["budget"].get("maxTurns", 12) <= 100
        ):
            raise RuntimeFailure("NATIVE_PACKET_INVALID", "native WorkPacket scope/criteria/risk/budget must match its canonical task")
        if not host_owner or len(host_owner) > 256:
            raise RuntimeFailure("NATIVE_OWNER_REQUIRED", "a live host owner handle is required")
        if owner_handle and not any(
            worker.get("nativeBinding", {}).get("hostTaskId") == owner_handle
            and worker["taskId"] == task_id
            and worker["nativeBinding"]["owner"] == host_owner
            and worker["nativeBinding"]["objectiveVersion"] == state["objective"]["version"]
            for worker in state["workers"]
        ):
            raise RuntimeFailure("NATIVE_OWNER_TASK_MISMATCH", "retained owner must already belong to this task and objective")
        packet_budget = budget_signal(state, self.events(run_id), self.repository)
        if packet_budget and packet_budget["signal"] == "BUDGET_100":
            raise RuntimeFailure("BUDGET_100", "budget exhausted; no new native workspace or child")
        if not task.get("workspace"):
            WorkspaceManager(self.repository).create(run_id, task_id)
            task = find_task(self.load(run_id), task_id)
        workspace = Path(task["workspace"]).resolve()
        if workspace == self.repository or not workspace.is_dir() or git_status(workspace):
            raise RuntimeFailure("WORKSPACE_NOT_ISOLATED", "native admission requires a clean isolated worktree")
        snapshot = {
            "workspace": str(workspace),
            "head": run_command(["git", "rev-parse", "HEAD"], workspace),
            "ignored": ignored_fingerprint(workspace),
        }
        worker_id = f"native-{uuid.uuid4().hex}"
        state = self.start_task(
            run_id, task_id, worker_id=worker_id,
            lease_seconds=task["workPacket"]["budget"]["timeoutSeconds"], actor="native-host",
            retry_hypothesis=retry_hypothesis,
        )
        snapshot["source"] = workspace_fingerprint(self.repository)
        task = find_task(state, task_id)
        worker = next(item for item in state["workers"] if item["id"] == worker_id)
        snapshot["budget"] = copy.deepcopy(worker.get("admittedBudget", task["workPacket"]["budget"]))
        snapshot["authority"] = sha256_value({
            "policy": state["policy"], "autonomy": state["autonomy"],
            "objective": state["objective"], "task": task,
            "pending": [item for item in state["externalCheckpoints"] if item["status"] == "PENDING"],
        })
        binding = {
            "runId": run_id, "taskId": task_id, "workerId": worker_id,
            "workPacketId": task["workPacket"]["workPacketId"],
            "objectiveVersion": state["objective"]["version"], "revision": state["revision"],
            "acquiredAt": task["lease"]["acquiredAt"], "owner": host_owner, "hostTaskId": None,
        }
        return NativeWorkerTicket(self.__native_issuer, binding, snapshot)

    def bind_native_owner(self, ticket: NativeWorkerTicket, host_task_id: str) -> dict[str, Any]:
        if not isinstance(host_task_id, str) or not host_task_id or len(host_task_id) > 256:
            raise RuntimeFailure("NATIVE_OWNER_REQUIRED", "host did not admit an agent task")
        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            task = find_task(state, ticket.binding["taskId"])
            self._require_native_ticket(ticket, state, task, allow_expired_failure=True)
            if ticket.binding["hostTaskId"] is not None:
                raise RuntimeFailure("NATIVE_RESULT_STALE", "native owner is already bound")
            worker = next(item for item in state["workers"] if item["id"] == ticket.binding["workerId"])
            worker["nativeBinding"] = {**ticket.binding, "hostTaskId": host_task_id, "revision": state["revision"] + 1}
            return {"workerId": worker["id"], "hostTaskId": host_task_id}
        state = self._transaction(
            ticket.binding["runId"], mutate, event_type="worker.admitted", actor="native-host",
            task_id=ticket.binding["taskId"],
        )
        ticket.binding["hostTaskId"] = host_task_id
        ticket.binding["revision"] = state["revision"]
        return state

    def accept_native_candidate(
        self, ticket: NativeWorkerTicket, *, host_task_id: str, host_status: str, text: str,
        host_observation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Accept only a result independently observed on the joined host RPC connection."""
        from worker_adapters import git_status, ignored_fingerprint, path_allowed, workspace_fingerprint

        if not isinstance(ticket, NativeWorkerTicket):
            raise RuntimeFailure("NATIVE_RESULT_UNTRUSTED", "serialized native results are not accepted")
        state = self.load(ticket.binding["runId"])
        task = find_task(state, ticket.binding["taskId"])
        self._require_native_ticket(ticket, state, task, allow_expired_failure=host_status == "cancelled")
        if host_task_id != ticket.binding["hostTaskId"] or host_status not in {"completed", "idle", "failed", "cancelled"}:
            raise RuntimeFailure("NATIVE_RESULT_UNTRUSTED", "result does not match the admitted host task")
        workspace = Path(ticket.snapshot["workspace"])
        changed = sorted(git_status(workspace))
        errors = []
        if host_status in {"failed", "cancelled"}:
            errors.append(f"host worker {host_status}")
        if any(not path_allowed(path, task["mutablePaths"]) for path in changed):
            errors.append("worker changed paths outside its WorkPacket")
        if run_command(["git", "rev-parse", "HEAD"], workspace) != ticket.snapshot["head"]:
            errors.append("worker changed workspace history")
        if ignored_fingerprint(workspace) != ticket.snapshot["ignored"]:
            errors.append("worker changed ignored files")
        if workspace_fingerprint(self.repository) != ticket.snapshot["source"]:
            errors.append("worker changed the coordinator workspace")
        limit = min(ticket.snapshot["budget"]["maxOutputBytes"], 8192)
        bounded = text.encode("utf-8")[:limit].decode("utf-8", "ignore")
        artifact_id = f"native-result-{uuid.uuid4().hex}"
        path = self.run_dir(state["runId"]) / "workers" / f"{artifact_id}.json"
        result = {
            "schema": "architrave.native-candidate.v1", "binding": ticket.binding,
            "status": "failed" if errors else "candidate", "observedHostStatus": host_status,
            "summary": redact(bounded), "truncated": len(text.encode("utf-8")) > limit,
            "changedPaths": changed, "errors": errors, "observedAt": utc_now(),
            "hostObservation": redact(host_observation or {}),
        }
        self._atomic_write(path, result)
        def mutate(current: dict[str, Any]) -> dict[str, Any]:
            current_task = find_task(current, task["id"])
            self._require_native_ticket(ticket, current, current_task, allow_expired_failure=host_status == "cancelled")
            worker = next(item for item in current["workers"] if item["id"] == ticket.binding["workerId"])
            worker["status"] = "FAILED" if errors else "FINISHED"
            worker["finishedAt"] = utc_now()
            worker["reason"] = "; ".join(errors) or "candidate only"
            current_task["lease"] = None
            if errors:
                self._apply_task_retry_or_terminate(
                    current, current_task, "WORKER_FAILURE",
                    failure_cause={"hostStatus": host_status, "errors": errors,
                                   "budgetStop": (host_observation or {}).get("budgetStop")},
                )
            else:
                current_task["status"] = "WAITING_RESOURCE"
                append_checkpoint(current, task["id"], "WORKER_COMPLETION")
            artifact = {
                "id": artifact_id, "kind": "worker-result", "producer": "worker",
                "path": path.relative_to(self.repository).as_posix(), "createdAt": utc_now(),
                "sha256": sha256_file(path), "evidenceRefs": [f"task:{task['id']}"],
                "consumedByTask": None,
            }
            artifact["attestation"] = self._artifact_attestation(artifact)
            current["artifacts"].append(artifact)
            current["status"] = derive_run_status(current)
            return {
                "workerId": worker["id"], "hostTaskId": host_task_id, "candidateStatus": result["status"],
                "reason": canonical_json(redact({
                    "hostStatus": host_status, "errors": errors,
                    "budgetStop": (host_observation or {}).get("budgetStop"),
                }))[:2000] if errors else "candidate only",
            }
        try:
            self._transaction(
                state["runId"], mutate, event_type="worker.finished", actor="native-host",
                task_id=task["id"],
            )
        except RuntimeFailure:
            path.unlink(missing_ok=True)
            raise
        ticket.consumed = True
        return {**result, "artifactRef": f"artifact:{artifact_id}"}

    def _semantic_authority(self, state: dict[str, Any], task: dict[str, Any]) -> str:
        scope = {key: value for key, value in task.items()
                 if key not in {"status", "attempts", "lease", "retryNotBefore", "retryHypothesis", "loop"}}
        return sha256_value({
            "policy": state["policy"], "autonomy": state["autonomy"],
            "objective": state["objective"], "task": scope,
            "pending": [item for item in state["externalCheckpoints"] if item["status"] == "PENDING"],
        })

    def _native_review_storage(self, run_id: str) -> Path:
        current = self.repository
        for part in (".architrave", "runs", require_id(run_id, "run id"), "workers"):
            current = current / part
            try:
                info = current.lstat()
            except FileNotFoundError:
                continue
            if not stat.S_ISDIR(info.st_mode) or current.is_symlink() or _is_reparse_point(info):
                raise RuntimeFailure("SEMANTIC_STORAGE_UNSAFE", "native review storage must use real in-repository directories")
        return current

    def prepare_native_semantic_review(
        self, run_id: str, task_id: str, *, host_owner: str, invocation_id: str, reviewer: str,
    ) -> tuple[NativeSemanticTicket, str]:
        """Only the installed joined bridge executes this producer, never an imported report."""
        from worker_adapters import git_status, workspace_fingerprint

        if reviewer not in {"code-review", "rubber-duck"}:
            raise RuntimeFailure("SEMANTIC_REVIEWER_UNSUPPORTED", "a supported independent review role is required")
        require_id(host_owner, "joined owner")
        require_id(invocation_id, "host invocation")
        state = self.load(run_id)
        self._assert_repository_baseline(state)
        self._native_review_storage(run_id)
        task = find_task(state, task_id)
        if task["objectiveVersion"] != state["objective"]["version"] or task["status"] in {"DEFERRED", "CANCELLED", "FAILED", "RUNNING"}:
            raise RuntimeFailure("SEMANTIC_SCOPE_INVALID", "review must bind a current, stable task")
        if git_status(self.repository):
            raise RuntimeFailure("SEMANTIC_SOURCE_UNFROZEN", "commit the review subject before native semantic execution")
        budget = effective_work_budget(state, task)
        signal = budget_signal(state, self.events(run_id), self.repository)
        if signal and signal["signal"] == "BUDGET_100":
            raise RuntimeFailure("BUDGET_100", "budget exhausted; no native semantic model invocation")
        source = {"commit": state["baseline"]["commit"],
                  "sha256": workspace_fingerprint(self.repository, include_ignored=False)}
        source_files, review_scope = native_source_inventory(self.repository)
        for artifact in state["artifacts"]:
            if artifact["producer"] != "semantic-judge":
                continue
            prior = self._read_json_receipt(artifact["path"], "semantic")
            binding = prior.get("binding") or {}
            if (prior.get("schema") == "architrave.native-semantic-review.v1"
                    and binding.get("taskId") == task_id and binding.get("source") == source
                    and binding.get("objectiveVersion") == state["objective"]["version"]
                    and binding.get("authority") == self._semantic_authority(state, task)
                    and binding.get("role") == reviewer):
                raise RuntimeFailure("SEMANTIC_ALREADY_OBSERVED", "this role already reviewed the frozen subject; new source/evidence is required")
        challenge = secrets.token_hex(32)
        now = dt.datetime.now(dt.timezone.utc)
        binding = {
            "runId": run_id, "taskId": task_id, "criteria": list(task["acceptanceCriteria"]),
            "objectiveVersion": state["objective"]["version"], "revision": state["revision"],
            "source": source, "authority": self._semantic_authority(state, task),
            "owner": host_owner, "invocationId": invocation_id, "role": reviewer,
            "hostTaskId": None, "challengeHash": sha256_value(challenge),
            "preparedAt": now.isoformat(), "expiresAt": (now + dt.timedelta(seconds=budget["timeoutSeconds"])).isoformat(),
            "reviewScope": review_scope,
        }
        instructions = {
            "scope": str(self.repository), "source": source, "criteria": binding["criteria"],
            "objective": state["objective"]["description"], "task": task["objective"],
            "challenge": challenge,
            "reviewScope": review_scope,
        }
        prompt = (
            "Independently review the FULL frozen IMPLEMENTATION SOURCE, not a previous report. "
            "The declared reviewScope explicitly excludes canonical/private control-plane history and trust metadata; "
            "do not claim tracked-repository/history/Run acceptance. Retain that uncovered category in your summary. "
            "Read repository instructions, "
            "Cover every implementation area named in the task. Use bounded view_range sections for large files; "
            "a truncated first view is not full inspection. Uninspected required source must yield REVISE, not PASS. "
            "Your summary must identify inspected implementation areas and required coverage gaps; "
            "uninspected governing or load-bearing baseline is not a FULL implementation-source PASS. "
            "architrave.config.json, governing sources and gates/rubric.md. Grade source and observed deterministic "
            "evidence; publication/family receipt admission is the host qualifier's responsibility, not a circular "
            "condition for your source verdict. Use the configured profile; do not invent product acceptance. "
            "READ ONLY: only view of tracked regular source files and source-inventory-bounded rg are permitted. "
            "No recursive glob or directory view; use the supplied source inventory and absolute paths. "
            "No shell/execute, private .git/.architrave reads, file/history/Run/policy changes, scratch files, "
            "agent spawning, control-plane tools, provider SDK or agent CLI. The trusted executor has already "
            "bound the exact source commit/hash; do not execute git to rediscover it. "
            "Do not rerun unrelated full suites. Return only ONE JSON object with exactly "
            "these keys: verdict (PASS|REVISE|FAIL), criteria (the supplied IDs), sourceCommit, sourceSha256, "
            "challenge (the supplied nonce), summary (nonempty, <=1600 characters), findings (<=12 objects, "
            "each exactly severity (blocker|major|minor), path (repository-relative), message (<=800 characters)). "
            "PASS cannot contain blocker/major findings. Put uncovered verification/publication phases in summary; "
            "do not guess model/family or put model fields in your report. Keep output within "
            f"{budget['maxOutputBytes']} UTF-8 bytes. High semantic effort is requested only within host-supported "
            "defaults; no per-task reasoning override is available. Bound subject:\n" + canonical_json(redact(instructions))
        )
        ticket = NativeSemanticTicket(self.__semantic_issuer, binding, challenge, budget)
        ticket.source_files = source_files
        return ticket, prompt

    def bind_native_semantic_owner(self, ticket: NativeSemanticTicket, host_task_id: str) -> None:
        if (not isinstance(ticket, NativeSemanticTicket) or ticket.issuer is not self.__semantic_issuer
                or ticket.consumed or ticket.binding["hostTaskId"] is not None):
            raise RuntimeFailure("SEMANTIC_RESULT_UNTRUSTED", "a live, unbound joined review invocation is required")
        require_id(host_task_id, "admitted reviewer")
        ticket.binding["hostTaskId"] = host_task_id

    def _assert_native_semantic_receipt(
        self, state: dict[str, Any], artifact: dict[str, Any], receipt: dict[str, Any],
        task_id: str | None, criteria: Sequence[str], family: str, *, allow_consumed: bool = False,
    ) -> None:
        from worker_adapters import git_status, workspace_fingerprint

        binding = receipt.get("binding") or {}
        observed = receipt.get("completion") or {}
        task = find_task(state, str(binding.get("taskId", "")))
        source = {"commit": run_command(["git", "rev-parse", "HEAD"], self.repository),
                  "sha256": workspace_fingerprint(self.repository, include_ignored=False)}
        if (binding.get("runId") != state["runId"] or task_id != task["id"]
                or binding.get("objectiveVersion") != state["objective"]["version"]
                or task["objectiveVersion"] != state["objective"]["version"]
                or set(criteria) != set(binding.get("criteria") or [])
                or binding.get("source") != source or git_status(self.repository)
                or binding.get("reviewScope") != native_source_inventory(self.repository)[1]
                or binding.get("authority") != self._semantic_authority(state, task)):
            raise RuntimeFailure("SEMANTIC_SOURCE_STALE", "native semantic receipt no longer binds current scope/source/policy/holds")
        if (observed.get("agentId") != binding.get("hostTaskId")
                or observed.get("toolCallId") != binding.get("hostTaskId")
                or observed.get("agentName") != binding.get("role")
                or observed.get("type") != "subagent.completed" or observed.get("cancelled")
                or observed.get("ephemeral") or not observed.get("id")
                or native_review_family(observed.get("firstDispatchedModel")) != family
                or receipt.get("family") != family):
            raise RuntimeFailure("SEMANTIC_HOST_PROVENANCE", "native receipt owner/completion/actual-model provenance is invalid")
        if artifact["consumedByTask"] is not None and not (
                allow_consumed and artifact["consumedByTask"] == task_id):
            raise RuntimeFailure("EVIDENCE_REPLAY", "native semantic producer evidence was already consumed")

    def _native_semantic_gate_is_current(self, state: dict[str, Any], gate: dict[str, Any]) -> bool:
        refs = set(gate["evidenceRefs"])
        for artifact in state["artifacts"]:
            if f"artifact:{artifact['id']}" not in refs or artifact["producer"] != "semantic-judge":
                continue
            receipt = self._read_json_receipt(artifact["path"], "semantic")
            if receipt.get("schema") != "architrave.native-semantic-review.v1":
                continue
            try:
                self._assert_native_semantic_receipt(
                    state, artifact, receipt, gate["taskId"], gate["criteria"], gate["family"], allow_consumed=True,
                )
            except RuntimeFailure as exc:
                if exc.code == "SEMANTIC_SOURCE_STALE":
                    return False
                raise
        return True

    def accept_native_semantic_review(
        self, ticket: NativeSemanticTicket, *, host_task_id: str, host_status: str,
        text: str, completion: dict[str, Any],
    ) -> dict[str, Any]:
        """Trusted private transport completion, not a caller-labelled result or file importer."""
        from worker_adapters import workspace_fingerprint

        if (not isinstance(ticket, NativeSemanticTicket) or ticket.issuer is not self.__semantic_issuer
                or ticket.consumed):
            raise RuntimeFailure("SEMANTIC_RESULT_UNTRUSTED", "native semantic results require a live process-held invocation")
        ticket.consumed = True
        binding = ticket.binding
        state = self.load(binding["runId"])
        task = find_task(state, binding["taskId"])
        if (state["revision"] != binding["revision"] or parse_iso(binding["expiresAt"]) <= dt.datetime.now(dt.timezone.utc)
                or binding["hostTaskId"] != host_task_id or host_status not in {"idle", "completed"}):
            raise RuntimeFailure("SEMANTIC_RESULT_STALE", "review owner/revision/deadline is stale or replayed")
        if not isinstance(text, str) or len(text.encode("utf-8")) > ticket.budget["maxOutputBytes"]:
            raise RuntimeFailure("SEMANTIC_RESULT_INVALID", "review output exceeds its canonical bound")
        structured = text.strip()
        lines = structured.splitlines()
        if len(lines) >= 3 and lines[0] == "```json" and lines[-1] == "```":
            structured = "\n".join(lines[1:-1]).strip()
        try:
            report = json.loads(structured, object_pairs_hook=_reject_duplicate_json_keys)
        except (ValueError, json.JSONDecodeError) as exc:
            raise RuntimeFailure("SEMANTIC_RESULT_INVALID", "reviewer must return the requested structured JSON") from exc
        fields = {"verdict", "criteria", "sourceCommit", "sourceSha256", "challenge", "summary", "findings"}
        if (not isinstance(report, dict) or set(report) != fields
                or report["verdict"] not in {"PASS", "REVISE", "FAIL"}
                or report["criteria"] != binding["criteria"] or report["challenge"] != ticket.challenge
                or report["sourceCommit"] != binding["source"]["commit"]
                or report["sourceSha256"] != binding["source"]["sha256"]
                or not isinstance(report["summary"], str) or not report["summary"].strip() or len(report["summary"]) > 1600
                or not isinstance(report["findings"], list) or len(report["findings"]) > 12):
            raise RuntimeFailure("SEMANTIC_RESULT_INVALID", "review scope/challenge/verdict shape is invalid")
        for finding in report["findings"]:
            if (not isinstance(finding, dict) or set(finding) != {"severity", "path", "message"}
                    or finding["severity"] not in {"blocker", "major", "minor"} or not isinstance(finding["path"], str)
                    or not isinstance(finding["message"], str) or not finding["message"].strip() or len(finding["message"]) > 800):
                raise RuntimeFailure("SEMANTIC_RESULT_INVALID", "review finding is malformed")
            path = safe_relative_path(finding["path"], "review finding path")
            if path not in ticket.source_files:
                raise RuntimeFailure("SEMANTIC_RESULT_INVALID", "review finding must belong to the declared implementation inventory")
            finding["path"] = path
            if report["verdict"] == "PASS" and finding["severity"] in {"blocker", "major"}:
                raise RuntimeFailure("SEMANTIC_RESULT_INVALID", "PASS contradicts blocking findings")
        if (not isinstance(completion, dict) or not isinstance(completion.get("timestamp"), str)
                or parse_iso(completion["timestamp"]) < parse_iso(binding["preparedAt"])
                or parse_iso(completion["timestamp"]) > dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=5)
                or parse_iso(completion["timestamp"]) > parse_iso(binding["expiresAt"])):
            raise RuntimeFailure("SEMANTIC_HOST_PROVENANCE", "completion is outside the live review interval")
        family = native_review_family(completion.get("firstDispatchedModel"))
        artifact = {"consumedByTask": None}
        receipt = {
            "schema": "architrave.native-semantic-review.v1", "verdict": report["verdict"],
            "family": family, "reviewer": "host-native", "criteria": binding["criteria"],
            "binding": binding, "completion": completion, "report": redact({
                "summary": report["summary"], "findings": report["findings"],
            }), "resultSha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "observedAt": utc_now(), "effort": {"requested": "high", "effective": None},
        }
        self._assert_native_semantic_receipt(state, artifact, receipt, task["id"], binding["criteria"], family)
        if workspace_fingerprint(self.repository, include_ignored=False) != binding["source"]["sha256"]:
            raise RuntimeFailure("SEMANTIC_SOURCE_STALE", "reviewed source changed before receipt creation")
        artifact_id = f"native-semantic-{uuid.uuid4().hex}"
        path = self._native_review_storage(state["runId"]) / f"{artifact_id}.json"
        self._atomic_write(path, receipt)
        ticket.receipt_sha256 = sha256_file(path)
        artifact = {
            "id": artifact_id, "kind": "semantic-verdict", "producer": "semantic-judge",
            "path": path.relative_to(self.repository).as_posix(), "createdAt": utc_now(),
            "sha256": ticket.receipt_sha256, "evidenceRefs": [f"task:{task['id']}"], "consumedByTask": None,
        }
        status = {"PASS": "PASS", "REVISE": "BLOCKED", "FAIL": "FAIL"}[report["verdict"]]
        gate_id = f"semantic-{uuid.uuid4().hex}"
        try:
            self.record_gate(
                state["runId"], gate_id=gate_id, task_id=task["id"], gate_type="semantic", status=status,
                evidence_refs=[f"artifact:{artifact_id}"], family=family, criteria=binding["criteria"],
                reviewer="host-native", effort="high", actor="native-semantic-review",
                _native_receipt=(ticket, artifact),
            )
        except RuntimeFailure:
            path.unlink(missing_ok=True)
            raise
        finally:
            ticket.receipt_sha256 = None
        return {"status": status, "verdict": report["verdict"], "family": family,
                "artifactRef": f"artifact:{artifact_id}", "gateRef": f"gate:{gate_id}",
                "source": binding["source"], "hostTaskId": host_task_id,
                "completionEventId": completion["id"], "summary": receipt["report"]["summary"]}

    def recover_workers(self, run_id: str, *, task_id: str | None = None) -> dict[str, Any]:
        """Close orphan/expired records; an explicit failed task recovery never runs commands."""
        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            closed = []
            now = dt.datetime.now(dt.timezone.utc)
            for task in state["tasks"]:
                if task["status"] == "RUNNING" and (
                    not task.get("lease") or parse_iso(task["lease"]["expiresAt"]) <= now
                ):
                    close_task_workers(state, task, "lease expired")
                    task["lease"] = None
                    if task.get("sideEffect") and task["sideEffect"]["state"] in {"PENDING", "UNCERTAIN"}:
                        task["sideEffect"]["state"] = "UNCERTAIN"
                        task["status"] = "WAITING_RESOURCE"
                        append_checkpoint(state, task["id"], "SIDE_EFFECT_AMBIGUITY")
                    else:
                        task["status"] = "FAILED"
                    closed.append(task["id"])
            active = {task["lease"]["owner"] for task in state["tasks"]
                      if task["status"] == "RUNNING" and task.get("lease")}
            for worker in state["workers"]:
                if worker["status"] == "RUNNING" and worker["id"] not in active:
                    worker["status"] = "FAILED"
                    worker["finishedAt"] = utc_now()
                    worker["reason"] = "orphaned worker without active task lease"
            if task_id:
                if state["status"] in {"COMPLETED", "CANCELLED"}:
                    raise RuntimeFailure("RECOVERY_UNSAFE", "cannot revive a terminal Run")
                task = find_task(state, task_id)
                if task.get("loop", {}).get("stopped"):
                    raise RuntimeFailure("REPEATED_FAILURE", "recovery cannot bypass a repeated-failure stop")
                if task["status"] != "FAILED" or task.get("sideEffect") is not None:
                    raise RuntimeFailure("RECOVERY_UNSAFE", "explicit recovery requires a failed task with no side effect")
                if task["objectiveVersion"] != state["objective"]["version"]:
                    raise RuntimeFailure("OBJECTIVE_SUPERSEDED", "cannot recover a historical task")
                if any(gate["taskId"] == task_id and gate["status"] == "FAIL" for gate in state["gateResults"]):
                    raise RuntimeFailure("RECOVERY_GATE_FAILED", "a failed deterministic/product gate needs separate reconciliation")
                task["retryPolicy"]["maxAttempts"] = max(task["retryPolicy"]["maxAttempts"], task["attempts"] + 1)
                task["status"] = ("WAITING_EXTERNAL" if task_has_pending_checkpoint(state, task["id"])
                                  else "READY" if dependencies_completed(state, task) else "NOT_READY")
                task["retryNotBefore"] = None
                task["workspace"] = None
            if state["status"] not in {"COMPLETED", "CANCELLED"}:
                state["status"] = "RECOVERING"
                state["status"] = derive_run_status(state)
            return {"closedTasks": closed, "recoveredTask": task_id, "sideEffectsReplayed": False}
        return self._transaction(run_id, mutate, event_type="worker.recovered", actor="coordinator", task_id=task_id)

    def recover_native_checkpoint(self, run_id: str, checkpoint_id: str, *, host_owner: str) -> dict[str, Any]:
        """Withdraw an obsolete integration wait, not resolve human/product authority."""
        if not host_owner:
            raise RuntimeFailure("NATIVE_OWNER_REQUIRED", "live joined host required")
        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            checkpoint = next((item for item in state["externalCheckpoints"] if item["id"] == checkpoint_id), None)
            if (
                checkpoint is None or checkpoint_id != "native-adapter-required"
                or checkpoint["status"] != "PENDING"
                or checkpoint["type"] != "HUMAN_JUDGMENT_REQUIRED"
                or checkpoint.get("policyAmendment") is not None
                or checkpoint["objectiveVersion"] != state["objective"]["version"]
                or "native" not in checkpoint["reason"].lower()
                or "adapter" not in checkpoint["reason"].lower()
                or checkpoint["provider"] != "copilot-host"
                or "spawn agent CLIs forbidden by execution-policy" not in checkpoint["reason"]
                or "No package sign deploy launch auth grant." not in checkpoint["reason"]
            ):
                raise RuntimeFailure("RECOVERY_UNSAFE", "only the obsolete native-adapter integration wait can be withdrawn")
            task = find_task(state, checkpoint["taskId"])
            if (task.get("sideEffect") is not None or task.get("lease")
                or task["attempts"] != 0 or task.get("operations") or task.get("targetIdentity")
                or task["status"] != "WAITING_EXTERNAL"):
                raise RuntimeFailure("RECOVERY_UNSAFE", "integration recovery cannot bypass side-effect reconciliation")
            checkpoint["status"] = "CANCELLED"
            checkpoint["resolvedAt"] = utc_now()
            checkpoint["resolvedBy"] = "native-host"
            checkpoint["resolutionRef"] = None
            task["status"] = ("WAITING_EXTERNAL" if task_has_pending_checkpoint(state, task["id"])
                              else "READY" if dependencies_completed(state, task) else "NOT_READY")
            state["status"] = "RECOVERING"
            state["status"] = derive_run_status(state)
            return {"withdrawnCheckpoint": checkpoint_id, "owner": host_owner, "criteriaSatisfied": []}
        return self._transaction(run_id, mutate, event_type="worker.integration_recovered", actor="native-host")

    def execute_gate(
        self, run_id: str, task_id: str, *, recipe: str = "test", ci_run_id: int | None = None
    ) -> dict[str, Any]:
        """Run a configured deterministic gate; accept no caller-authored result or command."""
        from platform_launch import configured_shell_command, LaunchError
        from worker_adapters import command_for, git_status, run_bounded, workspace_fingerprint

        before = self.load(run_id)
        task = find_task(before, task_id)
        self._assert_repository_baseline(before)
        if task["objectiveVersion"] != before["objective"]["version"]:
            raise RuntimeFailure("OBJECTIVE_SUPERSEDED", "cannot gate a historical task")
        if task["status"] != "WAITING_RESOURCE":
            raise RuntimeFailure("GATE_NOT_READY", "gate execution requires a finished candidate")
        config = repository_config(str(self.repository))
        ci_environment = None
        gate_cwd = self.repository
        if recipe == "ci":
            if git_status(self.repository):
                raise RuntimeFailure("CI_SOURCE_DIRTY", "CI cannot verify staged, unstaged, or untracked local source")
            if not isinstance(ci_run_id, int) or isinstance(ci_run_id, bool) or ci_run_id <= 0:
                raise RuntimeFailure("CI_BINDING_REQUIRED", "CI observation requires an exact positive workflow Run id")
            remote = run_command(["git", "remote", "get-url", "origin"], self.repository)
            match = re.fullmatch(r"(?:https://|git@)([A-Za-z0-9.-]+)[/:]([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?", remote)
            if not match:
                raise RuntimeFailure("CI_SOURCE_UNSUPPORTED", "CI observation requires an exact GitHub origin")
            host, repository = match.groups()
            gh = shutil.which("gh")
            if not gh:
                raise RuntimeFailure("CI_EXECUTOR_REQUIRED", "installed GitHub CLI is required to observe CI")
            command = [gh, "run", "view", str(ci_run_id), "--repo", repository,
                       "--json", "databaseId,headSha,conclusion,status,url"]
            ci_environment = {name: value for name, value in os.environ.items()
                              if name not in {"GH_TOKEN", "GITHUB_TOKEN"}}
            ci_environment["GH_HOST"] = host
        elif recipe == "task":
            if task["workerProfile"] != "shell" or task.get("sideEffect") is not None:
                raise RuntimeFailure("GATE_RECIPE_DENIED", "task argv gates require a deterministic side-effect-free shell WorkPacket")
            command, gate_cwd = command_for("shell", task["workPacket"], self.repository)
        elif recipe == "quick":
            runner = Path(__file__).resolve().parents[1] / "gates" / "gate_runner.py"
            command = [sys.executable, str(runner), "checks", "--quick", "--repo", str(self.repository)]
        elif recipe in {"test", "build"} and isinstance(config.get(recipe), str) and config[recipe].strip():
            try:
                command = configured_shell_command(config[recipe])
            except LaunchError as exc:
                raise RuntimeFailure("GATE_RECIPE_DENIED", str(exc)) from exc
        else:
            raise RuntimeFailure("GATE_RECIPE_REQUIRED", "choose quick, CI, stored deterministic task argv, or configured build/test")
        source = workspace_fingerprint(self.repository, include_ignored=False)
        result = run_bounded(
            command, cwd=gate_cwd, environment=ci_environment or dict(os.environ),
            timeout_seconds=task["workPacket"]["budget"]["timeoutSeconds"],
            max_output_bytes=min(task["workPacket"]["budget"]["maxOutputBytes"], 8192),
        )
        after = self.load(run_id)
        if (
            after["revision"] != before["revision"]
            or after["objective"]["version"] != before["objective"]["version"]
            or workspace_fingerprint(self.repository, include_ignored=False) != source
            or (recipe == "ci" and git_status(self.repository))
        ):
            raise RuntimeFailure("GATE_RESULT_STALE", "Run or source changed during deterministic observation")
        passed = result["exitCode"] == 0 and not result["timedOut"]
        ci_observation = None
        if recipe == "ci" and passed:
            try:
                ci_observation = json.loads(result["stdout"])
            except ValueError as exc:
                raise RuntimeFailure("CI_RESULT_INVALID", "GitHub did not return a bounded workflow observation") from exc
            if (ci_observation.get("databaseId") != ci_run_id
                or ci_observation.get("headSha") != before["baseline"]["commit"]):
                raise RuntimeFailure("CI_SOURCE_MISMATCH", "CI Run does not belong to this exact source commit")
            if ci_observation.get("status") != "completed":
                raise RuntimeFailure("CI_PENDING", "CI is still running; no result has been registered", exit_code=2)
            passed = ci_observation.get("status") == "completed" and ci_observation.get("conclusion") == "success"
        gate_id = f"gate-{recipe}-{uuid.uuid4().hex}"
        receipt = {
            "schema": "architrave.deterministic-observation.v1",
            "binding": {"runId": run_id, "taskId": task_id, "objectiveVersion": before["objective"]["version"],
                        "revision": before["revision"], "criteria": task["acceptanceCriteria"], "risk": task["risk"]},
            "source": {"commit": before["baseline"]["commit"], "sha256": source, "scope": "git-visible-source"},
            "command": command, "cwd": str(gate_cwd), "recipe": recipe, "status": "pass" if passed else "fail",
            "observedAt": utc_now(), **redact(result),
            "ci": ci_observation,
        }
        path = self.run_dir(run_id) / "deterministic" / f"{gate_id}.json"
        self._atomic_write(path, receipt)
        self._record_artifact(
            run_id, artifact_id=gate_id, kind="deterministic-result",
            path=path.relative_to(self.repository).as_posix(), evidence_refs=[f"task:{task_id}"],
            actor="deterministic-executor", producer="deterministic",
        )
        artifact_ref = f"artifact:{gate_id}"
        self.record_gate(
            run_id, gate_id=gate_id, task_id=task_id, gate_type="deterministic",
            status="PASS" if passed else "FAIL", evidence_refs=[artifact_ref] if artifact_ref else [],
            criteria=task["acceptanceCriteria"], actor="deterministic-executor",
        )
        return {"gateRef": f"gate:{gate_id}", "artifactRef": artifact_ref,
                "status": "PASS" if passed else "FAIL", "exitCode": result["exitCode"],
                "source": receipt["source"], "observedAt": receipt["observedAt"]}

    def assert_gate_sources_current(self, state: dict[str, Any], references: Sequence[str]) -> None:
        from worker_adapters import workspace_fingerprint
        gate_ids = {ref.split(":", 1)[1] for ref in references if ref.startswith("gate:")}
        refs = {ref for gate in state["gateResults"] if gate["id"] in gate_ids for ref in gate["evidenceRefs"]}
        observed_source = None
        for artifact in state["artifacts"]:
            if f"artifact:{artifact['id']}" in refs and artifact["producer"] == "semantic-judge":
                receipt = self._read_json_receipt(artifact["path"], "semantic")
                if receipt.get("schema") == "architrave.native-semantic-review.v1":
                    for gate in state["gateResults"]:
                        if gate["id"] in gate_ids and f"artifact:{artifact['id']}" in gate["evidenceRefs"]:
                            self._assert_native_semantic_receipt(
                                state, artifact, receipt, gate["taskId"], gate["criteria"], gate["family"], allow_consumed=True,
                            )
            if f"artifact:{artifact['id']}" in refs and artifact["producer"] == "legibility":
                self._assert_product_binding(state, artifact, task_id=None, criteria=None)
            if f"artifact:{artifact['id']}" not in refs or artifact["producer"] != "deterministic":
                continue
            receipt = self._read_json_receipt(artifact["path"], "deterministic")
            if receipt.get("schema") != "architrave.deterministic-observation.v1":
                continue
            if observed_source is None:
                observed_source = workspace_fingerprint(self.repository, include_ignored=False)
            binding = receipt["binding"]
            task = find_task(state, binding["taskId"])
            if (
                binding["runId"] != state["runId"]
                or binding["objectiveVersion"] != state["objective"]["version"]
                or binding["risk"] != task["risk"]
                or binding["criteria"] != task["acceptanceCriteria"]
                or receipt["source"]["commit"] != state["baseline"]["commit"]
                or receipt["source"]["sha256"] != observed_source
            ):
                raise RuntimeFailure("EVIDENCE_SOURCE_STALE", "deterministic evidence no longer matches current source/objective/task/risk")

    def _assert_product_binding(self, state: dict[str, Any], artifact: dict[str, Any],
                                *, task_id: str | None, criteria: Sequence[str] | None) -> None:
        from worker_adapters import workspace_fingerprint
        receipt = self._read_json_receipt(artifact["path"], "product")
        if receipt.get("status") != "pass" or receipt.get("failed") != []:
            raise RuntimeFailure("LEGIBILITY_RECEIPT", "PASS requires a passing observed product receipt")
        binding = receipt.get("binding")
        if binding is None:
            return  # Historical receipts remain readable; milestone advancement rejects them.
        source = receipt.get("source", {})
        bound_task = find_task(state, binding["taskId"]) if binding.get("taskId") else None
        if (binding.get("runId") != state["runId"]
                or binding.get("objectiveVersion") != state["objective"]["version"]
                or bound_task and bound_task["objectiveVersion"] != state["objective"]["version"]
                or task_id is not None and binding.get("taskId") != task_id
                or criteria is not None and not set(criteria).issubset(binding.get("criteria", []))
                or source.get("commit") != run_command(["git", "rev-parse", "HEAD"], self.repository)
                or source.get("sha256") != workspace_fingerprint(self.repository, include_ignored=False)):
            raise RuntimeFailure("EVIDENCE_SOURCE_STALE", "frozen product receipt no longer binds current task/objective/source")

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
        reviewer: str | None = None,
        effort: str | None = None,
        actor: str = "coordinator",
        _native_receipt: tuple[NativeSemanticTicket, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        require_id(gate_id, "gate id")
        requested_level, _, effective_level = (effort or "").partition(":")
        if effort is not None and requested_level not in {"low", "default", "high"}:
            raise RuntimeFailure("INVALID_GATE", "effort must be low|default|high[:effective host mapping]")
        if gate_type not in {"deterministic", "e2e", "semantic", "reality", "policy", "security"}:
            raise RuntimeFailure("INVALID_GATE", f"invalid gate type: {gate_type}")
        if gate_type == "semantic":
            reviewer = reviewer or "architrave-judge"
            if reviewer not in {"host-native", "architrave-judge"}:
                raise RuntimeFailure("INVALID_GATE", "semantic reviewer must be host-native or architrave-judge")
        elif reviewer is not None:
            raise RuntimeFailure("INVALID_GATE", "only semantic gates record a reviewer kind")
        if family is not None and not ID_RE.fullmatch(family):
            raise RuntimeFailure("INVALID_GATE", f"invalid gate reviewer identity: {family}")
        if gate_type == "semantic" and family is None:
            raise RuntimeFailure("INVALID_GATE", "semantic gates require an independent reviewer identity")
        if gate_type == "security" and family not in {None, "security"}:
            raise RuntimeFailure("INVALID_GATE", "security gate family must be security")
        if status not in {"PASS", "FAIL", "BLOCKED", "SKIPPED"}:
            raise RuntimeFailure("INVALID_GATE", f"invalid gate status: {status}")

        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            if _native_receipt is not None:
                ticket, artifact = _native_receipt
                if (not isinstance(ticket, NativeSemanticTicket) or ticket.issuer is not self.__semantic_issuer
                        or not ticket.consumed or not ticket.receipt_sha256
                        or gate_type != "semantic" or task_id != ticket.binding["taskId"]
                        or run_id != ticket.binding["runId"] or artifact["sha256"] != ticket.receipt_sha256
                        or sha256_file(self.repository / artifact["path"]) != ticket.receipt_sha256):
                    raise RuntimeFailure("SEMANTIC_RESULT_UNTRUSTED", "atomic producer admission requires its verified live capability")
                if any(item["id"] == artifact["id"] for item in state["artifacts"]):
                    raise RuntimeFailure("EVIDENCE_REPLAY", "native semantic artifact already exists")
                if state["revision"] != ticket.binding["revision"]:
                    raise RuntimeFailure("SEMANTIC_RESULT_STALE", "review scope changed before atomic gate admission")
                self._assert_native_semantic_receipt(
                    state, artifact, self._read_json_receipt(artifact["path"], "semantic"),
                    task_id, list(criteria or []), family,
                )
                artifact["attestation"] = self._artifact_attestation(artifact)
                state["artifacts"].append(artifact)
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
            high_risk = {item["id"] for item in state["acceptanceCriteria"] if item["risk"] in {"R3", "R4"}}
            cross_family = bool((repository_config(str(self.repository)).get("review") or {}).get("crossFamily"))
            duplicate = next((
                item["id"] for item in state["gateResults"]
                if cross_family and gate_type == "semantic" and status == "PASS" and item["type"] == "semantic"
                and item["status"] == "PASS" and item.get("family") == family
                and item.get("objectiveVersion") == state["objective"]["version"]
                and high_risk.intersection(bound_criteria).intersection(item["criteria"])
                and self._native_semantic_gate_is_current(state, item)
            ), None)
            if duplicate:
                raise RuntimeFailure(
                    "DUPLICATE_REVIEW_FAMILY",
                    f"R3/R4 review family {family} already passed in {duplicate}; the second review needs a different family",
                )
            if status == "PASS":
                require_evidence_refs(state, evidence_refs, allowed={"artifact", "external"})
                artifact_ids = [reference.split(":", 1)[1] for reference in evidence_refs if reference.startswith("artifact:")]
                for artifact in state["artifacts"]:
                    if artifact["id"] in artifact_ids and artifact["producer"] == "legibility":
                        self._assert_product_binding(state, artifact, task_id=task_id, criteria=bound_criteria)
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
                if gate_type == "deterministic":
                    for artifact in state["artifacts"]:
                        if artifact["id"] not in artifact_ids or artifact["producer"] != "deterministic":
                            continue
                        receipt = self._read_json_receipt(artifact["path"], "deterministic")
                        if receipt.get("status") != "pass" or receipt.get("exitCode") != 0:
                            raise RuntimeFailure("DETERMINISTIC_RECEIPT", "PASS requires a passing observed command receipt")
                if gate_type == "semantic":
                    for artifact in state["artifacts"]:
                        if artifact["id"] not in artifact_ids:
                            continue
                        verdict = self._read_json_receipt(artifact["path"], "semantic")
                        if (verdict.get("verdict") != "PASS" or verdict.get("family") != family
                                or not set(bound_criteria).issubset(set(verdict.get("criteria") or []))):
                            raise RuntimeFailure("SEMANTIC_RECEIPT", "semantic gate does not match verdict family/criteria")
                        if verdict.get("schema") == "architrave.native-semantic-review.v1":
                            self._assert_native_semantic_receipt(state, artifact, verdict, task_id, bound_criteria, family)
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
            if status == "PASS" and gate_type == "semantic":
                for artifact in state["artifacts"]:
                    if artifact["id"] in artifact_ids:
                        receipt = self._read_json_receipt(artifact["path"], "semantic")
                        if receipt.get("schema") == "architrave.native-semantic-review.v1":
                            artifact["consumedByTask"] = task_id
                            artifact["attestation"] = self._artifact_attestation(artifact)
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
                    **({"reviewer": reviewer} if gate_type == "semantic" else {}),
                    **({"effort": {"requested": requested_level, "effective": effective_level or None}}
                       if effort is not None else {}),
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
                self.assert_gate_sources_current(state, evidence_refs)
                require_evidence_refs(state, evidence_refs, allowed={"gate", "external"})
                primary = state["focus"].get("primaryCriterion") or {}
                if status == "PASS" and primary.get("id") == criterion_id:
                    rejected = [reference for reference in evidence_refs
                                if not observed_product_outcome(state, criterion_id, reference)]
                    if rejected:
                        raise RuntimeFailure(
                            "PRIMARY_EVIDENCE_NOT_OBSERVED",
                            "the primary criterion passes only on a runtime-bound reality/e2e receipt or a "
                            "PRODUCT_OUTCOME_CONFIRMED user confirmation; CI/test, auth/MFA/policy checkpoints, "
                            "and self-authored evidence are rejected",
                            details={"rejected": rejected},
                        )
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

    def renew_target_checkpoint(
        self,
        run_id: str,
        *,
        checkpoint_id: str,
        actor: str,
    ) -> tuple[dict[str, Any], str]:
        challenge = "arc_" + secrets.token_urlsafe(32)
        challenge_hash = hashlib.sha256(challenge.encode("utf-8")).hexdigest()

        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            checkpoint = next(
                (item for item in state["externalCheckpoints"] if item["id"] == checkpoint_id),
                None,
            )
            task = find_task(state, checkpoint["taskId"]) if checkpoint else None
            if (
                checkpoint is None
                or task is None
                or checkpoint["status"] != "PENDING"
                or checkpoint["type"] != "SAFE_WRITE_TARGET_REQUIRED"
                or checkpoint["objectiveVersion"] != state["objective"]["version"]
                or task["status"] != "WAITING_EXTERNAL"
                or task["attempts"] != 0
                or task.get("lease") is not None
                or actor != f"human:{checkpoint['principal']}"
                or checkpoint.get("policyAmendment") is not None
            ):
                raise RuntimeFailure(
                    "CHECKPOINT_RENEWAL_DENIED",
                    "only an unchanged unstarted pending target checkpoint can be renewed",
                )
            intended = task.get("targetIdentity")
            if (
                not isinstance(intended, dict)
                or set(intended) != TARGET_IDENTITY_FIELDS
                or intended["provider"] != checkpoint["provider"]
            ):
                raise RuntimeFailure("TARGET_IDENTITY_REQUIRED", "renewed checkpoint target identity is invalid")
            checkpoint["challengeHash"] = challenge_hash
            checkpoint["targetBindingHash"] = sha256_value(
                {
                    "runId": state["runId"],
                    "objectiveVersion": state["objective"]["version"],
                    "taskId": task["id"],
                    "provider": checkpoint["provider"],
                    "principal": checkpoint["principal"],
                    "intended": intended,
                    "challengeHash": challenge_hash,
                }
            )
            checkpoint["createdAt"] = utc_now()
            checkpoint["reason"] = f"{checkpoint['reason']} (challenge renewed)"
            return {
                "checkpointId": checkpoint_id,
                "taskId": task["id"],
                "provider": checkpoint["provider"],
                "principal": checkpoint["principal"],
            }

        state = self._transaction(
            run_id,
            mutate,
            event_type="external.challenge_renewed",
            actor=actor,
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
            if checkpoint.get("focusCorrection") is not None:
                raise RuntimeFailure("FOCUS_CORRECTION_AUTHORITY", "use the exact factual correction API, not generic hold resolution")
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

    def attest_side_effect_reconciliation(
        self,
        run_id: str,
        task_id: str,
        *,
        actor: str = "coordinator",
    ) -> dict[str, Any]:
        before = self.load(run_id)
        task = find_task(before, task_id)
        side_effect = task.get("sideEffect")
        if side_effect is None or side_effect.get("state") != "UNCERTAIN":
            raise RuntimeFailure("RECONCILIATION_NOT_REQUIRED", "task has no uncertain side effect")
        registry = self._read_executor_registry()["exactTarget"]
        enrolled = [
            target
            for target in registry.get("targets") or []
            if isinstance(target, dict)
            and (target.get("reconciliation") or {}).get("runId") == run_id
            and (target.get("reconciliation") or {}).get("taskId") == task_id
            and (target.get("reconciliation") or {}).get("operation") == side_effect["operation"]
            and (target.get("reconciliation") or {}).get("target") == side_effect["target"]
        ]
        if len(enrolled) != 1:
            raise RuntimeFailure(
                "RECONCILIATION_TARGET_NOT_TRUSTED",
                "uncertain side effect is not uniquely enrolled for trusted reconciliation",
            )
        trusted_identity = enrolled[0].get("identity")
        if not isinstance(trusted_identity, dict) or set(trusted_identity) != TARGET_IDENTITY_FIELDS:
            raise RuntimeFailure("EXECUTOR_REGISTRY_INVALID", "trusted reconciliation identity is invalid")
        checkpoint = {
            "provider": trusted_identity["provider"],
            "type": "SIDE_EFFECT_RECONCILIATION_REQUIRED",
        }
        executor, trusted_target = self._trusted_exact_target_executor(checkpoint, trusted_identity)
        reconciliation = trusted_target.get("reconciliation")
        binding = {
            "runId": run_id,
            "objectiveVersion": before["objective"]["version"],
            "revision": before["revision"],
            "taskId": task_id,
            "checkpointId": f"reconcile:{task_id}",
            "checkpointType": "SIDE_EFFECT_RECONCILIATION_REQUIRED",
            "provider": trusted_identity["provider"],
            "principal": actor,
            "challengeHash": sha256_value(reconciliation),
        }
        result = self._invoke_exact_target_executor(
            executor,
            {
                "schema": EXACT_TARGET_REQUEST_SCHEMA,
                "binding": binding,
                "intended": trusted_identity,
                "target": {
                    "transport": trusted_target["transport"],
                    "artifactPath": trusted_target["artifactPath"],
                    "workspaceMode": trusted_target["workspaceMode"],
                    "ssh": trusted_target["ssh"],
                    "reconciliation": reconciliation,
                },
            },
        )
        outcome = reconciliation["outcome"]
        artifact_id = f"reconciliation-{uuid.uuid4().hex}"
        evidence_ref = f"artifact:{artifact_id}"
        receipt_relative = (
            Path(".architrave") / "runs" / run_id / "evidence" / f"{artifact_id}.json"
        ).as_posix()
        receipt_path = self.repository / receipt_relative
        receipt = {
            "runId": run_id,
            "objectiveVersion": before["objective"]["version"],
            "revision": before["revision"],
            "taskId": task_id,
            "operation": side_effect["operation"],
            "target": side_effect["target"],
            "outcome": outcome,
            "observedAt": utc_now(),
            "observation": result["observation"],
            "historicalEvidence": trusted_identity,
        }
        receipt_bytes = (canonical_json(receipt) + "\n").encode("utf-8")
        receipt_sha256 = hashlib.sha256(receipt_bytes).hexdigest()

        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            current_task = find_task(state, task_id)
            current_side_effect = current_task.get("sideEffect")
            if (
                state["revision"] != before["revision"]
                or state["objective"]["version"] != before["objective"]["version"]
                or current_side_effect is None
                or current_side_effect.get("state") != "UNCERTAIN"
                or current_side_effect.get("operation") != reconciliation["operation"]
                or current_side_effect.get("target") != reconciliation["target"]
            ):
                raise RuntimeFailure("RECONCILIATION_STALE", "side-effect reconciliation became stale")
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(prefix=f".{receipt_path.name}.", dir=receipt_path.parent)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(receipt_bytes)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, receipt_path)
            finally:
                with contextlib.suppress(FileNotFoundError):
                    os.unlink(temporary)
            artifact = {
                "id": artifact_id,
                "kind": "reconciliation-receipt",
                "producer": "reconciliation",
                "path": receipt_relative,
                "createdAt": utc_now(),
                "sha256": receipt_sha256,
                "evidenceRefs": [f"task:{task_id}"],
                "consumedByTask": task_id,
            }
            artifact["attestation"] = self._artifact_attestation(artifact)
            state["artifacts"].append(artifact)
            current_side_effect["state"] = "CONFIRMED" if outcome == "applied-closed" else "NONE"
            current_side_effect["reconciliation"] = evidence_ref
            current_task["status"] = "FAILED"
            current_task["lease"] = None
            state["status"] = derive_run_status(state)
            return {"taskId": task_id, "outcome": outcome, "evidenceRef": evidence_ref}

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
                close_task_workers(state, task, "resume abandoned the prior worker lease")
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
            active_workers = {task["lease"]["owner"] for task in state["tasks"]
                              if task["status"] == "RUNNING" and task.get("lease")}
            for worker in state["workers"]:
                if worker["status"] == "RUNNING" and worker["id"] not in active_workers:
                    worker["status"] = "FAILED"
                    worker["finishedAt"] = utc_now()
                    worker["reason"] = "resume closed orphaned worker"
            state["status"] = derive_run_status(state)
            if state["status"] == "PAUSED" and state["autonomy"]["scope"] == "current-task":
                state["status"] = "RUNNING" if any(task["status"] == "READY" for task in state["tasks"]) else state["status"]
            return {"recoveredTasks": recovered, "uncertainSideEffects": uncertain, "baselineDriftAccepted": bool(drift)}

        return self._transaction(run_id, mutate, event_type="run.resumed", actor=actor)

    def verify(self, run_id: str, actor: str = "coordinator") -> tuple[dict[str, Any], bool]:
        outcome: dict[str, Any] = {}

        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            required = [criterion for criterion in state["acceptanceCriteria"] if criterion["blocking"]]
            self.assert_gate_sources_current(state, [ref for criterion in required for ref in criterion["evidenceRefs"]])
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
                    "pushback": "KEEP:migrated legacy phase",
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
            "timeoutSeconds": int((value.get("budget") or {}).get("timeoutSeconds", 600)),
            "maxOutputBytes": int((value.get("budget") or {}).get("maxOutputBytes", 4096)),
            "maxTurns": int((value.get("budget") or {}).get("maxTurns", 12)),
        },
        "execution": normalize_execution(value.get("execution")),
    }


def retry_evidence_digest(state: dict[str, Any], task: dict[str, Any], repository: Path) -> str:
    paths = set(task["mutablePaths"] + task["workPacket"]["contextBundle"])
    files = {path: sha256_path(repository / path) for path in paths
             if not any(char in path for char in "*?[") and (repository / path).exists()}
    patterns = [path for path in paths if any(char in path for char in "*?[")]
    if patterns:
        tracked = run_command(["git", "ls-files", "--cached", "--others", "--exclude-standard"], repository).splitlines()
        files.update({path: sha256_path(repository / path) for path in tracked
                      if any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)
                      and (repository / path).exists()})
    provenance = {"binding", "observedAt", "createdAt", "updatedAt", "timestamp",
                  "revision", "durationMs", "stateHash", "attestation", "runId",
                  "taskId", "workerId", "artifactRef", "evidenceRefs", "receiptId"}

    def substantive(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: substantive(item) for key, item in value.items() if key not in provenance}
        if isinstance(value, list):
            return [substantive(item) for item in value]
        return value

    observed = set()
    for artifact in state["artifacts"]:
        if (artifact["producer"] not in {"deterministic", "legibility", "external-proof", "reconciliation"}
                or f"task:{task['id']}" not in artifact["evidenceRefs"]):
            continue
        path = repository / artifact["path"]
        if path.suffix == ".json":
            try:
                receipt = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise RuntimeFailure("RETRY_EVIDENCE_INVALID", "cannot read task observation for retry fingerprint") from exc
            observed.add(sha256_value(substantive(receipt)))
        else:
            observed.add(artifact["sha256"])
    return sha256_value({"paths": files, "observed": sorted(observed)})


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
    primary = state["focus"].get("primaryCriterion")
    if primary is not None and (
        not isinstance(primary, dict)
        or primary.get("id") not in criteria_ids
        or not primary.get("paths")
        or not isinstance(primary.get("threshold"), int)
        or primary["threshold"] < 1
        or not isinstance(primary.get("eventSequence"), int)
    ):
        raise RuntimeFailure("RUN_INVALID", "primary criterion focus is invalid")
    lanes = state["lanes"]
    if int(lanes.get("maxActive", 0)) < 1 or len(lanes.get("active") or []) > lanes["maxActive"]:
        raise RuntimeFailure("RUN_INVALID", "active lane limit exceeded")
    validate_task_graph(state["tasks"])
    for task in state["tasks"]:
        if task["risk"] not in RISK_CLASSES or task["status"] not in TASK_STATUSES:
            raise RuntimeFailure("RUN_INVALID", f"task {task['id']} risk or status is invalid")
        reset = task.get("feasibility")
        if reset:
            if reset.get("decision") not in {"CONTINUE", "BOUNDED_GO", "PIVOT", "PARK"}:
                raise RuntimeFailure("RUN_INVALID", "feasibility decision is invalid")
            for key in ("timeoutSeconds", "maxTurns", "maxOutputBytes"):
                chosen = reset.get("window", {}).get(key)
                cap = reset.get("ceiling", {}).get(key)
                if type(chosen) is not int or type(cap) is not int or cap < 1 or not 0 <= chosen <= cap:
                    raise RuntimeFailure("RUN_INVALID", "feasibility window must stay inside its finite original ceiling")
        if not set(task["acceptanceCriteria"]).issubset(criteria_ids):
            raise RuntimeFailure("RUN_INVALID", f"task {task['id']} references unknown criteria")
        for path in task["mutablePaths"]:
            safe_relative_path(path, "mutable path")
        for path in task["workPacket"]["contextBundle"]:
            safe_relative_path(path, "context path")
        turns = task["workPacket"]["budget"].get("maxTurns", 12)
        if not isinstance(turns, int) or isinstance(turns, bool) or not 1 <= turns <= 100:
            raise RuntimeFailure("RUN_INVALID", "WorkPacket turn budget must be an integer between 1 and 100")
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


def close_task_workers(state: dict[str, Any], task: dict[str, Any], reason: str) -> None:
    owner = (task.get("lease") or {}).get("owner")
    for worker in state["workers"]:
        if worker["status"] == "RUNNING" and (
            worker["id"] == owner or worker.get("taskId") == task["id"]
        ):
            worker["status"] = "FAILED"
            worker["finishedAt"] = utc_now()
            worker["reason"] = reason


def task_has_pending_checkpoint(state: dict[str, Any], task_id: str) -> bool:
    return any(checkpoint["status"] == "PENDING"
               and task_id in {checkpoint["taskId"], checkpoint["resumeTask"]}
               for checkpoint in state["externalCheckpoints"])


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


def observed_product_outcome(state: dict[str, Any], criterion_id: str, reference: str) -> bool:
    """True only for a runtime-bound reality/e2e receipt or a typed user product confirmation."""
    kind, _, identifier = reference.partition(":")
    started = parse_iso(state["createdAt"])
    if kind == "gate":
        gate = next((item for item in state["gateResults"] if item["id"] == identifier), None)
        if gate is None or gate["type"] not in {"reality", "e2e"} or gate["status"] != "PASS" \
                or criterion_id not in gate["criteria"] or parse_iso(gate["startedAt"]) < started:
            return False
        artifact_ids = {ref.split(":", 1)[1] for ref in gate["evidenceRefs"] if ref.startswith("artifact:")}
        artifacts = [item for item in state["artifacts"] if item["id"] in artifact_ids]
        return bool(artifacts) and all(
            item["producer"] in {"legibility", "external-proof", "mutation"}
            and parse_iso(item["createdAt"]) >= started for item in artifacts)
    if kind == "external":
        checkpoint = next((item for item in state["externalCheckpoints"] if item["id"] == identifier), None)
        return bool(checkpoint) and checkpoint["type"] == "PRODUCT_OUTCOME_CONFIRMED" \
            and checkpoint["status"] == "RESOLVED" and parse_iso(checkpoint["createdAt"]) >= started \
            and criterion_id in find_task(state, checkpoint["taskId"])["acceptanceCriteria"]
    return False


def map_effort(requested: str, host: dict[str, Any]) -> dict[str, Any]:
    """Map a capability signal to what the host exposes; never a model name."""
    tiers = {"low": "efficiency", "default": None, "high": "intelligence"}
    effective: dict[str, Any] | None = None
    if requested != "default" and host.get("autoTier"):
        effective = {"autoTier": tiers[requested]}
    elif requested != "default" and requested in (host.get("reasoningLevels") or []):
        effective = {"reasoning_effort": requested}
    return {"requested": requested, "effective": effective,
            "note": None if effective else "host default inherited (no per-task effort control or default requested)"}


def requested_effort(state: dict[str, Any], task: dict[str, Any], stalled: bool = False) -> str:
    primary = (state["focus"].get("primaryCriterion") or {}).get("id")
    if task.get("effort"):
        return task["effort"]
    if stalled and primary in task["acceptanceCriteria"]:
        return "high"
    return "low" if task["risk"] in {"R0", "R1"} else "default"


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
    cross_family = bool((repo_config.get("review") or {}).get("crossFamily"))
    store = RunStore(state["baseline"]["repository"])
    missing: list[str] = []
    for criterion in criteria:
        requirements = list(
            dict.fromkeys(
                [
                    *(gate if cross_family or gate != "semantic-independent-2" else "semantic-any"
                      for gate in DEFAULT_RISK_GATES[criterion["risk"]]),
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
            and (gate["type"] != "semantic" or store._native_semantic_gate_is_current(state, gate))
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


def normalize_primary_criterion(
    state: dict[str, Any],
    criterion_id: str,
    paths: Sequence[str],
    threshold: int,
    since_commit: str,
) -> dict[str, Any]:
    if criterion_id not in state["objective"]["acceptanceCriteria"]:
        raise RuntimeFailure("INVALID_PRIMARY_CRITERION", "primary criterion must be a current objective criterion")
    criterion = next(item for item in state["acceptanceCriteria"] if item["id"] == criterion_id)
    if criterion["verificationType"] not in OBSERVED_OUTCOME_TYPES:
        raise RuntimeFailure(
            "INVALID_PRIMARY_CRITERION",
            "primary criterion must be verified by an observed product outcome (reality, e2e, or external "
            "user confirmation); CI and test counts cannot pass it",
        )
    normalized_paths = list(dict.fromkeys(safe_relative_path(str(path), "primary path") for path in paths))
    if not normalized_paths:
        raise RuntimeFailure("INVALID_PRIMARY_CRITERION", "primary criterion requires at least one code path")
    if int(threshold) < 1:
        raise RuntimeFailure("INVALID_PRIMARY_CRITERION", "stall threshold must be at least 1")
    return {
        "id": criterion_id,
        "paths": normalized_paths,
        "threshold": int(threshold),
        "sinceCommit": since_commit,
        "declaredAt": utc_now(),
        "eventSequence": state["eventCursor"]["sequence"] + 1,
    }


def _path_touches(changed: str, declared: str) -> bool:
    declared = declared.rstrip("/")
    return changed == declared or changed.startswith(declared + "/") or fnmatch.fnmatchcase(changed, declared)


def _primary_commits(repository: Path, primary: dict[str, Any]) -> list[tuple[dt.datetime, int, str, bool]]:
    since = primary["sinceCommit"]
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", since, "HEAD"], cwd=repository, capture_output=True, check=False,
    ).returncode == 0
    selector = [f"{since}..HEAD"] if ancestor else [f"--since={primary['declaredAt']}", "HEAD"]
    output = run_command(
        ["git", "-c", "core.quotepath=false", "log", "--reverse", "--no-merges",
         "--format=%x1e%H%x1f%cI", "--name-only", *selector],
        repository,
    )
    commits: list[tuple[dt.datetime, int, str, bool]] = []
    for record in output.split("\x1e"):
        lines = [line.strip() for line in record.strip().splitlines() if line.strip()]
        if not lines:
            continue
        sha, committed = lines[0].split("\x1f", 1)
        touched = any(_path_touches(name, path) for name in lines[1:] for path in primary["paths"])
        commits.append((parse_iso(committed), 0, f"commit:{sha[:12]}", touched))
    return commits


def primary_criterion_status(
    state: dict[str, Any], events: Sequence[dict[str, Any]], repository: Path,
) -> dict[str, Any] | None:
    """Count consecutive commits/worker results that neither touch nor move the primary criterion."""
    primary = state["focus"].get("primaryCriterion")
    if not primary:
        return None
    criterion = next((item for item in state["acceptanceCriteria"] if item["id"] == primary["id"]), None)
    criterion_status = criterion["status"] if criterion else "NOT_APPLICABLE"
    tasks = {task["id"]: task for task in state["tasks"]}
    gates = {gate["id"]: gate for gate in state["gateResults"]}
    timeline = _primary_commits(repository, primary)
    for event in events:
        if event["sequence"] <= primary["eventSequence"] or event["type"] not in PRIMARY_BOUND_EVENTS:
            continue
        payload = event.get("payload") or {}
        task = tasks.get(str(event.get("taskId") or ""))
        gate = gates.get(str(payload.get("gateId") or ""))
        bound = (
            payload.get("criterionId") == primary["id"]
            or (gate is not None and primary["id"] in gate["criteria"])
            or (task is not None and primary["id"] in task["acceptanceCriteria"])
        )
        if bound:
            timeline.append((parse_iso(event["timestamp"]), 1, f"event:{event['sequence']}", True))
        elif event["type"] in PRIMARY_RESULT_EVENTS:
            timeline.append((parse_iso(event["timestamp"]), 1, f"task:{event.get('taskId')}", False))
    streak = 0
    counted: set[str] = set()
    last_touch = None
    for _, _, label, touched in sorted(timeline, key=lambda item: (item[0], item[1])):
        if touched:
            streak, counted, last_touch = 0, set(), label
        elif label not in counted:
            counted.add(label)
            streak += 1
    failed_attempts = primary_failures(state, events, primary["id"])
    open_criterion = criterion_status not in {"PASS", "NOT_APPLICABLE"}
    milestones = [event for event in events if event["sequence"] > primary["eventSequence"]
                  and event["type"] == "product.milestone" and event["payload"].get("criterionId") == primary["id"]]
    milestone_at = parse_iso(milestones[-1]["timestamp"]) if milestones else parse_iso(primary["declaredAt"])
    milestone_sequence = milestones[-1]["sequence"] if milestones else primary["eventSequence"]
    work_since = [label for timestamp, _, label, _ in timeline
                  if (label.startswith("event:") and int(label.split(":")[1]) > milestone_sequence)
                  or not label.startswith("event:") and (timestamp > milestone_at if milestones else timestamp >= milestone_at)]
    leased = [task["id"] for task in state["tasks"] if primary["id"] in task["acceptanceCriteria"]
              and task["objectiveVersion"] == state["objective"]["version"] and task["status"] == "RUNNING"
              and task.get("lease") and parse_iso(task["lease"]["expiresAt"]) > dt.datetime.now(dt.timezone.utc)]
    return {
        "id": primary["id"],
        "criterionStatus": criterion_status,
        "paths": list(primary["paths"]),
        "threshold": primary["threshold"],
        "untouchedStreak": streak,
        "lastTouch": last_touch,
        "stalled": open_criterion and streak >= primary["threshold"],
        "failedAttempts": failed_attempts,
        "loopCapped": open_criterion and len(failed_attempts) >= primary["threshold"],
        "verifiedMilestones": len(milestones), "lastVerifiedMilestone": milestones[-1]["payload"]["milestone"] if milestones else None,
        "workSinceMilestone": len(work_since), "pathTouchIsProductEvidence": False,
        "milestoneReviewNeeded": open_criterion and len(work_since) >= primary["threshold"] and not leased,
        "liveBoundTasks": leased,
    }


def lane_feasibility(state: dict[str, Any], task: dict[str, Any]) -> dict[str, Any] | None:
    decisions = [item["feasibility"] for item in state["tasks"] if item.get("feasibility")
                 and item["lane"] == task["lane"] and item["objectiveVersion"] == state["objective"]["version"]]
    return max(decisions, key=lambda item: item["recordedSequence"]) if decisions else None


def feasibility_status(state: dict[str, Any], task: dict[str, Any]) -> dict[str, Any] | None:
    reset = lane_feasibility(state, task)
    if not reset:
        return None
    seconds = max(0, int((parse_iso(reset["expiresAt"]) - dt.datetime.now(dt.timezone.utc)).total_seconds()))
    turns_used, output_used = feasibility_usage(state, task, reset)
    turns = max(0, reset["window"]["maxTurns"] - turns_used) if turns_used is not None else None
    output = max(0, reset["window"]["maxOutputBytes"] - output_used)
    limits = (repository_config(state["baseline"]["repository"]).get("evaluation") or {}).get("budget") or {}
    if limits.get("maxMinutes"):
        seconds = min(seconds, max(0, int(limits["maxMinutes"] * 60 -
                      (dt.datetime.now(dt.timezone.utc) - parse_iso(state["createdAt"])).total_seconds())))
    exhausted = False
    if limits:
        repository = Path(state["baseline"]["repository"])
        store = RunStore(repository)
        signal = budget_signal(state, store._read_events(store.run_dir(state["runId"])), repository)
        exhausted = bool(signal and signal["signal"] == "BUDGET_100")
    expired = reset["partial"] or seconds == 0 or turns == 0 or output == 0 or exhausted
    unknown = turns is None
    return {**reset, "decision": "PARK" if expired else reset["decision"],
            "partial": expired, "expired": expired, "remainingSeconds": seconds,
            "remainingHostTurns": turns, "remainingOutputBytes": output,
            "hostTurnsUnknown": unknown, "turnMethod": "reported host turns since reset; global transition proxy remains separate"}


def feasibility_usage(state: dict[str, Any], task: dict[str, Any], reset: dict[str, Any]) -> tuple[int | None, int]:
    repository = Path(state["baseline"]["repository"])
    store = RunStore(repository)
    events = store._read_events(store.run_dir(state["runId"]))
    lane_tasks = {item["id"] for item in state["tasks"] if item["lane"] == task["lane"]
                  and item["objectiveVersion"] == state["objective"]["version"]}
    owners = {event["payload"]["workerId"] for event in events
              if event["sequence"] > reset["startSequence"] and event["type"] == "task.started"
              and event.get("taskId") in lane_tasks}
    turns, output, reported = 0, 0, set()
    unknown = False
    for artifact in state["artifacts"]:
        if artifact["producer"] != "worker":
            continue
        receipt = json.loads((repository / artifact["path"]).read_text(encoding="utf-8"))
        owner = receipt.get("workerId") or (receipt.get("binding") or {}).get("workerId")
        if owner not in owners:
            continue
        reported.add(owner)
        value = (receipt.get("hostObservation") or {}).get("turnsObserved")
        if type(value) is int:
            turns += value
        else:
            unknown = True
        # WorkPacket output means retained candidate/diagnostic bytes, not model tokens.
        if receipt.get("schema") == "architrave.native-candidate.v1":
            output += len(receipt["summary"].encode("utf-8"))
        else:
            output += sum(len(str(receipt.get(key, "")).encode("utf-8")) for key in ("stdout", "stderr"))
    # In-flight owners are bounded by their admission budget; missing *finished*
    # owner telemetry cannot silently become a fresh zero-spend allowance.
    finished = {item["id"] for item in state["workers"] if item["id"] in owners and item["status"] != "RUNNING"}
    unknown = unknown or bool(finished - reported)
    return (None if unknown else turns), output


def feasibility_evidence(state: dict[str, Any], task: dict[str, Any], repository: Path) -> str:
    return sha256_value({
        "taskEvidence": retry_evidence_digest(state, task, repository),
        "criteria": [(item["id"], item["status"]) for item in state["acceptanceCriteria"] if item["id"] in task["acceptanceCriteria"]],
        "dependencies": [(item, find_task(state, item)["status"]) for item in task["dependencies"]],
        "holds": [(item["id"], item["status"]) for item in state["externalCheckpoints"]],
        "sideEffect": task["sideEffect"], "objective": state["objective"],
        "failure": task.get("loop"),
    })


def feasibility_remaining(
    state: dict[str, Any], task: dict[str, Any], repository: Path, events: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Actual clocks/observed child turns; absent host counters are unknown."""
    now = dt.datetime.now(dt.timezone.utc)
    starts = [parse_iso(event["timestamp"]) for event in events
              if event.get("taskId") == task["id"] and event["type"] == "task.started"]
    task_seconds = task["workPacket"]["budget"]["timeoutSeconds"]
    if starts:
        task_seconds = max(0, int(task_seconds - (now - min(starts)).total_seconds()))
    task_turns = None
    observed = []
    for artifact in state["artifacts"]:
        if artifact["producer"] == "worker" and f"task:{task['id']}" in artifact["evidenceRefs"]:
            receipt = json.loads((repository / artifact["path"]).read_text(encoding="utf-8"))
            observed.append((receipt.get("hostObservation") or {}).get("turnsObserved"))
    if observed and all(type(item) is int for item in observed):
        task_turns = max(0, task["workPacket"]["budget"].get("maxTurns", 12) - sum(observed))
    global_config = (repository_config(str(repository)).get("evaluation") or {}).get("budget") or {}
    global_seconds = None
    if global_config.get("maxMinutes"):
        global_seconds = max(0, int(global_config["maxMinutes"] * 60 - (now - parse_iso(state["createdAt"])).total_seconds()))
    global_turns = None
    if global_config.get("maxTurns"):
        global_turns = max(0, global_config["maxTurns"] - state["eventCursor"]["sequence"] - 1)
    seconds = min([task_seconds] + ([global_seconds] if global_seconds is not None else []))
    turns = min([item for item in (task_turns, global_turns) if item is not None], default=None)
    return {"timeoutSeconds": seconds, "maxTurns": turns,
            "taskTurnsObserved": task_turns, "globalSeconds": global_seconds,
            "globalTurnProxy": global_turns, "hostCredits": None, "hostOutputRemaining": None,
            "unknown": ["hostCredits", "hostOutputRemaining"] + ([] if task_turns is not None else ["taskTurnsObserved"])}


def effective_work_budget(state: dict[str, Any], task: dict[str, Any]) -> dict[str, int]:
    budget = dict(task["workPacket"]["budget"])
    reset = feasibility_status(state, task)
    if reset:
        if any(other["id"] != task["id"] and other["lane"] == task["lane"] and other["status"] == "RUNNING"
               for other in state["tasks"]):
            raise RuntimeFailure("FEASIBILITY_LANE_BUSY", "one discriminating owner at a time in the reset lane; retain other lanes' independent work")
        repository = Path(state["baseline"]["repository"])
        store = RunStore(repository)
        remaining = feasibility_remaining(state, task, repository, store._read_events(store.run_dir(state["runId"])))
        budget["timeoutSeconds"] = min(budget["timeoutSeconds"], reset["remainingSeconds"])
        if reset["hostTurnsUnknown"]:
            raise RuntimeFailure("FEASIBILITY_BUDGET_UNKNOWN", "finished owner did not report turns; do not assume zero spend for another dispatch")
        budget["maxTurns"] = min(budget.get("maxTurns", 12), reset["remainingHostTurns"])
        budget["maxOutputBytes"] = min(budget["maxOutputBytes"], reset["remainingOutputBytes"])
        budget["timeoutSeconds"] = min(budget["timeoutSeconds"], remaining["timeoutSeconds"])
        if remaining["maxTurns"] is not None:
            budget["maxTurns"] = min(budget["maxTurns"], remaining["maxTurns"])
        if reset["expired"] or reset["decision"] not in {"CONTINUE", "BOUNDED_GO"}:
            raise RuntimeFailure("FEASIBILITY_STOP", "lane is paused/expired; no new action", details=reset)
        if budget["timeoutSeconds"] < 1 or budget["maxTurns"] < 1:
            raise RuntimeFailure("FEASIBILITY_STOP", "remaining parent/task/global budget exhausted; synthesize partial result")
    return budget


def budget_signal(state: dict[str, Any], events: Sequence[dict[str, Any]], repository: Path) -> dict[str, Any] | None:
    """Real-signal counters since Run creation against optional evaluation.budget limits."""
    limits = (repository_config(str(repository)).get("evaluation") or {}).get("budget") or {}
    if not limits:
        return None
    base = state["baseline"]["commit"]
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", base, "HEAD"], cwd=repository,
                              capture_output=True, check=False).returncode == 0
    counters = {
        "turns": state["eventCursor"]["sequence"],
        "commits": int(run_command(["git", "rev-list", "--count", f"{base}..HEAD"], repository)) if ancestor else None,
        "dispatches": sum(1 for event in events if event["type"] == "task.started"),
        "minutes": int((dt.datetime.now(dt.timezone.utc) - parse_iso(state["createdAt"])).total_seconds() // 60),
    }
    active = {name: limits[key] for name, key in BUDGET_LIMITS.items() if limits.get(key)}
    ratios = {name: counters[name] / limit for name, limit in active.items() if counters[name] is not None}
    unknown = sorted(name for name in active if counters[name] is None)
    peak = max(ratios.values(), default=0)
    signal = ("BUDGET_100" if peak >= 1 else "BUDGET_UNKNOWN" if unknown
              else "BUDGET_80" if peak >= 0.8 else None)
    return {"counters": counters, "limits": active, "signal": signal, "unknown": unknown,
            "over": sorted(name for name, ratio in ratios.items() if ratio >= 0.8)}


def primary_failures(state: dict[str, Any], events: Sequence[dict[str, Any]], criterion_id: str) -> list[dict[str, Any]]:
    """Failed attempts on one criterion across workers and gates since its last observed PASS or objective replacement."""
    tasks = {task["id"]: task for task in state["tasks"]}
    gates = {gate["id"]: gate for gate in state["gateResults"]}
    attempts: list[dict[str, Any]] = []
    for event in events:
        payload = event.get("payload") or {}
        task = tasks.get(str(event.get("taskId") or ""))
        if event["type"] == "objective.replaced" or (
                event["type"] == "product.progress" and payload.get("criterionId") == criterion_id):
            attempts = []
        elif event["type"] in {"task.failed", "worker.finished"} and task and criterion_id in task["acceptanceCriteria"] \
                and (event["type"] == "task.failed" or str(payload.get("candidateStatus", "")).upper() == "FAILED"):
            attempts.append({"taskId": task["id"], "reason": str(payload.get("reason") or "worker failed")[:200]})
        elif event["type"] == "gate.failed" and criterion_id in (gates.get(str(payload.get("gateId"))) or {}).get("criteria", []):
            attempts.append({"gateId": payload.get("gateId"), "reason": "gate failed"})
        elif event["type"] == "acceptance.updated" and payload.get("criterionId") == criterion_id \
                and payload.get("status") == "FAIL":
            attempts.append({"criterionId": criterion_id, "reason": "criterion observed FAIL"})
    return attempts


def primary_stalled_escalation(stall: dict[str, Any]) -> dict[str, Any]:
    attempts = stall["failedAttempts"]
    return {
        "code": "PRIMARY_STALLED",
        "criterion": stall["id"],
        "bestAttempt": attempts[-1],
        "caveats": [item["reason"] for item in attempts],
        "message": (f"{len(attempts)} failed attempts on {stall['id']}; new work on it is blocked. Report the best "
                    "attempt with its caveats and ask the user to approve a different approach or criterion"),
    }


def stalled_primary_escalation(stall: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": "STALLED_PRIMARY_CRITERION",
        "criterion": stall["id"],
        "message": (
            f"{stall['untouchedStreak']} consecutive commits/worker results did not touch "
            f"{stall['id']} ({', '.join(stall['paths'])}) or change its outcome; return to its "
            "code path or ask the user to replace the objective"
        ),
    }


def runtime_identity() -> dict[str, Any]:
    """Loaded module bytes, not a claim about host prompts or plugin registry."""
    root = Path(__file__).resolve().parents[1]
    manifest = root / "plugin.json"
    stamp = root / "gates" / ".kit-version"
    version = None
    if manifest.is_file():
        version = json.loads(manifest.read_text(encoding="utf-8")).get("version")
    elif stamp.is_file():
        version = stamp.read_text(encoding="utf-8").strip()
    files = [Path(__file__).resolve(), root / "agents" / "architrave.agent.md", root / "skills" / "architrave-cto" / "SKILL.md"]
    digests = {path.relative_to(root).as_posix(): sha256_file(path) for path in files if path.is_file()}
    return {"version": version, "fingerprint": sha256_value(digests), "source": "executing module filesystem",
            "installedPlugin": "UNKNOWN (query supported host registry)", "sessionLoadedInstructions": "UNKNOWN",
            "adoptedKitVersion": stamp.read_text(encoding="utf-8").strip() if stamp.is_file() else None}


def state_summary(state: dict[str, Any]) -> dict[str, Any]:
    from worker_adapters import workspace_fingerprint

    now = dt.datetime.now(dt.timezone.utc)
    active_worker_ids = {task["lease"]["owner"] for task in state["tasks"]
                         if task["status"] == "RUNNING" and task.get("lease")
                         and parse_iso(task["lease"]["expiresAt"]) > now}
    repository = Path(state["baseline"]["repository"])
    current_commit = run_command(["git", "rev-parse", "HEAD"], repository)
    source_sha = workspace_fingerprint(repository, include_ignored=False)
    evidence = []
    for artifact in state["artifacts"]:
        item = {"id": artifact["id"], "producer": artifact["producer"],
                "sha256": artifact["sha256"], "createdAt": artifact["createdAt"],
                "bindings": artifact["evidenceRefs"], "freshness": "historical"}
        if artifact["producer"] == "deterministic":
            receipt = json.loads((repository / artifact["path"]).read_text(encoding="utf-8"))
            if receipt.get("schema") == "architrave.deterministic-observation.v1":
                item["source"] = receipt["source"]
                item["objectiveVersion"] = receipt["binding"]["objectiveVersion"]
                item["freshness"] = (
                    "current" if receipt["source"]["sha256"] == source_sha
                    and receipt["source"]["commit"] == current_commit
                    and receipt["binding"]["objectiveVersion"] == state["objective"]["version"]
                    else "stale"
                )
        evidence.append(item)
    summary = {
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
        "observedAt": utc_now(),
        "source": {"commit": state["baseline"]["commit"], "branch": state["baseline"]["branch"],
                   "observedCommit": current_commit, "sha256": source_sha,
                   "baselineFresh": state["baseline"]["commit"] == current_commit},
        "activeWorkers": [worker["id"] for worker in state["workers"]
                          if worker["status"] == "RUNNING" and worker["id"] in active_worker_ids],
        "historicalWorkers": {worker["id"]: worker["status"] for worker in state["workers"]
                              if worker["status"] != "RUNNING"},
        "staleWorkers": [worker["id"] for worker in state["workers"]
                        if worker["status"] == "RUNNING" and worker["id"] not in active_worker_ids],
        "evidence": evidence,
        "runtime": runtime_identity(),
        "hostWorkers": {"visibility": "UNKNOWN", "source": "canonical Run cannot observe direct host sessions",
                        "idleProven": False},
        "reconciliation": {"required": state["baseline"]["commit"] != current_commit,
                           "automaticRepair": False, "humanHoldsPreserved": True,
                           "action": "owner-bound objective/path correction and explicit resume/reconciliation; never substitute chat PASS"},
    }
    missing_pushback = [task["id"] for task in state["tasks"]
                        if "pushback" not in task and task.get("objectiveVersion") == state["objective"]["version"]]
    if missing_pushback:
        summary["missingPushback"] = missing_pushback
    store = RunStore(repository)
    events = store._read_events(store.run_dir(state["runId"]))
    budget = budget_signal(state, events, repository)
    if budget:
        summary["budget"] = budget
    resets = {task["lane"]: reset for task in state["tasks"]
              if task.get("feasibility") and (reset := feasibility_status(state, task)) is not None}
    if resets:
        summary["feasibility"] = resets
        paused = {lane for lane, reset in resets.items()
                  if reset["expired"] or reset["hostTurnsUnknown"] or reset["decision"] not in {"CONTINUE", "BOUNDED_GO"}}
        summary["readyTasks"] = [task["id"] for task in state["tasks"]
                                 if task["status"] == "READY" and task["lane"] not in paused]
    if state["focus"].get("primaryCriterion"):
        stall = primary_criterion_status(state, events, repository)
        summary["primaryCriterion"] = stall
        if state["baseline"]["commit"] != current_commit:
            summary["primaryCriterion"]["freshness"] = "STALE_SOURCE"
            summary["feasibilityAdvice"] = {"reason": "Run/source mismatch; stale stall projection is not product failure",
                                          "action": "owning coordinator reconciles current objective/path/source at a safe boundary"}
        elif stall and stall["loopCapped"]:
            summary["escalation"] = primary_stalled_escalation(stall)
        elif stall and stall["stalled"] and not stall["liveBoundTasks"]:
            summary["escalation"] = stalled_primary_escalation(stall)
        elif stall and stall["milestoneReviewNeeded"]:
            summary["feasibilityAdvice"] = {"reason": "Activity without a verified product milestone",
                                          "action": "on-demand CTO bounded discriminating check; not a product FAIL or a time-based halt"}
    lint = owner_message_lint(" ".join(
        str(text) for text in (summary["objective"], summary["nextCheapestTest"],
                               (summary.get("escalation") or {}).get("message")) if text))
    if lint:
        summary["ownerMessageLint"] = lint
    return summary


def owner_message_lint(text: str) -> dict[str, Any] | None:
    """Owner summaries fail when dense with full SHAs, PIDs, run-* IDs, or UUIDs (evidence payloads are exempt)."""
    findings = [match.group(0) for pattern in OWNER_MESSAGE_NOISE for match in pattern.finditer(text)]
    if len(text) > 2400:
        return {"code": "OWNER_MESSAGE_LINT_FAIL", "findings": ["owner summary exceeds 2400 characters"],
                "message": "send only the actionable correction; keep machine evidence by reference"}
    if len(findings) < 3:
        return None
    return {"code": "OWNER_MESSAGE_LINT_FAIL", "findings": findings,
            "message": "rewrite in plain sentences with at most two identifiers"}


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
    create.add_argument("--primary-criterion", help="failing user-visible criterion watched by the stall detector")
    create.add_argument("--primary-path", action="append", default=[], help="repository path/glob of its code path")
    create.add_argument("--stall-threshold", type=int, default=PRIMARY_STALL_THRESHOLD)

    primary = subparsers.add_parser("primary-set", help="declare the failing primary criterion and its code paths")
    primary.add_argument("run_id")
    primary.add_argument("--criterion", required=True)
    primary.add_argument("--path", action="append", required=True)
    primary.add_argument("--threshold", type=int, default=PRIMARY_STALL_THRESHOLD)

    for command in ("status", "inspect", "events", "ready", "resume", "verify", "checkpoint", "ribbon-snapshot"):
        current = subparsers.add_parser(command)
        current.add_argument("run_id", nargs="?")
        if command == "resume":
            current.add_argument("--accept-commit", action="store_true")

    recover = subparsers.add_parser("worker-recover", help="close expired/orphan workers without replaying side effects")
    recover.add_argument("run_id")
    recover.add_argument("--task-id", help="explicitly release one failed, side-effect-free task for a new candidate")
    milestone = subparsers.add_parser("milestone-advance", help="source-bound verified intermediate progress, never criterion PASS")
    milestone.add_argument("run_id")
    milestone.add_argument("task_id")
    milestone.add_argument("--criterion", required=True)
    milestone.add_argument("--milestone", required=True)
    milestone.add_argument("--gate", required=True)
    correction = subparsers.add_parser("focus-correction-request", help="owner-bound correction of primary repository paths only")
    correction.add_argument("run_id")
    correction.add_argument("task_id")
    correction.add_argument("--path", action="append", required=True)
    correction.add_argument("--principal", required=True)
    correction.add_argument("--actor", required=True)
    correction.add_argument("--id", required=True)
    apply_focus = subparsers.add_parser("focus-correction-apply")
    apply_focus.add_argument("run_id")
    apply_focus.add_argument("checkpoint_id")
    apply_focus.add_argument("--challenge", required=True)
    apply_focus.add_argument("--actor", required=True)

    feasibility = subparsers.add_parser("feasibility-record", help="record an on-demand, finite evidence-driven lane decision")
    feasibility.add_argument("run_id")
    feasibility.add_argument("task_id")
    feasibility.add_argument("--trigger", choices=["user", "stall", "repeated-failure", "budget"], required=True)
    feasibility.add_argument("--decision", choices=["CONTINUE", "BOUNDED_GO", "PIVOT", "PARK"], required=True)
    for option in ("rationale", "next-step", "revisit", "uncertainty", "product-delta", "blocker"):
        feasibility.add_argument("--" + option, required=True)
    feasibility.add_argument("--hypothesis", action="append", default=[])
    feasibility.add_argument("--seconds", type=int, required=True)
    feasibility.add_argument("--turns", type=int, required=True)
    feasibility.add_argument("--output-bytes", type=int, required=True)
    feasibility.add_argument("--owner-seconds", type=int)
    feasibility.add_argument("--owner-turns", type=int)
    feasibility.add_argument("--owner-output-bytes", type=int)
    feasibility.add_argument("--owner-deadline")

    execute = subparsers.add_parser("gate-execute", help="observe a real configured command, never import a claimed PASS")
    execute.add_argument("run_id")
    execute.add_argument("task_id")
    execute.add_argument("--recipe", choices=["quick", "build", "test", "ci", "task"], default="test")
    execute.add_argument("--ci-run-id", type=int)

    task_add = subparsers.add_parser("task-add")
    task_add.add_argument("run_id")
    task_add.add_argument("--id", required=True)
    task_add.add_argument("--title", required=True)
    task_add.add_argument("--objective", required=True)
    task_add.add_argument("--depends-on")
    task_add.add_argument("--worker", choices=["native", "shell"], default="native")
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
    task_add.add_argument("--pushback", help="KEEP|CUT|DEFER:one-line reason (push-back verdict for this item)")
    task_add.add_argument("--effort", choices=["low", "default", "high"],
                          help="capability signal mapped only to host-exposed controls; never a model name")
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

    attest = subparsers.add_parser("target-attest")
    attest.add_argument("run_id")
    attest.add_argument("--checkpoint-id", required=True)
    attest.add_argument("--challenge", required=True)
    attest.add_argument("--actor", required=True)

    review = subparsers.add_parser("review-record")
    review.add_argument("run_id")
    review.add_argument("--verdict", choices=["PASS", "REVISE", "FAIL"], required=True)
    review.add_argument("--evidence", action="append", default=[])

    task_start = subparsers.add_parser("task-start")
    task_start.add_argument("run_id")
    task_start.add_argument("task_id")
    task_start.add_argument("--worker-id", required=True)
    task_start.add_argument("--lease-seconds", type=int, default=3600)
    task_start.add_argument("--retry-hypothesis", help="new bounded failure hypothesis for a retry")
    task_start.add_argument("--retry-evidence", action="append", default=[])
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
    gate.add_argument("--reviewer", choices=["host-native", "architrave-judge"],
                      help="semantic reviewer kind: the host's native reviewer or the Architrave judge fallback")
    gate.add_argument("--effort", help="requested low|default|high[:effective host mapping], e.g. high:none")
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

    renew = subparsers.add_parser("checkpoint-renew")
    renew.add_argument("run_id")
    renew.add_argument("checkpoint_id")
    renew.add_argument("--actor", required=True)

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

    reconcile_attest = subparsers.add_parser("reconcile-attest")
    reconcile_attest.add_argument("run_id")
    reconcile_attest.add_argument("task_id")

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
                primary_criterion=args.primary_criterion,
                primary_paths=args.primary_path,
                primary_threshold=args.stall_threshold,
            )
            output = state_summary(state)
        elif command == "status":
            output = state_summary(store.load(args.run_id))
        elif command == "ribbon-snapshot":
            from ribbon import ribbon_snapshot, RuntimeFailure as ProjectionFailure
            try:
                output = ribbon_snapshot(store, args.run_id)
            except ProjectionFailure as exc:
                raise RuntimeFailure(exc.code, exc.message, details=exc.details) from exc
        elif command == "worker-recover":
            output = state_summary(store.recover_workers(args.run_id, task_id=args.task_id))
        elif command == "gate-execute":
            output = store.execute_gate(args.run_id, args.task_id, recipe=args.recipe, ci_run_id=args.ci_run_id)
            if output["status"] != "PASS":
                print(json.dumps({"status": "failed", "result": output}, indent=2))
                return 1
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
        elif command == "primary-set":
            output = state_summary(
                store.set_primary_criterion(
                    args.run_id, criterion_id=args.criterion, paths=args.path, threshold=args.threshold,
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
        elif command == "target-attest":
            output = state_summary(
                store.attest_target_identity_checkpoint(
                    args.run_id,
                    checkpoint_id=args.checkpoint_id,
                    challenge=args.challenge,
                    actor=args.actor,
                )
            )
        elif command == "milestone-advance":
            output = state_summary(store.advance_milestone(args.run_id, args.task_id, criterion_id=args.criterion,
                                                          milestone=args.milestone, gate_ref=args.gate))
        elif command == "focus-correction-request":
            state, challenge = store.request_focus_correction(args.run_id, args.task_id, paths=args.path,
                principal=args.principal, actor=args.actor, checkpoint_id=args.id)
            output = {**state_summary(state), "resolutionChallenge": challenge}
        elif command == "focus-correction-apply":
            output = state_summary(store.apply_focus_correction(args.run_id, args.checkpoint_id,
                challenge=args.challenge, actor=args.actor))
        elif command == "feasibility-record":
            output = state_summary(store.record_feasibility(
                args.run_id, args.task_id, trigger=args.trigger, decision=args.decision,
                window={"timeoutSeconds": args.seconds, "maxTurns": args.turns, "maxOutputBytes": args.output_bytes},
                owner_ceiling={key: value for key, value in (
                    ("timeoutSeconds", args.owner_seconds), ("maxTurns", args.owner_turns),
                    ("maxOutputBytes", args.owner_output_bytes)) if value is not None},
                owner_deadline=args.owner_deadline, rationale=args.rationale, next_step=args.next_step,
                revisit=args.revisit, uncertainty=args.uncertainty, product_delta=args.product_delta,
                blocker=args.blocker,
                failed_hypotheses=args.hypothesis,
            ))
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
                    "pushback": args.pushback,
                    "effort": args.effort,
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
                    retry_hypothesis=args.retry_hypothesis,
                    retry_evidence=args.retry_evidence,
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
                    reviewer=args.reviewer,
                    effort=args.effort,
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
        elif command == "checkpoint-renew":
            state, challenge = store.renew_target_checkpoint(
                args.run_id,
                checkpoint_id=args.checkpoint_id,
                actor=args.actor,
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
        elif command == "reconcile-attest":
            output = state_summary(
                store.attest_side_effect_reconciliation(
                    args.run_id,
                    args.task_id,
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