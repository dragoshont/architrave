#!/usr/bin/env python3
"""Judge Architrave benchmark rows with Copilot CLI.

This is optional and resumable. It reads bench results JSONL, asks a frontier
model to score each row against the benchmark rubric, and writes judged JSONL.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        rows = []
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            missing = [key for key in ("run_id", "scenario", "arm", "repeat", "passed") if key not in row]
            if missing:
                raise ValueError(f"{path}:{number}: missing required result keys: {', '.join(missing)}")
            rows.append(row)
        return rows


def scenario_map(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {scenario["id"]: scenario for scenario in config["scenarios"]}


def excerpt(path: str | None, limit: int) -> str:
    if not path:
        return ""
    file_path = Path(path)
    if not file_path.exists():
        return ""
    text = file_path.read_text(encoding="utf-8", errors="replace")
    return text[-limit:]


def prompt_for(row: dict[str, Any], scenario: dict[str, Any], rubric: str, limit: int) -> str:
    cell_dir = Path(row.get("cell_dir", ""))
    stdout = excerpt(str(cell_dir / "agent.stdout"), limit)
    stderr = excerpt(str(cell_dir / "agent.stderr"), 2000)
    validations = row.get("validation", [])
    artifacts = row.get("artifacts", [])
    diff = row.get("diff", {})
    diff_artifacts = row.get("diff_artifacts", {})
    patch = excerpt(diff_artifacts.get("patch"), limit)
    status = excerpt(diff_artifacts.get("status"), 2000)
    return f"""You are judging one Architrave benchmark run.

Return ONLY JSON with this shape:
{{
  "scenario": "...",
  "arm": "...",
  "scores": {{
    "correctness": 0-5,
    "clarity": 0-5,
    "yagni": 0-5,
    "process": 0-5,
    "repo_fit": 0-5
  }},
  "verdict": "PASS|REVISE|FAIL",
  "findings": ["short evidence-backed finding"],
  "human_review_recommended": true|false
}}

Rubric:
{rubric}

Scenario:
{json.dumps(scenario, indent=2)}

Scenario-specific scoring checklist:
{json.dumps(scenario.get('scoring', {}), indent=2)}

Run row:
{json.dumps(row, indent=2)}

Validation:
{json.dumps(validations, indent=2)}

Artifact checks:
{json.dumps(artifacts, indent=2)}

Diff metrics:
{json.dumps(diff, indent=2)}

Git status:
{status}

Diff patch tail:
{patch}

Agent stdout tail:
{stdout}

Agent stderr tail:
{stderr}
"""


def copilot_complete(prompt: str, model: str | None, timeout: int) -> tuple[str, dict[str, Any]]:
    cmd = [
        "copilot",
        "--no-custom-instructions",
        "--disable-builtin-mcps",
        "--output-format",
        "json",
        "--stream",
        "off",
        "--silent",
        "--allow-all-tools",
        "-p",
        prompt,
    ]
    if model and model != "auto":
        cmd[1:1] = ["--model", model]
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
    content = ""
    output_tokens = 0
    for line in proc.stdout.splitlines():
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        data = event.get("data") or {}
        if event.get("type") == "assistant.message":
            content = data.get("content") or content
            output_tokens += int(data.get("outputTokens") or 0)
    return content, {"returncode": proc.returncode, "stderr": proc.stderr[-2000:], "output_tokens": output_tokens}


def parse_judge_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end >= start:
        text = text[start : end + 1]
    return json.loads(text)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", default="benchmarks/scenarios.json", type=Path)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--rubric", default="benchmarks/judge-rubric.md", type=Path)
    parser.add_argument("--model", default=os.environ.get("ARCHITRAVE_BENCH_JUDGE_MODEL", "auto"), help="Copilot judge model id. 'auto' means Copilot CLI default; set ARCHITRAVE_BENCH_JUDGE_MODEL to pin.")
    parser.add_argument("--timeout", type=int, default=300, help="Per-row judge timeout in seconds. Increase for long diffs or slow frontier models.")
    parser.add_argument("--excerpt-chars", type=int, default=12000)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    scenarios = scenario_map(read_json(args.scenarios))
    rubric = args.rubric.read_text(encoding="utf-8")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if args.out.exists():
        for row in read_rows(args.out):
            done.add((row.get("scenario"), row.get("arm"), row.get("repeat")))
    count = 0
    with args.out.open("a", encoding="utf-8") as handle:
        for row in read_rows(args.results):
            key = (row.get("scenario"), row.get("arm"), row.get("repeat"))
            if key in done:
                continue
            if args.limit and count >= args.limit:
                break
            content, meta = copilot_complete(prompt_for(row, scenarios[row["scenario"]], rubric, args.excerpt_chars), args.model, args.timeout)
            judged = {"scenario": row.get("scenario"), "arm": row.get("arm"), "repeat": row.get("repeat"), "judge_model": args.model, "judge_meta": meta}
            try:
                judged.update(parse_judge_json(content))
            except Exception as exc:
                judged.update({"verdict": "FAIL", "parse_error": repr(exc), "raw_content": content[-4000:]})
            handle.write(json.dumps(judged, sort_keys=True) + "\n")
            handle.flush()
            count += 1
            print(f"judged {key}: {judged.get('verdict')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())