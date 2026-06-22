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
import re
import signal
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


def as_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


SECRET_PATTERNS = [
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"(?i)(token\s*[=:]\s*)[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"(?i)(password\s*[=:]\s*)\S{8,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
]


def redact_text(text: str, env: dict[str, str] | None = None) -> str:
    redacted = text
    env = env or os.environ
    for name in filter(None, os.environ.get("ARCHITRAVE_BENCH_SECRET_ENV_VARS", "").split(",")):
        value = env.get(name.strip())
        if value:
            redacted = redacted.replace(value, f"<redacted:{name.strip()}>")
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(lambda match: (match.group(1) if match.lastindex else "") + "<redacted>", redacted)
    return redacted


def redact_file(path: Path, env: dict[str, str] | None = None) -> None:
    if path.exists():
        path.write_text(redact_text(path.read_text(encoding="utf-8", errors="replace"), env), encoding="utf-8")


def normalize_git_path(path: str) -> str:
    return path.replace("\\", "/")


def run_to_files(cmd: list[str], cwd: Path, env: dict[str, str], timeout: int, stdout_path: Path, stderr_path: Path) -> tuple[int, bool, int]:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    start = time.time()
    timed_out = False
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            env=env,
            text=True,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
        try:
            returncode = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name == "posix" and hasattr(os, "killpg"):
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                    returncode = proc.wait(timeout=10)
                except Exception:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except Exception:
                        proc.kill()
                    returncode = proc.wait(timeout=10)
            else:
                proc.terminate()
                try:
                    returncode = proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    returncode = proc.wait(timeout=10)
            stderr.write(f"\nARCHITRAVE_BENCH_TIMEOUT after {timeout}s\n")
    duration_ms = int((time.time() - start) * 1000)
    return returncode, timed_out, duration_ms


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
    worktrees = run(["git", "-C", str(repo), "worktree", "list", "--porcelain"]).stdout or ""
    if str(worktree) in worktrees or worktree.exists():
        proc = run(["git", "-C", str(repo), "worktree", "remove", "--force", str(worktree)])
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())


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
    if arm["runner"] == "copilot":
        returncode, timed_out, duration_ms = run_to_files(copilot_command(arm, worktree, prompt, session_md), worktree, env, timeout, raw_stdout, raw_stderr)
    elif arm["runner"] == "shell":
        returncode, timed_out, duration_ms = run_to_files(arm["command"], worktree, env, timeout, raw_stdout, raw_stderr)
    else:
        raise RuntimeError(f"unknown runner: {arm['runner']}")
    redact_file(raw_stdout, env)
    redact_file(raw_stderr, env)
    metrics = parse_copilot_events(raw_stdout) if arm["runner"] == "copilot" else {}
    metrics.update({"returncode": returncode, "timed_out": timed_out, "duration_ms": duration_ms})
    return metrics


