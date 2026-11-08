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

    def test_tournament_result_binds_task_source_without_side_effects(self) -> None:
        fixture = json.loads((ROOT / "scripts" / "fixtures" / "tournament-result.json").read_text(encoding="utf-8"))
        bound = {**fixture, "task": "T1", "source": "abc"}
        result, ledger = self.run_dir / "result.json", self.run_dir / "tournaments.jsonl"
        result.write_text(json.dumps(bound), encoding="utf-8")
        quiet = contextlib.redirect_stdout(io.StringIO())
        with quiet:
            self.assertEqual(1, CLI.tournament_review(self.run_dir, False, result, {"task": "T2"}))
            self.assertEqual(1, CLI.tournament_review(self.run_dir, False, result, {"task": "T1", "source": "old"}))
            self.assertEqual(2, CLI.tournament_review(self.run_dir, False, result, None, ledger))
            self.assertFalse(ledger.exists())
            self.assertEqual(0, CLI.tournament_review(self.run_dir, False, result, {"task": "T1", "source": "abc"}))
            self.assertEqual(2, CLI.tournament_review(self.run_dir, False, result, {"task": "T1"}, ledger))
        self.assertFalse(ledger.exists())

    def test_malformed_tournament_results_and_ledger_fail_explicitly(self) -> None:
        fixture = json.loads((ROOT / "scripts" / "fixtures" / "tournament-result.json").read_text(encoding="utf-8"))
        for result in ([], {**fixture, "options": 1}, {**fixture, "options": [{"kind": []}]},
                       {**fixture, "winner": "NOT_AN_OPTION"}, {**fixture, "winnerBeatsDoNothing": True}):
            self.assertTrue(CLI.validate_tournament_result(result))
        result, ledger = self.run_dir / "result.json", self.run_dir / "tournaments.jsonl"
        result.write_text(json.dumps({**fixture, "task": "T1"}), encoding="utf-8")
        for content in ("not json", "null", "[]"):
            ledger.write_text(content, encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(2, CLI.tournament_review(self.run_dir, False, result, {"task": "T1"}, ledger))
            self.assertEqual(content, ledger.read_text(encoding="utf-8"))

    def test_tournament_validation_cannot_create_an_authority_ledger(self) -> None:
        fixture = json.loads((ROOT / "scripts" / "fixtures" / "tournament-result.json").read_text(encoding="utf-8"))
        result, ledger = self.run_dir / "result.json", self.run_dir / "tournaments.jsonl"
        result.write_text(json.dumps({**fixture, "task": "T1"}), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(2, CLI.tournament_review(self.run_dir, False, result, {"task": "T1"}, ledger))
        self.assertFalse(ledger.exists())
        self.assertTrue(CLI.validate_tournament_result({**fixture, "options": fixture["options"] * 2}))
        self.assertTrue(CLI.validate_tournament_result({**fixture, "options": [
            {"kind": "DO_NOTHING"}, {"kind": "SMALLEST_VIABLE"}]}))

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
