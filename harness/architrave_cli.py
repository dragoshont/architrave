#!/usr/bin/env python3
"""Canonical cross-platform Architrave harness entrypoint."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from architrave_runtime import cli as runtime_cli
from validate_learning import validate as validate_learning
from validate_run_v2 import validate as validate_run_v2


def latest_run(root: Path) -> Path | None:
    runs = root / ".architrave" / "runs"
    candidates = [path for path in runs.iterdir() if path.is_dir()] if runs.is_dir() else []
    return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None


def validate_run(path: Path | None) -> int:
    path = path or latest_run(Path.cwd())
    if path is None or not path.is_dir():
        print("validate-run: run dir not found", file=sys.stderr)
        return 2
    if (path / "run.json").is_file():
        print(json.dumps({"status": "pass", "result": validate_run_v2(path)}, indent=2))
        print("ARCHITRAVE-RUN-V2: PASS")
        return 0
    try:
        summary = json.loads((path / "summary.json").read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"validate-run: invalid legacy summary ({exc})")
        return 1
    if (
        summary.get("schema") != "architrave.run.v1"
        or not summary.get("runId")
        or summary.get("status") not in {"in-progress", "blocked", "passed", "revised", "failed"}
    ):
        print("ARCHITRAVE-RUN: FAIL")
        return 1
    print("ARCHITRAVE-RUN: PASS")
    return 0


def semantic_review(run_dir: Path, provider: str, execute: bool) -> int:
    if not run_dir.is_dir():
        print("semantic-review: run dir not found", file=sys.stderr)
        return 2
    if execute:
        print("NATIVE_HOST_REQUIRED: invoke the adversarial judge through the current host; agent CLI launchers are prohibited.",
              file=sys.stderr)
        return 2
    print(json.dumps({
        "status": "advisory", "agent": "architrave:adversarial-judge", "run": str(run_dir),
        "prompt": "Review canonical state and referenced evidence against gates/rubric.md. "
                  "Return evidence-grounded PASS, REVISE or FAIL through host-native structured invocation.",
        "execution": "host-owned; this helper cannot execute or attest a reviewer",
    }, indent=2))
    return 0


def validate_tournament_result(result: object) -> list[str]:
    """Typed tournament result: DO_NOTHING and SMALLEST_VIABLE baselines plus why the winner beats doing nothing."""
    errors = []
    options = result.get("options") if isinstance(result, dict) else None
    kinds = {item.get("kind") for item in options or [] if isinstance(item, dict)}
    for kind in ("DO_NOTHING", "SMALLEST_VIABLE"):
        if kind not in kinds:
            errors.append(f"options must include kind {kind}")
    if not isinstance(result, dict) or not result.get("winner"):
        errors.append("winner is required")
    if not isinstance(result, dict) or not str(result.get("winnerBeatsDoNothing") or "").strip():
        errors.append("winnerBeatsDoNothing must explain why the winner beats doing nothing")
    return errors


def tournament_review(run_dir: Path, execute: bool, result_path: Path | None = None) -> int:
    if result_path is not None:
        try:
            errors = validate_tournament_result(json.loads(result_path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            errors = [f"unreadable tournament result ({exc})"]
        for error in errors:
            print(f"FAIL  {error}")
        print("TOURNAMENT-RESULT: FAIL" if errors else "TOURNAMENT-RESULT: PASS")
        return 1 if errors else 0
    if not run_dir.is_dir():
        print("tournament-review: run dir not found", file=sys.stderr)
        return 2
    if execute:
        print("NATIVE_HOST_REQUIRED: invoke Tournament Analyst through the current host; agent CLI launchers are prohibited.",
              file=sys.stderr)
        return 2
    print(json.dumps({
        "status": "advisory", "agent": "architrave:tournament-analyst", "run": str(run_dir),
        "prompt": "Compare viable options against canonical state and governing repository sources; do not edit or authorize mutations. "
                  "Options must include kinds DO_NOTHING and SMALLEST_VIABLE; return winner and winnerBeatsDoNothing.",
        "execution": "host-owned; this helper cannot execute or attest a reviewer",
    }, indent=2))
    return 0
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    runtime = subparsers.add_parser("runtime")
    runtime.add_argument("arguments", nargs=argparse.REMAINDER)
    run_validation = subparsers.add_parser("validate-run")
    run_validation.add_argument("run_dir", nargs="?")
    learning = subparsers.add_parser("validate-learning")
    learning.add_argument("root", nargs="?", default=".")
    semantic = subparsers.add_parser("semantic-review")
    semantic.add_argument("--provider", choices=["copilot", "claude", "both"], default="both", help=argparse.SUPPRESS)
    semantic.add_argument("--run", dest="run_dir")
    semantic.add_argument("--execute", action="store_true")
    tournament = subparsers.add_parser("tournament-review")
    tournament.add_argument("--run", dest="run_dir")
    tournament.add_argument("--execute", action="store_true")
    tournament.add_argument("--result", help="validate a returned tournament result JSON")
    args = parser.parse_args(argv)
    if args.command == "runtime":
        return runtime_cli(args.arguments)
    if args.command == "validate-run":
        return validate_run(Path(args.run_dir).resolve() if args.run_dir else None)
    if args.command == "validate-learning":
        passed, errors = validate_learning(Path(args.root))
        for item in passed:
            print(f"ok    {item}")
        if errors:
            for error in errors:
                print(f"FAIL  {error}")
            print("ARCHITRAVE-LEARNING: FAIL")
            return 1
        print("ARCHITRAVE-LEARNING: PASS")
        return 0
    if args.command == "semantic-review":
        run_dir = Path(args.run_dir).resolve() if args.run_dir else latest_run(Path.cwd())
        if run_dir is None:
            print("semantic-review: run dir not found", file=sys.stderr)
            return 2
        return semantic_review(run_dir, args.provider, args.execute)
    if args.command == "tournament-review":
        if not args.result and not args.run_dir:
            parser.error("tournament-review needs --run or --result")
        return tournament_review(Path(args.run_dir or ".").resolve(), args.execute,
                                 Path(args.result) if args.result else None)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
