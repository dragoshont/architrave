#!/usr/bin/env python3
"""Validate one durable Run v2 and its human-readable projections."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Sequence

from architrave_runtime import RunStore, RuntimeFailure


REQUIRED_PROJECTIONS = (
    "intake.md",
    "tournament.md",
    "recommended-plan.md",
    "phase-ledger.md",
    "deterministic-gates.md",
    "summary.json",
)


def repository_root(start: Path) -> Path:
    process = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=start,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeFailure("REPOSITORY_IDENTITY", "Run v2 validation requires a git repository", exit_code=2)
    return Path(process.stdout.strip()).resolve()


def validate(run_dir: Path) -> dict[str, object]:
    run_dir = run_dir.resolve()
    root = repository_root(run_dir)
    expected_parent = (root / ".architrave" / "runs").resolve()
    if run_dir.parent != expected_parent:
        raise RuntimeFailure("PATH_ESCAPE", "Run directory is outside .architrave/runs")
    store = RunStore(root)
    state = store.load(run_dir.name)
    missing = [name for name in REQUIRED_PROJECTIONS if not (run_dir / name).is_file() or (run_dir / name).stat().st_size == 0]
    if missing:
        raise RuntimeFailure("PROJECTION_MISSING", "required Run projections are missing", details={"files": missing})
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    if summary.get("schema") != "architrave.run.v2" or summary.get("runId") != state["runId"]:
        raise RuntimeFailure("PROJECTION_DIVERGED", "summary.json does not project the canonical Run")
    events = store.events(run_dir.name)
    return {
        "runId": state["runId"],
        "status": state["status"],
        "revision": state["revision"],
        "events": len(events),
        "tasks": len(state["tasks"]),
        "acceptanceCriteria": len(state["acceptanceCriteria"]),
    }


def cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir")
    args = parser.parse_args(argv)
    try:
        result = validate(Path(args.run_dir))
        print(json.dumps({"status": "pass", "result": result}, indent=2))
        print("ARCHITRAVE-RUN-V2: PASS")
        return 0
    except (RuntimeFailure, OSError, json.JSONDecodeError) as exc:
        if isinstance(exc, RuntimeFailure):
            payload = {"code": exc.code, "message": exc.message, "details": exc.details}
            exit_code = exc.exit_code
        else:
            payload = {"code": "RUN_INVALID", "message": str(exc)}
            exit_code = 1
        print(json.dumps({"status": "fail", "error": payload}, indent=2), file=sys.stderr)
        print("ARCHITRAVE-RUN-V2: FAIL", file=sys.stderr)
        return exit_code


if __name__ == "__main__":
    raise SystemExit(cli())