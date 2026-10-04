#!/usr/bin/env python3
"""Rebuild pinned trials and verify published orchestration evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
BASELINE_SHA = "165da5284e0fff5ecfa7b1fff18593c949ad8fd3"
BASELINE_MANIFEST = ROOT / "benchmarks/results/orchestration-baseline.json"
AFTER_MANIFEST = ROOT / "benchmarks/results/orchestration-after.json"
LEDGER = ROOT / "docs/orchestration-audit.md"
MEASURE = ROOT / "scripts/measure-basic-sh-sdd.py"


def git(*arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != "architrave.orchestration-metrics.v1":
        raise ValueError(f"invalid metrics schema: {path}")
    for key in ("orchestrationArtifacts", "actualCodeArtifacts"):
        records = value.get(key)
        if not isinstance(records, list):
            raise ValueError(f"missing artifact list {key}: {path}")
        if any(not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", ""))) for item in records):
            raise ValueError(f"invalid artifact digest: {path}")
    if len(value["orchestrationArtifacts"]) != value.get("orchestrationFiles"):
        raise ValueError(f"artifact count mismatch: {path}")
    if sum(int(item["bytes"]) for item in value["orchestrationArtifacts"]) != value.get("orchestrationBytes"):
        raise ValueError(f"artifact byte mismatch: {path}")
    return value


def materialize(commit: str, path: Path) -> None:
    git("cat-file", "-e", f"{commit}^{{commit}}")
    completed = subprocess.run(
        ["git", "worktree", "add", "--detach", str(path), commit],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        raise RuntimeError(
            f"cannot materialize {commit} (exit {completed.returncode}):\n{completed.stdout}\n{completed.stderr}"
        )


def measure(source: Path, output: Path, label: str) -> dict[str, object]:
    manifest = output / f"{label}.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(MEASURE),
            "--source",
            str(source),
            "--output",
            str(output / "trials"),
            "--label",
            label,
            "--manifest",
            str(manifest),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        raise RuntimeError(
            f"measurement failed for {source} (exit {completed.returncode}):\n{completed.stdout}\n{completed.stderr}"
        )
    return load(manifest)


def comparable(value: dict[str, object]) -> dict[str, object]:
    return {key: item for key, item in value.items() if key != "platform"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-after", default=load(AFTER_MANIFEST)["sourceSha"])
    args = parser.parse_args()
    baseline_published = load(BASELINE_MANIFEST)
    after_published = load(AFTER_MANIFEST)
    if baseline_published["sourceSha"] != BASELINE_SHA:
        raise SystemExit("baseline manifest is not pinned to the canonical baseline")
    if after_published["sourceSha"] != args.expected_after:
        raise SystemExit("after manifest SHA does not match --expected-after")
    with tempfile.TemporaryDirectory(prefix="architrave-metrics-") as temporary:
        base = Path(temporary)
        baseline_tree = base / "baseline"
        after_tree = base / "after"
        try:
            materialize(BASELINE_SHA, baseline_tree)
            materialize(str(args.expected_after), after_tree)
            baseline_generated = measure(baseline_tree, base, "baseline")
            after_generated = measure(after_tree, base, "after")
        finally:
            for tree in (baseline_tree, after_tree):
                if tree.exists():
                    subprocess.run(
                        ["git", "worktree", "remove", "--force", str(tree)],
                        cwd=ROOT,
                        check=False,
                        capture_output=True,
                    )
    if comparable(baseline_generated) != comparable(baseline_published):
        raise SystemExit("published baseline manifest does not match source-derived measurement")
    if comparable(after_generated) != comparable(after_published):
        raise SystemExit("published after manifest does not match source-derived measurement")
    reductions = {
        "files": 100 * (int(baseline_generated["orchestrationFiles"]) - int(after_generated["orchestrationFiles"])) / int(baseline_generated["orchestrationFiles"]),
        "bytes": 100 * (int(baseline_generated["orchestrationBytes"]) - int(after_generated["orchestrationBytes"])) / int(baseline_generated["orchestrationBytes"]),
        "tokens": 100 * (int(baseline_generated["approxTokens"]) - int(after_generated["approxTokens"])) / int(baseline_generated["approxTokens"]),
    }
    if min(reductions.values()) < 80:
        raise SystemExit(f"published reduction is below 80%: {reductions}")
    ledger = LEDGER.read_text(encoding="utf-8")
    expected_lines = (
        f"| Orchestration files | {baseline_generated['orchestrationFiles']} | {after_generated['orchestrationFiles']} |",
        f"| Orchestration bytes | {int(baseline_generated['orchestrationBytes']):,} | {int(after_generated['orchestrationBytes']):,} |",
        f"| Approximate tokens (`bytes / 4`) | {int(baseline_generated['approxTokens']):,} | {int(after_generated['approxTokens']):,} |",
    )
    if any(line not in ledger for line in expected_lines):
        raise SystemExit("ledger metrics do not match source-derived manifests")
    print(
        "orchestration metrics: PASS "
        + " ".join(f"{name}={value:.2f}%" for name, value in reductions.items())
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
