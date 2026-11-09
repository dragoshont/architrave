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
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
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

    def read_payload(self, **overrides):
        return {
            "sessionId": self.session, "cwd": str(ROOT),
            "toolName": "view", "toolArgs": {"path": "example.py", "view_range": [1, 20]},
            "toolResult": {"resultType": "success", "textResultForLlm": "unchanged source"},
            **overrides,
        }

    def test_repeated_unchanged_reads_inject_one_advisory_through_the_command(self):
        for _ in range(3):
            self.assertEqual({}, self.invoke("post-tool-use", self.read_payload()))
        result = self.invoke("post-tool-use", self.read_payload())
        self.assertEqual({"additionalContext"}, set(result))
        context = result["additionalContext"]
        self.assertIn("Possible investigation loop", context)
        self.assertIn("4 identical results", context)
        self.assertIn("next authorized action", context)
        self.assertIn("explicit stops", context)
        self.assertIn("necessary research", context)
        self.assertNotIn("permissionDecision", result)
        self.assertNotIn("modifiedResult", result)
        for _ in range(8):
            self.assertEqual({}, self.invoke("post-tool-use", self.read_payload()))

    def test_interleaved_reads_and_resume_keep_loop_evidence(self):
        for _ in range(3):
            self.assertEqual({}, guard.post_tool_use(self.read_payload()))
            self.assertEqual({}, guard.post_tool_use(self.read_payload(
                toolName="rg", toolArgs={"pattern": "request", "glob": "*.py"},
            )))
        self.invoke("session-start", {"sessionId": self.session, "source": "resume"})
        self.assertIn("additionalContext", self.invoke("post-tool-use", self.read_payload()))
        # A nearby repeated search must not generate another immediate reminder.
        self.assertEqual({}, guard.post_tool_use(self.read_payload(
            toolName="rg", toolArgs={"pattern": "request", "glob": "*.py"},
        )))

    def test_changed_evidence_and_distinct_questions_do_not_trigger(self):
        for index in range(32):
            self.assertEqual({}, guard.post_tool_use(self.read_payload(
                toolArgs={"path": "example.py", "view_range": [index, index + 10]},
            )))
            self.assertEqual({}, guard.post_tool_use(self.read_payload(
                toolResult={"resultType": "success", "textResultForLlm": f"revision {index}"},
            )))
        # Changing a formerly repeated result starts a fresh observation, not a stale alert.
        for _ in range(3):
            self.assertEqual({}, guard.post_tool_use(self.read_payload()))
        self.assertEqual({}, guard.post_tool_use(self.read_payload(
            toolResult={"resultType": "success", "textResultForLlm": "changed source"},
        )))
        self.assertEqual({}, guard.post_tool_use(self.read_payload()))

    def test_file_touches_do_not_count_as_verified_progress(self):
        for _ in range(3):
            self.assertEqual({}, guard.post_tool_use(self.read_payload()))
            self.assertEqual({}, guard.post_tool_use(self.read_payload(toolName="edit")))
        self.assertIn("additionalContext", guard.post_tool_use(self.read_payload()))

    def test_loop_cache_is_bounded_private_and_isolated_by_session_and_cwd(self):
        private_payload = self.read_payload(
            toolArgs={"path": "PRIVATE_PATH", "query": "PRIVATE_QUERY"},
            toolResult={"resultType": "success", "textResultForLlm": "PRIVATE_SOURCE"},
        )
        for _ in range(3):
            self.assertEqual({}, guard.post_tool_use(private_payload))
        self.assertEqual({}, guard.post_tool_use({**private_payload, "sessionId": str(uuid4())}))
        self.assertEqual({}, guard.post_tool_use({**private_payload, "cwd": str(self.home)}))
        self.assertEqual({}, guard.post_tool_use({**private_payload, "agentId": "separate-agent"}))
        for index in range(64):
            self.assertEqual({}, guard.post_tool_use(self.read_payload(toolArgs={"path": f"{index}.py"})))
        cache = self.report.with_name("architrave-loop.json")
        serialized = cache.read_text(encoding="utf-8")
        for secret in ("PRIVATE_PATH", "PRIVATE_QUERY", "PRIVATE_SOURCE", str(ROOT)):
            self.assertNotIn(secret, serialized)
        state = json.loads(serialized)
        self.assertLessEqual(len(state["history"]), 24)
        self.assertLessEqual(len(state["notified"]), 24)
        self.assertLess(cache.stat().st_size, 16384)
        self.assertFalse(self.report.exists())
        self.assertEqual({}, guard.post_tool_use(private_payload))

    def test_reminders_rearm_after_changed_evidence_or_window_eviction(self):
        for _ in range(3):
            self.assertEqual({}, guard.post_tool_use(self.read_payload()))
        self.assertIn("additionalContext", guard.post_tool_use(self.read_payload()))
        for _ in range(12):
            self.assertEqual({}, guard.post_tool_use(self.read_payload()))
        changed = self.read_payload(
            toolResult={"resultType": "success", "textResultForLlm": "new source"},
        )
        for _ in range(3):
            self.assertEqual({}, guard.post_tool_use(changed))
        self.assertIn("additionalContext", guard.post_tool_use(changed))
        for index in range(24):
            self.assertEqual({}, guard.post_tool_use(self.read_payload(toolArgs={"path": f"{index}.py"})))
        for _ in range(3):
            self.assertEqual({}, guard.post_tool_use(changed))
        self.assertIn("additionalContext", guard.post_tool_use(changed))

    def test_copilot_snake_case_and_json_arguments_share_fingerprints(self):
        payload = {
            "session_id": self.session, "cwd": str(ROOT), "tool_name": "Read",
            "tool_input": json.dumps(self.read_payload()["toolArgs"]),
            "tool_result": {"result_type": "success", "text_result_for_llm": "unchanged source"},
        }
        for _ in range(3):
            self.assertEqual({}, guard.post_tool_use(payload))
        self.assertIn("additionalContext", guard.post_tool_use(self.read_payload(toolName="functions.view")))

    def test_only_successful_supported_reads_are_observed(self):
        for payload in (
            self.read_payload(toolName="powershell"),
            self.read_payload(toolName="task_complete"),
            self.read_payload(toolName="edit"),
            self.read_payload(toolResult={"resultType": "failure", "textResultForLlm": "failed"}),
        ):
            for _ in range(5):
                self.assertEqual({}, guard.post_tool_use(payload))
        self.assertEqual([], list(self.home.iterdir()))

    def test_invalid_input_and_broken_cache_warn_without_denying_or_leaking(self):
        for payload in (
            self.read_payload(sessionId="../escape"),
            self.read_payload(session_id=str(uuid4())),
            self.read_payload(toolArgs="PRIVATE_INVALID_JSON"),
            self.read_payload(toolResult=None),
        ):
            result = self.invoke("post-tool-use", payload)
            self.assertEqual({"additionalContext"}, set(result))
            self.assertIn("loop monitoring unavailable", result["additionalContext"])
            self.assertNotIn("PRIVATE_INVALID_JSON", json.dumps(result))
        cache = self.report.with_name("architrave-loop.json")
        cache.parent.mkdir(parents=True, exist_ok=True)
        for content in ("{PRIVATE_BROKEN_CACHE", '[]', '{"schema":"unexpected"}', "x" * 20000):
            cache.write_text(content, encoding="utf-8")
            result = self.invoke("post-tool-use", self.read_payload())
            self.assertEqual({"additionalContext"}, set(result))
            self.assertIn("loop monitoring unavailable", result["additionalContext"])
            self.assertEqual(content, cache.read_text(encoding="utf-8"))

    def test_parallel_hook_processes_do_not_lose_counts_or_repeat_notices(self):
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(
                lambda _: self.invoke("post-tool-use", self.read_payload()), range(8),
            ))
        notices = [result for result in results if result]
        self.assertEqual(1, len(notices), notices)
        self.assertIn("Possible investigation loop", notices[0]["additionalContext"])
        state = json.loads(self.report.with_name("architrave-loop.json").read_text(encoding="utf-8"))
        self.assertEqual(8, len(state["history"]))

    def test_lock_contention_warns_within_the_hook_deadline(self):
        self.report.parent.mkdir(parents=True, exist_ok=True)
        lock = self.report.with_name("architrave-loop.lock")
        with guard._loop_lock(lock):
            started = time.monotonic()
            result = self.invoke("post-tool-use", self.read_payload())
        self.assertLess(time.monotonic() - started, 5)
        self.assertEqual({"additionalContext"}, set(result))
        self.assertIn("loop monitoring unavailable (TimeoutError)", result["additionalContext"])
        self.assertFalse(self.report.with_name("architrave-loop.json").exists())

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
            self.assertIn("Development loop: one case", context)
            self.assertIn("hold unclear specifications for sidebar research", context)
            self.assertIn("Code ready means written implementation", context)
            self.assertIn("qualification/permission holds block dependent operations", context)
            self.assertIn("All code ready before two independent final reviews by default", context)
            self.assertIn("route accepted findings as REQ corrections to fresh implementers", context)
            self.assertIn("resolve before authorized deployment", context)
            self.assertIn("Never invent prerequisites; respect scoped grants, stops, host permissions and the owner's selected mode", context)
            self.assertIn("declare scope per docs/program-board.md", context)
            self.assertIn("Restore case/phase after resume; stop unchanged rereads and take the next authorized action or state the exact hold", context)
            self.assertLess(context.index("Development loop:"), context.index("Before non-trivial implementation:"))
            self.assertIn("Read-only/trivial", context)
            self.assertIn("work needs no declaration, board or sidebar", context)
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
        self.assertEqual({"sessionStart", "preToolUse", "postToolUse"}, set(hooks["hooks"]))
        for event, command in (
            ("sessionStart", "session-start"), ("preToolUse", "pre-tool-use"),
            ("postToolUse", "post-tool-use"),
        ):
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
        matcher = hooks["hooks"]["postToolUse"][0]["matcher"]
        for tool in ("view", "rg", "grep", "glob", "web_fetch", "web_search",
                     "semantic_code_search", "read_file", "functions.view"):
            self.assertIsNotNone(re.fullmatch(matcher, tool), tool)
        for tool in ("powershell", "bash", "edit", "ask_user", "task_complete", "preview"):
            self.assertIsNone(re.fullmatch(matcher, tool), tool)
        claude = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertNotIn("hooks", claude)


if __name__ == "__main__":
    unittest.main()
