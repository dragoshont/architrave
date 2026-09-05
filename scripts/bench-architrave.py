#!/usr/bin/env python3
"""Architrave benchmark runner.

Creates isolated git worktrees, runs configured agent arms, captures CLI traces,
diff metrics, validation output, and writes one JSONL row per run.

Default mode is safe: list/plan only. Pass --execute to run agents.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shlex
import signal
import shutil
import subprocess
import sys
import time
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PRODUCER_PROMPT_VERSION = 2
PROFILE_INTENTS = {
    "FAST": {"modelClass": "fast", "reasoning": "low", "context": "narrow", "verification": "default"},
    "BALANCED": {"modelClass": "default", "reasoning": "default", "context": "default", "verification": "default"},
    "DEEP": {"modelClass": "strong", "reasoning": "high", "context": "default", "verification": "independent"},
    "CRITICAL": {"modelClass": "strong", "reasoning": "high", "context": "default", "verification": "cross-family"},
}
MODEL_CLASSES = {"inherit", "fast", "default", "strong"}
REASONING_INTENTS = {"low", "default", "high", "max"}
CONTEXT_INTENTS = {"narrow", "default", "long"}
VERIFICATION_INTENTS = {"default", "independent", "cross-family"}
COPILOT_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh", "max"}
COPILOT_CONTEXT_TIERS = {"default", "long_context"}
RUNNER_CONTROL_FIELDS = {
    "copilot": {"agent", "model", "reasoningEffort", "contextTier", "customInstructions", "allowAll", "noAskUser", "pluginDir"},
    "claude": {"model"},
    "codex": {"model"},
    "shell": set(),
}


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def positive_seconds(value: str) -> int:
    seconds = int(value)
    if seconds < 1:
        raise argparse.ArgumentTypeError("must be at least one second")
    return seconds


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


def run_to_files(
    cmd: list[str],
    cwd: Path,
    env: dict[str, str],
    timeout: float,
    stdout_path: Path,
    stderr_path: Path,
    heartbeat_interval: float = 60,
) -> tuple[int, bool, int]:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
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
            deadline = start + timeout
            next_heartbeat = start + heartbeat_interval
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(cmd, timeout)
                try:
                    returncode = proc.wait(timeout=min(remaining, max(0.01, next_heartbeat - time.monotonic())))
                    break
                except subprocess.TimeoutExpired:
                    now = time.monotonic()
                    if now >= next_heartbeat:
                        elapsed = int(now - start)
                        print(f"ARCHITRAVE_BENCH_HEARTBEAT agent running {elapsed}s/{math.ceil(timeout)}s", flush=True)
                        next_heartbeat = now + heartbeat_interval
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
            stderr.write(f"\nARCHITRAVE_BENCH_TIMEOUT after {math.ceil(timeout)}s\n")
    duration_ms = int((time.monotonic() - start) * 1000)
    return returncode, timed_out, duration_ms


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def execution_intent_errors(intent: object, label: str) -> list[str]:
    if not isinstance(intent, dict):
        return [f"{label} must be an object"]
    errors = []
    allowed = {"profile", "modelClass", "reasoning", "context", "verification"}
    unknown = set(intent) - allowed
    if unknown:
        errors.append(f"{label} has unknown field(s): {', '.join(sorted(unknown))}")
    checks = (
        ("modelClass", MODEL_CLASSES),
        ("reasoning", REASONING_INTENTS),
        ("context", CONTEXT_INTENTS),
        ("verification", VERIFICATION_INTENTS),
    )
    for field, values in checks:
        if intent.get(field) not in values:
            errors.append(f"{label}.{field} is invalid")
    profile = intent.get("profile")
    if profile is not None:
        if profile not in PROFILE_INTENTS:
            errors.append(f"{label}.profile is invalid")
        elif any(intent.get(field) != value for field, value in PROFILE_INTENTS[profile].items()):
            errors.append(f"{label}.profile does not match its dimensions")
    return errors


def benchmark_config_errors(config: object) -> list[str]:
    if not isinstance(config, dict):
        return ["benchmark config must be an object"]
    errors = []
    arms = config.get("arms") or []
    scenarios = config.get("scenarios") or []
    for label, items in (("arm", arms), ("scenario", scenarios)):
        ids = [item.get("id") for item in items if isinstance(item, dict)]
        duplicates = sorted({item_id for item_id in ids if item_id and ids.count(item_id) > 1})
        if duplicates:
            errors.append(f"duplicate {label} id(s): {', '.join(duplicates)}")
    for arm in arms:
        if not isinstance(arm, dict):
            errors.append("arm must be an object")
            continue
        label = f"arm {arm.get('id', '<missing>')}"
        runner = arm.get("runner")
        if runner not in RUNNER_CONTROL_FIELDS:
            errors.append(f"{label}.runner is invalid")
            continue
        unsupported_controls = sorted(set(RUNNER_CONTROL_FIELDS["copilot"]).difference(RUNNER_CONTROL_FIELDS[runner]).intersection(arm))
        if unsupported_controls:
            errors.append(f"{label} {runner} runner cannot set unsupported control(s): {', '.join(unsupported_controls)}")
        if runner == "copilot":
            if "command" in arm:
                errors.append(f"{label} cannot set command for the Copilot runner")
        elif runner in {"claude", "codex"}:
            if "command" in arm:
                errors.append(f"{label} cannot set command for the {runner} runner")
        elif runner == "shell":
            if not isinstance(arm.get("command"), list) or not arm.get("command"):
                errors.append(f"{label} requires a nonempty command")
        effort = arm.get("reasoningEffort")
        if effort is not None and effort not in COPILOT_EFFORTS:
            errors.append(f"{label}.reasoningEffort is invalid")
        context_tier = arm.get("contextTier")
        if context_tier is not None and context_tier not in COPILOT_CONTEXT_TIERS:
            errors.append(f"{label}.contextTier is invalid")
        if effort is not None and (not arm.get("model") or str(arm.get("model")).lower() == "auto"):
            errors.append(f"{label} controlled reasoning effort requires an explicit non-auto model")
        if "execution" in arm:
            errors.extend(execution_intent_errors(arm["execution"], f"{label}.execution"))
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            errors.append("scenario must be an object")
            continue
        if "expectedExecution" in scenario:
            errors.extend(execution_intent_errors(scenario["expectedExecution"], f"scenario {scenario.get('id', '<missing>')}.expectedExecution"))
    return errors


def resolve_repo(repo: str, config_dir: Path) -> Path:
    path = Path(repo).expanduser()
    return (path if path.is_absolute() else config_dir / path).resolve()


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


def create_fixture_worktree(fixture: Path, worktree: Path, *, install_kit: bool = False) -> str:
    if worktree.exists():
        shutil.rmtree(worktree)
    shutil.copytree(fixture, worktree)
    if install_kit:
        kit_root = Path(__file__).resolve().parents[1]
        installed = run([str(kit_root / "tools" / "install.sh"), str(worktree)], cwd=kit_root)
        if installed.returncode != 0:
            raise RuntimeError(installed.stderr.strip() or installed.stdout.strip() or "fixture kit install failed")
    run(["git", "init", "-q"], cwd=worktree)
    run(["git", "config", "user.email", "architrave-bench@example.invalid"], cwd=worktree)
    run(["git", "config", "user.name", "Architrave Benchmark"], cwd=worktree)
    run(["git", "add", "."], cwd=worktree)
    commit = run(["git", "commit", "-qm", "frozen fixture"], cwd=worktree)
    if commit.returncode != 0:
        raise RuntimeError(commit.stderr.strip() or "fixture commit failed")
    return git_output(worktree, ["rev-parse", "HEAD"])


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
Repeat: {repeat}
Producer prompt version: {PRODUCER_PROMPT_VERSION}

Rules:
- Work only in this benchmark worktree.
- Do not ask the user for confirmation; this benchmark grants approval to proceed unless the task is impossible or unsafe.
- Keep secrets out of logs and artifacts.
- If you are Architrave, use visible intake, Tournament of Options, YAGNI ladder, and durable run artifacts.
- If you are Architrave, classify provider-neutral execution intent from task evidence and record the selection in the run summary. Do not infer a concrete model binding.
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
    if arm.get("reasoningEffort"):
        cmd.extend(["--effort", arm["reasoningEffort"]])
    if arm.get("contextTier"):
        cmd.extend(["--context", arm["contextTier"]])
    if arm.get("pluginDir"):
        cmd.extend(["--plugin-dir", arm["pluginDir"]])
    secret_env_vars = os.environ.get("ARCHITRAVE_BENCH_SECRET_ENV_VARS")
    if secret_env_vars:
        cmd.extend(["--secret-env-vars", secret_env_vars])
    return cmd


def run_arm(
    arm: dict[str, Any],
    worktree: Path,
    prompt: str,
    run_dir: Path,
    timeout: float,
    heartbeat_interval: float,
) -> dict[str, Any]:
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
        returncode, timed_out, duration_ms = run_to_files(
            copilot_command(arm, worktree, prompt, session_md), worktree, env, timeout, raw_stdout, raw_stderr, heartbeat_interval
        )
    elif arm["runner"] == "claude":
        command = ["claude", "-p", prompt, "--output-format", "json"]
        if arm.get("model"):
            command.extend(["--model", arm["model"]])
        returncode, timed_out, duration_ms = run_to_files(command, worktree, env, timeout, raw_stdout, raw_stderr, heartbeat_interval)
    elif arm["runner"] == "codex":
        command = ["codex", "-C", str(worktree), "-s", "workspace-write", "-a", "never", "exec", "--json", prompt]
        if arm.get("model"):
            command[1:1] = ["-m", arm["model"]]
        returncode, timed_out, duration_ms = run_to_files(command, worktree, env, timeout, raw_stdout, raw_stderr, heartbeat_interval)
    elif arm["runner"] == "shell":
        returncode, timed_out, duration_ms = run_to_files(arm["command"], worktree, env, timeout, raw_stdout, raw_stderr, heartbeat_interval)
    else:
        raise RuntimeError(f"unknown runner: {arm['runner']}")
    redact_file(raw_stdout, env)
    redact_file(raw_stderr, env)
    metrics = parse_copilot_events(raw_stdout) if arm["runner"] == "copilot" else {}
    output_text = raw_stdout.read_text(encoding="utf-8", errors="replace")
    metrics["unnecessary_questions"] = len(
        re.findall(r"(?i)(?:ask[_ -]?user|please confirm|could you clarify|should I proceed)", output_text)
    )
    metrics.update({"returncode": returncode, "timed_out": timed_out, "duration_ms": duration_ms})
    return metrics


def parse_copilot_events(path: Path) -> dict[str, Any]:
    models: set[str] = set()
    assistant_messages = 0
    output_tokens = 0
    output_tokens_observed = False
    tool_requests = 0
    event_count = 0
    final_text = ""
    result_usage: dict[str, Any] = {}
    non_json_lines = 0
    json_errors = 0
    model_reasoning: set[tuple[str, str | None, str | None]] = set()
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
                if "outputTokens" in data and data.get("outputTokens") is not None:
                    output_tokens += int(data["outputTokens"])
                    output_tokens_observed = True
                tool_requests += len(data.get("toolRequests") or [])
                if data.get("content"):
                    final_text = data["content"]
            if event.get("type") == "session.usage_checkpoint":
                for state in data.get("promptCacheBreakState") or []:
                    if not isinstance(state, dict) or state.get("conversation") != "main":
                        continue
                    checkpoint_models = state.get("models") or {}
                    if not isinstance(checkpoint_models, dict):
                        continue
                    for model_id, metadata in checkpoint_models.items():
                        if not isinstance(metadata, dict):
                            continue
                        observed_model = metadata.get("model") or model_id
                        if observed_model:
                            models.add(observed_model)
                            model_reasoning.add((observed_model, metadata.get("vendor"), metadata.get("reasoning_effort")))
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
        "model_reasoning": [
            {"model": model, "vendor": vendor, "reasoningEffort": effort}
            for model, vendor, effort in sorted(model_reasoning, key=lambda item: tuple(value or "" for value in item))
        ],
        "assistant_messages": assistant_messages,
        "output_tokens": output_tokens if output_tokens_observed else None,
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
            files.append(normalize_git_path(file_path))
            if add.isdigit():
                additions += int(add)
            if delete.isdigit():
                deletions += int(delete)
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


def run_validation(
    worktree: Path,
    commands: list[str],
    out_dir: Path,
    timeout: int,
    deadline: float | None = None,
) -> list[dict[str, Any]]:
    results = []
    for index, command in enumerate(commands, start=1):
        python_command = subprocess.list2cmdline([sys.executable]) if os.name == "nt" else shlex.quote(sys.executable)
        resolved_command = command.replace("{python}", python_command)
        remaining = (deadline - time.monotonic()) if deadline is not None else None
        if remaining is not None and remaining <= 0:
            results.append(
                {
                    "command": resolved_command,
                    "returncode": 124,
                    "timed_out": True,
                    "duration_ms": 0,
                    "budget_exhausted": True,
                }
            )
            break
        start = time.time()
        env = os.environ.copy()
        command_timeout = min(timeout, remaining) if remaining is not None else timeout
        budget_limited = remaining is not None and remaining < timeout
        try:
            proc = run_shell(resolved_command, cwd=worktree, env=env, timeout=command_timeout)
            timed_out = False
        except subprocess.TimeoutExpired as exc:
            proc = subprocess.CompletedProcess(resolved_command, 124, as_text(exc.stdout), as_text(exc.stderr))
            timed_out = True
        except Exception as exc:
            proc = subprocess.CompletedProcess(resolved_command, 125, "", repr(exc))
            timed_out = False
        duration_ms = int((time.time() - start) * 1000)
        write(out_dir / f"validation-{index}.stdout", redact_text(proc.stdout or "", env))
        write(out_dir / f"validation-{index}.stderr", redact_text(proc.stderr or "", env))
        results.append(
            {
                "command": resolved_command,
                "returncode": proc.returncode,
                "timed_out": timed_out,
                "duration_ms": duration_ms,
                "budget_exhausted": bool(timed_out and budget_limited),
            }
        )
    return results


def artifact_results(worktree: Path, artifacts: list[str]) -> list[dict[str, Any]]:
    return [{"path": artifact, "exists": (worktree / artifact).exists()} for artifact in artifacts]


def arm_values(scenario: dict[str, Any], key: str, arm_id: str) -> list[str]:
    by_arm = scenario.get(f"{key}ByArm", {}) or {}
    if arm_id in by_arm:
        return list(by_arm[arm_id])
    return list(scenario.get(key, []) or [])


def execution_snapshot(scenario: dict[str, Any], arm: dict[str, Any]) -> dict[str, Any]:
    return {
        "expected": copy.deepcopy(scenario.get("expectedExecution")),
        "requested": {
            "semantic": copy.deepcopy(arm.get("execution")),
            "runner": arm["runner"],
            "agent": arm.get("agent"),
            "model": arm.get("model"),
            "reasoningEffort": arm.get("reasoningEffort"),
            "contextTier": arm.get("contextTier"),
        },
        "reportedSelection": None,
        "controlStatus": {
            "model": "not-requested",
            "reasoningEffort": "not-requested",
            "contextTier": "not-requested",
            "controlsHonored": None,
        },
    }


def run_summary_paths(worktree: Path) -> set[Path]:
    run_root = worktree / ".architrave" / "runs"
    return {path.resolve() for path in run_root.glob("*/summary.json")} if run_root.exists() else set()


def reported_execution(worktree: Path, preexisting: set[Path] | None = None) -> dict[str, Any] | None:
    run_root = worktree / ".architrave" / "runs"
    preexisting = preexisting or set()
    summaries = sorted(
        (path for path in run_root.glob("*/summary.json") if path.resolve() not in preexisting),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    ) if run_root.exists() else []
    for summary_path in summaries:
        try:
            execution = json.loads(summary_path.read_text(encoding="utf-8")).get("execution")
        except (OSError, json.JSONDecodeError, AttributeError):
            continue
        if not isinstance(execution, dict) or execution_intent_errors(execution.get("intent"), "reported intent"):
            continue
        return {
            "profile": execution.get("profile"),
            "intent": copy.deepcopy(execution["intent"]),
            "effectiveVerification": execution.get("effectiveVerification"),
            "selectionReason": execution.get("selectionReason"),
        }
    return None


def control_status(requested: dict[str, Any], agent: dict[str, Any]) -> dict[str, Any]:
    requested_model = requested.get("model")
    requested_effort = requested.get("reasoningEffort")
    requested_context = requested.get("contextTier")
    observed_models = {str(model).casefold() for model in agent.get("models", [])}
    observations = agent.get("model_reasoning", []) or []

    if requested_model is None:
        model_status = "not-requested"
    elif not observed_models:
        model_status = "unobserved"
    elif str(requested_model).casefold() in observed_models:
        model_status = "honored"
    else:
        model_status = "mismatch"

    if requested_effort is None:
        effort_status = "not-requested"
    elif not requested_model:
        effort_status = "unobserved"
    elif not observations:
        effort_status = "unobserved"
    else:
        matching = [item for item in observations if str(item.get("model", "")).casefold() == str(requested_model).casefold()]
        observed_efforts = [item.get("reasoningEffort") for item in matching if item.get("reasoningEffort") is not None]
        if not observed_efforts:
            effort_status = "unobserved"
        else:
            effort_status = "honored" if requested_effort in observed_efforts else "mismatch"

    context_status = "not-requested" if requested_context is None else "unobserved"
    requested_statuses = [status for status in (model_status, effort_status, context_status) if status != "not-requested"]
    if not requested_statuses:
        honored: bool | None = None
    elif "mismatch" in requested_statuses:
        honored = False
    elif "unobserved" in requested_statuses:
        honored = None
    else:
        honored = True
    return {"model": model_status, "reasoningEffort": effort_status, "contextTier": context_status, "controlsHonored": honored}


def controls_allow_pass(status: dict[str, Any]) -> bool:
    """Require telemetry confirmation for requested model and reasoning controls."""
    return all(status.get(control) in {"not-requested", "honored"} for control in ("model", "reasoningEffort"))


def failure_mode(row: dict[str, Any]) -> str | None:
    agent = row.get("agent") or {}
    if row.get("budget_exhausted"):
        return "run_budget_exhausted"
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
    control_status = ((row.get("execution") or {}).get("controlStatus") or {})
    if not controls_allow_pass(control_status):
        return "control_unhonored"
    if row.get("passed") is False:
        return "unknown"
    return None


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def validate_scenarios(config: dict[str, Any], config_dir: Path, *, allow_missing_repos: bool = False) -> int:
    failures = 0
    for scenario in config.get("scenarios", []):
        if scenario.get("fixture"):
            fixture = resolve_repo(scenario["fixture"], config_dir)
            if fixture.is_dir():
                print(f"ok   {scenario['id']}: fixture {fixture}")
            else:
                failures += 1
                print(f"FAIL {scenario['id']}: fixture not found: {fixture}")
            continue
        repo = resolve_repo(scenario["repo"], config_dir)
        if not repo.is_dir():
            if allow_missing_repos:
                print(f"skip {scenario['id']}: external repository unavailable: {repo}")
                continue
            failures += 1
            print(f"FAIL {scenario['id']}: repository not found: {repo}")
            continue
        proc = run(["git", "-C", str(repo), "rev-parse", "--verify", f"{scenario['baseRef']}^{{commit}}"])
        if proc.returncode != 0:
            failures += 1
            print(f"FAIL {scenario['id']}: baseRef {scenario['baseRef']} not found in {repo}")
        else:
            print(f"ok   {scenario['id']}: {scenario['baseRef']} -> {proc.stdout.strip()}")
    return failures


def durable_run_metrics(worktree: Path, duration_ms: int, row_passed: bool) -> dict[str, Any] | None:
    run_files = sorted(
        worktree.glob(".architrave/runs/*/run.json"),
        key=lambda path: path.stat().st_mtime,
    )
    if not run_files:
        return None
    state = json.loads(run_files[-1].read_text(encoding="utf-8"))
    if state.get("schema") != "architrave.run.v2":
        return {"schema": state.get("schema"), "status": state.get("status"), "outcome_pass": False, "false_pass": bool(row_passed)}
    required = [item for item in state.get("acceptanceCriteria", []) if item.get("blocking")]
    passed = [item for item in required if item.get("status") in {"PASS", "NOT_APPLICABLE"}]
    checkpoints = state.get("externalCheckpoints", [])
    human_interventions = sum(1 for item in checkpoints if item.get("status") == "RESOLVED")
    ready = [task for task in state.get("tasks", []) if task.get("status") == "READY"]
    false_external_blockers = int(state.get("status") == "WAITING_EXTERNAL" and bool(ready))
    repeated_work = sum(max(0, int(task.get("attempts", 0)) - 1) for task in state.get("tasks", []))
    events_path = run_files[-1].parent / "events.jsonl"
    active: set[str] = set()
    peak = 0
    if events_path.is_file():
        for line in events_path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            task_id = event.get("taskId")
            if event.get("type") == "task.started" and task_id:
                active.add(task_id)
                peak = max(peak, len(active))
            elif event.get("type") in {"worker.finished", "task.failed", "task.completed"} and task_id:
                active.discard(task_id)
    gates = state.get("gateResults", [])
    deployment_verified = any(
        gate.get("type") == "reality" and gate.get("status") == "PASS" and str(gate.get("id", "")).startswith("deployment-")
        for gate in gates
    )
    e2e_failures = sum(1 for gate in gates if gate.get("type") in {"e2e", "reality"} and gate.get("status") == "FAIL")
    outcome_pass = state.get("status") == "COMPLETED" and len(passed) == len(required)
    return {
        "schema": state.get("schema"),
        "status": state.get("status"),
        "outcome_pass": outcome_pass,
        "acceptance_required": len(required),
        "acceptance_passed": len(passed),
        "false_pass": bool(row_passed and not outcome_pass),
        "human_interventions": human_interventions,
        "false_external_blockers": false_external_blockers,
        "repeated_work_after_resume": repeated_work,
        "peak_parallel_workers": peak,
        "deployment_verified": deployment_verified,
        "product_e2e_failures": e2e_failures,
        "time_to_verified_outcome_per_intervention_ms": duration_ms / max(1, human_interventions) if outcome_pass else None,
    }


def bench(args: argparse.Namespace) -> int:
    scenarios_path = Path(args.scenarios).expanduser().resolve()
    config = load_config(scenarios_path)
    config_errors = benchmark_config_errors(config)
    if config_errors:
        raise SystemExit("invalid benchmark config:\n  - " + "\n  - ".join(config_errors))
    if args.validate:
        return 1 if validate_scenarios(config, scenarios_path.parent, allow_missing_repos=args.allow_missing_repos) else 0
    if args.execute and not args.scenario and not args.all_enabled:
        raise SystemExit("refusing to execute an implicit one-scenario subset; pass --scenario <id> or --all-enabled")
    scenarios = selected(config["scenarios"], args.scenario, args.all_enabled or args.list)
    arms = selected(config["arms"], args.arm, all_enabled=True)
    if args.list or not args.execute:
        print("Scenarios:")
        for scenario in scenarios:
            source = scenario.get("repo") or scenario.get("fixture")
            base = scenario.get("baseRef") or "frozen-fixture"
            print(f"  {scenario['id']} ({scenario['lane']}) source={source} base={base}")
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
    run_started = time.monotonic()
    run_deadline = run_started + args.run_timeout
    budget_exhausted = False
    print(
        f"run budget={args.run_timeout}s; per-cell agent timeout={args.agent_timeout}s; "
        f"heartbeat interval={args.heartbeat_interval}s"
    )
    for scenario in scenarios:
        repo = resolve_repo(scenario.get("repo") or scenario.get("fixture"), scenarios_path.parent)
        for repeat in range(args.repeats):
            for arm in arms:
                remaining = run_deadline - time.monotonic()
                if remaining <= 0:
                    budget_exhausted = True
                    print("ARCHITRAVE_BENCH_BUDGET_EXHAUSTED: no additional cells will be launched.", file=sys.stderr)
                    break
                cell_dir = root / scenario["id"] / arm["id"] / f"rep-{repeat}"
                worktree = cell_dir / "worktree"
                cell_dir.mkdir(parents=True, exist_ok=True)
                prompt = prompt_for(scenario, arm, repeat)
                write(cell_dir / "prompt.md", prompt)
                row: dict[str, Any] = {
                    "run_id": run_id,
                    "scenario": scenario["id"],
                    "category": scenario.get("category", "feature"),
                    "lane": scenario["lane"],
                    "arm": arm["id"],
                    "repeat": repeat,
                    "repo": str(repo),
                    "base_ref": scenario.get("baseRef") or f"fixture:{scenario.get('fixture')}",
                    "cell_dir": str(cell_dir),
                    "worktree": str(worktree),
                    "prompt_file": str(cell_dir / "prompt.md"),
                    "producer_prompt_version": PRODUCER_PROMPT_VERSION,
                    "execution": execution_snapshot(scenario, arm),
                    "run_budget_seconds": args.run_timeout,
                    "budget_remaining_at_start_ms": max(0, int(remaining * 1000)),
                    "started_at": datetime.now(timezone.utc).isoformat(),
                }
                try:
                    if scenario.get("fixture"):
                        row["base_commit"] = create_fixture_worktree(
                            repo,
                            worktree,
                            install_kit=bool(scenario.get("installKit")),
                        )
                    else:
                        row["base_commit"] = create_worktree(repo, scenario["baseRef"], worktree)
                    preexisting_summaries = run_summary_paths(worktree)
                    agent_timeout = min(args.agent_timeout, remaining)
                    agent_budget_limited = remaining < args.agent_timeout
                    row["agent"] = run_arm(
                        arm,
                        worktree,
                        prompt,
                        cell_dir,
                        agent_timeout,
                        args.heartbeat_interval,
                    )
                    if row["agent"].get("timed_out") and agent_budget_limited:
                        row["budget_exhausted"] = True
                        row["agent"]["timeout_reason"] = "run_budget"
                    elif row["agent"].get("timed_out"):
                        row["agent"]["timeout_reason"] = "cell_timeout"
                    row["execution"]["reportedSelection"] = reported_execution(worktree, preexisting_summaries)
                    row["execution"]["controlStatus"] = control_status(row["execution"]["requested"], row["agent"])
                    row["diff"] = diff_metrics(worktree)
                    row["diff_artifacts"] = save_diff_artifacts(worktree, cell_dir, os.environ.copy())
                    row["validation"] = run_validation(
                        worktree,
                        arm_values(scenario, "validation", arm["id"]),
                        cell_dir,
                        args.validation_timeout,
                        run_deadline,
                    )
                    if any(item.get("budget_exhausted") for item in row["validation"]):
                        row["budget_exhausted"] = True
                    row["artifacts"] = artifact_results(worktree, arm_values(scenario, "expectedArtifacts", arm["id"]))
                    row["passed"] = (
                        row["agent"].get("returncode") == 0
                        and not row["agent"].get("timed_out")
                        and all(item["returncode"] == 0 for item in row["validation"])
                        and all(item["exists"] for item in row["artifacts"])
                        and controls_allow_pass(row["execution"]["controlStatus"])
                    )
                    row["durable_run"] = durable_run_metrics(
                        worktree,
                        int((row.get("agent") or {}).get("duration_ms") or 0),
                        row["passed"],
                    )
                except Exception as exc:  # keep batch moving; DNF is data
                    row["passed"] = False
                    row["error"] = repr(exc)
                finally:
                    row["failure_mode"] = failure_mode(row)
                    row["finished_at"] = datetime.now(timezone.utc).isoformat()
                    append_jsonl(results_path, row)
                    if not row.get("passed"):
                        failures += 1
                    if args.cleanup_worktrees and worktree.exists():
                        try:
                            if scenario.get("fixture"):
                                shutil.rmtree(worktree)
                            else:
                                cleanup_worktree(repo, worktree)
                        except Exception as exc:
                            print(f"warn cleanup failed for {worktree}: {exc}", file=sys.stderr)
                    print(
                        f"{scenario['id']} {arm['id']} rep={repeat} passed={row.get('passed')} "
                        f"failure_mode={row.get('failure_mode')} -> {cell_dir}"
                    )
                    if row.get("budget_exhausted"):
                        budget_exhausted = True
                        print(
                            f"ARCHITRAVE_BENCH_BUDGET_EXHAUSTED: {scenario['id']} {arm['id']} "
                            "used the remaining run budget; no additional cells will be launched.",
                            file=sys.stderr,
                        )
            if budget_exhausted:
                break
        if budget_exhausted:
            break
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
    parser.add_argument("--agent-timeout", type=positive_seconds, default=600, help="maximum seconds per agent cell (default: 600)")
    parser.add_argument("--validation-timeout", type=positive_seconds, default=900)
    parser.add_argument("--run-timeout", type=positive_seconds, default=1200, help="total benchmark wall-time budget in seconds (default: 1200)")
    parser.add_argument("--heartbeat-interval", type=positive_seconds, default=60, help="agent progress heartbeat interval in seconds (default: 60)")
    parser.add_argument("--cleanup-worktrees", action="store_true")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--validate", action="store_true", help="validate scenario repo/baseRef references and exit")
    parser.add_argument("--allow-missing-repos", action="store_true", help="during validation, skip unavailable external repositories while still validating frozen fixtures")
    return bench(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())