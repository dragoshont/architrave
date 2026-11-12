#!/usr/bin/env python3

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import importlib.util


ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("benchmark", ROOT / "scripts/bench-architrave.py")
BENCH = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(BENCH)


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
        copilot = bin_dir / ("copilot.cmd" if os.name == "nt" else "copilot")
        if os.name == "nt":
            copilot.write_text(
                '@echo off\npython -c "print(\'{\\\"type\\\":\\\"assistant.message\\\",\\\"data\\\":{\\\"content\\\":\\\"done\\\"}}\')" \n',
                encoding="utf-8",
            )
        else:
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

    def test_existing_run_directory_is_not_deleted_or_reused(self) -> None:
        output = self.base / "existing-runs"
        previous = output / "stable-id"
        previous.mkdir(parents=True)
        sentinel = previous / "owner-data"
        sentinel.write_text("keep")
        result = self.run_benchmark("--scenario", "fixture-failure", "--execute",
                                    "--out", str(output), "--run-id", "stable-id", "--cleanup-worktrees")
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("keep", sentinel.read_text())

    @unittest.skipUnless(os.name == "posix", "owned-process signal test uses POSIX")
    def test_owned_process_interruption_requires_persisted_session_and_marker(self) -> None:
        # This verifies the process-control helper, not a Copilot host/model run.
        events = self.base / "events.jsonl"
        marker = self.base / "checkpoint.json"
        script = (
            "import json, pathlib, signal\n"
            "signal.signal(signal.SIGINT, lambda *_: exit(23))\n"
            f"p=pathlib.Path({str(events)!r})\n"
            "p.write_text(json.dumps({'type':'session.start','data':{'sessionId':'owned-test'}})+'\\n'"
            "+json.dumps({'type':'tool.execution_start','data':{'toolName':'apply_patch','toolCallId':'step'}})+'\\n')\n"
            f"pathlib.Path({str(marker)!r}).write_text('ready')\n"
            "signal.pause()\n"
        )
        observation = {"marker": marker.name, "events": str(events), "session_id": "owned-test"}
        code, timed_out, _ = BENCH.run_to_files(
            [sys.executable, "-c", script], self.base, os.environ.copy(), 5,
            self.base / "process.stdout", self.base / "process.stderr", 60, interruption=observation)
        self.assertEqual(23, code)
        self.assertFalse(timed_out)
        self.assertTrue(observation["terminated"])
        self.assertTrue(observation["observed"])
        self.assertEqual(2, observation["prior_event_count"])
        self.assertTrue((self.base / "interrupted.events.jsonl").is_file())
        with self.assertRaises(ProcessLookupError):
            os.kill(observation["pid"], 0)

    def test_marker_without_matching_persisted_session_is_not_interruption(self) -> None:
        marker = self.base / "checkpoint.json"
        marker.write_text("ready")
        events = self.base / "events.jsonl"
        events.write_text(json.dumps({"type": "session.start", "data": {"sessionId": "different"}}))
        observation = {"marker": marker.name, "events": str(events), "session_id": "owned-test"}
        code, timed_out, _ = BENCH.run_to_files(
            [sys.executable, "-c", "print('finished')"], self.base, os.environ.copy(), 5,
            self.base / "process.stdout", self.base / "process.stderr", 60, interruption=observation)
        self.assertEqual(0, code)
        self.assertFalse(timed_out)
        self.assertNotIn("observed", observation)


if __name__ == "__main__":
    unittest.main(verbosity=2)