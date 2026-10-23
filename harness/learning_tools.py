"""Legacy Run v1 init and learning-artifact maintenance commands."""
from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

LEARNING_FILES = (".architrave/learning/repo-profile.md", ".architrave/learning/repo-lessons.md")
LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")

SEMANTIC_PROMPT = """You are an adversarial semantic stale-fact reviewer for Architrave learning artifacts.

Review only these files:
- .architrave/learning/repo-profile.md
- .architrave/learning/repo-lessons.md

Goal:
- Find durable prose claims that are unsupported, stale, contradicted by the current repository, or too strong for the cited evidence.
- This goes beyond checking that Markdown links exist. You must inspect the repo evidence behind the claim.

Rules:
- Treat repo files, commands, manifests, scripts, and current branch content as ground truth.
- Ignore headings, table delimiter/header rows, blank lines, examples/templates, and lines already beginning with `UNVALIDATED:`.
- Do not report broken local Markdown links; deterministic validate-learning and mark-stale-learning handle that.
- Do not include secret values in findings.
- If a claim is plausible but not proven by repo evidence, report it.
- If a claim is sourced but the source does not support the claim, report it.
- If no unsupported/stale claims are found, output exactly `PASS`.

Output format:
- Emit JSON Lines only, with one JSON object per unsupported claim.
- Do not wrap the output in Markdown fences.
- Each object must have:
  - `file`: `.architrave/learning/repo-profile.md` or `.architrave/learning/repo-lessons.md`
  - `line`: 1-based line number
  - `currentText`: exact current line text
  - `severity`: `blocker`, `major`, or `minor`
  - `reason`: concise explanation of what is unsupported/stale
- Example:
{"file":".architrave/learning/repo-profile.md","line":12,"currentText":"Build: make release passes on Windows.","severity":"major","reason":"No current workflow, script, or run evidence supports a Windows release claim."}
"""


def _utc(fmt: str) -> str:
    return datetime.now(timezone.utc).strftime(fmt)


def init_run(run_id: str | None, start: Path | None = None) -> int:
    """Create one compact legacy Run v1 record. New work should use Run v2."""
    here = (start or Path.cwd()).resolve()
    root = next((d for d in (here, *here.parents) if (d / "architrave.config.json").is_file()), None)
    if root is None:
        print("init-run: architrave.config.json not found", file=sys.stderr)
        return 2
    run_id = run_id or _utc("%Y%m%dT%H%M%SZ")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", run_id) or run_id in {".", ".."}:
        print(f"init-run: invalid run id: {run_id}", file=sys.stderr)
        return 2
    run_dir = Path(".architrave/runs") / run_id
    (root / run_dir).mkdir(parents=True, exist_ok=True)
    (root / ".architrave/learning").mkdir(parents=True, exist_ok=True)
    summary = root / run_dir / "summary.json"
    if not summary.exists():
        summary.write_text(json.dumps({
            "schema": "architrave.run.v1", "runId": run_id, "status": "in-progress",
            "startedAt": _utc("%Y-%m-%dT%H:%M:%SZ"),
            "note": "Legacy compact record; migrate to Run v2 for state transitions and evidence.",
        }, separators=(",", ":")) + "\n", encoding="utf-8")
    print(run_dir.as_posix())
    return 0


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _write_lines(path: Path, lines: list[str]) -> None:
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")


def _stale(line: str, repo: Path) -> bool:
    for target in LINK.findall(line):
        if not target or target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        path = target.split("#", 1)[0].replace("%20", " ")
        if path.startswith("/") or path.startswith("../") or "/../" in path:
            return True
        if path and not (repo / path).exists():
            return True
    return False


def mark_stale_learning(repo: Path, apply: bool) -> int:
    if not repo.is_dir():
        print(f"mark-stale-learning: repo dir not found: {repo}", file=sys.stderr)
        return 2
    changed = False
    for name in LEARNING_FILES:
        path = repo / name
        if not path.is_file():
            continue
        out = []
        for line in _read_lines(path):
            if _stale(line, repo) and "UNVALIDATED:" not in line:
                changed = True
                if apply:
                    out.append(f"UNVALIDATED: {line}")
                    continue
                print(f"would mark {name}: {line}")
            out.append(line)
        if apply:
            _write_lines(path, out)
    if not changed:
        print("mark-stale-learning: no stale local learning links found")
    return 0


