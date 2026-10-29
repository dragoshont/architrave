#!/usr/bin/env python3
"""Explicit quick checks remain; scoped startup/completion hooks never poll."""
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
        scratch = ROOT / ".architrave/test-fixtures"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="quality-cadence-", dir=scratch)
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
            text = (ROOT / name).read_text()
            windows_job = text.split("  windows-python:\n", 1)[1].split("\n  release:", 1)[0]
            self.assertIn("runs-on: windows-2025", windows_job)
            self.assertNotIn("shell:", windows_job)
            self.assertNotIn("continue-on-error:", windows_job)
            self.assertNotIn("$LASTEXITCODE", windows_job)
            commands = [line.strip()[5:] for line in windows_job.splitlines()
                        if line.startswith("        run: ")]
            self.assertGreater(len(commands), 10)
            for command in commands:
                self.assertTrue(command.startswith(("python ", "node ")), command)
                self.assertNotIn(";", command)
                self.assertNotIn("\n", command)
                self.assertNotIn(".ps1", command)
                self.assertNotIn(".sh", command)

    def test_actual_browser_contract_is_required_in_validate_and_release(self):
        for name in (".github/workflows/validate.yml", ".github/workflows/release.yml"):
            text = (ROOT / name).read_text()
            browser_job = text.split("  session-browser:\n", 1)[1].split("\n  windows-python:", 1)[0]
            self.assertIn("playwright==1.56.0", browser_job)
            self.assertIn("playwright install --with-deps chromium", browser_job)
            self.assertIn("COMPANION_VISUAL_OUTPUT:", browser_job)
            self.assertIn("scripts/test-session-companion.mjs", browser_job)
            self.assertIn("actions/upload-artifact@v4", browser_job)
        self.assertIn("needs: [validate, windows-python, session-browser]",
                      (ROOT / ".github/workflows/release.yml").read_text())
    def test_public_hook_json_compatibility_remains(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(0, gate.quality(self.repo, True))
        self.assertEqual({"continue": True}, json.loads(output.getvalue()))

    def test_scoped_session_hooks_do_not_restore_quality_polling(self):
        hooks = json.loads((ROOT / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        self.assertEqual({"sessionStart", "preToolUse"}, set(hooks))
        self.assertEqual("^task_complete$", hooks["preToolUse"][0]["matcher"])
        for entries in hooks.values():
            for entry in entries:
                self.assertEqual("command", entry["type"])
                for command in (entry["bash"], entry["powershell"]):
                    self.assertIn("session_guard.py", command)
                    self.assertNotIn("quality-gate", command)
        docs = (ROOT / "docs" / "quality-check-cadence.md").read_text(encoding="utf-8")
        self.assertIn("command timeouts fail open", docs)
        self.assertIn("not complete enforcement", docs)
        self.assertIn("not Claude compatibility", docs.replace("\n", " "))

    def test_agent_skill_cadence_and_ci_coverage_are_explicit(self):
        text = " ".join((ROOT / "agents/architrave.agent.md").read_text().split())
        self.assertIn("python gates/gate_runner.py quality-gate", text)
        self.assertIn("final integration", text)
        self.assertIn("after relevant config, referenced design JSON or configured product-copy changes", text)
        skill = (ROOT / "skills/architrave/SKILL.md").read_text()
        stanza = (ROOT / "templates/AGENTS.stanza.md").read_text()
        self.assertIn("agents/architrave.agent.md", skill)
        self.assertIn(".github/agents/architrave.agent.md", stanza)
        self.assertIn("canonical lead contract", skill)
        self.assertIn("delegation, verification and stop rules", stanza)
        self.assertIn("test-quality-cadence.py", (ROOT / ".github/workflows/validate.yml").read_text())
        self.assertIn("test-quality-cadence.py", (ROOT / "scripts/check_manifests.py").read_text())


if __name__ == "__main__":
    unittest.main()
