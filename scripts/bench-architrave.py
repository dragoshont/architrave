#!/usr/bin/env python3
"""Architrave benchmark runner.

Creates isolated git worktrees, runs configured agent arms, captures CLI traces,
diff metrics, validation output, and writes one JSONL row per run.

Default mode is safe: list/plan only. Pass --execute to run agents.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def run(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None, timeout: int | None = None, capture: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        timeout=timeout,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        check=False,
    )


def run_shell(command: str, cwd: Path, env: dict[str, str], timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd),
        env=env,
        timeout=timeout,
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def selected(items: list[dict[str, Any]], requested: list[str], all_enabled: bool = False) -> list[dict[str, Any]]:
    if requested:
        wanted = set(requested)
        chosen = [item for item in items if item["id"] in wanted]
        missing = wanted - {item["id"] for item in chosen}
        if missing:
            raise SystemExit(f"unknown id(s): {', '.join(sorted(missing))}")
        return chosen
    if all_enabled:
        return [item for item in items if item.get("enabled", True)]
    return [item for item in items if item.get("enabled", True)][:1]


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def git_output(repo: Path, args: list[str]) -> str:
    proc = run(["git", "-C", str(repo), *args])
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
    return proc.stdout.strip()


def create_worktree(repo: Path, base_ref: str, worktree: Path) -> str:
    commit = git_output(repo, ["rev-parse", base_ref])
    if worktree.exists():
        shutil.rmtree(worktree)
    worktree.parent.mkdir(parents=True, exist_ok=True)
    proc = run(["git", "-C", str(repo), "worktree", "add", "--detach", str(worktree), commit])
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
    return commit


def cleanup_worktree(repo: Path, worktree: Path) -> None:
    run(["git", "-C", str(repo), "worktree", "remove", "--force", str(worktree)])


def prompt_for(scenario: dict[str, Any], arm: dict[str, Any], repeat: int) -> str:
    return f"""You are running an Architrave benchmark.

Scenario: {scenario['id']}
Lane: {scenario['lane']}
Arm: {arm['id']}
Repeat: {repeat}

Rules:
- Work only in this benchmark worktree.
- Do not ask the user for confirmation; this benchmark grants approval to proceed unless the task is impossible or unsafe.
- Keep secrets out of logs and artifacts.
- If you are Architrave, use visible intake, Tournament of Options, YAGNI ladder, and durable run artifacts.
- Finish by running the validation commands when feasible.

