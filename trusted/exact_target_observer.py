#!/usr/bin/env python3
"""Read-only exact filesystem target observer for trusted Architrave installs."""

from __future__ import annotations

import hashlib
import base64
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import threading
import time
from typing import Any


REQUEST_SCHEMA = "architrave.exact-target-request.v1"
RESULT_SCHEMA = "architrave.exact-target-result.v1"
IDENTITY_FIELDS = {
    "provider",
    "artifact",
    "version",
    "sha256",
    "environment",
    "workspace",
    "acceptanceTarget",
}
REQUEST_LIMIT = 32 * 1024
STDOUT_LIMIT = 64 * 1024
STDERR_LIMIT = 8 * 1024
REMOTE_HELPER = r"""
import base64, hashlib, json, os, pathlib, stat, sys
request = json.loads(base64.b64decode("__REQUEST__").decode("utf-8"))
adapter = pathlib.Path("__ADAPTER__")
adapter_info = adapter.lstat()
if not stat.S_ISREG(adapter_info.st_mode) or adapter.is_symlink() or (getattr(adapter_info, "st_file_attributes", 0) & 0x400):
    raise SystemExit("remote adapter must be a regular non-link file")
adapter_bytes = adapter.read_bytes()
if hashlib.sha256(adapter_bytes).hexdigest() != "__ADAPTER_SHA256__":
    raise SystemExit("remote adapter SHA-256 does not match")
binding = request["binding"]
intended = request["intended"]
target = request["target"]
namespace = {"__name__": "architrave_remote_observer", "__file__": str(adapter)}
exec(compile(adapter_bytes, str(adapter), "exec"), namespace)
result = namespace["observe_local"](request)
result["observation"]["transport"] = "ssh"
sys.stdout.write(json.dumps(result, separators=(",", ":"), ensure_ascii=True))
"""


def fail(message: str) -> int:
    print(message[:1000], file=sys.stderr)
    return 1


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_stream(handle: Any) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def is_reparse(info: os.stat_result) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & 0x400)


def validate_path_components(path: Path, label: str) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            return
        if current.is_symlink() or is_reparse(info):
            raise ValueError(f"{label} path contains a link or reparse point")


