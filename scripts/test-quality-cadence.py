#!/usr/bin/env python3
"""The old quick validator is retained; only automatic scheduling is retired."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("quality_gate_fixture", ROOT / "gates" / "gate_runner.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class QualityCadenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        self.config = {
            "platform": "web", "stack": "fixture", "designSource": {"path": "design.json"},
            "designMap": "map.json", "tokens": "tokens.json", "applyTo": ["*.json"],
            "build": "must-not-run", "test": "must-not-run",
            "productCopy": {"paths": ["strings.json"]},
        }
        for name in ("design.json", "map.json", "tokens.json"):
            (self.repo / name).write_text("{}")
        (self.repo / "strings.json").write_text('{"title":"Welcome"}')
        self.write_config()

    def tearDown(self):
        self.temp.cleanup()

    def write_config(self):
        (self.repo / "architrave.config.json").write_text(json.dumps(self.config))

    def quiet_quality(self, hook=False):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return gate.quality(self.repo, hook)

    def test_quick_does_not_execute_full_build_test_recipes(self):
        with mock.patch.object(gate, "run_recipe", side_effect=AssertionError("expensive recipe")), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, gate.checks(self.repo, True))
        self.assertEqual(0, self.quiet_quality())

    def test_each_existing_design_json_reference_remains_validated(self):
        for name in ("design.json", "map.json", "tokens.json"):
            (self.repo / name).write_text("{invalid")
            self.assertEqual(2, self.quiet_quality())
            (self.repo / name).write_text("{}")
        self.assertEqual(0, self.quiet_quality())

    def test_profile_and_config_failures_block(self):
        self.config["kind"] = "unrecognized"
        self.write_config()
        self.assertEqual(2, self.quiet_quality())
        (self.repo / "architrave.config.json").write_text("{invalid")
        self.assertEqual(2, self.quiet_quality())

    def test_product_copy_rules_remain_executable(self):
        (self.repo / "strings.json").write_text('{"title":"Evidence registry only"}')
        self.assertEqual(2, self.quiet_quality())
        (self.repo / "strings.json").write_text('{"title":"Welcome"}')
        self.config["productCopy"]["forbidden"] = ["["]
        self.write_config()
        self.assertEqual(2, self.quiet_quality())

    def test_all_windows_fixture_processes_propagate_failure_immediately(self):
        for name in (".github/workflows/validate.yml", ".github/workflows/release.yml"):
            lines = (ROOT / name).read_text().splitlines()
            checked = 0
            windows_job = False
            for index, line in enumerate(lines):
                if line.startswith("  ") and not line.startswith("    ") and line.endswith(":"):
                    windows_job = False
                if line.strip() == "runs-on: windows-2025":
                    windows_job = True
                if windows_job and line.strip().startswith(("python ", "node ", "powershell ")):
                    self.assertEqual("if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }", lines[index + 1].strip())
                    checked += 1
            self.assertGreater(checked, 10)

    def test_actual_browser_contract_is_required_in_validate_and_release(self):
        for name in (".github/workflows/validate.yml", ".github/workflows/release.yml"):
            text = (ROOT / name).read_text()
            browser_job = text.split("  session-browser:\n", 1)[1].split("\n  powershell-harness:", 1)[0]
            self.assertIn("playwright==1.56.0", browser_job)
            self.assertIn("playwright install --with-deps chromium", browser_job)
            self.assertIn("COMPANION_VISUAL_OUTPUT:", browser_job)
            self.assertIn("scripts/test-session-companion.mjs", browser_job)
            self.assertIn("actions/upload-artifact@v4", browser_job)
        self.assertIn("needs: [validate, powershell-harness, session-browser]",
                      (ROOT / ".github/workflows/release.yml").read_text())
    def test_public_hook_json_compatibility_remains(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(0, gate.quality(self.repo, True))
        self.assertEqual({"continue": True}, json.loads(output.getvalue()))

    def test_agent_skill_cadence_and_ci_coverage_are_explicit(self):
        for name in ("agents/architrave.agent.md", "skills/architrave/SKILL.md", "templates/AGENTS.stanza.md"):
            text = (ROOT / name).read_text()
            self.assertIn("python gates/gate_runner.py quality-gate", text)
            self.assertIn("final integration", text.replace("\n", " "))
        self.assertIn("test-quality-cadence.py", (ROOT / ".github/workflows/validate.yml").read_text())
        self.assertIn("test-quality-cadence.py", (ROOT / "scripts/check-manifests.sh").read_text())


if __name__ == "__main__":
    unittest.main()
