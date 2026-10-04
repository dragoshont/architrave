#!/usr/bin/env python3
"""Run the reproducible basic-sh backend+UI SDD footprint trial."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import sys


def command(args: list[str], cwd: Path, *, env: dict[str, str] | None = None) -> str:
    return subprocess.run(
        args,
        cwd=cwd,
        env={**os.environ, **(env or {})},
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def file_record(path: Path, root: Path) -> dict[str, object]:
    data = path.read_bytes()
    root_values = {str(root), str(root.resolve()), str(root.absolute())}
    if os.name == "nt":
        import ctypes
        buffer = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.kernel32.GetLongPathNameW(str(root), buffer, len(buffer)):
            root_values.add(buffer.value)

    def normalize_value(value, key: str = ""):
        if key in {"stateHash", "hash", "lastHash", "previousHash", "attestation", "sha256"}:
            return "<VOLATILE>"
        if key in {"acquiredAt", "expiresAt", "retryNotBefore"}:
            return "<TIME>"
        if key == "commit":
            return "<FIXTURE_COMMIT>"
        if isinstance(value, dict):
            return {item_key: normalize_value(item, item_key) for item_key, item in value.items()}
        if isinstance(value, list):
            return [normalize_value(item) for item in value]
        if isinstance(value, str):
            for root_value in sorted(root_values, key=len, reverse=True):
                value = value.replace(root_value, "<REPO>")
            normalized_path = value.replace("\\", "/")
            tail = f"{root.parent.name}/{root.name}"
            position = normalized_path.casefold().find(tail.casefold())
            if position >= 0:
                value = "<REPO>" + normalized_path[position + len(tail):]
            return value
        return value

    try:
        text = data.decode("utf-8")
        if path.suffix == ".json":
            normalized = json.dumps(
                normalize_value(json.loads(text)),
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        elif path.suffix == ".jsonl":
            normalized = "\n".join(
                json.dumps(normalize_value(json.loads(line)), sort_keys=True, separators=(",", ":"))
                for line in text.splitlines()
            ).encode("utf-8")
        else:
            for root_value in sorted(root_values, key=len, reverse=True):
                text = text.replace(root_value, "<REPO>")
            normalized = text.encode("utf-8")
    except (UnicodeDecodeError, json.JSONDecodeError):
        normalized = data
    return {
        "path": path.resolve().relative_to(root.resolve()).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(normalized).hexdigest(),
    }


def fixture(repo: Path) -> tuple[str, list[str]]:
    repo.mkdir(parents=True)
    for directory in ("contract", "web", "tests"):
        (repo / directory).mkdir()
    api_name = "api.cmd" if os.name == "nt" else "api.sh"
    api_command = (
        [os.environ.get("ComSpec", "cmd.exe"), "/c", str(repo / api_name), "status"]
        if os.name == "nt"
        else ["sh", api_name, "status"]
    )
    (repo / ".gitignore").write_text(".architrave/\n", encoding="utf-8")
    (repo / "README.md").write_text("# basic-sh\n", encoding="utf-8")
    (repo / api_name).write_text("", encoding="utf-8")
    (repo / "contract/status.json").write_text("{}\n", encoding="utf-8")
    (repo / "web/index.html").write_text("", encoding="utf-8")
    (repo / "architrave.config.json").write_text(
        json.dumps(
            {
                "platform": "web",
                "stack": "other",
                "designSource": {"type": "design-doc", "path": "web"},
                "build": f'"{sys.executable}" tests/verify.py',
                "test": f'"{sys.executable}" tests/verify.py',
                "backend": {
                    "stack": "other",
                    "solution": ".",
                    "architectureDocs": ["README.md"],
                    "contracts": "contract/status.json",
                    "applyTo": [api_name, "contract/**"],
                    "build": f'"{sys.executable}" tests/verify.py',
                    "test": f'"{sys.executable}" tests/verify.py',
                },
                "workers": {"defaultAdapter": "shell", "enabledAdapters": ["shell"]},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (repo / "tests/verify.py").write_text(
        f"""import json, os, subprocess
