#!/usr/bin/env python3
"""Program board renders lanes, REQ dots, children and metrics from a ledger and local session logs."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
COORD = "11111111-1111-1111-1111-111111111111"
CHILD = "22222222-2222-2222-2222-222222222222"
LANE = ("| Lane | Repo | Project ID | Branch | Push target | REQ IDs | Depends on | Session ID | Assignment ID | State | "
        "Mutable paths | Heavy build | Preflight | Preflight evidence | Preflight reported | Owner-only decisions | Superseded by |\n"
        + "|---" * 17 + "|\n")


def events(path: Path, rows: list[dict]) -> None:
    path.mkdir(parents=True)
    (path / "events.jsonl").write_text("\n".join(json.dumps(r) for r in rows))


class ProgramBoard(unittest.TestCase):
    def test_board_shows_lane_dots_children_and_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            ledger = base / "ledger"
            ledger.mkdir()
            subprocess.run(["git", "init", "-q", str(ledger)], check=True)
            (ledger / "SPEC.md").write_text(
                "| ID | Requirement | Acceptance | Owner | Status | Evidence |\n|---|---|---|---|---|---|\n"
                "| REQ-1 | Show <b>sync</b> | `t` | L1 | accepted | abc1234 |\n| REQ-2 | Fix x | `t` | L1 | blocked | - |\n\n"
                + LANE + f"| L1-app | app | p | b | origin | REQ-1, REQ-2 | - | {CHILD} | - | running | src | no | ok | - | no | [] | - |\n"
                "\n## Handoff\nNext: x\nFailed approaches: x\nVerify: x\n")
            state = base / "home" / "session-state"
            usage = {"inputTokens": 50000, "outputTokens": 900, "maxPromptTokens": 200000, "model": "m"}
            events(state / COORD, [
                {"type": "session.start", "timestamp": "2026-10-26T10:00:00Z", "data": {"startTime": "2026-10-26T10:00:00Z", "selectedModel": "m"}},
                {"type": "tool.execution_start", "timestamp": "2026-10-26T10:01:00Z", "data": {"toolName": "create_session", "toolCallId": "c1", "arguments": {"name": "L1 app", "kickoff": {"agent": "architrave:backend-implementer"}}}},
                {"type": "tool.execution_complete", "timestamp": "2026-10-26T10:01:05Z", "data": {"toolCallId": "c1", "result": f"Created session (id: {CHILD})"}},
                {"type": "session.usage_record", "timestamp": "2026-10-26T10:02:00Z", "data": {"usage": usage}}])
            events(state / CHILD, [
                {"type": "session.start", "timestamp": "2026-10-26T10:01:10Z", "data": {"startTime": "2026-10-26T10:01:10Z"}},
                {"type": "assistant.turn_start", "timestamp": "2026-10-26T10:02:00Z", "data": {}},
                {"type": "subagent.selected", "timestamp": "2026-10-26T10:02:30Z", "data": {"agentName": "code-review"}},
                {"type": "session.usage_record", "timestamp": "2026-10-26T10:03:00Z", "data": {"usage": usage}},
                {"type": "assistant.turn_end", "timestamp": "2026-10-26T10:12:00Z", "data": {}}])
            out = base / "board.html"
            env = dict(os.environ, COPILOT_HOME=str(base / "home"))
            proc = subprocess.run([sys.executable, str(ROOT / "harness/program_board.py"), "--ledger", str(ledger),
                                   "--session", COORD, "--output", str(out)], capture_output=True, text=True, env=env)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            page = out.read_text()
            self.assertIn("<b>1/2</b>", page)
            self.assertIn("class='sq done'", page)
            self.assertIn("class='sq blocked'", page)
            self.assertIn("L1 app", page)
            self.assertIn("backend-implementer", page)
            self.assertNotIn("code-review", page)
            self.assertIn("ctx 50k / 200k", page)
            self.assertIn("10 model / 11 wall min", page)
            self.assertNotIn("<b>sync</b>", page)
            self.assertNotIn("http", page.split("</style>")[1].split("<script>")[0])


if __name__ == "__main__":
    unittest.main()