def parse_copilot_events(path: Path) -> dict[str, Any]:
    models: set[str] = set()
    assistant_messages = 0
    output_tokens = 0
    tool_requests = 0
    event_count = 0
    final_text = ""
    result_usage: dict[str, Any] = {}
    non_json_lines = 0
    json_errors = 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line.startswith("{"):
                if line:
                    non_json_lines += 1
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                json_errors += 1
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
            if event.get("type") == "result":
                usage = event.get("usage") or {}
                result_usage = {
                    "premium_requests": usage.get("premiumRequests"),
                    "total_api_duration_ms": usage.get("totalApiDurationMs"),
                    "session_duration_ms": usage.get("sessionDurationMs"),
                    "code_changes": usage.get("codeChanges"),
                    "exit_code": event.get("exitCode"),
                    "session_id": event.get("sessionId"),
                }
    return {
        "event_count": event_count,
        "models": sorted(models),
        "assistant_messages": assistant_messages,
        "output_tokens": output_tokens,
        "tool_requests": tool_requests,
        "final_text_chars": len(final_text),
        "result_usage": result_usage,
        "non_json_lines": non_json_lines,
        "json_errors": json_errors,
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
                files.append(normalize_git_path(file_path))
            dep_files = [file for file in files if file.endswith(("package.json", "package-lock.json", ".csproj", ".fsproj", ".sln", ".slnx", "Package.swift", "project.yml"))]
    return {
        "changed_files": len(files),
        "additions": additions,
        "deletions": deletions,
        "net_loc": additions - deletions,
        "dependency_or_project_files": dep_files,
        "status": status.splitlines(),
    }


def save_diff_artifacts(worktree: Path, out_dir: Path, env: dict[str, str] | None = None) -> dict[str, str]:
    status = redact_text(run(["git", "-C", str(worktree), "status", "--porcelain=v1"]).stdout or "", env)
    numstat = redact_text(run(["git", "-C", str(worktree), "diff", "--numstat"]).stdout or "", env)
    patch = redact_text(run(["git", "-C", str(worktree), "diff", "--binary"]).stdout or "", env)
    write(out_dir / "status.txt", status)
    write(out_dir / "numstat.txt", numstat)
    write(out_dir / "diff.patch", patch)
    return {
        "status": str(out_dir / "status.txt"),
        "numstat": str(out_dir / "numstat.txt"),
        "patch": str(out_dir / "diff.patch"),
    }


def run_validation(worktree: Path, commands: list[str], out_dir: Path, timeout: int) -> list[dict[str, Any]]:
    results = []
    for index, command in enumerate(commands, start=1):
        start = time.time()
        env = os.environ.copy()
        try:
            proc = run_shell(command, cwd=worktree, env=env, timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired as exc:
            proc = subprocess.CompletedProcess(command, 124, as_text(exc.stdout), as_text(exc.stderr))
            timed_out = True
        except Exception as exc:
            proc = subprocess.CompletedProcess(command, 125, "", repr(exc))
            timed_out = False
        duration_ms = int((time.time() - start) * 1000)
        write(out_dir / f"validation-{index}.stdout", redact_text(proc.stdout or "", env))
        write(out_dir / f"validation-{index}.stderr", redact_text(proc.stderr or "", env))
        results.append({"command": command, "returncode": proc.returncode, "timed_out": timed_out, "duration_ms": duration_ms})
    return results


def artifact_results(worktree: Path, artifacts: list[str]) -> list[dict[str, Any]]:
    return [{"path": artifact, "exists": (worktree / artifact).exists()} for artifact in artifacts]


def arm_values(scenario: dict[str, Any], key: str, arm_id: str) -> list[str]:
    by_arm = scenario.get(f"{key}ByArm", {}) or {}
    if arm_id in by_arm:
        return list(by_arm[arm_id])
    return list(scenario.get(key, []) or [])


def failure_mode(row: dict[str, Any]) -> str | None:
    agent = row.get("agent") or {}
    if agent.get("timed_out"):
        return "timeout"
    if agent and agent.get("returncode") != 0:
        return "agent_error"
    if row.get("error"):
        return "setup_error"
    if any(item.get("timed_out") for item in row.get("validation", [])):
        return "validation_timeout"
    if any(item.get("returncode") != 0 for item in row.get("validation", [])):
        return "validation_failed"
    if any(not item.get("exists") for item in row.get("artifacts", [])):
        return "artifact_missing"
    if row.get("passed") is False:
        return "unknown"
    return None


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def validate_scenarios(config: dict[str, Any]) -> int:
    failures = 0
    for scenario in config.get("scenarios", []):
        repo = Path(scenario["repo"]).expanduser().resolve()
        proc = run(["git", "-C", str(repo), "rev-parse", "--verify", scenario["baseRef"]])
        if proc.returncode != 0:
            failures += 1
            print(f"FAIL {scenario['id']}: baseRef {scenario['baseRef']} not found in {repo}")
        else:
            print(f"ok   {scenario['id']}: {scenario['baseRef']} -> {proc.stdout.strip()}")
    return failures


def bench(args: argparse.Namespace) -> int:
    config = load_config(Path(args.scenarios))
    if args.validate:
        return 1 if validate_scenarios(config) else 0
    if args.execute and not args.scenario and not args.all_enabled:
        raise SystemExit("refusing to execute an implicit one-scenario subset; pass --scenario <id> or --all-enabled")
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
    root = Path(args.out).expanduser().resolve() / run_id
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
                    row["diff_artifacts"] = save_diff_artifacts(worktree, cell_dir, os.environ.copy())
                    row["validation"] = run_validation(worktree, arm_values(scenario, "validation", arm["id"]), cell_dir, args.validation_timeout)
                    row["artifacts"] = artifact_results(worktree, arm_values(scenario, "expectedArtifacts", arm["id"]))
                    row["passed"] = (
                        row["agent"].get("returncode") == 0
                        and not row["agent"].get("timed_out")
                        and all(item["returncode"] == 0 for item in row["validation"])
                        and all(item["exists"] for item in row["artifacts"])
                    )
                except Exception as exc:  # keep batch moving; DNF is data
                    failures += 1
                    row["passed"] = False
                    row["error"] = repr(exc)
                finally:
                    row["failure_mode"] = failure_mode(row)
                    row["finished_at"] = datetime.now(timezone.utc).isoformat()
                    append_jsonl(results_path, row)
                    if args.cleanup_worktrees and worktree.exists():
                        try:
                            cleanup_worktree(repo, worktree)
                        except Exception as exc:
                            print(f"warn cleanup failed for {worktree}: {exc}", file=sys.stderr)
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
    parser.add_argument("--validate", action="store_true", help="validate scenario repo/baseRef references and exit")
    return bench(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())