def duplicate_reject(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def verify_file(path_value: Any, digest_value: Any, label: str) -> Path:
    path = Path(str(path_value))
    if not path.is_absolute() or not isinstance(digest_value, str) or len(digest_value) != 64:
        raise ValueError(f"{label} path or pin is invalid")
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or path.is_symlink() or is_reparse(info):
        raise ValueError(f"{label} must be a regular non-link file")
    if sha256_file(path) != digest_value:
        raise ValueError(f"{label} SHA-256 pin does not match")
    return path


def bounded_reader(stream: Any, limit: int, output: bytearray, overflow: threading.Event) -> None:
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


def invoke_ssh(ssh: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "executable",
        "executableSha256",
        "host",
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
    if set(ssh) != fields:
        raise ValueError("SSH settings are invalid")
    executable = verify_file(ssh["executable"], ssh["executableSha256"], "SSH executable")
    identity = verify_file(ssh["identityFile"], ssh["identityFileSha256"], "SSH identity")
    known_hosts = verify_file(ssh["knownHosts"], ssh["knownHostsSha256"], "SSH known-hosts")
    safe_atom = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    safe_remote_path = re.compile(r"^/[A-Za-z0-9_./+-]+$")
    if (
        not isinstance(ssh["host"], str)
        or not safe_atom.fullmatch(ssh["host"])
        or not isinstance(ssh["user"], str)
        or not safe_atom.fullmatch(ssh["user"])
        or not isinstance(ssh["port"], int)
        or isinstance(ssh["port"], bool)
        or not 1 <= ssh["port"] <= 65535
        or not isinstance(ssh["remotePython"], str)
        or not safe_remote_path.fullmatch(ssh["remotePython"])
        or not isinstance(ssh["remoteAdapter"], str)
        or not safe_remote_path.fullmatch(ssh["remoteAdapter"])
        or not isinstance(ssh["remoteAdapterSha256"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", ssh["remoteAdapterSha256"])
    ):
        raise ValueError("SSH host or remote executable settings are invalid")
    remote_request = {
        **request,
        "target": {
            "transport": "local",
            "artifactPath": request["target"]["artifactPath"],
            "workspaceMode": request["target"]["workspaceMode"],
            "ssh": None,
        },
    }
    encoded_request = json.dumps(remote_request, separators=(",", ":"), sort_keys=True).encode("utf-8")
    helper = REMOTE_HELPER.replace(
        "__REQUEST__",
        base64.b64encode(encoded_request).decode("ascii"),
    ).replace(
        "__ADAPTER__",
        ssh["remoteAdapter"],
    ).replace(
        "__ADAPTER_SHA256__",
        ssh["remoteAdapterSha256"],
    ).encode("utf-8")
    null_config = "NUL" if os.name == "nt" else "/dev/null"
    process = subprocess.Popen(
        [
            str(executable),
            "-F",
            null_config,
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"UserKnownHostsFile={known_hosts}",
            "-i",
            str(identity),
            "-p",
            str(ssh["port"]),
            f"{ssh['user']}@{ssh['host']}",
            ssh["remotePython"],
            "-I",
            "-S",
            "-",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        env={
            key: value
            for key, value in os.environ.items()
            if key.upper() in {"SYSTEMROOT", "WINDIR", "TMP", "TEMP", "TMPDIR"}
        },
    )
    stdout = bytearray()
    stderr = bytearray()
    stdout_overflow = threading.Event()
    stderr_overflow = threading.Event()
    threads = [
        threading.Thread(target=bounded_reader, args=(process.stdout, STDOUT_LIMIT, stdout, stdout_overflow), daemon=True),
        threading.Thread(target=bounded_reader, args=(process.stderr, STDERR_LIMIT, stderr, stderr_overflow), daemon=True),
    ]
    for thread in threads:
        thread.start()
    try:
        assert process.stdin is not None
        process.stdin.write(helper)
        process.stdin.close()
        deadline = time.monotonic() + 30
        while process.poll() is None:
            if stdout_overflow.is_set() or stderr_overflow.is_set():
                process.kill()
                raise ValueError("SSH observer output exceeds the size limit")
            if time.monotonic() >= deadline:
                process.kill()
                raise ValueError("SSH observer timed out")
            time.sleep(0.01)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        for thread in threads:
            thread.join(timeout=1)
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()
    if process.returncode != 0:
        raise ValueError("SSH observer failed: " + bytes(stderr).decode("utf-8", "replace")[:1000])
    if stdout_overflow.is_set() or stderr_overflow.is_set():
        raise ValueError("SSH observer output exceeds the size limit")
    result = json.loads(bytes(stdout).decode("utf-8"), object_pairs_hook=duplicate_reject)
    if (
        not isinstance(result, dict)
        or result.get("schema") != RESULT_SCHEMA
        or result.get("binding") != request["binding"]
        or result.get("observed") != request["intended"]
    ):
        raise ValueError("remote observer result is invalid")
    result["observation"]["sshHost"] = ssh["host"]
    return result


def observe_local(request: dict[str, Any]) -> dict[str, Any]:
    binding = request["binding"]
    intended = request["intended"]
    target = request["target"]
    binding_fields = {
        "runId",
        "objectiveVersion",
        "revision",
        "taskId",
        "checkpointId",
        "checkpointType",
        "provider",
        "principal",
        "challengeHash",
    }
    if (
        not isinstance(binding, dict)
        or set(binding) != binding_fields
        or binding.get("checkpointType") != "SAFE_WRITE_TARGET_REQUIRED"
        or not isinstance(intended, dict)
        or set(intended) != IDENTITY_FIELDS
        or not isinstance(target, dict)
        or set(target) != {"transport", "artifactPath", "workspaceMode", "ssh"}
        or target.get("transport") != "local"
        or target.get("ssh") is not None
        or binding.get("provider") != intended.get("provider")
    ):
        raise ValueError("request binding is invalid")
    artifact = Path(str(target["artifactPath"]))
    workspace = Path(str(intended["workspace"]))
    if not artifact.is_absolute() or not workspace.is_absolute():
        raise ValueError("artifact and workspace paths must be absolute")
    validate_path_components(artifact, "artifact")
    validate_path_components(workspace, "workspace")
    try:
        artifact_info = artifact.lstat()
    except OSError:
        raise ValueError("artifact is unavailable")
    if not stat.S_ISREG(artifact_info.st_mode) or artifact.is_symlink() or is_reparse(artifact_info):
        raise ValueError("artifact must be a regular non-link file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(artifact), flags)
    except OSError:
        raise ValueError("artifact could not be opened without following links")
    with os.fdopen(descriptor, "rb") as handle:
        opened_info = os.fstat(handle.fileno())
        if not stat.S_ISREG(opened_info.st_mode):
            raise ValueError("opened artifact is not a regular file")
        artifact_digest = sha256_stream(handle)
    try:
        after_info = artifact.lstat()
    except OSError:
        raise ValueError("artifact changed during observation")
    identity_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    if any(getattr(opened_info, field) != getattr(after_info, field) for field in identity_fields):
        raise ValueError("artifact changed during observation")
    if artifact_digest != intended["sha256"]:
        raise ValueError("artifact SHA-256 does not match the trusted identity")
    workspace_mode = target["workspaceMode"]
    try:
        workspace_info = workspace.lstat()
    except FileNotFoundError:
        if workspace_mode != "absent-or-exact-directory":
            raise ValueError("workspace does not exist")
        workspace_state = "absent"
    except OSError:
        raise ValueError("workspace cannot be observed")
    else:
        if (
            workspace_mode not in {"exact-directory", "absent-or-exact-directory"}
            or not stat.S_ISDIR(workspace_info.st_mode)
            or workspace.is_symlink()
            or is_reparse(workspace_info)
        ):
            raise ValueError("workspace must be an exact non-link directory")
        workspace_state = "directory"
    result = {
        "schema": RESULT_SCHEMA,
        "status": "observed",
        "binding": binding,
        "observed": intended,
        "observation": {
            "artifactPath": str(artifact),
            "artifactSha256": artifact_digest,
            "artifactSize": opened_info.st_size,
            "workspacePath": str(workspace),
            "workspaceState": workspace_state,
            "observerSha256": sha256_file(Path(__file__)),
            "transport": "local",
        },
    }
    return result


def trusted_user_state_root() -> Path:
    if os.name == "nt":
        import ctypes

        buffer = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 40, None, 0, buffer) != 0:
            raise OSError("Windows user profile path is unavailable")
        return Path(buffer.value) / ".architrave"
    import pwd

    return Path(pwd.getpwuid(os.getuid()).pw_dir) / ".architrave"


def ensure_private_directory(path: Path) -> None:
    if not path.parent.is_dir():
        raise OSError("trusted state parent is unavailable or unsafe")
    path.mkdir(mode=0o700, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or path.is_symlink() or is_reparse(info):
        raise OSError("trusted state directory is unsafe")
    if os.name != "nt":
        if info.st_uid != os.getuid():
            raise OSError("trusted state directory owner is unsafe")
        path.chmod(0o700)


def install_self() -> int:
    root = trusted_user_state_root()
    executors_root = root / "executors"
    source = Path(__file__).resolve()
    source_bytes = source.read_bytes()
    source_digest = hashlib.sha256(source_bytes).hexdigest()
    version_root = executors_root / "exact-target-v1"
    destination_root = version_root / source_digest[:32]
    ensure_private_directory(root)
    ensure_private_directory(executors_root)
    ensure_private_directory(version_root)
    ensure_private_directory(destination_root)
    destination = destination_root / "observer.py"
    temporary = destination_root / (".observer." + str(os.getpid()) + ".tmp")
    temporary.write_bytes(source_bytes)
    if os.name != "nt":
        temporary.chmod(0o700)
    os.replace(str(temporary), str(destination))
    result = {"adapter": str(destination), "sha256": source_digest}
    sys.stdout.write(json.dumps(result, separators=(",", ":"), ensure_ascii=True))
    return 0


def main() -> int:
    if sys.argv[1:] == ["--install"]:
        return install_self()
    raw = sys.stdin.buffer.read(REQUEST_LIMIT + 1)
    if len(raw) > REQUEST_LIMIT:
        return fail("request exceeds size limit")
    try:
        request = json.loads(raw.decode("utf-8"), object_pairs_hook=duplicate_reject)
        if not isinstance(request, dict) or set(request) != {"schema", "binding", "intended", "target"}:
            raise ValueError("request schema is invalid")
        if request["schema"] != REQUEST_SCHEMA:
            raise ValueError("request schema is unsupported")
        target = request["target"]
        if not isinstance(target, dict):
            raise ValueError("target is invalid")
        if target.get("transport") == "ssh":
            result = invoke_ssh(target.get("ssh"), request)
        else:
            result = observe_local(request)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        return fail(str(exc) or "observation failed")
    sys.stdout.write(json.dumps(result, separators=(",", ":"), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