from pathlib import Path
root = Path(__file__).resolve().parents[1]
cmd = {api_command!r}
payload = json.loads(subprocess.run(cmd, cwd=root, check=True, text=True, capture_output=True).stdout)
assert payload == {{"status":"ready","source":"basic-sh"}}
contract = json.loads((root / "contract/status.json").read_text())
assert contract == {{"path":"/api/status","response":payload}}
html = (root / "web/index.html").read_text()
assert "fetch('/api/status')" in html and 'id="status"' in html and "Service status" in html
print("basic-sh acceptance: PASS")
""",
        encoding="utf-8",
    )
    command(["git", "init", "-q"], repo)
    command(["git", "config", "user.email", "architrave@example.invalid"], repo)
    command(["git", "config", "user.name", "Architrave Trial"], repo)
    command(["git", "add", "."], repo)
    command(
        ["git", "commit", "-qm", "basic-sh fixture"],
        repo,
        env={
            "GIT_AUTHOR_DATE": "2026-10-04T00:00:00Z",
            "GIT_COMMITTER_DATE": "2026-10-04T00:00:00Z",
        },
    )
    return api_name, api_command


def receipt(store, repo: Path, run_id: str, task_id: str, argv: list[str]) -> str:
    result = subprocess.run(argv, cwd=repo, text=True, capture_output=True)
    path = store.run_dir(run_id) / "evidence" / f"{task_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "status": "pass" if result.returncode == 0 else "fail",
                "exitCode": result.returncode,
                "command": argv,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            },
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    artifact_id = f"deterministic-{task_id}"
    store._record_deterministic_result(
        run_id,
        artifact_id=artifact_id,
        path=path.resolve().relative_to(repo.resolve()).as_posix(),
        evidence_refs=[f"task:{task_id}"],
    )
    store.record_gate(
        run_id,
        gate_id=f"gate-{task_id}",
        task_id=task_id,
        gate_type="deterministic",
        status="PASS",
        evidence_refs=[f"artifact:{artifact_id}"],
    )
    return f"gate:gate-{task_id}"


def run_task(store, manager, execute, repo: Path, run_id: str, spec: dict[str, object]) -> None:
    task_id = str(spec["id"])
    store.add_task(run_id, spec)
    workspace = Path(manager.create(run_id, task_id)["workspace"])
    worker_id = f"worker-{task_id}"
    store.start_task(run_id, task_id, worker_id=worker_id)
    result = execute(store, run_id, task_id, worker_id)
    if result["status"] != "candidate":
        raise RuntimeError(json.dumps(result, indent=2))
    candidate = manager.collect(run_id, task_id)
    store.prepare_side_effect(run_id, task_id, operation="edit", target="repository")
    for relative in candidate["changedPaths"]:
        destination = repo / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(workspace / relative, destination)
    store.reconcile_side_effect(run_id, task_id, result="applied", evidence_ref=candidate["patchArtifactRef"])
    store._transaction(
        run_id,
        lambda state: {"taskId": task_id, "workspace": str(workspace), "patch": candidate["patch"]},
        event_type="workspace.integrated",
        actor="coordinator",
        task_id=task_id,
        evidence_refs=[candidate["patchArtifactRef"]],
    )
    gate = receipt(store, repo, run_id, task_id, list(spec.pop("evidenceCommand")))
    store.complete_task(run_id, task_id, evidence_refs=[gate])
    store.set_criterion(run_id, str(spec["acceptanceCriteria"][0]), "PASS", [gate])
    manager.cleanup(run_id, task_id, force=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    target = args.output / args.label
    if target.exists():
        def remove_readonly(function, path, error):
            os.chmod(path, stat.S_IWRITE)
            function(path)
        shutil.rmtree(target, onexc=remove_readonly)
    repo = target / "repo"
    api_name, api_command = fixture(repo)

    sys.path.insert(0, str(args.source / "harness"))
    from architrave_runtime import RunStore
    import architrave_runtime
    import worker_adapters
    from worker_adapters import execute_work_packet
    import workspaces
    from workspaces import WorkspaceManager

    counter = itertools.count(1)

    def deterministic_uuid():
        import uuid
        return uuid.UUID(int=next(counter))

    architrave_runtime.uuid.uuid4 = deterministic_uuid
    architrave_runtime.utc_now = lambda: "2026-10-04T00:00:00Z"
    architrave_runtime.secrets.token_bytes = lambda size: b"\x01" * size
    original_run_bounded = worker_adapters.run_bounded

    def deterministic_run_bounded(*arguments, **keywords):
        result = original_run_bounded(*arguments, **keywords)
        result["durationMs"] = 0
        return result

    worker_adapters.run_bounded = deterministic_run_bounded
    workspaces.uuid.uuid4 = deterministic_uuid

    store = RunStore(repo)
    state = store.create(
        goal="Build a dependency-free shell status API and a small UI that consumes its contract.",
        outcome="The shell API returns truthful status JSON and the UI consumes the documented endpoint.",
        criteria=[
            {"id": "API-001", "description": "The shell API returns documented status.", "scope": api_name, "risk": "R1", "verificationType": "deterministic", "status": "UNTESTED", "evidenceRefs": [], "blocking": True},
            {"id": "UI-001", "description": "The UI consumes the documented endpoint.", "scope": "web/index.html", "risk": "R1", "verificationType": "deterministic", "status": "UNTESTED", "evidenceRefs": [], "blocking": True},
        ],
        autonomy_scope="approved-program",
        policy_allow=[{"scope": "repository", "operations": ["edit"]}],
        run_id=f"basic-sh-{args.label}",
    )
    api_body = (
        '@echo off\nif not "%1"=="status" (exit /b 2)\necho {"status":"ready","source":"basic-sh"}\n'
        if os.name == "nt"
        else '#!/bin/sh\n[ "${1:-}" = status ] || exit 2\nprintf \'%s\\n\' \'{"status":"ready","source":"basic-sh"}\'\n'
    )
    backend = (
        "from pathlib import Path; import json; "
        f"Path({api_name!r}).write_text({api_body!r},encoding='utf-8',newline='\\n'); "
        "Path('contract/status.json').write_text(json.dumps({'path':'/api/status','response':{'status':'ready','source':'basic-sh'}},separators=(',',':'))+'\\n'); print('backend complete')"
    )
    common = {"workerProfile": "shell", "tools": ["filesystem", "shell"], "risk": "R1", "requiredArtifacts": ["worker-result"], "gate": "basic-sh acceptance"}
    run_task(store, WorkspaceManager(repo), execute_work_packet, repo, state["runId"], {
        **common, "id": "backend", "title": "Implement shell API", "objective": "Implement the shell endpoint and contract.", "mutablePaths": [api_name, "contract/status.json"], "acceptanceCriteria": ["API-001"], "evidenceCommand": api_command,
        "workPacket": {"execution": {"command": [sys.executable, "-c", backend], "cwd": None, "environment": []}, "budget": {"timeoutSeconds": 30, "maxOutputBytes": 65536}},
    })
    html = "<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><title>Service status</title><main><h1>Service status</h1><output id=\"status\" aria-live=\"polite\">Loading...</output></main><script>fetch('/api/status').then(r=>r.json()).then(d=>status.textContent=d.status).catch(()=>status.textContent='Unavailable');</script></html>\n"
    run_task(store, WorkspaceManager(repo), execute_work_packet, repo, state["runId"], {
        **common, "id": "ui", "title": "Implement status UI", "objective": "Render status from the documented endpoint.", "mutablePaths": ["web/index.html"], "acceptanceCriteria": ["UI-001"], "evidenceCommand": [sys.executable, "tests/verify.py"],
        "workPacket": {"execution": {"command": [sys.executable, "-c", f"from pathlib import Path; Path('web/index.html').write_text({html!r},encoding='utf-8')"], "cwd": None, "environment": []}, "budget": {"timeoutSeconds": 30, "maxOutputBytes": 65536}},
    })
    final, complete = store.verify(state["runId"])
    if not complete:
        raise RuntimeError("Run did not complete")
    run_dir = store.run_dir(state["runId"])
    files = [path for path in run_dir.rglob("*") if path.is_file()]
    code = [repo / api_name, repo / "contract/status.json", repo / "web/index.html"]
    orchestration_records = [file_record(path, repo) for path in sorted(files)]
    code_records = [file_record(path, repo) for path in code]
    metrics = {
        "schema": "architrave.orchestration-metrics.v1",
        "label": args.label,
        "sourceSha": command(["git", "rev-parse", "HEAD"], args.source),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "orchestrationFiles": len(orchestration_records),
        "orchestrationBytes": sum(int(item["bytes"]) for item in orchestration_records),
        "approxTokens": round(sum(int(item["bytes"]) for item in orchestration_records) / 4),
        "actualCodeFiles": len(code_records),
        "actualCodeBytes": sum(int(item["bytes"]) for item in code_records),
        "runStatus": final["status"],
        "criteria": {item["id"]: item["status"] for item in final["acceptanceCriteria"]},
        "orchestrationArtifacts": orchestration_records,
        "actualCodeArtifacts": code_records,
    }
    target.mkdir(parents=True, exist_ok=True)
    (target / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
