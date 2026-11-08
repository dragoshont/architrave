#!/usr/bin/env python3
"""Fixtures for init-run, mark-stale-learning and semantic learning findings."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "harness" / "architrave_cli.py"
PROFILE = ".architrave/learning/repo-profile.md"


def run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(CLI), *args], cwd=repo, capture_output=True, text=True)


def check(name: str, condition: bool, detail: str = "") -> None:
    if not condition:
        raise SystemExit(f"FAIL {name} {detail}")
    print(f"ok   {name}")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        learning = repo / ".architrave" / "learning"
        learning.mkdir(parents=True)
        (repo / "docs").mkdir()
        (repo / "docs" / "guide.md").write_text("# Guide\n")
        (repo / "architrave.config.json").write_text("{}\n")

        result = run(repo / "docs", "init-run", "r1")
        summary = repo / ".architrave/runs/r1/summary.json"
        check("init-run", result.returncode == 0 and json.loads(summary.read_text())["runId"] == "r1", result.stderr)
        check("init-run-rejects-traversal", run(repo, "init-run", "../x").returncode == 2)

        (learning / "repo-profile.md").write_text("# Profile\nValid [g](docs/guide.md)\nBroken [m](docs/missing.md)\n")
        (learning / "repo-lessons.md").write_text("# Lessons\n")
        result = run(repo, "mark-stale-learning")
        check("stale-dry-run", "would mark" in result.stdout and "UNVALIDATED" not in (repo / PROFILE).read_text())
        run(repo, "mark-stale-learning", "--apply")
        text = (repo / PROFILE).read_text()
        check("stale-apply", "UNVALIDATED: Broken" in text and "UNVALIDATED: Valid" not in text)

        (repo / "docs/ADR-0020.md").write_text(
            "# ADR-0020\nStatus: accepted\nRetire the engine; supersedes ADR-0016 and ADR-0018.\n")
        (repo / "docs/ADR-0019.md").write_text("# ADR-0019\nStatus: superseded by ADR-0020.\n")
        (repo / PROFILE).write_text(
            "# Project map\n"
            "Current architecture: [accepted ADR-0020](docs/ADR-0020.md); engine retired.\n"
            "Unresolved issue references: [ADR-0016](docs/ADR-0016.md), [ADR-0018](docs/ADR-0018.md).\n"
            "Historical engine plan: [ADR-0019](docs/ADR-0019.md).\n")
        result = run(repo, "mark-stale-learning", "--apply")
        text = (repo / PROFILE).read_text()
        check("project-map-current-authority", result.returncode == 0
              and "\nCurrent architecture:" in text and "engine retired" in text)
        check("project-map-deleted-issue-references-unresolved",
              "\nUNVALIDATED: Unresolved issue references:" in text)
        check("project-map-existing-link-is-not-semantic-proof",
              "\nHistorical engine plan:" in text)
        findings = learning / "semantic-stale-facts.jsonl"
        findings.write_text(json.dumps({
            "file": PROFILE, "line": 4,
            "currentText": "Historical engine plan: [ADR-0019](docs/ADR-0019.md).",
            "severity": "major", "reason": "ADR-0020 retires this engine; ADR-0019 is superseded",
        }) + "\n")
        result = run(repo, "apply-semantic-learning-findings", "--apply")
        check("project-map-reviewed-supersession",
              result.returncode == 0 and "\nUNVALIDATED: Historical engine plan:" in (repo / PROFILE).read_text())

        (repo / PROFILE).write_text("# Repo Profile\n\nBuild uses make release on Windows.\nUNVALIDATED: Old claim.\n")
        (learning / "repo-lessons.md").write_text("# Repo Lessons\n\nNo durable semantic claims here.\n")
        result = run(repo, "semantic-learning-review", "--provider", "copilot")
        prompt = (learning / "semantic-stale-facts-prompt.md").read_text()
        check("semantic-review-prompt", "semantic-learning-review prompt:" in result.stdout and "JSON Lines only" in prompt
              and "copilot -C" not in result.stdout and "claude --agent" not in result.stdout)
        (learning / "semantic-stale-facts-prompt.md").unlink()
        result = run(repo, "semantic-learning-review", "--execute")
        check("semantic-review-execute-refused",
              result.returncode == 2 and "NATIVE_HOST_REQUIRED" in result.stderr
              and not (learning / "semantic-stale-facts-prompt.md").exists())

        findings = learning / "semantic-stale-facts.jsonl"
        findings.write_text(
            json.dumps({"file": PROFILE, "line": 3, "currentText": "Build uses make release on Windows.",
                        "severity": "major", "reason": "no evidence"}) + "\n"
            + json.dumps({"file": PROFILE, "line": 4, "currentText": "Old claim.", "severity": "minor",
                          "reason": "already marked"}) + "\n")
        result = run(repo, "apply-semantic-learning-findings")
        check("semantic-dry-run", f"would mark {PROFILE}:3" in result.stdout
              and "UNVALIDATED: Build" not in (repo / PROFILE).read_text())
        run(repo, "apply-semantic-learning-findings", "--apply")
        text = (repo / PROFILE).read_text()
        check("semantic-apply", "UNVALIDATED: Build uses make release on Windows.\n" in text)
        check("semantic-existing-unvalidated", text.count("UNVALIDATED: Old claim.") == 1)

        findings.write_text(json.dumps({"file": PROFILE, "line": 3, "currentText": "Different text."}) + "\n")
        check("semantic-stale-finding", run(repo, "apply-semantic-learning-findings", "--apply").returncode == 1)
        findings.write_text(json.dumps({"file": "README.md", "line": 1, "currentText": "# README"}) + "\n")
        check("semantic-invalid-target", run(repo, "apply-semantic-learning-findings", "--apply").returncode == 1)
        findings.write_text("PASS\n")
        check("semantic-pass-output", "no semantic stale findings" in run(repo, "apply-semantic-learning-findings").stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
