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


if __name__ == "__main__":
    unittest.main(verbosity=2)
