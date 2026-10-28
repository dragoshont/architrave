#!/usr/bin/env python3
"""Program board renders lanes, REQ dots, children and metrics from a ledger and local session logs."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
COORD = "11111111-1111-1111-1111-111111111111"
CHILD = "22222222-2222-2222-2222-222222222222"
REMOTE = "33333333-3333-3333-3333-333333333333"
BROWSER_OUTPUT = None
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
                f"| REQ-1 | Show <b>sync</b> | `t` | L1 | accepted | {sha}; review: judge PASS |\n| REQ-2 | Fix x | `t` | L1 | blocked | - |\n"
                "| REQ-3 | Claimed done | `t` | L2 | accepted | deadbee |\n| REQ-4 | Loose | `t` | x | open | - |\n| REQ-5 | Shipped | `t` | L3 | claimed | - |\n\n"
                + LANE + f"| L1-app | app | p | b | origin | REQ-1, REQ-2 | - | {CHILD} | - | running | src | no | ok | - | no | [] | - |\n"
                f"| L2-remote | app | p | b | origin | REQ-3 | - | {REMOTE} | - | running | docs | no | ok | - | no | [] | - |\n"
                "| L3-done | app | p | b | origin | REQ-3, REQ-5 | - | - | - | done | lib | no | ok | - | no | [] | - |\n"
                "\n## Handoff\nNext: x\nFailed approaches: x\nVerify: x\n")
            state = base / "home" / "session-state"
            usage = {"inputTokens": 50000, "cacheReadTokens": 40000, "outputTokens": 900, "maxPromptTokens": 200000, "model": "m"}
            events(state / COORD, [
                {"type": "session.start", "timestamp": "2026-10-26T10:00:00Z", "data": {"startTime": "2026-10-26T10:00:00Z", "selectedModel": "m"}},
                {"type": "tool.execution_start", "timestamp": "2026-10-26T10:01:00Z", "data": {"toolName": "create_session", "toolCallId": "c1", "arguments": {"name": "L1 app", "kickoff": {"agent": "architrave:backend-implementer"}}}},
                {"type": "tool.execution_complete", "timestamp": "2026-10-26T10:01:05Z", "data": {"toolCallId": "c1", "result": f"Created session (id: {CHILD})"}},
                {"type": "session.usage_record", "timestamp": "2026-10-26T10:02:00Z", "data": {"usage": usage}},
                {"type": "session.task_complete", "timestamp": "2026-10-26T10:02:30Z", "data": {}}])
            big = {"inputTokens": 120000, "cacheReadTokens": 0, "outputTokens": 10, "maxPromptTokens": 200000, "model": "m"}
            events(state / CHILD, [
                {"type": "session.start", "timestamp": "2026-10-26T10:01:10Z", "data": {"startTime": "2026-10-26T10:01:10Z"}},
                {"type": "assistant.turn_start", "timestamp": "2026-10-26T10:02:00Z", "data": {}},
                {"type": "subagent.selected", "timestamp": "2026-10-26T10:02:30Z", "data": {"agentName": "code-review"}},
                {"type": "session.usage_record", "timestamp": "2026-10-26T10:03:00Z", "data": {"usage": usage}},
                {"type": "assistant.turn_end", "timestamp": "2026-10-26T10:12:00Z", "data": {}},
                {"type": "session.usage_record", "timestamp": "2026-10-26T10:11:30Z", "data": {"usage": big}},
                1, {"type": "x", "data": [1]}, {"type": "tool.execution_start", "timestamp": 5, "data": {"toolName": "create_session", "arguments": "str"}},
                {"type": "session.usage_record", "timestamp": "2026-10-26T10:11:00Z", "data": {"usage": {"inputTokens": "n/a"}}}])
            out = base / "board.html"
            env = dict(os.environ, COPILOT_HOME=str(base / "home"), COPILOT_AGENT_SESSION_ID=COORD)
            proc = subprocess.run([sys.executable, str(ROOT / "harness/program_board.py"), "--ledger", str(ledger),
                                   "--output", str(out), "--all-reqs"], capture_output=True, text=True, env=env)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            page = out.read_text()
            self.assertIn("<b>2/5</b>", page)
            self.assertIn("Not in a lane", page)
            self.assertIn("done · review missing", page)
            self.assertIn("sq delivered", page)
            self.assertIn("delivered by this lane, awaiting acceptance", page)
            self.assertIn("sq done warn", page)
            self.assertNotIn("sq done warn' data-d='REQ-1", page)
            self.assertIn("L2-remote", page)
            self.assertIn("not logged on this machine", page)
            self.assertIn("130,000 new input / 40,000 cached / 910 output tokens", page)
            self.assertEqual(page.count("<article class='session-record'>"), 3)
            self.assertNotIn("Full session names and exact history metrics", page)
            self.assertNotIn("Hover a row", page)
            self.assertIn("class='sq done", page)
            self.assertIn("class='sq blocked'", page)
            self.assertIn("L1 app", page)
            self.assertIn("backend-implementer", page)
            self.assertIn("ran reviewer code-review (verdict is in the ledger", page)
            self.assertIn("no reviewer run", page)
            self.assertIn("coordinator · task completed", page)
            self.assertIn("running · idle", page)
            self.assertIn("rotate at next task boundary", page)
            self.assertIn(CHILD, out.with_suffix(".rotate.json").read_text())
            self.assertIn('"since"', out.with_suffix(".rotate.json").read_text())
            self.assertNotIn(COORD, out.with_suffix(".rotate.json").read_text())
            self.assertIn("sq done rev", page)
            self.assertIn("box active unrev", page)
            self.assertIn("reviewed 1/2", page)
            self.assertIn("<b>1</b><span>accepted, not reviewed</span>", page)
            self.assertIn("Context 50,000 / 200,000", page)
            self.assertIn("10.0 model / 10.8 wall minutes", page)
            self.assertNotIn("<b>sync</b>", page)
            self.assertNotIn("http", page.split("</style>")[1].split("<script>")[0])
            self.assertNotIn("http-equiv", page)
            pointer = state / COORD / "files" / "program-board.watch"
            pointer.parent.mkdir(parents=True, exist_ok=True)
            pointer.write_text(json.dumps({"pid": 2 ** 22 + 12345, "output": "old", "ledger": "old"}))
            watch = subprocess.run([sys.executable, str(ROOT / "harness/program_board.py"), "--ledger", str(ledger),
                                    "--output", str(out), "--watch", "120", "--all-reqs"], capture_output=True, text=True, env=env, timeout=30)
            self.assertEqual(watch.returncode, 0, watch.stderr)
            self.assertFalse(pointer.exists(), "the watcher registers itself (replacing a stale pointer) and unregisters on exit")
            bad = subprocess.run([sys.executable, str(ROOT / "harness/program_board.py"), "--ledger", str(ledger),
                                  "--session", "../escape", "--output", str(out), "--all-reqs"], capture_output=True, text=True, env=env, timeout=30)
            self.assertEqual(bad.returncode, 2)
            self.assertIn("not a host session UUID", bad.stderr)
            self.assertNotIn("http-equiv='refresh'", out.read_text())
            self.assertIn("Stopped watcher; static snapshot", out.read_text())
            out.with_suffix(".pid").write_text(str(os.getpid()))
            dup = subprocess.run([sys.executable, str(ROOT / "harness/program_board.py"), "--ledger", str(ledger),
                                  "--output", str(out), "--watch", "120", "--all-reqs"], capture_output=True, text=True, env=env, timeout=30)
            self.assertIn("already running", dup.stdout)


class Parsing(unittest.TestCase):
    def test_incremental_reads_and_baseline_relative_flags(self):
        import importlib.util
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["COPILOT_HOME"] = tmp
            spec = importlib.util.spec_from_file_location("pb", ROOT / "harness/program_board.py")
            pb = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(pb)
            sid = "44444444-4444-4444-4444-444444444444"
            path = Path(tmp) / "session-state" / sid
            path.mkdir(parents=True)
            log = path / "events.jsonl"

            def usage(ts, prompt, limit):
                return json.dumps({"type": "session.usage_record", "timestamp": ts,
                                   "data": {"usage": {"inputTokens": prompt, "maxPromptTokens": limit}}}) + "\n"
            log.write_text(usage("2026-10-26T10:00:00Z", 70000, 128000))
            first = pb.read_session(sid)
            self.assertEqual(first["calls"], 1)
            self.assertIsNone(first["rotate"], "a fresh small-window session must not be flagged")
            with log.open("a") as handle:
                handle.write(usage("2026-10-26T10:05:00Z", 80000, 128000))
                handle.write('{"type": "session.usage_rec')
            second = pb.read_session(sid)
            self.assertEqual(second["calls"], 2)
            self.assertIsNone(second["rotate"], "modest growth over the baseline is not flagged")
            with log.open("a") as handle:
                handle.write('ord", "timestamp": "2026-10-26T10:09:00Z", "data": {"usage": {"inputTokens": 150000, "maxPromptTokens": 300000}}}\n')
            third = pb.read_session(sid)
            self.assertEqual(third["calls"], 3)
            self.assertEqual(third["rotate"], "hard")
            self.assertEqual(first["calls"], 1, "snapshots are not mutated by later reads")
            replaced = Path(tmp) / "replacement.jsonl"
            replaced.write_text(usage("2026-10-26T11:00:00Z", 10000, 128000) * 3)
            replaced.replace(log)
            self.assertEqual(pb.read_session(sid)["calls"], 3, "a replaced file is re-read from the start")
            with log.open("w") as handle:
                handle.write(usage("2026-10-26T12:00:00Z", 20000, 128000) * 5)
            self.assertEqual(pb.read_session(sid)["calls"], 5, "a truncated and regrown file is re-read")
            headroom = "55555555-5555-5555-5555-555555555555"
            (Path(tmp) / "session-state" / headroom).mkdir()
            (Path(tmp) / "session-state" / headroom / "events.jsonl").write_text(
                usage("2026-10-26T10:00:00Z", 70000, 128000) + usage("2026-10-26T10:30:00Z", 125000, 128000))
            self.assertEqual(pb.read_session(headroom)["rotate"], "hard", "growth into most of the headroom is hard")
            clipped = pb.read_session(headroom, pb.when("2026-10-26T10:10:00Z"))
            self.assertEqual(clipped["baseline"], 70000, "baseline is the first prompt even when events are clipped")


class EvidenceAndSnapshots(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.ledger = self.base / "ledger"
        self.ledger.mkdir()
        self.env = patch.dict(os.environ, {"COPILOT_HOME": str(self.base / "home")})
        self.env.start()
        self.addCleanup(self.env.stop)
        spec = importlib.util.spec_from_file_location("board_fixture", ROOT / "harness/program_board.py")
        self.pb = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.pb)
        self.state = self.pb.STATE_HOME
        self.source = self.ledger / "SPEC.md"
        self.source.write_text(
            "| ID | Requirement | Acceptance | Owner | Status | Evidence |\n|---|---|---|---|---|---|\n"
            "| REQ-1 | Initial task | Read it | writer | open | - |\n"
            "\n## Handoff\nNext: finish\nFailed approaches: none\nVerify: read\n")
        events(self.state / COORD, [{"type": "session.start", "timestamp": "2026-10-26T23:00:00-07:00",
                                    "data": {"selectedModel": "fixture"}}])

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.ledger), *args], capture_output=True, text=True, check=True).stdout.strip()

    def commit_seed(self):
        self.git("init", "-q")
        (self.ledger / "seed").write_text("unrelated")
        self.git("add", "seed")
        self.git("-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", "unrelated")
        return self.git("rev-parse", "HEAD")

    def test_artifact_identity_and_declared_review_are_separate(self):
        unrelated = self.commit_seed()
        artifact = self.ledger / "uncommitted report.md"
        artifact.write_bytes(b"reviewed artifact\n")
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()

        def claim(**extra):
            return "artifact: " + json.dumps({"path": artifact.name, "sha256": digest, **extra})

        def identity(text):
            return self.pb.evidence_identity(text, self.ledger, [self.ledger])

        self.assertEqual(identity("-")["state"], "missing")
        self.assertEqual(identity("artifact: report.md " + unrelated)["state"], "unsupported")
        self.assertEqual(identity("artifact: " + json.dumps({"path": artifact.name}))["state"], "incomplete")
        self.assertEqual(identity(digest + " " + unrelated)["state"], "unsupported")
        self.assertEqual(identity("artifact: {} " + unrelated)["state"], "unsupported")
        result = identity(claim())
        self.assertEqual(result["state"], "verified")
        self.assertIn("review binding missing", result["detail"])
        bound = claim(reviewed_sha256=digest) + "; review: judge PASS"
        self.assertFalse(self.pb.evidence_resolves(bound + " " + unrelated, [self.ledger]))
        result = identity(bound)
        self.assertEqual(result["state"], "verified")
        self.assertIn("declared digest binding; review note only", result["detail"])
        self.assertIn("review binding missing", identity(claim(reviewed_sha256="0" * 64) + "; review: judge PASS")["detail"])
        reviewer = self.state / CHILD
        events(reviewer, [
            {"type": "subagent.selected", "data": {"agentName": "architrave:adversarial-judge"}},
            {"type": "session.task_complete", "data": {"summary": "Verdict: PASS\nInspected the supplied artifact."}}])
        self.assertIn("review execution verified", identity(claim(reviewed_sha256=digest) + f"; review: {CHILD} PASS")["detail"])
        artifact.write_text("changed")
        self.assertEqual(identity(bound + " " + unrelated)["state"], "changed")
        artifact.unlink()
        self.assertEqual(identity(bound + " " + unrelated)["state"], "missing")
        self.assertEqual(identity("commit " + unrelated)["state"], "commit")
        self.assertIn("artifact identity", identity(unrelated)["detail"])
        self.assertEqual(identity("artifact: " + json.dumps({"path": str(self.ledger), "sha256": digest}))["state"], "unavailable")

    def test_plugin_only_notes_blockers_source_and_six_errors(self):
        sha = self.commit_seed()
        data = self.pb.build(self.ledger, COORD)
        self.assertEqual(data["source_state"], "untracked")
        self.assertEqual(data["source_digest"], hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.assertEqual(data["commit"], sha)
        page = self.pb.render(data)
        self.assertIn("<b>0/0</b><span>worker lanes running", page)
        self.assertIn("Synthetic requirement group (not a worker lane)", page)
        self.assertIn("ledger structural checks", page)
        self.assertIn("unavailable here: no repository configuration", page)
        self.assertFalse((self.ledger / "architrave.config.json").exists())
        self.git("add", "SPEC.md")
        self.git("-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", "ledger")
        self.assertEqual(self.pb.build(self.ledger, COORD)["source_state"], "clean")
        self.source.write_text(self.source.read_text().replace("Initial task", "Final correction"))
        changed = self.pb.build(self.ledger, COORD)
        self.assertEqual(changed["source_state"], "modified")
        self.assertNotEqual(data["source_digest"], changed["source_digest"])
        self.source.write_text(self.source.read_text() + (
            "\n| ID | Question | Source | Claim | Author | Status | Reviewed by |\n|---|---|---|---|---|---|---|\n"
            "| E-1 | Route | absent@abcdef1:route.md | Route exists | writer | unverified | - |\n"
            "\n| ID | Severity | Target | Finding | Raised by | Disposition | Verified by | Evidence |\n|---|---|---|---|---|---|---|---|\n"
            "| F-1 | high | REQ-1 | Auth uncertain | judge | open | - | - |\n"))
        noted = self.pb.build(self.ledger, COORD)
        self.assertTrue(noted["notes"])
        self.assertEqual(noted["blockers"], ["F-1"])
        self.assertIn("absent checkout not configured", self.pb.render(noted))
        self.assertIn("Open serious finding blocks completion: F-1", self.pb.render(noted))
        bad_rows = "".join(f"| REQ-bad{i} | Bad row {i} | check | writer | invalid-{i} | - |\n" for i in range(6))
        self.source.write_text(self.source.read_text().replace("\n\n## Handoff", "\n" + bad_rows + "\n## Handoff"))
        data = self.pb.build(self.ledger, COORD)
        self.assertEqual(len(data["errors"]), 6)
        for i in range(6):
            self.assertIn(f"REQ-bad{i} status", self.pb.render(data))

    def test_completion_and_multi_day_utc_history(self):
        log = self.state / COORD / "events.jsonl"
        with log.open("a") as handle:
            handle.write("\n" + json.dumps({"type": "session.task_complete", "timestamp": "2026-10-29T01:00:00-07:00", "data": {}}))
        complete = self.pb.build(self.ledger, COORD)
        self.assertIn("Host task completion observed", self.pb.render(complete))
        self.assertIn("10-27 06:00 UTC", self.pb.render(complete))
        self.assertIn("10-29 08:00 UTC", self.pb.render(complete))
        with log.open("a") as handle:
            handle.write("\n" + json.dumps({"type": "assistant.turn_start", "timestamp": "2026-10-29T08:01:00Z", "data": {}}))
        active = self.pb.build(self.ledger, COORD)
        self.assertIn("pre-completion projection", self.pb.render(active))
        self.assertIn("Cumulative session history (not current-task cost)", self.pb.render(active))
        self.assertNotIn("http-equiv", self.pb.render(active))

    def test_merged_history_empty_and_remote_records(self):
        remote = [{"lane": "Remote worker with a complete name", "session id": REMOTE, "state": "running"}]
        page = self.pb.timeline([], {}, remote)
        self.assertIn("Remote worker with a complete name", page)
        self.assertIn("metrics unavailable", page)
        self.assertNotIn("output tokens", page)
        self.assertIn("No local session logs found", self.pb.timeline([], {}))

    def test_explicit_scope_excludes_historical_requirements(self):
        self.source.write_text(self.source.read_text().replace("| REQ-1 |", (
            "| REQ-old | Historical work | Check | old-owner | accepted | old prose note |\n| REQ-1 |")))
        command = [sys.executable, str(ROOT / "harness/program_board.py"), "--ledger", str(self.ledger),
                   "--session", COORD, "--output", str(self.base / "scoped.html")]
        missing = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(missing.returncode, 2)
        self.assertIn("--reqs", missing.stderr)
        self.assertIn("--all-reqs", missing.stderr)
        for flags in (["--reqs", " , "], ["--reqs", "REQ-1", "--all-reqs"]):
            rejected = subprocess.run(command + flags, capture_output=True, text=True)
            self.assertEqual(rejected.returncode, 2, rejected.stderr)
        out = self.base / "scoped.html"
        scoped = subprocess.run(command + ["--reqs", "req-1,REQ-1"], capture_output=True, text=True)
        self.assertEqual(scoped.returncode, 0, scoped.stderr)
        page = out.read_text()
        self.assertIn("Session requirements: REQ-1", page)
        self.assertIn("<b>0/1</b><span>REQs accepted", page)
        self.assertNotIn("REQ-old", page)
        self.assertNotIn("Historical work", page)
        self.assertNotIn("old prose note", page)
        for mode in ([], ["--watch", "120"]):
            unknown = subprocess.run(command + ["--reqs", "REQ-missing"] + mode,
                                     capture_output=True, text=True, timeout=3)
            self.assertNotEqual(unknown.returncode, 0)
            self.assertIn("unknown session REQ IDs", unknown.stderr)
            self.assertEqual(out.read_text(), page)
            self.assertFalse(out.with_suffix(".pid").exists())
            self.assertFalse((self.state / COORD / "files/program-board.watch").exists())
        all_reqs = subprocess.run(command + ["--all-reqs"], capture_output=True, text=True)
        self.assertEqual(all_reqs.returncode, 0, all_reqs.stderr)
        self.assertIn("Repository-wide requirements", out.read_text())
        self.assertIn("REQ-old", out.read_text())
        # A mixed lane is projected to selected IDs; unrelated lanes are not workers in this view.
        self.source.write_text(self.source.read_text() + LANE
            + f"| Mixed | app | p | b | origin | REQ-old, REQ-1 | - | {CHILD} | - | ready | src | no | ok | - | no | [] | - |\n"
            + f"| Historic | app | p | b | origin | REQ-old | - | {REMOTE} | - | done | docs | no | ok | - | no | [] | - |\n")
        data = self.pb.build(self.ledger, COORD, ["REQ-1"])
        self.assertEqual(len(data["lanes"]), 1)
        self.assertEqual(data["lanes"][0]["req ids"], "REQ-1")
        self.assertEqual(set(data["identities"]), {"REQ-1"})
        self.assertNotIn("REQ-old", self.pb.render(data))

    def test_live_watcher_stops_with_fresh_static_snapshot(self):
        out = self.base / "watched.html"
        (self.state / COORD / "events.jsonl").write_text(json.dumps({
            "type": "session.start", "timestamp": datetime.now(timezone.utc).isoformat(), "data": {}}) + "\n")
        env = dict(os.environ, COPILOT_AGENT_SESSION_ID=COORD)
        process = subprocess.Popen([sys.executable, str(ROOT / "harness/program_board.py"), "--ledger", str(self.ledger),
                                    "--output", str(out), "--watch", "30", "--reqs", "REQ-1"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        self.addCleanup(lambda: process.kill() if process.poll() is None else None)
        self.assertIn("program-board:", process.stdout.readline())
        self.assertIsNone(process.poll())
        self.source.write_text(self.source.read_text().replace("Initial task", "Final correction"))
        process.terminate()
        process.communicate(timeout=10)
        self.assertIn("Stopped watcher; static snapshot", out.read_text())
        self.assertIn("Final correction", out.read_text())
        self.assertIn("Session requirements: REQ-1", out.read_text())
        self.assertIn(hashlib.sha256(self.source.read_bytes()).hexdigest(), out.read_text())
        self.assertFalse(out.with_suffix(".pid").exists())
        self.assertFalse((self.state / COORD / "files/program-board.watch").exists())

    def test_browser_print_and_observation(self):
        if BROWSER_OUTPUT is None:
            self.skipTest("use --browser-output for actual PDF and interactive checks")
        from playwright.sync_api import sync_playwright
        from pypdf import PdfReader
        output = BROWSER_OUTPUT.resolve()
        output.mkdir(parents=True, exist_ok=True)
        history = []
        names = []
        for i in range(26):
            sid = f"{i + 10:08x}-2222-4222-8222-222222222222"
            name = f"Worker {i:02d} complete long session name retained in static export"
            names.append(name)
            history += [
                {"type": "tool.execution_start", "timestamp": "2026-10-28T08:00:00Z",
                 "data": {"toolName": "create_session", "toolCallId": sid, "arguments": {"name": name}}},
                {"type": "tool.execution_complete", "timestamp": "2026-10-28T08:00:01Z",
                 "data": {"toolCallId": sid, "result": f"Created session {sid}"}}]
            events(self.state / sid, [
                {"type": "session.start", "timestamp": "2026-10-28T08:00:02Z", "data": {"selectedModel": "fixture"}},
                {"type": "session.usage_record", "timestamp": "2026-10-29T08:00:00Z",
                 "data": {"usage": {"inputTokens": 2345678, "cacheReadTokens": 1111111,
                                    "outputTokens": 987654, "maxPromptTokens": 3000000, "model": "fixture"}}}])
        log = self.state / COORD / "events.jsonl"
        with log.open("a") as handle:
            handle.write("\n" + "\n".join(json.dumps(row) for row in history) + "\n")
        bad_rows = "".join(f"| REQ-bad{i} | Bad row {i} | check | writer | invalid-{i} | - |\n" for i in range(6))
        self.source.write_text(self.source.read_text().replace("\n\n## Handoff", "\n" + bad_rows + "\n## Handoff"))
        html_path = output / "program-board-print.html"
        html_path.write_text(self.pb.render(self.pb.build(self.ledger, COORD)))
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": 760, "height": 900})
                page.goto(html_path.as_uri(), wait_until="networkidle")
                self.assertIn("Page observed at", page.locator("#page-observation").inner_text())
                original_snapshot = page.locator("#snapshot").get_attribute("data-snapshot")
                page.locator("button.sq").first.focus()
                page.keyboard.press("Enter")
                self.assertIn("Initial task", page.locator("#detail").inner_text())
                page.keyboard.press("Space")
                self.assertIn("Initial task", page.locator("#detail").inner_text())
                self.assertEqual(page.locator("#detail").get_attribute("role"), "status")
                self.source.write_text(self.source.read_text().replace("Initial task", "Final correction"))
                html_path.write_text(self.pb.render(self.pb.build(self.ledger, COORD)))
                self.assertEqual(page.locator("#snapshot").get_attribute("data-snapshot"), original_snapshot,
                                 "saved bytes are not a new consumer observation")
                self.assertNotIn("Final correction", page.locator("button.sq").first.get_attribute("aria-label"))
                page.reload(wait_until="networkidle")
                self.assertNotEqual(page.locator("#snapshot").get_attribute("data-snapshot"), original_snapshot)
                self.assertIn("Final correction", page.locator("button.sq").first.get_attribute("aria-label"))
                self.assertIn("pre-completion projection", page.locator(".provenance").inner_text())
                for i in range(6):
                    self.assertIn(f"REQ-bad{i} status", page.locator(".issues").inner_text())
                for width in (390, 760):
                    page.set_viewport_size({"width": width, "height": 900})
                    self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
                    self.assertTrue(page.locator(".session-record").evaluate_all(
                        "nodes=>nodes.every(n=>n.scrollWidth<=n.clientWidth)"))
                    self.assertEqual(page.locator(".session-record").count(), len(names) + 1)
                    for record in page.locator(".session-record").all():
                        self.assertTrue(record.locator("h3").is_visible())
                        self.assertTrue(record.locator(".history-visual").is_visible())
                        self.assertIn("output tokens", record.inner_text())
                        self.assertIn("Context", record.inner_text())
                    page.screenshot(path=str(output / f"board-{width}.png"), full_page=True)
                page.emulate_media(media="print")
                self.assertFalse(page.locator("#detail").is_visible())
                self.assertTrue(page.locator(".interactive-only").evaluate_all(
                    "nodes=>nodes.every(n=>getComputedStyle(n).display==='none')"))
                pdf_path = output / "program-board.pdf"
                page.pdf(path=str(pdf_path), prefer_css_page_size=True, print_background=True)
                pdf = PdfReader(pdf_path)
                self.assertGreaterEqual(len(pdf.pages), 3)
                self.assertLessEqual(len(pdf.pages), 8)
                pages = [" ".join(p.extract_text().split()) for p in pdf.pages]
                text = " ".join(pages)
                for name in names:
                    self.assertIn(name, text)
                for value in ("1,234,567", "1,111,111", "987,654", "2,345,678", "3,000,000"):
                    self.assertIn(value, text)
                self.assertNotIn("Select a square", text)
                self.assertNotIn("Hover a row", text)
                self.assertIn("Print/export requested at", text)
                self.assertIn("pre-completion projection", text)
                for content in pages:
                    if "Cumulative session history" in content:
                        self.assertIn("Coordinator", content, "timeline heading must not be orphaned")
                for content in pages[1:-1]:
                    self.assertGreaterEqual(content.count("new input /"), 3, "unexpected large pagination gap")
                # Completion after the saved/observed page is not retroactive.
                with log.open("a") as handle:
                    handle.write(json.dumps({"type": "session.task_complete", "timestamp": "2026-10-29T09:00:00Z", "data": {}}) + "\n")
                self.assertIn("pre-completion projection", page.locator(".provenance").inner_text())
                html_path.write_text(self.pb.render(self.pb.build(self.ledger, COORD)))
                page.reload(wait_until="networkidle")
                self.assertIn("Host task completion observed", page.locator(".provenance").inner_text())
                (output / "browser-result.json").write_text(json.dumps({
                    "pdf_pages": len(pdf.pages), "full_names_checked": len(names), "errors_exposed": 6,
                    "keyboard_enter_space": "passed", "saved_vs_observed": "passed",
                    "completion_after_snapshot": "passed", "screen_widths": [390, 760],
                    "browser": browser.version, "synthetic_only": True}, indent=2))
            finally:
                browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser-output", type=Path, help="also verify a real multi-page PDF and keyboard interaction (requires playwright and pypdf)")
    args, remaining = parser.parse_known_args()
    BROWSER_OUTPUT = args.browser_output
    unittest.main(argv=[sys.argv[0], *remaining])
