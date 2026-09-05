#!/usr/bin/env python3
"""Summarize Architrave benchmark JSONL rows."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, median, pvariance
from typing import Any


def rows(path: Path) -> list[dict[str, Any]]:
    out = []
    with path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if line.strip():
                row = json.loads(line)
                missing = [key for key in ("run_id", "scenario", "arm", "repeat", "passed") if key not in row]
                if missing:
                    raise ValueError(f"{path}:{number}: missing required result keys: {', '.join(missing)}")
                out.append(row)
    return out


def fmt(value: float | int | None, digits: int = 1) -> str:
    if value is None:
        return ""
    if isinstance(value, int):
        return str(value)
    return f"{value:.{digits}f}"


def group_values(group: list[dict[str, Any]], getter) -> str:
    values = {str(value) for row in group if (value := getter(row)) not in (None, "")}
    return ", ".join(sorted(values)) or "inherit"


def control_observability(row: dict[str, Any]) -> str:
    status = ((row.get("execution") or {}).get("controlStatus") or {})
    return "; ".join(
        [
            f"honored={status.get('controlsHonored')}",
            f"model={status.get('model', 'unreported')}",
            f"reasoning={status.get('reasoningEffort', 'unreported')}",
            f"context={status.get('contextTier', 'unreported')}",
        ]
    )


def percentile(values: list[float | int], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * fraction + 0.5)))
    return float(ordered[index])


def summarize(items: list[dict[str, Any]]) -> str:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in items:
        groups[(row.get("scenario", ""), row.get("arm", ""))].append(row)

    lines = ["# Architrave Benchmark Summary", ""]
    lines.append("| Scenario | Arm | Profile | Requested binding | Control observability | n | pass % | median ms | p90 ms | variance ms | durable evidence | outcome % (all rows) | human interventions | false PASS | repeated work | timeouts |")
    lines.append("|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for (scenario, arm), group in sorted(groups.items()):
        n = len(group)
        pass_rate = 100 * sum(1 for row in group if row.get("passed")) / n if n else 0
        agents = [row.get("agent") or {} for row in group]
        durations = [agent.get("duration_ms") for agent in agents if agent.get("duration_ms") is not None]
        durable = [row.get("durable_run") or {} for row in group]
        outcomes = [item for item in durable if item]
        outcome_rate = 100 * sum(1 for item in outcomes if item.get("outcome_pass")) / n if n else 0
        evidence_coverage = f"{len(outcomes)}/{n} ({100 * len(outcomes) / n:.1f}%)" if n else "0/0"
        interventions = sum(int(item.get("human_interventions") or 0) for item in outcomes)
        false_passes = sum(1 for item in outcomes if item.get("false_pass"))
        repeated_work = sum(int(item.get("repeated_work_after_resume") or 0) for item in outcomes)
        timeouts = sum(1 for agent in agents if agent.get("timed_out"))
        profile = group_values(group, lambda row: ((((row.get("execution") or {}).get("requested") or {}).get("semantic") or {}).get("profile")))
        binding = group_values(
            group,
            lambda row: "/".join(
                str(value)
                for value in (
                    ((row.get("execution") or {}).get("requested") or {}).get("model"),
                    ((row.get("execution") or {}).get("requested") or {}).get("reasoningEffort"),
                    ((row.get("execution") or {}).get("requested") or {}).get("contextTier"),
                )
                if value
            ),
        )
        controls = group_values(group, control_observability)
        lines.append(
            "| "
            + " | ".join(
                [
                    scenario,
                    arm,
                    profile,
                    binding,
                    controls,
                    str(n),
                    fmt(pass_rate),
                    fmt(median(durations) if durations else None, 0),
                    fmt(percentile(durations, 0.90), 0),
                    fmt(pvariance(durations) if len(durations) > 1 else 0, 0),
                    evidence_coverage,
                    fmt(outcome_rate),
                    str(interventions),
                    str(false_passes),
                    str(repeated_work),
                    str(timeouts),
                ]
            )
            + " |"
        )

    lines.append("")
    lines.append("## Failed Rows")
    lines.append("")
    failed = [row for row in items if not row.get("passed")]
    if not failed:
        lines.append("None.")
    else:
        for row in failed:
            reason = row.get("failure_mode") or row.get("error") or "validation/artifact failure"
            lines.append(f"- `{row.get('scenario')}` / `{row.get('arm')}` rep `{row.get('repeat')}`: {reason} ({row.get('cell_dir')})")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    text = summarize(rows(args.results))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())