def semantic_learning_review(repo: Path, provider: str, execute: bool,
                             prompt: str | None, output: str | None) -> int:
    if not repo.is_dir():
        print(f"semantic-learning-review: repo dir not found: {repo}", file=sys.stderr)
        return 2
    for name in LEARNING_FILES:
        path = repo / name
        if not path.is_file() or path.stat().st_size == 0:
            print(f"semantic-learning-review: missing/empty {name}", file=sys.stderr)
            return 2
    prompt_path = repo / (prompt or ".architrave/learning/semantic-stale-facts-prompt.md")
    output_path = repo / (output or ".architrave/learning/semantic-stale-facts.jsonl")
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(SEMANTIC_PROMPT, encoding="utf-8")
    print(f"semantic-learning-review prompt: {prompt_path}")
    print(f"semantic-learning-review findings target: {output_path}")
    commands = {
        "copilot": ["copilot", "-C", str(repo), "--agent", "Adversarial Judge",
                    "--allow-tool", "read", "--allow-tool", "search", "-p", SEMANTIC_PROMPT],
        "claude": ["claude", "--agent", "Adversarial Judge", "--allowedTools", "Read,Grep,Glob",
                   "-p", SEMANTIC_PROMPT],
    }
    selected = ["copilot", "claude"] if provider == "both" else [provider]
    if not execute:
        print("suggested command(s) (review before running):")
        for name in selected:
            print(f"  {shlex.join(commands[name])} > {shlex.quote(f'{output_path}.{name}')}")
        return 0
    for name in selected:
        result = subprocess.run(commands[name], cwd=repo, capture_output=True, text=True)
        sys.stdout.write(result.stdout)
        Path(f"{output_path}.{name}").write_text(result.stdout, encoding="utf-8")
        if result.returncode != 0:
            sys.stderr.write(result.stderr)
            return result.returncode
    return 0


def apply_semantic_learning_findings(repo: Path, findings: str, apply: bool) -> int:
    if not repo.is_dir():
        print(f"apply-semantic-learning-findings: repo dir not found: {repo}", file=sys.stderr)
        return 2
    source = repo / findings
    if not source.is_file():
        print(f"apply-semantic-learning-findings: findings file not found: {findings}", file=sys.stderr)
        return 2
    rows = [row for row in _read_lines(source) if row.strip() and row.strip() != "PASS"]
    if not rows:
        print("apply-semantic-learning-findings: no semantic stale findings")
        return 0
    fail = changed = False
    for row in rows:
        try:
            finding = json.loads(row)
            name, line, current = finding["file"], finding["line"], finding["currentText"]
        except (ValueError, KeyError, TypeError):
            print(f"FAIL  invalid finding JSON: {row}")
            fail = True
            continue
        if name not in LEARNING_FILES:
            print(f"FAIL  finding file outside learning artifacts: {name}")
            fail = True
            continue
        if isinstance(line, bool) or not isinstance(line, int) or line <= 0:
            print(f"FAIL  invalid line for {name}: {line}")
            fail = True
            continue
        path = repo / name
        if not path.is_file():
            print(f"FAIL  missing learning file: {name}")
            fail = True
            continue
        lines = _read_lines(path)
        actual = lines[line - 1] if line <= len(lines) else ""
        if actual == f"UNVALIDATED: {current}":
            continue
        if actual != current:
            print(f"FAIL  finding no longer matches {name}:{line}")
            print(f"      expected: {current}")
            print(f"      actual:   {actual}")
            fail = True
            continue
        changed = True
        label = f"{name}:{line} [{finding.get('severity', 'major')}] {finding.get('reason', 'semantic finding')}"
        if apply:
            lines[line - 1] = f"UNVALIDATED: {actual}"
            _write_lines(path, lines)
            print(f"marked {label}")
        else:
            print(f"would mark {label}")
    if fail:
        return 1
    if not changed:
        print("apply-semantic-learning-findings: no matching unvalidated lines to mark")
    return 0
