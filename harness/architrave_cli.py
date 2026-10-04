#!/usr/bin/env python3
"""Canonical cross-platform Architrave harness entrypoint."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid

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


def command_text(arguments: list[str]) -> str:
        return subprocess.list2cmdline(arguments) if os.name == "nt" else shlex.join(arguments)


def final_review_text(label: str, output: str) -> str:
        if label == "claude":
            try:
                return str(json.loads(output).get("result") or "")
            except json.JSONDecodeError:
                return ""
        messages = []
        for line in output.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "assistant.message":
                messages.append(str((event.get("data") or {}).get("content") or ""))
        return messages[-1] if messages else ""


def verified_pass(content: str, nonce: str, terminal: str) -> bool:
        lines = [line.rstrip("\r") for line in content.splitlines()]
        nonempty = [line for line in lines if line.strip()]
        return (
            lines.count(f"EVIDENCE_NONCE: {nonce}") == 1
            and sum(line.startswith("VERDICT: ") for line in lines) == 1
            and bool(nonempty)
            and nonempty[-1] == terminal
        )


def semantic_review(run_dir: Path, provider: str, execute: bool) -> int:
        if not run_dir.is_dir():
            print("semantic-review: run dir not found", file=sys.stderr)
            return 2
        root = Path.cwd()
        agent = root / "agents" / "adversarial-judge.agent.md"
        if not agent.is_file():
            agent = root / ".github" / "agents" / "adversarial-judge.agent.md"
        if not agent.is_file():
            print("semantic-review: adversarial judge agent not found", file=sys.stderr)
            return 2
        body = (
            f"Review canonical state and referenced evidence in {run_dir} against gates/rubric.md.\n"
            "Focus on Outcome/acceptance coverage, TaskGraph scope, repository contract fit, "
            "deterministic and runtime evidence, safety, capability honesty, and missing tests.\n"
            "Return concise findings ordered by severity, then VERDICT: PASS|REVISE|FAIL."
        )
        commands = {
            "copilot": [
                shutil.which("copilot") or "copilot", "-C", str(root), "--agent",
                "architrave:adversarial-judge", "--available-tools", "view,grep,glob",
                "--allow-tool", "view", "--allow-tool", "grep", "--allow-tool", "glob",
                "--no-ask-user", "--output-format", "json", "--stream", "off", "--silent",
                "--no-color", "-p", body,
            ],
            "claude": [
                shutil.which("claude") or "claude", "--tools", "Read,Grep,Glob",
                "--allowedTools", "Read,Grep,Glob", "--append-system-prompt-file", str(agent),
                "--output-format", "json", "-p", body,
            ],
        }
        selected = ["copilot", "claude"] if provider == "both" else [provider]
        if not execute:
            print("suggested command(s) (host-selected model):")
            for label in selected:
                print(f"  {command_text(commands[label])}")
            return 0
        nonce = str(uuid.uuid4()).lower()
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            handle.write(nonce + "\n")
            nonce_path = Path(handle.name)
        try:
            failed = False
            for label in selected:
                command = list(commands[label])
                command[-1] = body + (
                    f"\n\nRead {nonce_path} and include EVIDENCE_NONCE: <value>. "
                    "End with exactly VERDICT: PASS, VERDICT: REVISE, or VERDICT: FAIL."
                )
                process = subprocess.run(command, text=True, capture_output=True, check=False)
                content = final_review_text(label, process.stdout)
                if content:
                    print(content)
                if process.returncode != 0 or not verified_pass(content, nonce, "VERDICT: PASS"):
                    print(f"semantic-review: {label} reviewer did not return a verified PASS", file=sys.stderr)
                    failed = True
            return 1 if failed else 0
        finally:
            nonce_path.unlink(missing_ok=True)


def tournament_review(run_dir: Path, execute: bool) -> int:
        if not run_dir.is_dir():
            print("tournament-review: run dir not found", file=sys.stderr)
            return 2
        root = Path.cwd()
        agent = root / "agents" / "tournament-analyst.agent.md"
        if not agent.is_file():
            agent = root / ".github" / "agents" / "tournament-analyst.agent.md"
        if not agent.is_file():
            print("tournament-review: Tournament Analyst agent not found", file=sys.stderr)
            return 2
        body = (
            f"Read canonical state and governing repository sources for the Architrave run at {run_dir}.\n"
            "Compare viable options using the canonical Tournament Analyst instructions.\n"
            "Do not edit files or authorize mutations. End with one line exactly TOURNAMENT: COMPLETE."
        )
        command = [
            shutil.which("claude") or "claude", "--tools", "Read,Grep,Glob", "--allowedTools",
            "Read,Grep,Glob", "--append-system-prompt-file", str(agent), "-p", body,
        ]
        if not execute:
            print("suggested command (host-selected model):")
            print(f"  {command_text(command)}")
            return 0
        nonce = str(uuid.uuid4()).lower()
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            handle.write(nonce + "\n")
            nonce_path = Path(handle.name)
        try:
            command[-1] = body + f"\n\nRead {nonce_path} and include EVIDENCE_NONCE: <value>."
            process = subprocess.run(command, text=True, capture_output=True, check=False)
            content = process.stdout.replace("\r\n", "\n").rstrip("\r")
            if content:
                print(content)
            lines = [line for line in content.splitlines() if line.strip()]
            valid = (
                process.returncode == 0
                and content.splitlines().count(f"EVIDENCE_NONCE: {nonce}") == 1
                and content.splitlines().count("TOURNAMENT: COMPLETE") == 1
                and bool(lines)
                and lines[-1] == "TOURNAMENT: COMPLETE"
            )
            if not valid:
                print("tournament-review: unverified result", file=sys.stderr)
                return 1
            return 0
        finally:
            nonce_path.unlink(missing_ok=True)
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
    semantic.add_argument("--provider", choices=["copilot", "claude", "both"], default="both")
    semantic.add_argument("--run", dest="run_dir")
    semantic.add_argument("--execute", action="store_true")
    tournament = subparsers.add_parser("tournament-review")
    tournament.add_argument("--run", dest="run_dir", required=True)
    tournament.add_argument("--execute", action="store_true")
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
        return tournament_review(Path(args.run_dir).resolve(), args.execute)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
