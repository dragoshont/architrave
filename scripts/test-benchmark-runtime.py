#!/usr/bin/env python3

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BenchmarkRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.fixture = self.base / "fixture"
        self.fixture.mkdir()
        (self.fixture / "README.md").write_text("# Fixture\n", encoding="utf-8")
        self.scenarios = self.base / "scenarios.json"
        self.scenarios.write_text(
            json.dumps(
                {
                    "version": 2,
                    "arms": [
                        {
                            "id": "failing-shell",
                            "runner": "shell",
                            "command": [sys.executable, "-c", "raise SystemExit(7)"],
                        }
                    ],
                    "scenarios": [
                        {
                            "id": "fixture-failure",
                            "enabled": True,
                            "fixture": str(self.fixture),
                            "lane": "runtime",
                            "category": "short-mechanical",
                            "prompt": "Fail deterministically.",
                            "validation": [],
                            "expectedArtifacts": [],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_benchmark(self, *arguments: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "bench-architrave.py"), "--scenarios", str(self.scenarios), *arguments],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )

    def test_fixture_scenario_lists_without_repo_or_base_ref(self) -> None:
        result = self.run_benchmark("--scenario", "fixture-failure", "--list")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("frozen-fixture", result.stdout)

    def test_failed_agent_row_fails_benchmark_process(self) -> None:
        result = self.run_benchmark(
            "--scenario",
            "fixture-failure",
            "--arm",
            "failing-shell",
            "--execute",
            "--out",
            str(self.base / "runs"),
            "--cleanup-worktrees",
        )
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        results = list((self.base / "runs").glob("*/results.jsonl"))
        self.assertEqual(1, len(results))
        row = json.loads(results[0].read_text(encoding="utf-8"))
        self.assertFalse(row["passed"])
        self.assertEqual("agent_error", row["failure_mode"])

    def test_unobserved_requested_model_cannot_pass(self) -> None:
        bin_dir = self.base / "bin"
        bin_dir.mkdir()
        copilot = bin_dir / "copilot"
        copilot.write_text(
            "#!/usr/bin/env python3\n"
            "print('{\"type\":\"assistant.message\",\"data\":{\"content\":\"done\"}}')\n",
            encoding="utf-8",
        )
        copilot.chmod(0o755)
        self.scenarios.write_text(
            json.dumps(
                {
                    "version": 2,
                    "arms": [{"id": "controlled-copilot", "runner": "copilot", "model": "requested-model"}],
                    "scenarios": [
                        {
                            "id": "fixture-model-observation",
                            "fixture": str(self.fixture),
                            "lane": "runtime",
                            "category": "short-mechanical",
                            "prompt": "Finish successfully without model telemetry.",
                            "validation": [],
                            "expectedArtifacts": [],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
        result = self.run_benchmark(
            "--scenario",
            "fixture-model-observation",
            "--arm",
            "controlled-copilot",
            "--execute",
            "--out",
            str(self.base / "controlled-runs"),
            "--cleanup-worktrees",
            env=env,
        )
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        results = list((self.base / "controlled-runs").glob("*/results.jsonl"))
        self.assertEqual(1, len(results))
        row = json.loads(results[0].read_text(encoding="utf-8"))
        self.assertFalse(row["passed"])
        self.assertEqual("unobserved", row["execution"]["controlStatus"]["model"])
        self.assertEqual("control_unhonored", row["failure_mode"])

    def test_run_budget_stops_remaining_cells_and_reports_heartbeat(self) -> None:
        self.scenarios.write_text(
            json.dumps(
                {
                    "version": 2,
                    "arms": [
                        {
                            "id": "slow-shell",
                            "runner": "shell",
                            "command": [sys.executable, "-c", "import time; time.sleep(3)"],
                        },
                        {
                            "id": "not-launched",
                            "runner": "shell",
                            "command": [sys.executable, "-c", "print('should not run')"],
                        },
                    ],
                    "scenarios": [
                        {
                            "id": "fixture-budget",
                            "fixture": str(self.fixture),
                            "lane": "runtime",
                            "category": "short-mechanical",
                            "prompt": "Run within the wall-time budget.",
                            "validation": [],
                            "expectedArtifacts": [],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        result = self.run_benchmark(
            "--scenario",
            "fixture-budget",
            "--execute",
            "--out",
            str(self.base / "budget-runs"),
            "--run-timeout",
            "2",
            "--heartbeat-interval",
            "1",
            "--cleanup-worktrees",
        )
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("per-cell agent timeout=600s", result.stdout)
        self.assertIn("ARCHITRAVE_BENCH_HEARTBEAT", result.stdout)
        self.assertIn("ARCHITRAVE_BENCH_BUDGET_EXHAUSTED", result.stderr)
        results = list((self.base / "budget-runs").glob("*/results.jsonl"))
        self.assertEqual(1, len(results))
        rows = [json.loads(line) for line in results[0].read_text(encoding="utf-8").splitlines()]
        self.assertEqual(1, len(rows))
        self.assertEqual("slow-shell", rows[0]["arm"])
        self.assertTrue(rows[0]["budget_exhausted"])
        self.assertEqual("run_budget_exhausted", rows[0]["failure_mode"])
        self.assertEqual("run_budget", rows[0]["agent"]["timeout_reason"])


if __name__ == "__main__":
    unittest.main(verbosity=2)