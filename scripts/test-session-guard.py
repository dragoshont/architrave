#!/usr/bin/env python3
"""Copilot hook protocol/process checks, not live-host or provider acceptance."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gates"))
import session_guard as guard


class SessionGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="architrave-session-guard-")
        self.home = Path(self.temp.name)
        self.previous_home = os.environ.get("COPILOT_HOME")
        os.environ["COPILOT_HOME"] = str(self.home)
        self.session = str(uuid4())
        self.report = self.home / "session-state" / self.session / "files" / "architrave-delivery.json"
        self.payload = {
            "sessionId": self.session, "cwd": str(ROOT),
            "toolName": "task_complete", "toolArgs": {"summary": "Not evidence"},
        }

    def tearDown(self):
        if self.previous_home is None:
            os.environ.pop("COPILOT_HOME", None)
        else:
            os.environ["COPILOT_HOME"] = self.previous_home
        self.temp.cleanup()

    def invoke(self, event, payload):
        result = subprocess.run(
            [sys.executable, "-B", str(ROOT / "gates" / "session_guard.py"), event],
            input=json.dumps(payload), text=True, encoding="utf-8",
            capture_output=True, cwd=ROOT, timeout=30,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stderr)
        return json.loads(result.stdout)

    def write_report(self, content):
        self.report.parent.mkdir(parents=True, exist_ok=True)
        self.report.write_text(content, encoding="utf-8")

    def assert_denied(self, result):
        self.assertEqual({"permissionDecision", "permissionDecisionReason"}, set(result))
        self.assertEqual("deny", result["permissionDecision"])
        self.assertTrue(result["permissionDecisionReason"].strip())

    def test_start_is_compact_path_bound_context_only(self):
        for payload in (
            {"sessionId": self.session, "cwd": str(ROOT), "source": "startup",
             "initialPrompt": "PRIVATE_PROMPT_MUST_NOT_BE_ECHOED"},
            {"hook_event_name": "SessionStart", "session_id": self.session,
             "cwd": str(ROOT), "source": "resume"},
        ):
            result = self.invoke("session-start", payload)
            self.assertEqual({"additionalContext"}, set(result))
            context = result["additionalContext"]
            self.assertLessEqual(len(context.split()), 140)
            self.assertIn(str(ROOT / "skills" / "architrave" / "SKILL.md"), context)
            self.assertIn(str(ROOT / "agents" / "architrave.agent.md"), context)
            self.assertIn("Read-only/trivial", context)
            self.assertIn("assigned workers/reviewers", context)
            self.assertNotIn("PRIVATE_PROMPT_MUST_NOT_BE_ECHOED", context)
        self.assertEqual([], list(self.home.iterdir()))

    def test_undeclared_work_is_untouched_without_checking_cwd(self):
        for payload in (
            self.payload,
            {"session_id": self.session, "tool_name": "task_complete"},
        ):
            self.assertEqual({}, self.invoke("pre-tool-use", payload))
        self.assertEqual([], list(self.home.iterdir()))

    def test_unrelated_tools_never_consult_a_broken_declaration(self):
        self.write_report("{invalid")
        for tool in ("view", "powershell", "ask_user", "task", "task_complete_extra"):
            self.assertEqual({}, self.invoke("pre-tool-use", {
                **self.payload, "toolName": tool,
            }))

    def test_real_checker_rejects_incomplete_and_malformed_declarations(self):
        from delivery_check import check_session, session_report_path

        self.assertEqual(self.report, session_report_path(self.session))
        for content in (
            '{"schema":"architrave.delivery.v1","state":"prepared"}',
            '{"schema":"architrave.delivery.v1","state":"sealed"}',
            '{"schema":"architrave.delivery.v1","state":"prepared","active":false}',
            "{invalid",
            "[]",
        ):
            with self.subTest(content=content):
                self.write_report(content)
                errors = check_session(ROOT, self.session)
                self.assertTrue(errors)
                before = self.report.read_bytes()
                for payload in (
                    self.payload,
                    {"session_id": self.session, "cwd": str(ROOT),
                     "tool_name": "task_complete", "tool_input": {}},
                ):
                    result = self.invoke("pre-tool-use", payload)
                    self.assert_denied(result)
                    for error in errors:
                        self.assertIn(error, result["permissionDecisionReason"])
                self.assertEqual(before, self.report.read_bytes())

    def test_unreadable_report_shape_and_missing_active_cwd_deny(self):
        self.report.mkdir(parents=True)
        self.assert_denied(self.invoke("pre-tool-use", self.payload))
        self.assert_denied(self.invoke("pre-tool-use", {
            "sessionId": self.session, "toolName": "task_complete",
        }))

    def test_adapter_only_explicit_checker_results_never_grant_permission(self):
        # These results exercise decision mapping only, not delivery verification.
        self.write_report('{"schema":"architrave.delivery.v1","state":"prepared"}')
        calls = []

        def accepted(root, session):
            calls.append((root, session))
            return []

        self.assertEqual({}, guard.pre_tool_use(self.payload, checker=accepted))
        self.assertEqual([(ROOT, self.session)], calls)
        result = guard.pre_tool_use(
            self.payload, checker=lambda root, session: ["Required board observation is missing"],
        )
        self.assert_denied(result)
        self.assertIn("Required board observation is missing", result["permissionDecisionReason"])

    def test_adapter_only_checker_failures_are_denied_without_logging_inputs(self):
        def missing_checker(root, session):
            raise ImportError("DO_NOT_LOG")

        self.assertEqual({}, guard.pre_tool_use(self.payload, checker=missing_checker))
        self.write_report('{"schema":"architrave.delivery.v1","state":"prepared"}')
        for error in (ImportError("DO_NOT_LOG"), RuntimeError("DO_NOT_LOG")):
            def failed(root, session):
                raise error

            result = guard.pre_tool_use(self.payload, checker=failed)
            self.assert_denied(result)
            self.assertIn(type(error).__name__, result["permissionDecisionReason"])
            self.assertNotIn("DO_NOT_LOG", json.dumps(result))
        for invalid in (None, False, "", [None], [""]):
            result = guard.pre_tool_use(
                self.payload, checker=lambda root, session: invalid,
            )
            self.assert_denied(result)

    def test_malformed_completion_identity_cannot_escape_scope(self):
        for session in ("../another-session", "", None):
            self.assert_denied(self.invoke("pre-tool-use", {
                **self.payload, "sessionId": session,
            }))
        self.write_report("{invalid")
        self.assert_denied(self.invoke("pre-tool-use", {
            **self.payload, "session_id": str(uuid4()),
        }))
        self.assert_denied(self.invoke("pre-tool-use", {
            **self.payload, "tool_name": "view",
        }))

    def test_plugin_registers_only_supported_narrow_copilot_commands(self):
        manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual("hooks.json", manifest["hooks"])
        hooks = json.loads((ROOT / manifest["hooks"]).read_text(encoding="utf-8"))
        self.assertEqual(1, hooks["version"])
        self.assertEqual({"sessionStart", "preToolUse"}, set(hooks["hooks"]))
        for event, command in (("sessionStart", "session-start"), ("preToolUse", "pre-tool-use")):
            entries = hooks["hooks"][event]
            self.assertEqual(1, len(entries))
            entry = entries[0]
            self.assertEqual("command", entry["type"])
            self.assertTrue(entry["bash"].startswith("python3 -B "))
            self.assertTrue(entry["powershell"].startswith("python -B "))
            self.assertIn('"${PLUGIN_ROOT}/gates/session_guard.py" ' + command, entry["bash"])
            self.assertIn('"${PLUGIN_ROOT}\\gates\\session_guard.py" ' + command, entry["powershell"])
            self.assertLessEqual(entry["timeoutSec"], 30)
            self.assertFalse({"env", "cwd", "prompt", "exec"} & set(entry))
        matcher = hooks["hooks"]["preToolUse"][0]["matcher"]
        self.assertTrue(re.fullmatch(matcher, "task_complete"))
        for tool in ("task", "view", "powershell", "not_task_complete", "task_complete_extra"):
            self.assertIsNone(re.fullmatch(matcher, tool))
        claude = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertNotIn("hooks", claude)


if __name__ == "__main__":
    unittest.main()
