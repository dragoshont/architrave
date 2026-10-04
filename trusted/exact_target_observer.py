#!/usr/bin/env python3
"""Read-only exact filesystem target observer for trusted Architrave installs."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import sys
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


def fail(message: str) -> int:
    print(message[:1000], file=sys.stderr)
    return 1


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_reparse(info: os.stat_result) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & 0x400)


def duplicate_reject(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def main() -> int:
    raw = sys.stdin.buffer.read(REQUEST_LIMIT + 1)
    if len(raw) > REQUEST_LIMIT:
        return fail("request exceeds size limit")
    try:
        request = json.loads(raw.decode("utf-8"), object_pairs_hook=duplicate_reject)
    except (UnicodeError, ValueError, json.JSONDecodeError):
        return fail("request is not valid JSON")
    if not isinstance(request, dict) or set(request) != {"schema", "binding", "intended", "target"}:
        return fail("request schema is invalid")
    if request["schema"] != REQUEST_SCHEMA:
        return fail("request schema is unsupported")
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
        or set(target) != {"artifactPath", "workspaceMode"}
        or binding.get("provider") != intended.get("provider")
    ):
        return fail("request binding is invalid")
    artifact = Path(str(target["artifactPath"]))
    workspace = Path(str(intended["workspace"]))
    if not artifact.is_absolute() or not workspace.is_absolute():
        return fail("artifact and workspace paths must be absolute")
    try:
        artifact_info = artifact.lstat()
    except OSError:
        return fail("artifact is unavailable")
    if not stat.S_ISREG(artifact_info.st_mode) or artifact.is_symlink() or is_reparse(artifact_info):
        return fail("artifact must be a regular non-link file")
    artifact_digest = sha256_file(artifact)
    if artifact_digest != intended["sha256"]:
        return fail("artifact SHA-256 does not match the trusted identity")
    workspace_mode = target["workspaceMode"]
    try:
        workspace_info = workspace.lstat()
    except FileNotFoundError:
        if workspace_mode != "absent-or-exact-directory":
            return fail("workspace does not exist")
        workspace_state = "absent"
    except OSError:
        return fail("workspace cannot be observed")
    else:
        if (
            workspace_mode not in {"exact-directory", "absent-or-exact-directory"}
            or not stat.S_ISDIR(workspace_info.st_mode)
            or workspace.is_symlink()
            or is_reparse(workspace_info)
        ):
            return fail("workspace must be an exact non-link directory")
        workspace_state = "directory"
    result = {
        "schema": RESULT_SCHEMA,
        "status": "observed",
        "binding": binding,
        "observed": intended,
        "observation": {
            "artifactPath": str(artifact.resolve()),
            "artifactSha256": artifact_digest,
            "artifactSize": artifact_info.st_size,
            "workspacePath": str(workspace),
            "workspaceState": workspace_state,
        },
    }
    sys.stdout.write(json.dumps(result, separators=(",", ":"), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
