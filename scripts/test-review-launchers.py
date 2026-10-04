#!/usr/bin/env python3

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import re
import subprocess
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


class ReviewLauncherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.temp.name) / "run"
        self.run_dir.mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def response(self, command: list[str], *, tournament: bool = False) -> subprocess.CompletedProcess[str]:
        prompt = command[-1]
        match = re.search(r"Read (.+?) and include EVIDENCE_NONCE", prompt)
        nonce = Path(match.group(1)).read_text(encoding="utf-8").strip() if match else ""
        if tournament:
            output = f"EVIDENCE_NONCE: {nonce}\nTOURNAMENT: COMPLETE\n"
        else:
            content = f"EVIDENCE_NONCE: {nonce}\nVERDICT: PASS"
            output = (
                json.dumps({"result": content})
                if Path(command[0]).stem == "claude"
                else json.dumps({"type": "assistant.message", "data": {"content": content}})
            ) + "\n"
        return subprocess.CompletedProcess(command, 0, output, "")

    def test_semantic_review_inherits_host_model_and_verifies_both(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.assertEqual(0, CLI.semantic_review(self.run_dir, "both", False))
        self.assertNotRegex(buffer.getvalue(), r"--model|--effort|--reasoning-effort")
        with patch.object(CLI.subprocess, "run", side_effect=lambda command, **_: self.response(command)):
            self.assertEqual(0, CLI.semantic_review(self.run_dir, "both", True))

    def test_semantic_review_fails_closed(self) -> None:
        def fail(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(command, 1, "", "failed")

        with patch.object(CLI.subprocess, "run", side_effect=fail):
            self.assertEqual(1, CLI.semantic_review(self.run_dir, "copilot", True))

    def test_tournament_review_inherits_host_model_and_verifies_completion(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.assertEqual(0, CLI.tournament_review(self.run_dir, False))
        self.assertNotRegex(buffer.getvalue(), r"--model|--effort|--reasoning-effort")
        with patch.object(
            CLI.subprocess,
            "run",
            side_effect=lambda command, **_: self.response(command, tournament=True),
        ):
            self.assertEqual(0, CLI.tournament_review(self.run_dir, True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
