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
REMOTE = "33333333-3333-3333-3333-333333333333"
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
            (ledger / "seed").write_text("x")
            subprocess.run(["git", "-C", str(ledger), "add", "seed"], check=True)
            subprocess.run(["git", "-C", str(ledger), "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", "s"], check=True)
            sha = subprocess.run(["git", "-C", str(ledger), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
            (ledger / "SPEC.md").write_text(
                f"| ID | Requirement | Acceptance | Owner | Status | Evidence |\n|---|---|---|---|---|---|\n"
                f"| REQ-1 | Show <b>sync</b> | `t` | L1 | accepted | {sha} |\n| REQ-2 | Fix x | `t` | L1 | blocked | - |\n"
                "| REQ-3 | Claimed done | `t` | L2 | accepted | deadbee |\n| REQ-4 | Loose | `t` | x | open | - |\n\n"
                + LANE + f"| L1-app | app | p | b | origin | REQ-1, REQ-2 | - | {CHILD} | - | running | src | no | ok | - | no | [] | - |\n"
                f"| L2-remote | app | p | b | origin | REQ-3 | - | {REMOTE} | - | running | docs | no | ok | - | no | [] | - |\n"
                "\n## Handoff\nNext: x\nFailed approaches: x\nVerify: x\n")
            state = base / "home" / "session-state"
            usage = {"inputTokens": 50000, "cacheReadTokens": 40000, "outputTokens": 900, "maxPromptTokens": 200000, "model": "m"}
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
                {"type": "assistant.turn_end", "timestamp": "2026-10-26T10:12:00Z", "data": {}},
                1, {"type": "x", "data": [1]}, {"type": "tool.execution_start", "timestamp": 5, "data": {"toolName": "create_session", "arguments": "str"}},
                {"type": "session.usage_record", "timestamp": "2026-10-26T10:11:00Z", "data": {"usage": {"inputTokens": "n/a"}}}])
            out = base / "board.html"
            env = dict(os.environ, COPILOT_HOME=str(base / "home"), COPILOT_AGENT_SESSION_ID=COORD)
            proc = subprocess.run([sys.executable, str(ROOT / "harness/program_board.py"), "--ledger", str(ledger),
                                   "--output", str(out)], capture_output=True, text=True, env=env)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            page = out.read_text()
            self.assertIn("<b>2/4</b>", page)
            self.assertIn("Not in a lane", page)
            self.assertIn("sq done warn", page)
            self.assertNotIn("sq done warn' data-d='REQ-1", page)
            self.assertIn("L2-remote", page)
            self.assertIn("not logged on this machine", page)
            self.assertIn("tok 10k new · 40k cache · 900 out", page)
            self.assertIn("class='sq done'", page)
            self.assertIn("class='sq blocked'", page)
            self.assertIn("L1 app", page)
            self.assertIn("backend-implementer", page)
            self.assertNotIn("code-review", page)
            self.assertIn("ctx 50k / 200k", page)
            self.assertIn("10 model / 11 wall min", page)
            self.assertNotIn("<b>sync</b>", page)
            self.assertNotIn("http", page.split("</style>")[1].split("<script>")[0])
            self.assertNotIn("http-equiv", page)
            watch = subprocess.run([sys.executable, str(ROOT / "harness/program_board.py"), "--ledger", str(ledger),
                                    "--output", str(out), "--watch", "120"], capture_output=True, text=True, env=env, timeout=30)
            self.assertEqual(watch.returncode, 0, watch.stderr)
            self.assertIn("http-equiv='refresh' content='120'", out.read_text())
            out.with_suffix(".pid").write_text(str(os.getpid()))
            dup = subprocess.run([sys.executable, str(ROOT / "harness/program_board.py"), "--ledger", str(ledger),
                                  "--output", str(out), "--watch", "120"], capture_output=True, text=True, env=env, timeout=30)
            self.assertIn("already running", dup.stdout)


if __name__ == "__main__":
    unittest.main()
