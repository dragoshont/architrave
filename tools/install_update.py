#!/usr/bin/env python3
"""Canonical, stdlib-only Architrave repository installer and updater."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
import time


BEGIN = "<!-- architrave:begin -->"
END = "<!-- architrave:end -->"
KNOWLEDGE_AGENTS = (
    "architrave",
    "adversarial-judge",
    "tournament-analyst",
    "product-research",
    "runtime-observer",
)
GATE_FILES = (
    "checks.sh",
    "checks.ps1",
    "reconcile.sh",
    "reconcile.ps1",
    "quality-gate.sh",
    "quality-gate.ps1",
    "backend-checks.sh",
    "backend-checks.ps1",
    "gate_runner.py",
    "rubric.md",
)
IGNORE_RULES = (
    ".architrave/runs/",
    ".architrave/worktrees/",
    ".architrave/runtime.key",
    ".architrave/resources.lock",
)
APPLICATION_CONFIG = """{
  "platform": "web",
  "stack": "react",
  "designSource": { "type": "storybook", "path": ".storybook", "url": "http://localhost:6006" },
  "designMap": "docs/design/ui-map.json",
  "tokens": "tokens/tokens.json",
  "applyTo": ["src/**"],
  "build": "npm run build",
  "test": "npm test",
  "learning": {
    "runArtifactsPath": ".architrave/runs",
    "repoProfilePath": ".architrave/learning/repo-profile.md",
    "lessonsPath": ".architrave/learning/repo-lessons.md",
    "capture": ["run-artifacts", "gate-results", "judge-verdicts", "runtime-evidence", "repo-profile", "lessons"],
    "redactionPolicy": "no-secrets",
    "staleFactPolicy": "validate-before-use",
    "promotionPolicy": "approval-required",
    "promoteAfterOccurrences": 2,
    "promoteTargets": ["architrave.config.json", "AGENTS.md", ".github/instructions", "docs"]
  }
}
"""
EXECUTOR_REGISTRY_SCHEMA = "architrave.executor-registry.v1"
TARGET_IDENTITY_FIELDS = {
    "provider",
    "artifact",
    "version",
    "sha256",
    "environment",
    "workspace",
    "acceptanceTarget",
}


class InstallerError(Exception):
    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


def _lstat(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def _is_reparse(info: os.stat_result) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _is_real_dir(info: os.stat_result) -> bool:
    return stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode) and not _is_reparse(info)


def _is_regular_file(info: os.stat_result) -> bool:
    return stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode) and not _is_reparse(info)


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def trusted_user_state_root() -> Path:
    if os.name == "nt":
        import ctypes

        buffer = ctypes.create_unicode_buffer(32768)
        result = ctypes.windll.shell32.SHGetFolderPathW(None, 40, None, 0, buffer)
        if result != 0 or not buffer.value:
            raise InstallerError("executor-install: Windows user profile path is unavailable")
        home = Path(buffer.value)
    else:
        import pwd

        home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    if not home.is_absolute():
        raise InstallerError("executor-install: user profile path is not absolute")
    return home / ".architrave"


def _ensure_private_directory(path: Path, label: str) -> None:
    if not path.parent.is_dir():
        raise InstallerError(f"{label}: trusted state parent is unavailable or unsafe")
    path.mkdir(mode=0o700, exist_ok=True)
    info = path.lstat()
    if not _is_real_dir(info):
        raise InstallerError(f"{label}: trusted state directory is unsafe")
    if os.name != "nt":
        if info.st_uid != os.getuid():
            raise InstallerError(f"{label}: trusted state directory owner is unsafe")
        path.chmod(0o700)


def _atomic_private_json(path: Path, value: dict[str, object]) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, separators=(",", ":"), ensure_ascii=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _replace_private_bytes(content: bytes, destination: Path, label: str) -> None:
    _ensure_private_directory(destination.parent, label)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        _ensure_private_directory(destination.parent, label)
        os.replace(temporary, destination)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def install_exact_target_executor(args: argparse.Namespace, kit: Path) -> int:
    source = kit / "trusted" / "exact_target_observer.py"
    require_source_file(source, "executor-install")
    source_bytes = source.read_bytes()
    state_root = trusted_user_state_root()
    executors_root = state_root / "executors"
    source_digest = hashlib.sha256(source_bytes).hexdigest()
    executor_root = executors_root / "exact-target-v1" / source_digest[:32]
    adapter = executor_root / "observer.py"
    executable = Path(sys.executable).resolve()
    if not executable.is_absolute() or not _is_regular_file(executable.lstat()):
        raise InstallerError("executor-install: Python executable is unsafe")
    executable_digest = sha256_file(executable)
    remote = bool(args.ssh_host)
    artifact_path_value = args.artifact_path if remote else str(Path(args.artifact_path).expanduser())
    workspace_value = args.workspace if remote else str(Path(args.workspace).expanduser())
    paths_are_absolute = (
        PurePosixPath(artifact_path_value).is_absolute() and PurePosixPath(workspace_value).is_absolute()
        if remote
        else Path(artifact_path_value).is_absolute() and Path(workspace_value).is_absolute()
    )
    if not paths_are_absolute:
        raise InstallerError("executor-install: artifact path and workspace must be absolute", code=2)
    if not re.fullmatch(r"[0-9a-f]{64}", args.sha256):
        raise InstallerError("executor-install: target SHA-256 must be 64 lowercase hex characters", code=2)
    identity = {
        "provider": args.provider,
        "artifact": args.artifact,
        "version": args.version,
        "sha256": args.sha256,
        "environment": args.environment,
        "workspace": workspace_value,
        "acceptanceTarget": args.acceptance_target,
    }
    if any(not isinstance(value, str) or not value for value in identity.values()) or set(identity) != TARGET_IDENTITY_FIELDS:
        raise InstallerError("executor-install: target identity fields must be non-empty", code=2)
    registry_path = state_root / "executors.json"
    registry: dict[str, object]
    if registry_path.exists():
        info = registry_path.lstat()
        if not _is_regular_file(info):
            raise InstallerError("executor-install: trusted executor registry is unsafe")
        if os.name != "nt" and (info.st_uid != os.getuid() or (info.st_mode & 0o077) != 0):
            raise InstallerError("executor-install: trusted executor registry permissions are unsafe")
        try:
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise InstallerError("executor-install: trusted executor registry is invalid") from exc
        if registry.get("schema") != EXECUTOR_REGISTRY_SCHEMA or not isinstance(registry.get("exactTarget"), dict):
            raise InstallerError("executor-install: trusted executor registry schema is invalid")
        targets = registry["exactTarget"].get("targets")
        if not isinstance(targets, list):
            raise InstallerError("executor-install: trusted target registry is invalid")
    else:
        registry = {"schema": EXECUTOR_REGISTRY_SCHEMA, "exactTarget": {"targets": []}}
        targets = registry["exactTarget"]["targets"]
    ssh_settings = None
    identity_source = None
    known_hosts_source = None
    identity_bytes = None
    known_hosts_bytes = None
    ssh_base = None
    ssh_root = None
    if remote:
        required_remote = {
            "ssh_user": args.ssh_user,
            "ssh_host_key_alias": args.ssh_host_key_alias,
            "ssh_executable": args.ssh_executable,
            "ssh_identity": args.ssh_identity,
            "ssh_known_hosts": args.ssh_known_hosts,
            "ssh_remote_python": args.ssh_remote_python,
            "ssh_remote_adapter": args.ssh_remote_adapter,
            "ssh_remote_adapter_sha256": args.ssh_remote_adapter_sha256,
        }
        if any(not value for value in required_remote.values()):
            raise InstallerError("executor-install: all SSH trust settings are required for a remote target", code=2)
        if (
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", args.ssh_host)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", args.ssh_host_key_alias)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", args.ssh_user)
            or not re.fullmatch(r"/[A-Za-z0-9_./+-]+", args.ssh_remote_python)
            or not re.fullmatch(r"/[A-Za-z0-9_./+-]+", args.ssh_remote_adapter)
            or not re.fullmatch(r"[0-9a-f]{64}", args.ssh_remote_adapter_sha256)
        ):
            raise InstallerError("executor-install: SSH host, user, remote paths, or adapter pin are invalid", code=2)
        ssh_executable = Path(args.ssh_executable).expanduser().resolve()
        identity_source = Path(args.ssh_identity).expanduser().resolve()
        known_hosts_source = Path(args.ssh_known_hosts).expanduser().resolve()
        for path, label in (
            (ssh_executable, "SSH executable"),
            (identity_source, "SSH identity"),
            (known_hosts_source, "SSH known-hosts"),
        ):
            if not path.is_absolute() or not _is_regular_file(path.lstat()):
                raise InstallerError(f"executor-install: {label} is unsafe")
        identity_bytes = identity_source.read_bytes()
        known_hosts_bytes = known_hosts_source.read_bytes()
        identity_digest = hashlib.sha256(identity_bytes).hexdigest()
        known_hosts_digest = hashlib.sha256(known_hosts_bytes).hexdigest()
        relay_id = hashlib.sha256(
            (
                f"{args.ssh_user}@{args.ssh_host}:{args.ssh_port}\0"
                f"{identity_digest}\0{known_hosts_digest}\0"
                f"{json.dumps(identity, separators=(',', ':'), sort_keys=True)}\0"
                f"{artifact_path_value}\0{workspace_value}"
            ).encode("utf-8")
        ).hexdigest()[:16]
        ssh_base = state_root / "ssh"
        ssh_root = ssh_base / relay_id
        identity_path = ssh_root / "identity"
        known_hosts = ssh_root / "known_hosts"
        ssh_settings = {
            "executable": str(ssh_executable),
            "executableSha256": sha256_file(ssh_executable),
            "host": args.ssh_host,
            "hostKeyAlias": args.ssh_host_key_alias,
            "port": args.ssh_port,
            "user": args.ssh_user,
            "identityFile": str(identity_path),
            "identityFileSha256": identity_digest,
            "knownHosts": str(known_hosts),
            "knownHostsSha256": known_hosts_digest,
            "remotePython": args.ssh_remote_python,
            "remoteAdapter": args.ssh_remote_adapter,
            "remoteAdapterSha256": args.ssh_remote_adapter_sha256,
        }
    target = {
        "identity": identity,
        "transport": "ssh" if remote else "local",
        "artifactPath": artifact_path_value,
        "workspaceMode": args.workspace_mode,
        "ssh": ssh_settings,
    }
    targets[:] = [
        item
        for item in targets
        if not isinstance(item, dict) or item.get("identity") != identity
    ]
    targets.append(target)
    providers = sorted(
        {
            item["identity"]["provider"]
            for item in targets
            if isinstance(item, dict)
            and isinstance(item.get("identity"), dict)
            and isinstance(item["identity"].get("provider"), str)
        }
    )
    _ensure_private_directory(state_root, "executor-install")
    _ensure_private_directory(executors_root, "executor-install")
    _ensure_private_directory(executors_root / "exact-target-v1", "executor-install")
    _ensure_private_directory(executor_root, "executor-install")
    _replace_private_bytes(source_bytes, adapter, "executor-install")
    if remote:
        assert ssh_base is not None and ssh_root is not None
        assert identity_bytes is not None and known_hosts_bytes is not None
        _ensure_private_directory(ssh_base, "executor-install")
        _ensure_private_directory(ssh_root, "executor-install")
        _replace_private_bytes(identity_bytes, Path(ssh_settings["identityFile"]), "executor-install")
        _replace_private_bytes(known_hosts_bytes, Path(ssh_settings["knownHosts"]), "executor-install")
    registry["exactTarget"] = {
        "executable": str(executable),
        "executableSha256": executable_digest,
        "adapter": str(adapter.resolve()),
        "adapterSha256": source_digest,
        "allowedProviders": providers,
        "allowedCheckpointTypes": ["SAFE_WRITE_TARGET_REQUIRED"],
        "timeoutSeconds": args.timeout_seconds,
        "targets": targets,
    }
    _atomic_private_json(registry_path, registry)
    print(f"Architrave trusted exact-target executor installed: {adapter}")
    print(f"Trusted target enrolled for provider: {args.provider}")
    return 0


def require_source_file(path: Path, label: str) -> None:
    info = _lstat(path)
    if info is None or not _is_regular_file(info):
        raise InstallerError(f"{label}: packaged source is not a regular non-link file: {path}")
    try:
        with path.open("rb") as stream:
            stream.read(1)
    except OSError as exc:
        raise InstallerError(f"{label}: packaged source is not readable: {path}") from exc


def require_source_tree(path: Path, label: str) -> None:
    info = _lstat(path)
    if info is None or not _is_real_dir(info):
        raise InstallerError(f"{label}: packaged source is not a real directory: {path}")
    for current, directories, files in os.walk(path, followlinks=False):
        current_path = Path(current)
        for name in (*directories, *files):
            entry = current_path / name
            entry_info = _lstat(entry)
            if entry_info is None:
                raise InstallerError(f"{label}: packaged source disappeared: {entry}")
            if name in directories:
                valid = _is_real_dir(entry_info)
            else:
                valid = _is_regular_file(entry_info)
            if not valid:
                raise InstallerError(f"{label}: packaged source tree contains an unsafe entry: {entry}")
            if name in files:
                require_source_file(entry, label)


class ManagedRoot:
    """Fail-closed writes confined to one canonical repository root."""

    def __init__(self, root: Path, label: str) -> None:
        try:
            resolved = root.expanduser().resolve(strict=True)
        except (FileNotFoundError, OSError) as exc:
            raise InstallerError(f"{label}: target dir not found: {root}") from exc
        info = _lstat(resolved)
        if info is None or not _is_real_dir(info):
            raise InstallerError(f"{label}: target root must resolve to a real directory")
        self.root = resolved
        self.label = label
        self.transaction: ManagedTransaction | None = None
        self.planned_dirs: set[Path] = set()

    def path(self, relative: str) -> Path:
        pure = PurePosixPath(relative)
        raw_parts = relative.split("/")
        if (
            not relative
            or pure.is_absolute()
            or "\\" in relative
            or any(part in ("", ".", "..") for part in raw_parts)
        ):
            raise InstallerError(f"{self.label}: unsafe managed path '{relative}'")
        candidate = self.root.joinpath(*pure.parts)
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise InstallerError(f"{self.label}: managed path escapes target root: {relative}") from exc
        return candidate

    def preflight_dir(self, relative: str) -> None:
        path = self.path(relative)
        current = self.root
        for part in path.relative_to(self.root).parts:
            current /= part
            info = _lstat(current)
            if info is None:
                return
            if not _is_real_dir(info):
                raise InstallerError(
                    f"{self.label}: unsafe managed path '{relative}': "
                    f"component '{part}' is not a real directory"
                )

    def require_dir(self, relative: str) -> Path:
        self.preflight_dir(relative)
        path = self.path(relative)
        info = _lstat(path)
        if info is None and path in self.planned_dirs:
            return path
        if info is None or not _is_real_dir(info):
            raise InstallerError(
                f"{self.label}: unsafe managed path '{relative}': directory is missing or unsafe"
            )
        return path

    def ensure_dir(self, relative: str) -> Path:
        path = self.path(relative)
        if self.transaction is not None:
            self.preflight_dir(relative)
            self.planned_dirs.add(path)
            return path
        current = self.root
        built: list[str] = []
        for part in path.relative_to(self.root).parts:
            current /= part
            built.append(part)
            info = _lstat(current)
            if info is None:
                current.mkdir()
            elif not _is_real_dir(info):
                raise InstallerError(
                    f"{self.label}: unsafe managed path '{relative}': "
                    f"component '{part}' is not a real directory"
                )
            self.require_dir("/".join(built))
        return path

    def preflight_file(self, relative: str) -> None:
        path = self.path(relative)
        parent = path.parent
        if parent != self.root:
            self.preflight_dir(parent.relative_to(self.root).as_posix())
        info = _lstat(path)
        if info is not None and not _is_regular_file(info):
            raise InstallerError(
                f"{self.label}: unsafe managed path '{relative}': "
                "destination is not a regular non-link file"
            )

    def require_file(self, relative: str) -> Path:
        self.preflight_file(relative)
        path = self.path(relative)
        info = _lstat(path)
        if info is None or not _is_regular_file(info):
            raise InstallerError(
                f"{self.label}: unsafe managed path '{relative}': regular file is missing or unsafe"
            )
        return path

    def preflight_tree(self, relative: str) -> None:
        self.preflight_dir(relative)
        path = self.path(relative)
        info = _lstat(path)
        if info is None:
            return
        if not _is_real_dir(info):
            raise InstallerError(f"{self.label}: unsafe managed tree '{relative}'")
        for current, directories, files in os.walk(path, followlinks=False):
            current_path = Path(current)
            for name in (*directories, *files):
                entry = current_path / name
                entry_info = _lstat(entry)
                if entry_info is None:
                    raise InstallerError(f"{self.label}: managed entry disappeared: {entry}")
                if name in directories:
                    valid = _is_real_dir(entry_info)
                else:
                    valid = _is_regular_file(entry_info)
                if not valid:
                    raise InstallerError(
                        f"{self.label}: unsafe managed tree '{relative}': unsafe entry '{entry}'"
                    )

    def _write_temp(self, parent: Path, data: bytes, mode: int) -> Path:
        if parent != self.root:
            self.require_dir(parent.relative_to(self.root).as_posix())
        temp = parent / f".architrave.tmp.{uuid.uuid4().hex}"
        descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temp, stat.S_IMODE(mode))
            return temp
        except Exception:
            try:
                os.close(descriptor)
            except OSError:
                pass
            temp.unlink(missing_ok=True)
            raise

    def replace_bytes(self, relative: str, data: bytes, mode: int = 0o644) -> None:
        if self.transaction is not None:
            self.transaction.stage_write(relative, data, mode, create_only=False)
            return
        self.preflight_file(relative)
        path = self.path(relative)
        parent_relative = path.parent.relative_to(self.root).as_posix()
        parent = self.root if path.parent == self.root else self.require_dir(parent_relative)
        temp = self._write_temp(parent, data, mode)
        try:
            self.preflight_file(relative)
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)
        self.require_file(relative)

    def create_bytes(self, relative: str, data: bytes, mode: int = 0o644) -> None:
        if self.transaction is not None:
            self.transaction.stage_write(relative, data, mode, create_only=True)
            return
        self.preflight_file(relative)
        path = self.path(relative)
        if _lstat(path) is not None:
            raise InstallerError(f"{self.label}: managed destination already exists: {relative}")
        parent_relative = path.parent.relative_to(self.root).as_posix()
        if path.parent != self.root:
            self.require_dir(parent_relative)
        try:
            self.preflight_file(relative)
            if _lstat(path) is not None:
                raise InstallerError(f"{self.label}: managed destination appeared before create: {relative}")
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IMODE(mode))
        except FileExistsError as exc:
            raise InstallerError(
                f"{self.label}: managed destination appeared before create: {relative}"
            ) from exc
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(path, stat.S_IMODE(mode))
        except Exception:
            try:
                os.close(descriptor)
            except OSError:
                pass
            path.unlink(missing_ok=True)
            raise
        self.require_file(relative)

    def replace_file(self, source: Path, relative: str) -> None:
        require_source_file(source, self.label)
        source_info = source.stat(follow_symlinks=False)
        self.replace_bytes(relative, source.read_bytes(), stat.S_IMODE(source_info.st_mode))

    def create_file(self, source: Path, relative: str) -> None:
        require_source_file(source, self.label)
        source_info = source.stat(follow_symlinks=False)
        self.create_bytes(relative, source.read_bytes(), stat.S_IMODE(source_info.st_mode))

    def remove_file(self, relative: str) -> None:
        if self.transaction is not None:
            self.transaction.stage_remove(relative)
            return
        self.preflight_file(relative)
        path = self.path(relative)
        if _lstat(path) is None:
            return
        self.require_file(relative)
        path.unlink()
        if _lstat(path) is not None:
            raise InstallerError(f"{self.label}: managed file remains after removal: {relative}")

    def copy_tree(self, source: Path, relative: str) -> None:
        require_source_tree(source, self.label)
        self.preflight_tree(relative)
        self.ensure_dir(relative)
        for current, directories, files in os.walk(source, followlinks=False):
            directories[:] = sorted(name for name in directories if name != "__pycache__")
            files = sorted(name for name in files if not name.endswith(".pyc"))
            current_path = Path(current)
            suffix = current_path.relative_to(source)
            destination_dir = PurePosixPath(relative, *suffix.parts).as_posix()
            self.ensure_dir(destination_dir)
            for name in files:
                destination = PurePosixPath(destination_dir, name).as_posix()
                self.replace_file(current_path / name, destination)


class ManagedTransaction:
    active: list["ManagedTransaction"] = []

    def __init__(self, managed: ManagedRoot) -> None:
        self.managed = managed
        self.root = managed.root
        self.lock = self.root / ".architrave-install.lock"
        self.directory = self.root / ".architrave-install-transaction"
        self.operations: list[dict[str, object]] = []
        self.created_dirs: set[Path] = set()

    def _write_manifest(self, value: dict[str, object]) -> None:
        path = self.directory / "manifest.json"
        path.write_text(json.dumps(value, separators=(",", ":")) + "\n", encoding="utf-8")
        with path.open("r+b") as stream:
            os.fsync(stream.fileno())

    def _recover(self) -> None:
        manifest_path = self.directory / "manifest.json"
        if not manifest_path.is_file():
            raise InstallerError(f"{self.managed.label}: stale transaction has no recovery manifest")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for item in reversed(manifest.get("operations", [])):
            destination = self.managed.path(str(item["relative"]))
            backup = self.directory / str(item["backup"]) if item.get("backup") else None
            if backup and backup.is_file():
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(backup, destination)
            elif not item.get("existed"):
                destination.unlink(missing_ok=True)
        for directory in sorted(
            (self.root / value for value in manifest.get("createdDirectories", [])),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            try:
                directory.rmdir()
            except OSError:
                pass
        shutil.rmtree(self.directory)

    def __enter__(self) -> "ManagedTransaction":
        try:
            descriptor = os.open(self.lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            try:
                owner = json.loads(self.lock.read_text(encoding="utf-8"))
                alive = _pid_alive(int(owner["pid"]))
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                alive = False
            if not alive:
                self.lock.unlink(missing_ok=True)
                descriptor = os.open(self.lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            else:
                raise InstallerError(f"{self.managed.label}: target is locked by another install/update")
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump({"pid": os.getpid(), "createdAt": time.time()}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        if self.directory.exists():
            self._recover()
        self.directory.mkdir()
        (self.directory / "stage").mkdir()
        (self.directory / "backup").mkdir()
        self.managed.transaction = self
        self.active.append(self)
        return self

    def stage_write(self, relative: str, data: bytes, mode: int, *, create_only: bool) -> None:
        self.managed.preflight_file(relative)
        destination = self.managed.path(relative)
        if create_only and _lstat(destination) is not None:
            raise InstallerError(f"{self.managed.label}: managed destination already exists: {relative}")
        index = len(self.operations)
        stage = self.directory / "stage" / str(index)
        stage.write_bytes(data)
        os.chmod(stage, stat.S_IMODE(mode))
        self.operations.append(
            {"kind": "write", "relative": relative, "stage": f"stage/{index}", "mode": mode}
        )
        parent = destination.parent
        while parent != self.root and _lstat(parent) is None:
            self.created_dirs.add(parent)
            parent = parent.parent

    def stage_remove(self, relative: str) -> None:
        self.managed.preflight_file(relative)
        self.operations.append({"kind": "remove", "relative": relative})

    def commit(self) -> None:
        manifest_operations: list[dict[str, object]] = []
        for index, operation in enumerate(self.operations):
            destination = self.managed.path(str(operation["relative"]))
            info = _lstat(destination)
            backup_name = None
            if info is not None:
                self.managed.require_file(str(operation["relative"]))
                backup_name = f"backup/{index}"
                shutil.copy2(destination, self.directory / backup_name, follow_symlinks=False)
            manifest_operations.append(
                {
                    **operation,
                    "existed": info is not None,
                    "backup": backup_name,
                }
            )
        manifest = {
            "status": "prepared",
            "applied": 0,
            "operations": manifest_operations,
            "createdDirectories": [
                path.relative_to(self.root).as_posix()
                for path in sorted(self.created_dirs, key=lambda value: len(value.parts))
            ],
        }
        self._write_manifest(manifest)
        fail_after = os.environ.get("ARCHITRAVE_INSTALL_FAIL_AFTER")
        try:
            for index, operation in enumerate(manifest_operations):
                if fail_after is not None and int(fail_after) == index:
                    raise OSError(f"injected install/update failure at replacement {index}")
                relative = str(operation["relative"])
                destination = self.managed.path(relative)
                destination.parent.mkdir(parents=True, exist_ok=True)
                if operation["kind"] == "write":
                    stage = self.directory / str(operation["stage"])
                    os.replace(stage, destination)
                    os.chmod(destination, stat.S_IMODE(int(operation["mode"])))
                else:
                    destination.unlink(missing_ok=True)
                manifest["applied"] = index + 1
                self._write_manifest(manifest)
        except Exception:
            self._recover()
            raise
        shutil.rmtree(self.directory)
        if self in self.active:
            self.active.remove(self)

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.managed.transaction = None
        try:
            if exc_type is None:
                self.commit()
            elif self.directory.exists():
                shutil.rmtree(self.directory)
        finally:
            self.lock.unlink(missing_ok=True)
            if self in self.active:
                self.active.remove(self)

    def abort(self) -> None:
        self.managed.transaction = None
        if self.directory.exists():
            shutil.rmtree(self.directory)
        self.lock.unlink(missing_ok=True)
        if self in self.active:
            self.active.remove(self)


class JsonObject(list[tuple[str, object]]):
    pass


def read_update_profile(config_path: Path) -> str:
    try:
        parsed = json.loads(
            config_path.read_text(encoding="utf-8-sig"),
            object_pairs_hook=lambda pairs: JsonObject(pairs),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InstallerError(f"update: invalid architrave.config.json ({exc})", 2) from exc
    if not isinstance(parsed, JsonObject):
        raise InstallerError("update: invalid architrave.config.json (root must be a JSON object)", 2)
    kind_like = [key for key, _ in parsed if key.lower() == "kind"]
    if any(key != "kind" for key in kind_like):
        raise InstallerError(
            "update: invalid architrave.config.json (kind property is case-sensitive)", 2
        )
    kinds = [value for key, value in parsed if key == "kind"]
    if len(kinds) > 1:
        raise InstallerError(
            "update: invalid architrave.config.json (kind must occur at most once)", 2
        )
    if not kinds:
        return "application"
    if kinds[0] != "knowledge" or not isinstance(kinds[0], str):
        raise InstallerError(
            "update: invalid architrave.config.json (kind must be absent or 'knowledge')", 2
        )
    return "knowledge"


def plugin_version(kit: Path, label: str) -> str:
    try:
        manifest = json.loads((kit / "plugin.json").read_text(encoding="utf-8"))
        version = manifest["version"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise InstallerError(f"{label}: plugin version is invalid") from exc
    if not isinstance(version, str) or not version:
        raise InstallerError(f"{label}: plugin version is invalid")
    return version


def preflight_common(
    managed: ManagedRoot,
    kit: Path,
    *,
    source_trees: tuple[str, ...],
    destination_trees: tuple[str, ...],
    destination_files: tuple[str, ...],
    source_files: tuple[str, ...],
) -> None:
    for source_tree in source_trees:
        require_source_tree(kit / source_tree, managed.label)
    for source_file in source_files:
        require_source_file(kit / source_file, managed.label)
    for destination_tree in destination_trees:
        managed.preflight_tree(destination_tree)
    for destination_file in destination_files:
        managed.preflight_file(destination_file)


def preflight_text(managed: ManagedRoot, relative: str) -> None:
    path = managed.path(relative)
    if _lstat(path) is None:
        return
    try:
        managed.require_file(relative).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise InstallerError(f"{managed.label}: managed text file is not readable UTF-8: {relative}") from exc


def run_codex(kit: Path, managed: ManagedRoot, *, preflight: bool, label: str) -> None:
    if sys.version_info < (3, 11):
        raise InstallerError(f"{label}: --codex requires Python 3.11+", 2)
    helper = kit / "tools" / "codex-roles.py"
    spec = importlib.util.spec_from_file_location("architrave_codex_roles", helper)
    if spec is None or spec.loader is None:
        raise InstallerError(f"{label}: cannot load Codex role helper")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    outputs = module.planned_outputs(kit, managed.root)
    if preflight:
        return
    for destination, content in outputs:
        relative = destination.relative_to(managed.root).as_posix()
        managed.ensure_dir(destination.parent.relative_to(managed.root).as_posix())
        managed.replace_bytes(relative, content)


def install_agents(managed: ManagedRoot, kit: Path, profile: str) -> None:
    managed.ensure_dir(".github/agents")
    if profile == "knowledge":
        for name in KNOWLEDGE_AGENTS:
            managed.replace_file(kit / "agents" / f"{name}.agent.md", f".github/agents/{name}.agent.md")
        print("  ok agents -> .github/agents/ (knowledge crew)")
        return
    for source in sorted((kit / "agents").glob("*.agent.md")):
        managed.replace_file(source, f".github/agents/{source.name}")
    print("  ok agents -> .github/agents/")


def update_agents(managed: ManagedRoot, kit: Path, profile: str) -> None:
    managed.ensure_dir(".github/agents")
    if profile == "knowledge":
        retained = {f"{name}.agent.md" for name in KNOWLEDGE_AGENTS}
        for source in sorted((kit / "agents").glob("*.agent.md")):
            if source.name not in retained:
                managed.remove_file(f".github/agents/{source.name}")
        for name in KNOWLEDGE_AGENTS:
            managed.replace_file(kit / "agents" / f"{name}.agent.md", f".github/agents/{name}.agent.md")
        print("  ok agents refreshed (knowledge crew)")
        return
    for source in sorted((kit / "agents").glob("*.agent.md")):
        managed.replace_file(source, f".github/agents/{source.name}")
    print("  ok agents refreshed")


def copy_shared_assets(managed: ManagedRoot, kit: Path) -> None:
    managed.ensure_dir("gates/hooks")
    for name in GATE_FILES:
        managed.replace_file(kit / "gates" / name, f"gates/{name}")
    managed.copy_tree(kit / "gates" / "hooks", "gates/hooks")
    print("  ok gates")
    managed.ensure_dir("knowledge")
    managed.copy_tree(kit / "knowledge", "knowledge")
    print("  ok knowledge")
    managed.ensure_dir("harness")
    managed.copy_tree(kit / "harness", "harness")
    print("  ok harness")


def active_hook(kit: Path, entrypoint: str) -> Path:
    name = "design-guard.windows.json" if entrypoint == "windows" else "design-guard.json"
    return kit / "gates" / "hooks" / name


def update_gitignore(managed: ManagedRoot) -> None:
    path = managed.path(".gitignore")
    if _lstat(path) is None:
        content = ""
    else:
        content = managed.require_file(".gitignore").read_text(encoding="utf-8")
    existing = set(content.splitlines())
    missing = [rule for rule in IGNORE_RULES if rule not in existing]
    if not missing:
        print("  - .gitignore already ignores Architrave private runtime files")
        return
    content += "\n# Architrave: private run evidence and isolated worker trees stay local.\n"
    content += "".join(f"{rule}\n" for rule in missing)
    managed.replace_bytes(".gitignore", content.encode("utf-8"))
    print("  ok .gitignore updated")


def update_agents_stanza(managed: ManagedRoot, kit: Path) -> None:
    path = managed.path("AGENTS.md")
    if _lstat(path) is None:
        content = "# AGENTS.md\n"
    else:
        content = managed.require_file("AGENTS.md").read_text(encoding="utf-8")
    while True:
        begin = content.find(BEGIN)
        if begin < 0:
            break
        end = content.find(END, begin + len(BEGIN))
        if end < 0:
            content = content[:begin]
            break
        content = content[:begin] + content[end + len(END) :]
    stanza = (kit / "templates" / "AGENTS.stanza.md").read_text(encoding="utf-8").rstrip()
    refreshed = f"{content.rstrip()}\n\n{BEGIN}\n{stanza}\n{END}\n"
    managed.replace_bytes("AGENTS.md", refreshed.encode("utf-8"))
    print("  ok AGENTS.md stanza refreshed")


def assert_required_tree_staged(transaction: ManagedTransaction) -> None:
    staged = {str(item["relative"]) for item in transaction.operations if item["kind"] == "write"}
    required = {
        "harness/architrave_runtime.py",
        "knowledge/execution-policy.md",
        "gates/hooks/design-guard.json",
    }
    missing = sorted(required - staged)
    if missing:
        raise InstallerError(
            "install/update transaction is missing required managed tree files: " + ", ".join(missing)
        )


def install(args: argparse.Namespace, kit: Path) -> int:
    managed = ManagedRoot(Path(args.target or os.getcwd()), "install")
    if managed.root == kit:
        raise InstallerError("install: refusing to install the kit into itself")
    constitutions = tuple(sorted(kit.glob("constitution-*.md")))
    source_files = (
        "templates/AGENTS.stanza.md",
        "templates/copilot-setup-steps.yml",
        "plugin.json",
        "gates/hooks/design-guard.json",
        "gates/hooks/design-guard.windows.json",
    )
    if args.profile == "knowledge":
        source_files += ("kit/examples/knowledge.architrave.json",)
    elif not constitutions:
        raise InstallerError("install: packaged constitutions are missing")
    preflight_common(
        managed,
        kit,
        source_trees=("agents", "gates", "knowledge", "harness"),
        destination_trees=(
            ".github/agents",
            ".github/hooks",
            ".github/workflows",
            "gates",
            "gates/hooks",
            "knowledge",
            "harness",
        ),
        destination_files=(
            "architrave.config.json",
            ".gitignore",
            "AGENTS.md",
            "constitution-apple.md",
            "constitution-windows.md",
            ".github/hooks/design-guard.json",
            ".github/workflows/copilot-setup-steps.yml",
            "gates/.kit-version",
        ),
        source_files=source_files,
    )
    for source in constitutions:
        require_source_file(source, "install")
    for relative in (".gitignore", "AGENTS.md"):
        preflight_text(managed, relative)
    try:
        (kit / "templates" / "AGENTS.stanza.md").read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise InstallerError("install: packaged AGENTS stanza is not readable UTF-8") from exc
    version = plugin_version(kit, "install")
    if args.codex:
        run_codex(kit, managed, preflight=True, label="install")

    transaction = ManagedTransaction(managed)
    transaction.__enter__()
    print(f"Architrave -> installing into: {managed.root}")
    for directory in (".github/agents", ".github/hooks", ".github/workflows", "gates/hooks", "knowledge", "harness"):
        managed.ensure_dir(directory)
    install_agents(managed, kit, args.profile)
    copy_shared_assets(managed, kit)
    if args.profile == "application":
        for source in constitutions:
            managed.replace_file(source, source.name)
        print("  ok constitution -> constitution-*.md")
    else:
        print("  - constitution-*.md skipped (knowledge profile)")

    config = managed.path("architrave.config.json")
    if _lstat(config) is None:
        if args.profile == "knowledge":
            managed.create_file(kit / "kit" / "examples" / "knowledge.architrave.json", "architrave.config.json")
        else:
            managed.create_bytes("architrave.config.json", APPLICATION_CONFIG.encode("utf-8"))
        print(f"  ok scaffolded architrave.config.json (profile: {args.profile})")
    else:
        print("  - architrave.config.json present - left as-is")

    update_gitignore(managed)
    update_agents_stanza(managed, kit)
    managed.replace_file(active_hook(kit, args.entrypoint), ".github/hooks/design-guard.json")
    print("  ok .github/hooks/design-guard.json")
    setup = managed.path(".github/workflows/copilot-setup-steps.yml")
    if _lstat(setup) is None:
        managed.create_file(
            kit / "templates" / "copilot-setup-steps.yml",
            ".github/workflows/copilot-setup-steps.yml",
        )
        print("  ok .github/workflows/copilot-setup-steps.yml")
    else:
        print("  - copilot-setup-steps.yml present - merge jq install manually")
    if args.codex:
        run_codex(kit, managed, preflight=False, label="install")
    assert_required_tree_staged(transaction)
    managed.replace_bytes("gates/.kit-version", f"{version}\n".encode("utf-8"))
    transaction.__exit__(None, None, None)
    print(f"  ok stamped gates/.kit-version = {version}")
    print(f"\nDone. Edit architrave.config.json to match this repo (profile: {args.profile}).")
    return 0


def update(args: argparse.Namespace, kit: Path) -> int:
    managed = ManagedRoot(Path(args.target or os.getcwd()), "update")
    if managed.root == kit:
        raise InstallerError("update: refusing to update the kit into itself")
    managed.preflight_file("architrave.config.json")
    config = managed.path("architrave.config.json")
    if _lstat(config) is None:
        raise InstallerError(
            f"update: {managed.root} has no safe architrave.config.json - run tools/install first"
        )
    profile = read_update_profile(managed.require_file("architrave.config.json"))
    constitutions = tuple(sorted(kit.glob("constitution-*.md")))
    if profile == "application" and not constitutions:
        raise InstallerError("update: packaged constitutions are missing")
    source_trees = ("gates", "knowledge", "harness") + (("agents",) if args.agents else ())
    destination_trees = (".github/hooks", "gates", "gates/hooks", "knowledge", "harness")
    if args.agents:
        destination_trees += (".github/agents",)
    preflight_common(
        managed,
        kit,
        source_trees=source_trees,
        destination_trees=destination_trees,
        destination_files=(
            "architrave.config.json",
            ".gitignore",
            "AGENTS.md",
            "constitution-apple.md",
            "constitution-windows.md",
            ".github/hooks/design-guard.json",
            "gates/.kit-version",
        ),
        source_files=(
            "templates/AGENTS.stanza.md",
            "plugin.json",
            "gates/hooks/design-guard.json",
            "gates/hooks/design-guard.windows.json",
        ),
    )
    for source in constitutions:
        require_source_file(source, "update")
    for relative in (".gitignore", "AGENTS.md"):
        preflight_text(managed, relative)
    try:
        (kit / "templates" / "AGENTS.stanza.md").read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise InstallerError("update: packaged AGENTS stanza is not readable UTF-8") from exc
    if args.codex:
        run_codex(kit, managed, preflight=True, label="update")
    version = plugin_version(kit, "update")

    transaction = ManagedTransaction(managed)
    transaction.__enter__()
    print(f"Architrave -> refreshing assets in: {managed.root} (kit v{version})")
    for directory in (".github/hooks", "gates/hooks", "knowledge", "harness"):
        managed.ensure_dir(directory)
    if args.agents:
        update_agents(managed, kit, profile)
    else:
        print("  - agents left unchanged (use --agents to refresh .github/agents/)")
    copy_shared_assets(managed, kit)
    managed.replace_file(active_hook(kit, args.entrypoint), ".github/hooks/design-guard.json")
    print("  ok active workspace hook refreshed")
    if profile == "knowledge":
        for name in ("constitution-apple.md", "constitution-windows.md"):
            managed.remove_file(name)
        print("  ok constitution removed/skipped (knowledge profile)")
    else:
        for source in constitutions:
            managed.replace_file(source, source.name)
        print("  ok constitution refreshed")
    update_gitignore(managed)
    update_agents_stanza(managed, kit)
    if args.codex:
        run_codex(kit, managed, preflight=False, label="update")
    assert_required_tree_staged(transaction)
    managed.replace_bytes("gates/.kit-version", f"{version}\n".encode("utf-8"))
    transaction.__exit__(None, None, None)
    print(f"  ok stamped gates/.kit-version = {version}")
    print("Done. (architrave.config.json left untouched.)")
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="install_update.py")
    subcommands = result.add_subparsers(dest="command", required=True)
    default_entrypoint = "windows" if os.name == "nt" else "posix"

    install_parser = subcommands.add_parser("install", add_help=False)
    install_parser.add_argument("-h", "--help", "-Help", action="help")
    install_parser.add_argument("--profile", "-Profile", choices=("application", "knowledge"), default="application")
    install_parser.add_argument("--codex", "-Codex", action="store_true")
    install_parser.add_argument("--entrypoint", choices=("posix", "windows"), default=default_entrypoint)
    install_parser.add_argument("target", nargs="?")

    update_parser = subcommands.add_parser("update", add_help=False)
    update_parser.add_argument("-h", "--help", "-Help", action="help")
    update_parser.add_argument("--agents", "-Agents", action="store_true")
    update_parser.add_argument("--codex", "-Codex", action="store_true")
    update_parser.add_argument("--entrypoint", choices=("posix", "windows"), default=default_entrypoint)
    update_parser.add_argument("target", nargs="?")

    executor = subcommands.add_parser("executor-install")
    executor.add_argument("--provider", required=True)
    executor.add_argument("--artifact", required=True)
    executor.add_argument("--artifact-path", required=True)
    executor.add_argument("--version", required=True)
    executor.add_argument("--sha256", required=True)
    executor.add_argument("--environment", required=True)
    executor.add_argument("--workspace", required=True)
    executor.add_argument("--acceptance-target", required=True)
    executor.add_argument(
        "--workspace-mode",
        choices=("exact-directory", "absent-or-exact-directory"),
        default="exact-directory",
    )
    executor.add_argument("--timeout-seconds", type=int, choices=range(1, 31), default=10)
    executor.add_argument("--ssh-host")
    executor.add_argument("--ssh-host-key-alias")
    executor.add_argument("--ssh-port", type=int, choices=range(1, 65536), default=22)
    executor.add_argument("--ssh-user")
    executor.add_argument("--ssh-executable")
    executor.add_argument("--ssh-identity")
    executor.add_argument("--ssh-known-hosts")
    executor.add_argument("--ssh-remote-python")
    executor.add_argument("--ssh-remote-adapter")
    executor.add_argument("--ssh-remote-adapter-sha256")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    kit = Path(__file__).resolve().parents[1]
    try:
        if args.command == "install":
            return install(args, kit)
        if args.command == "update":
            return update(args, kit)
        return install_exact_target_executor(args, kit)
    except InstallerError as exc:
        if str(exc):
            print(str(exc), file=sys.stderr)
        return exc.code
    except (OSError, UnicodeError) as exc:
        print(f"{args.command}: {exc}", file=sys.stderr)
        return 1
    finally:
        for transaction in list(ManagedTransaction.active):
            transaction.abort()


if __name__ == "__main__":
    raise SystemExit(main())