Task:
{scenario['prompt']}
"""


def copilot_command(arm: dict[str, Any], worktree: Path, prompt: str, session_md: Path) -> list[str]:
    cmd = [
        "copilot",
        "-C",
        str(worktree),
        "--output-format",
        "json",
        "--stream",
        "off",
        "--share",
        str(session_md),
        "-p",
        prompt,
    ]
    if arm.get("allowAll", True):
        cmd.append("--allow-all")
    if arm.get("noAskUser", True):
        cmd.append("--no-ask-user")
    if arm.get("customInstructions") is False:
        cmd.append("--no-custom-instructions")
    if arm.get("agent"):
        cmd.extend(["--agent", arm["agent"]])
    if arm.get("model"):
        cmd.extend(["--model", arm["model"]])
    if arm.get("pluginDir"):
        cmd.extend(["--plugin-dir", arm["pluginDir"]])
    secret_env_vars = os.environ.get("ARCHITRAVE_BENCH_SECRET_ENV_VARS")
    if secret_env_vars:
        cmd.extend(["--secret-env-vars", secret_env_vars])
    return cmd


def run_arm(arm: dict[str, Any], worktree: Path, prompt: str, run_dir: Path, timeout: int) -> dict[str, Any]:
    raw_stdout = run_dir / "agent.stdout"
    raw_stderr = run_dir / "agent.stderr"
    session_md = run_dir / "session.md"
    env = os.environ.copy()
    env.update(arm.get("env", {}))
    env.update(
        {
            "ARCHITRAVE_BENCH_WORKTREE": str(worktree),
            "ARCHITRAVE_BENCH_RUN_DIR": str(run_dir),
            "ARCHITRAVE_BENCH_PROMPT_FILE": str(run_dir / "prompt.md"),
        }
    )
    start = time.time()
    try:
        if arm["runner"] == "copilot":
            proc = run(copilot_command(arm, worktree, prompt, session_md), cwd=worktree, env=env, timeout=timeout)
        elif arm["runner"] == "shell":
            command = " ".join(shlex.quote(part) for part in arm["command"])
            proc = run_shell(command, cwd=worktree, env=env, timeout=timeout)
        else:
            raise RuntimeError(f"unknown runner: {arm['runner']}")
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        proc = subprocess.CompletedProcess(exc.cmd, 124, exc.stdout or "", exc.stderr or "")
        timed_out = True
    duration_ms = int((time.time() - start) * 1000)
    write(raw_stdout, proc.stdout or "")
    write(raw_stderr, proc.stderr or "")
    metrics = parse_copilot_events(raw_stdout) if arm["runner"] == "copilot" else {}
    metrics.update({"returncode": proc.returncode, "timed_out": timed_out, "duration_ms": duration_ms})
    return metrics


def parse_copilot_events(path: Path) -> dict[str, Any]:
    models: set[str] = set()
    assistant_messages = 0
    output_tokens = 0
    tool_requests = 0
    event_count = 0
    final_text = ""
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            event_count += 1
            data = event.get("data") or {}
            if event.get("type") == "assistant.message":
                assistant_messages += 1
                if data.get("model"):
                    models.add(data["model"])
                output_tokens += int(data.get("outputTokens") or 0)
                tool_requests += len(data.get("toolRequests") or [])
                if data.get("content"):
                    final_text = data["content"]
    return {
        "event_count": event_count,
        "models": sorted(models),
        "assistant_messages": assistant_messages,
        "output_tokens": output_tokens,
        "tool_requests": tool_requests,
        "final_text_chars": len(final_text),
    }


def diff_metrics(worktree: Path) -> dict[str, Any]:
    run(["git", "-C", str(worktree), "add", "-N", "."])
    status = run(["git", "-C", str(worktree), "status", "--porcelain=v1"]).stdout
    numstat = run(["git", "-C", str(worktree), "diff", "--numstat"]).stdout
    files: list[str] = []
    additions = 0
    deletions = 0
    for line in numstat.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            add, delete, file_path = parts[0], parts[1], parts[2]
            if add.isdigit():
                additions += int(add)
            if delete.isdigit():
                deletions += int(delete)
            files.append(file_path)
    dep_files = [file for file in files if file.endswith(("package.json", "package-lock.json", ".csproj", ".fsproj", ".sln", ".slnx", "Package.swift", "project.yml"))]
    return {
        "changed_files": len(files),
        "additions": additions,
        "deletions": deletions,
        "net_loc": additions - deletions,
        "dependency_or_project_files": dep_files,
        "status": status.splitlines(),
    }


def run_validation(worktree: Path, commands: list[str], out_dir: Path, timeout: int) -> list[dict[str, Any]]:
    results = []
    for index, command in enumerate(commands, start=1):
        start = time.time()
        try:
            proc = run_shell(command, cwd=worktree, env=os.environ.copy(), timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired as exc:
            proc = subprocess.CompletedProcess(command, 124, exc.stdout or "", exc.stderr or "")
            timed_out = True
        duration_ms = int((time.time() - start) * 1000)
        write(out_dir / f"validation-{index}.stdout", proc.stdout or "")
        write(out_dir / f"validation-{index}.stderr", proc.stderr or "")
        results.append({"command": command, "returncode": proc.returncode, "timed_out": timed_out, "duration_ms": duration_ms})
    return results


def artifact_results(worktree: Path, artifacts: list[str]) -> list[dict[str, Any]]:
    return [{"path": artifact, "exists": (worktree / artifact).exists()} for artifact in artifacts]


def bench(args: argparse.Namespace) -> int:
    config = load_config(Path(args.scenarios))
    scenarios = selected(config["scenarios"], args.scenario, args.all_enabled or args.list)
    arms = selected(config["arms"], args.arm, all_enabled=True)
    if args.list or not args.execute:
        print("Scenarios:")
        for scenario in scenarios:
            print(f"  {scenario['id']} ({scenario['lane']}) repo={scenario['repo']} base={scenario['baseRef']}")
        print("Arms:")
        for arm in arms:
            print(f"  {arm['id']} runner={arm['runner']} agent={arm.get('agent', '')}")
        if not args.execute:
            print("Dry run only. Pass --execute to run agents.")
            return 0

    run_id = args.run_id or utc_stamp()
    root = Path(args.out) / run_id
    root.mkdir(parents=True, exist_ok=True)
    results_path = root / "results.jsonl"
    failures = 0
    for scenario in scenarios:
        repo = Path(scenario["repo"]).expanduser().resolve()
        for repeat in range(args.repeats):
            for arm in arms:
                cell_dir = root / scenario["id"] / arm["id"] / f"rep-{repeat}"
                worktree = cell_dir / "worktree"
                cell_dir.mkdir(parents=True, exist_ok=True)
                prompt = prompt_for(scenario, arm, repeat)
                write(cell_dir / "prompt.md", prompt)
                row: dict[str, Any] = {
                    "run_id": run_id,
                    "scenario": scenario["id"],
                    "lane": scenario["lane"],
                    "arm": arm["id"],
                    "repeat": repeat,
                    "repo": str(repo),
                    "base_ref": scenario["baseRef"],
                    "cell_dir": str(cell_dir),
                    "worktree": str(worktree),
                    "prompt_file": str(cell_dir / "prompt.md"),
                    "started_at": datetime.now(timezone.utc).isoformat(),
                }
                try:
                    row["base_commit"] = create_worktree(repo, scenario["baseRef"], worktree)
                    row["agent"] = run_arm(arm, worktree, prompt, cell_dir, args.agent_timeout)
                    row["diff"] = diff_metrics(worktree)
                    row["validation"] = run_validation(worktree, scenario.get("validation", []), cell_dir, args.validation_timeout)
                    row["artifacts"] = artifact_results(worktree, scenario.get("expectedArtifacts", []))
                    row["passed"] = all(item["returncode"] == 0 for item in row["validation"]) and all(item["exists"] for item in row["artifacts"])
                except Exception as exc:  # keep batch moving; DNF is data
                    failures += 1
                    row["passed"] = False
                    row["error"] = repr(exc)
                finally:
                    row["finished_at"] = datetime.now(timezone.utc).isoformat()
                    with results_path.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(row, sort_keys=True) + "\n")
                    if args.cleanup_worktrees and worktree.exists():
                        cleanup_worktree(repo, worktree)
                    print(f"{scenario['id']} {arm['id']} rep={repeat} passed={row.get('passed')} -> {cell_dir}")
    print(f"results: {results_path}")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", default="benchmarks/scenarios.json")
    parser.add_argument("--out", default=".architrave/bench/runs")
    parser.add_argument("--run-id")
    parser.add_argument("--scenario", action="append", default=[])
    parser.add_argument("--arm", action="append", default=[])
    parser.add_argument("--all-enabled", action="store_true")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--agent-timeout", type=int, default=1800)
    parser.add_argument("--validation-timeout", type=int, default=900)
    parser.add_argument("--cleanup-worktrees", action="store_true")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--execute", action="store_true")
    return bench(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())