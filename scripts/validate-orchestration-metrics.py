#!/usr/bin/env python3
"""Validate compact published orchestration metrics against the audit ledger."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


BASELINE_SHA = "165da5284e0fff5ecfa7b1fff18593c949ad8fd3"


def load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != "architrave.orchestration-metrics.v1":
        raise ValueError(f"invalid metrics schema: {path}")
    records = value.get("orchestrationArtifacts")
    if not isinstance(records, list) or len(records) != value.get("orchestrationFiles"):
        raise ValueError(f"artifact count mismatch: {path}")
    if sum(int(item["bytes"]) for item in records) != value.get("orchestrationBytes"):
        raise ValueError(f"artifact byte mismatch: {path}")
    if any(not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", ""))) for item in records):
        raise ValueError(f"invalid artifact digest: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, default=Path("benchmarks/results/orchestration-baseline.json"))
    parser.add_argument("--after", type=Path, default=Path("benchmarks/results/orchestration-after.json"))
    parser.add_argument("--ledger", type=Path, default=Path("docs/orchestration-audit.md"))
    args = parser.parse_args()
    baseline = load(args.baseline)
    after = load(args.after)
    if baseline["sourceSha"] != BASELINE_SHA:
        raise SystemExit("baseline source SHA is not pinned to the published baseline")
    reductions = {
        "files": 100 * (int(baseline["orchestrationFiles"]) - int(after["orchestrationFiles"])) / int(baseline["orchestrationFiles"]),
        "bytes": 100 * (int(baseline["orchestrationBytes"]) - int(after["orchestrationBytes"])) / int(baseline["orchestrationBytes"]),
        "tokens": 100 * (int(baseline["approxTokens"]) - int(after["approxTokens"])) / int(baseline["approxTokens"]),
    }
    if min(reductions.values()) < 80:
        raise SystemExit(f"published reduction is below 80%: {reductions}")
    ledger = args.ledger.read_text(encoding="utf-8")
    expected = (
        f"| Orchestration files | {baseline['orchestrationFiles']} | {after['orchestrationFiles']} |",
        f"| Orchestration bytes | {int(baseline['orchestrationBytes']):,} | {int(after['orchestrationBytes']):,} |",
        f"| Approximate tokens (`bytes / 4`) | {int(baseline['approxTokens']):,} | {int(after['approxTokens']):,} |",
    )
    missing = [line for line in expected if line not in ledger]
    if missing:
        raise SystemExit("ledger metrics do not match manifests: " + "; ".join(missing))
    print(
        "orchestration metrics: PASS "
        + " ".join(f"{name}={value:.2f}%" for name, value in reductions.items())
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
