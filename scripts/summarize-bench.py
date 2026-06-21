#!/usr/bin/env python3
"""Summarize Architrave benchmark JSONL rows."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any


def rows(path: Path) -> list[dict[str, Any]]:
    out = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                out.append(json.loads(line))
    return out


def fmt(value: float | int | None, digits: int = 1) -> str:
    if value is None:
        return ""
    if isinstance(value, int):
        return str(value)
    return f"{value:.{digits}f}"


def summarize(items: list[dict[str, Any]]) -> str:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in items:
        groups[(row.get("scenario", ""), row.get("arm", ""))].append(row)

    lines = ["# Architrave Benchmark Summary", ""]
    lines.append("| Scenario | Arm | n | pass % | avg ms | avg net LOC | avg files | avg output tokens | timeouts |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for (scenario, arm), group in sorted(groups.items()):
        n = len(group)
        pass_rate = 100 * sum(1 for row in group if row.get("passed")) / n if n else 0
        durations = [row.get("agent", {}).get("duration_ms") for row in group if row.get("agent", {}).get("duration_ms") is not None]
        net_locs = [row.get("diff", {}).get("net_loc") for row in group if row.get("diff", {}).get("net_loc") is not None]
        files = [row.get("diff", {}).get("changed_files") for row in group if row.get("diff", {}).get("changed_files") is not None]
        output_tokens = [row.get("agent", {}).get("output_tokens") for row in group if row.get("agent", {}).get("output_tokens") is not None]
        timeouts = sum(1 for row in group if row.get("agent", {}).get("timed_out"))
        lines.append(
            "| "
            + " | ".join(
                [
                    scenario,
                    arm,
                    str(n),
                    fmt(pass_rate),
                    fmt(mean(durations) if durations else None, 0),
                    fmt(mean(net_locs) if net_locs else None),
                    fmt(mean(files) if files else None),
                    fmt(mean(output_tokens) if output_tokens else None),
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
            lines.append(f"- `{row.get('scenario')}` / `{row.get('arm')}` rep `{row.get('repeat')}`: {row.get('error') or 'validation/artifact failure'} ({row.get('cell_dir')})")
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