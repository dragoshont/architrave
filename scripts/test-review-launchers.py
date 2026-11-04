#!/usr/bin/env python3

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
SPEC = importlib.util.spec_from_file_location("architrave_cli", ROOT / "harness" / "architrave_cli.py")
assert SPEC and SPEC.loader
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)
import session_audit


class ReviewLauncherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.temp.name) / "run"
        self.run_dir.mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_semantic_review_is_native_advisory_only(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.assertEqual(0, CLI.semantic_review(self.run_dir, "both", False))
        self.assertNotRegex(buffer.getvalue(), r"--model|--effort|--reasoning-effort")
        self.assertEqual("advisory", json.loads(buffer.getvalue())["status"])
        self.assertEqual(2, CLI.semantic_review(self.run_dir, "both", True))

    def test_semantic_review_fails_closed(self) -> None:
        self.assertEqual(2, CLI.semantic_review(self.run_dir, "copilot", True))

    def test_tournament_review_is_native_advisory_only(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.assertEqual(0, CLI.tournament_review(self.run_dir, False))
        self.assertNotRegex(buffer.getvalue(), r"--model|--effort|--reasoning-effort")
        self.assertEqual("advisory", json.loads(buffer.getvalue())["status"])
        self.assertEqual(2, CLI.tournament_review(self.run_dir, True))

    def test_tournament_result_requires_do_nothing_and_smallest_viable(self) -> None:
        fixture = json.loads((ROOT / "scripts" / "fixtures" / "tournament-result.json").read_text(encoding="utf-8"))
        self.assertEqual([], CLI.validate_tournament_result(fixture))
        missing = {**fixture, "options": [item for item in fixture["options"] if item["kind"] != "DO_NOTHING"],
                   "winnerBeatsDoNothing": ""}
        errors = CLI.validate_tournament_result(missing)
        self.assertIn("options must include kind DO_NOTHING", errors)
        self.assertIn("winnerBeatsDoNothing must explain why the winner beats doing nothing", errors)

    def test_audit_numbers_do_not_turn_unknown_or_invalid_usage_into_zero(self) -> None:
        for value in (None, True, -1, "12", 1.5):
            self.assertIsNone(session_audit.number(value))
        self.assertEqual(0, session_audit.number(0))
        self.assertEqual(12, session_audit.number(12))
        values = session_audit.usage_values({"inputTokens": 12, "cacheReadTokens": 8, "cacheWriteTokens": 2})
        self.assertEqual(4, values["input"])
        self.assertEqual(8, values["cached"])
        self.assertEqual(2, values["cache_writes"])
        self.assertIsNone(values["output"])
        self.assertIsNone(session_audit.usage_values({"inputTokens": 2, "cacheReadTokens": 3})["input"])
        self.assertIsNone(session_audit.usage_values({
            "inputTokens": 12, "cacheReadTokens": 8, "cacheWriteTokens": 5})["cache_writes"])

    def test_audit_session_paths_reject_traversal_and_sidebar_names(self) -> None:
        for value in ("..", "coordinator", "../events.jsonl", "x" * 36):
            with self.assertRaises(ValueError):
                session_audit.session_path(value)

    def test_audit_excerpts_expose_truncation(self) -> None:
        self.assertFalse(session_audit.excerpt("short")["truncated"])
        result = session_audit.excerpt("x" * 2001)
        self.assertTrue(result["truncated"])
        self.assertEqual(2000, len(result["text"]))

    def test_audit_does_not_accept_an_empty_or_forged_packet(self) -> None:
        with self.assertRaises(ValueError):
            session_audit.validate_packet({})
        with self.assertRaises(ValueError):
            session_audit.validate_packet({"schema": session_audit.PACKET, "packet_sha256": "0" * 64})

    def test_audit_retains_native_boundary_events_without_claiming_delivery(self) -> None:
        sid = "00000000-0000-0000-0000-000000000037"
        data = [
            ("session.start", {"selectedModel": "selected", "copilotVersion": "host-version",
                               "reasoningEffort": "medium", "context": {"headCommit": "source"}}),
            ("assistant.message", {"content": "Please approve the operation"}),
            ("permission.requested", {"permissionRequest": {"kind": "shell", "intention": "x" * 2100},
                                      "requestId": "approval"}),
            ("permission.completed", {"requestId": "approval", "result": {"kind": "denied"}}),
            ("permission.completed", {"requestId": "other", "result": {"kind": "approved"}}),
            ("permission.completed", {"requestId": "unknown"}),
            ("subagent.started", {"toolCallId": "child", "requestedModel": "requested", "model": "reported"}),
            ("subagent.completed", {"toolCallId": "child", "firstDispatchedModel": "executed"}),
            ("assistant.turn_end", {}),
            ("session.idle", {}),
            ("session.resume", {}),
            ("abort", {}),
        ]
        with patch.dict("os.environ", {"COPILOT_HOME": self.temp.name}):
            path = session_audit.session_path(sid) / "events.jsonl"
            path.parent.mkdir(parents=True)
            path.write_text("".join(json.dumps({"id": str(i), "type": kind, "data": value,
                                               "agentId": "child-id" if kind.startswith("subagent.") else None}) + "\n"
                                    for i, (kind, value) in enumerate(data)), encoding="utf-8")
            packet = session_audit.collect([sid], [])
            row = packet["sessions"][0]
            self.assertEqual([kind for kind, _ in data], [e["type"] for e in row["trace"]])
            host = row["host_context"]
            self.assertIsNone(host["requested_model"])
            self.assertEqual("selected", host["selected_model"])
            self.assertEqual("source", host["context"]["headCommit"])
            self.assertIsNone(host["context"]["cwd"])
            self.assertEqual([], row["metrics"]["models"])
            self.assertNotIn("reported_result", row["trace"][1])
            self.assertTrue(row["trace"][2]["details"]["truncated"])
            self.assertEqual("approval", row["trace"][2]["request_id"])
            self.assertEqual(["denied", "approved", None],
                             [e["reported_result"] for e in row["trace"][3:6]])
            self.assertEqual("requested", row["trace"][6]["requested_model"])
            self.assertEqual("reported", row["trace"][6]["reported_model"])
            self.assertEqual("executed", row["trace"][7]["reported_model"])
            self.assertEqual("child-id", row["trace"][7]["agent_id"])
            self.assertNotIn("accepted", row)
            session_audit.validate_packet(packet)
            row["trace"][3]["reported_result"] = "approved"
            packet["packet_sha256"] = session_audit.digest(
                {k: v for k, v in packet.items() if k != "packet_sha256"})
            with self.assertRaisesRegex(ValueError, "differ from the actual source"):
                session_audit.validate_packet(packet)

    def test_audit_preserves_legacy_reconstruction_and_turn_scope(self) -> None:
        sid = "00000000-0000-0000-0000-000000000037"
        with patch.dict("os.environ", {"COPILOT_HOME": self.temp.name}):
            path = session_audit.session_path(sid) / "events.jsonl"
            path.parent.mkdir(parents=True)
            events = [("start", "session.start"), ("child", "session.start"),
                      ("turn", "assistant.turn_start"),
                      ("end", "assistant.turn_end"), ("next", "assistant.turn_start"),
                      ("later", "permission.requested"), ("future", "session.start")]
            path.write_text("".join(json.dumps({"id": eid, "type": kind, "data": {},
                                               "agentId": "child-id" if eid == "child" else None}) + "\n"
                                    for eid, kind in events), encoding="utf-8")
            for schema in (session_audit.LEGACY_PACKET, session_audit.COMPACTION_PACKET):
                packet = {"schema": schema, "sessions": [session_audit.collect_session(
                    sid, include_compaction=schema != session_audit.LEGACY_PACKET,
                    include_host_events=False)]}
                packet["packet_sha256"] = session_audit.digest(packet)
                session_audit.validate_packet(packet)
            selected = session_audit.collect([sid], [], "turn")
            self.assertEqual(["turn", "end"],
                             [e["event_id"] for e in selected["sessions"][0]["trace"]])
            self.assertEqual("start", selected["sessions"][0]["host_context"]["event_id"])
            session_audit.validate_packet(selected)
            session_audit.validate_analysis(selected, {
                "packet_sha256": selected["packet_sha256"], "reviewer": "protocol-test",
                "summary": "Context event is available for turn-scoped review; no outcome claims.",
                "goals": [], "findings": [], "strengths": [
                    {"session": sid, "events": ["start"], "practice": "Host context retained"}],
            })


if __name__ == "__main__":
    unittest.main(verbosity=2)
