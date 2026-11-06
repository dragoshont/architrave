#!/usr/bin/env python3
"""Acceptance-decision checks on protocol data, not provider/runtime acceptance."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch as mock_patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gates"))
import delivery_audit as audit
import delivery_check as check
import gate_runner as gate

SESSION = "11111111-1111-4111-8111-111111111111"
REVIEWER = "22222222-2222-4222-8222-222222222222"
SPEC = """# Requirements
| ID | Requirement | Acceptance | Owner | Status | Evidence |
|---|---|---|---|---|---|
| REQ-01 | Exercise the requested provider | Same-run provider and useful result | owner | open | |

## Handoff
Next: verify the actual target.
Failed approaches: none.
Verify: inspect the provider result.
"""


class DeliveryChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.home = self.root / "copilot"
        self.prior_home = os.environ.get("COPILOT_HOME")
        os.environ["COPILOT_HOME"] = str(self.home)
        self.addCleanup(self.restore_home)
        self.git("init", "--quiet")
        (self.repo / "SPEC.md").write_text(SPEC)
        (self.repo / "README.md").write_text("Real provider integration is required.\n")
        (self.repo / "provider.py").write_text("result = client.execute(request)\n")
        self.git("add", ".")
        self.git("-c", "user.name=Acceptance Test", "-c", "user.email=check@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "Original contract")
        self.config = self.root / "effective.json"
        self.config.write_text('{"provider":"official-emulator","enabled":true}')
        self.proof = self.root / "observation.json"
        self.proof.write_text('{"scope":"unit acceptance data, not actual external execution"}')
        self.log = [
            {"id": "owner-event", "timestamp": "2026-01-01T10:00:00Z", "type": "user.message",
             "data": {"content": "Use the official local emulator, switch to Azure when publishing."}},
        ]
        board = check.session_report_path(SESSION).parent / "program-board.html"
        board.parent.mkdir(parents=True)
        board.write_text("<html>REQ-01</html>")
        self.tool("open", "open_canvas", {"canvasId": "browser", "instanceId": "board",
                                        "input": {"url": board.as_uri()}})
        self.tool("read", "invoke_canvas_action", {"instanceId": "board", "actionName": "read_page"},
                  result="Program board REQ-01")
        self.tool("check", "powershell", {"description": "Observe required provider"},
                  result="bounded tool observation; proof SHA256 " + check.file_identity(self.proof)["sha256"])
        self.write_log(SESSION, self.log)
        snapshot = audit.scan(self.repo, reqs=["REQ-01"])
        self.report = {
            "schema": check.SCHEMA, "state": "sealed", "repo": str(self.repo),
            "session_id": SESSION, "reqs": ["REQ-01"], "base_sha": snapshot["base_sha"],
            "prepared_at": "2026-01-01T10:00:00Z",
            "sealed_at": "2026-01-01T10:01:02Z",
            "all_files": False, "document_paths": None,
            "original_requirements": snapshot["requirements"], "audit": snapshot,
            "owner_requests": [check.owner_reference("owner-event", self.log)], "references": [],
            "board": {"open_call_id": "open", "read_call_id": "read"},
            "expected": {"REQ-01": {"kind": "integration", "entrypoint": "actual-client",
                                    "provider": "official-emulator", "target": "local"}},
            "dispositions": {},
            "observations": {"REQ-01": self.observation()},
            "review": None,
        }

    def restore_home(self):
        if self.prior_home is None:
            os.environ.pop("COPILOT_HOME", None)
        else:
            os.environ["COPILOT_HOME"] = self.prior_home
        gate.SESSION_FACTS.clear()

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], stderr=subprocess.STDOUT)

    def tool(self, call_id, name, arguments, result="OK", success=True):
        self.log.extend([
            {"type": "tool.execution_start", "timestamp": "2026-01-01T10:01:00Z",
             "data": {"toolCallId": call_id, "toolName": name, "arguments": arguments}},
            {"type": "tool.execution_complete", "timestamp": "2026-01-01T10:01:01Z",
             "data": {"toolCallId": call_id, "success": success, "result": {"content": result}}},
        ])

    def write_log(self, sid, items):
        path = check.session_report_path(sid).parents[1] / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(e) + "\n" for e in items), encoding="utf-8")

    def observation(self):
        return {"kind": "integration", "outcome": "passed", "entrypoint": "actual-client",
                "provider": "official-emulator", "target": "local", "enabled": True,
                "provider_invoked": True, "result_mode": "fresh", "run_id": "run-1",
                "provider_run_id": "run-1", "result_run_id": "run-1",
                "effective_config": check.file_identity(self.config),
                "tool_call_id": "check", "proof": check.file_identity(self.proof),
                "meaning": "Acceptance-decision unit data only, not a live-provider claim."}

    def errors(self, report=None):
        return check.check_report(self.repo, report or self.report, require_review=False)

    def command(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(ROOT / "gates" / "gate_runner.py"),
             "delivery-audit", "--repo", str(self.repo), "--session", SESSION, *args],
            capture_output=True, text=True, encoding="utf-8")

    def scoped(self):
        self.report["source_paths"] = ["provider.py"]
        self.report["audit"] = audit.scan(
            self.repo, reqs=["REQ-01"], source_paths=["provider.py"])

    def reviewed(self):
        sha = check.report_digest(self.report)
        self.report["review"] = {"session_id": REVIEWER, "sha256": sha}
        self.write_log(REVIEWER, [
            {"type": "subagent.selected", "data": {"agentName": "architrave:adversarial-judge"}},
            {"type": "assistant.turn_start", "data": {}},
            {"type": "session.task_complete",
             "data": {"summary": f"Verdict: PASS\nDelivery digest: {sha}\nProtocol unit data only."}},
        ])
        check.write_report(check.session_report_path(SESSION), self.report)

    def requirements_command(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(ROOT / "gates" / "gate_runner.py"),
             "requirements", "--done", "--repo", str(self.repo), *args],
            capture_output=True, text=True, encoding="utf-8")

    def test_scoped_done_excludes_unrelated_requirements_lanes_and_findings(self):
        (self.repo / "architrave.config.json").write_text(json.dumps({
            "kind": "knowledge", "build": "git diff --check", "test": "python checks.py"}))
        ledger = SPEC.replace("| owner | open | |\n", "| owner | accepted | observed |\n"
                              "| REQ-02 | Unrelated task | Other result | other | open | |\n")
        lane = dict.fromkeys(gate.LANE_COLUMNS, "-")
        lane.update({"lane": "unrelated", "repo": "self", "req ids": "REQ-02", "state": "done",
                     "owner-only decisions": "[]"})
        ledger += ("\n| " + " | ".join(gate.LANE_COLUMNS) + " |\n| "
                   + " | ".join("---" for _ in gate.LANE_COLUMNS) + " |\n| "
                   + " | ".join(lane[c] for c in gate.LANE_COLUMNS) + " |\n")
        ledger += """
| ID | Severity | Target | Finding | Raised by | Disposition | Verified by | Evidence |
|---|---|---|---|---|---|---|---|
| F-1 | high | REQ-02 | Unrelated unfinished behavior | judge | open | - | - |
"""
        (self.repo / "SPEC.md").write_text(ledger)
        self.scoped()
        self.reviewed()
        scoped = self.requirements_command("--delivery-session", SESSION)
        self.assertEqual(scoped.returncode, 0, scoped.stdout + scoped.stderr)
        full = self.requirements_command()
        self.assertNotEqual(full.returncode, 0)
        for expected in ("REQ-02", "lane unrelated", "open serious findings"):
            self.assertIn(expected, full.stdout)
        (self.repo / "SPEC.md").write_text(ledger.replace("| high | REQ-02 |", "| high | REQ-01 |"))
        related = self.requirements_command("--delivery-session", SESSION)
        self.assertNotEqual(related.returncode, 0)
        self.assertIn("open serious findings", related.stdout)

    def test_scoped_inventory_ignores_unrelated_churn_but_binds_dependencies(self):
        self.scoped()
        before = self.report["audit"]["source_sha256"]
        (self.repo / "unrelated.py").write_text("result = FakeProvider()\n")
        (self.repo / "SPEC.md").write_text(SPEC.replace(
            "| owner | open | |\n", "| owner | open | |\n"
            "| REQ-02 | Unrelated task | Other result | other | open | |\n"))
        self.assertEqual(self.errors(), [])
        self.assertEqual(before, audit.scan(
            self.repo, reqs=["REQ-01"], source_paths=["provider.py"])["source_sha256"])
        for name in ("provider.py", "README.md", "architrave.config.json"):
            path = self.repo / name
            old = path.read_bytes() if path.exists() else None
            path.write_text("{}" if name.endswith(".json") else "changed\n")
            self.assertTrue(any("inventory changed" in e for e in self.errors()), name)
            if old is None:
                path.unlink()
            else:
                path.write_bytes(old)

    def test_scope_paths_reject_traversal_and_track_new_directory_files(self):
        for source in ("../outside", ".", "", r"C:\outside", "/outside", ".git/config"):
            with self.assertRaises(ValueError, msg=source):
                audit.scan(self.repo, reqs=["REQ-01"], source_paths=[source])
        (self.repo / "src").mkdir()
        first = audit.scan(self.repo, reqs=["REQ-01"], source_paths=["src"])
        (self.repo / "src" / "new.py").write_text("result = client.execute(request)\n")
        self.assertNotEqual(first["source_sha256"], audit.scan(
            self.repo, reqs=["REQ-01"], source_paths=["src"])["source_sha256"])

    def test_scoped_directory_case_matches_host_filesystem(self):
        source = self.repo / "gates"
        source.mkdir()
        implementation = source / "actual.py"
        implementation.write_text("result = client.execute(request)\n")
        self.git("add", "gates")
        alias_exists = (self.repo / "GATES").is_dir()
        try:
            first = audit.scan(self.repo, reqs=["REQ-01"], source_paths=["GATES"])
        except ValueError as exc:
            self.assertTrue(alias_exists)
            self.assertIn("source path spelling", str(exc))
            first = audit.scan(self.repo, reqs=["REQ-01"], source_paths=["gates"])
            implementation.write_text("result = other.execute(request)\n")
            self.assertNotEqual(first["source_sha256"], audit.scan(
                self.repo, reqs=["REQ-01"], source_paths=["gates"])["source_sha256"])
            return
        if alias_exists:
            self.assertEqual(first["source_paths"], ["gates"])
            self.assertIn("gates/actual.py", [row["path"] for row in first["source_files"]])
            implementation.write_text("result = other.execute(request)\n")
            self.assertNotEqual(first["source_sha256"], audit.scan(
                self.repo, reqs=["REQ-01"], source_paths=["GATES"])["source_sha256"])
        else:
            self.assertNotIn("gates/actual.py", [row["path"] for row in first["source_files"]])
            implementation.write_text("result = other.execute(request)\n")
            self.assertEqual(first["source_sha256"], audit.scan(
                self.repo, reqs=["REQ-01"], source_paths=["GATES"])["source_sha256"])

    def test_scoped_symlink_and_symlink_parent_are_rejected(self):
        link = self.repo / "linked"
        try:
            link.symlink_to(self.repo, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"host cannot create test symlink: {exc}")
        for name in ("linked", "linked/provider.py"):
            with self.assertRaises(ValueError):
                audit.scan(self.repo, reqs=["REQ-01"], source_paths=[name])

    def test_prepare_requires_explicit_sources_and_binds_owner_paths(self):
        missing = self.command("--prepare", "--reqs", "REQ-01", "--request", "owner-event")
        self.assertEqual(missing.returncode, 2)
        self.assertIn("--source", missing.stderr)
        result = self.command("--prepare", "--reqs", "REQ-01", "--request", "owner-event",
                              "--source", "provider.py")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = check.read_json(check.session_report_path(SESSION))
        self.assertEqual(report["source_paths"], ["provider.py"])
        self.assertEqual(report["owner_anchors"], {"REQ-01": ["owner-event"]})

    def test_unchanged_amendment_retains_outcomes_and_owner_anchor(self):
        self.scoped()
        check.write_report(check.session_report_path(SESSION), self.report, create=True)
        self.log.append({"id": "owner-correction", "timestamp": "2026-01-02T10:00:00Z",
                         "type": "user.message", "data": {"content": "Continue the unchanged scope."}})
        self.write_log(SESSION, self.log)
        result = self.command("--amend", "--request", "owner-correction")
        self.assertEqual(result.returncode, 0, result.stderr)
        updated = check.read_json(check.session_report_path(SESSION))
        self.assertEqual(updated["expected"], self.report["expected"])
        self.assertEqual(updated["observations"], self.report["observations"])
        self.assertEqual(updated["owner_anchors"]["REQ-01"], ["owner-event"])
        self.assertIsNone(updated["review"])
        result = self.command("--seal")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.errors(check.read_json(check.session_report_path(SESSION))), [])

    def test_new_requirement_preserves_only_unchanged_owned_outcome(self):
        self.scoped()
        check.write_report(check.session_report_path(SESSION), self.report, create=True)
        (self.repo / "SPEC.md").write_text(SPEC.replace(
            "| owner | open | |\n", "| owner | open | |\n"
            "| REQ-02 | Another check | Additional result | owner | open | |\n"))
        self.log.append({"id": "owner-addition", "timestamp": "2026-01-02T10:00:00Z",
                         "type": "user.message", "data": {"content": "Also check the additional result."}})
        self.write_log(SESSION, self.log)
        result = self.command("--amend", "--request", "owner-addition", "--reqs", "REQ-01,REQ-02")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = check.read_json(check.session_report_path(SESSION))
        self.assertEqual(report["observations"], self.report["observations"])
        self.assertEqual(report["expected"]["REQ-02"], {"kind": "unclassified"})
        self.assertEqual(report["owner_anchors"], {"REQ-01": ["owner-event"], "REQ-02": ["owner-addition"]})
        self.assertIsNone(report["board"])
        self.assertEqual(report["board_owner_event_ids"], ["owner-addition"])

    def test_changed_dependency_or_boundary_invalidates_outcomes_on_amendment(self):
        self.scoped()
        check.write_report(check.session_report_path(SESSION), self.report, create=True)
        self.log.append({"id": "owner-change", "timestamp": "2026-01-01T10:00:30Z",
                         "type": "user.message", "data": {"content": "Include the other dependency."}})
        self.write_log(SESSION, self.log)
        result = self.command("--amend", "--request", "owner-change",
                              "--source", "provider.py", "--source", "another.py")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = check.read_json(check.session_report_path(SESSION))
        self.assertEqual(report["observations"], {})
        self.assertEqual(report["owner_anchors"], {"REQ-01": ["owner-change"]})
        self.assertIsNone(report["review"])
        self.assertEqual(report["history"][-1]["source_paths"], ["provider.py"])
        # This old run follows the newer owner event but predates the changed
        # dependency capture. Restoring it cannot accept the amended source.
        report["expected"] = self.report["expected"]
        report["observations"] = self.report["observations"]
        check.write_report(check.session_report_path(SESSION), report)
        self.assertEqual(self.command("--seal").returncode, 0)
        self.assertTrue(any("earlier tool" in e for e in self.errors(
            check.read_json(check.session_report_path(SESSION)))))

    def test_changed_source_amendment_and_reseal_cannot_reuse_old_proof(self):
        self.scoped()
        check.write_report(check.session_report_path(SESSION), self.report, create=True)
        (self.repo / "provider.py").write_text("result = other.execute(request)\n")
        result = self.command("--seal")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(check.read_json(check.session_report_path(SESSION))["observations"], {})
        resealed = check.read_json(check.session_report_path(SESSION))
        resealed["observations"] = self.report["observations"]
        self.assertTrue(any("earlier tool" in e for e in self.errors(resealed)))
        self.log.append({"id": "owner-correction", "timestamp": "2026-01-02T10:00:00Z",
                         "type": "user.message", "data": {"content": "Revise the implementation."}})
        self.write_log(SESSION, self.log)
        result = self.command("--amend", "--request", "owner-correction")
        self.assertEqual(result.returncode, 0, result.stderr)
        updated = check.read_json(check.session_report_path(SESSION))
        self.assertEqual(updated["observations"], {})

    def test_pause_is_non_delivery_with_exact_hook_summary_and_explicit_resume(self):
        import session_guard

        self.scoped()
        check.write_report(check.session_report_path(SESSION), self.report, create=True)
        result = self.command("--pause", "blocked", "--reason", "Required target is unavailable.",
                              "--evidence", str(self.proof))
        self.assertEqual(result.returncode, 0, result.stderr)
        paused = check.read_json(check.session_report_path(SESSION))
        summary = check.terminal_summary(paused)
        payload = {"sessionId": SESSION, "cwd": str(self.repo), "toolName": "task_complete",
                   "toolArgs": {"summary": summary}}
        self.assertEqual(session_guard.pre_tool_use(payload), {})
        payload["toolArgs"]["summary"] = "Everything delivered."
        self.assertEqual(session_guard.pre_tool_use(payload)["permissionDecision"], "deny")
        self.assertTrue(check.check_session(self.repo, SESSION, allow_withdrawal=False))
        self.assertEqual(self.command("--check").returncode, 2)
        self.assertEqual(self.command("--seal").returncode, 2)
        (self.repo / "unrelated.py").write_text("unrelated = 1\n")
        payload["toolArgs"]["summary"] = summary
        self.assertEqual(session_guard.pre_tool_use(payload), {})
        self.assertEqual(self.command("--resume").returncode, 0)
        self.assertEqual(check.read_json(check.session_report_path(SESSION))["state"], "prepared")

    def test_paused_source_owner_and_evidence_drift_fail_closed(self):
        import session_guard

        self.scoped()
        check.write_report(check.session_report_path(SESSION), self.report, create=True)
        result = self.command("--pause", "handoff", "--reason", "Implementation handed to its owner.",
                              "--evidence", str(self.proof))
        self.assertEqual(result.returncode, 0, result.stderr)
        report = check.read_json(check.session_report_path(SESSION))
        payload = {"sessionId": SESSION, "cwd": str(self.repo), "toolName": "task_complete",
                   "toolArgs": {"summary": check.terminal_summary(report)}}
        self.log.append({"id": "reminder", "timestamp": "2026-01-03T10:00:00Z", "type": "user.message",
                         "data": {"content": "You have not yet marked the task as complete"}})
        self.write_log(SESSION, self.log)
        self.assertEqual(session_guard.pre_tool_use(payload), {})
        self.assertNotEqual(self.requirements_command("--delivery-session", SESSION).returncode, 0)
        before = (self.repo / "provider.py").read_bytes()
        (self.repo / "provider.py").write_text("result = different.execute(request)\n")
        self.assertEqual(session_guard.pre_tool_use(payload)["permissionDecision"], "deny")
        self.assertEqual(self.command("--resume").returncode, 2)
        (self.repo / "provider.py").write_bytes(before)
        self.proof.write_text("changed evidence")
        self.assertEqual(session_guard.pre_tool_use(payload)["permissionDecision"], "deny")

    def test_cross_repository_handoff_allows_only_validated_non_delivery(self):
        import session_guard

        caller = self.root / "caller"
        caller.mkdir()
        subprocess.check_call(["git", "-C", str(caller), "init", "--quiet"])
        self.scoped()
        check.write_report(check.session_report_path(SESSION), self.report, create=True)
        result = self.command("--pause", "handoff", "--reason", "Implementation handed to its owner.",
                              "--evidence", str(self.proof))
        self.assertEqual(result.returncode, 0, result.stderr)
        paused = check.read_json(check.session_report_path(SESSION))
        payload = {"sessionId": SESSION, "cwd": str(caller), "toolName": "task_complete",
                   "toolArgs": {"summary": check.terminal_summary(paused)}}
        before = check.session_report_path(SESSION).read_bytes()
        self.assertEqual(session_guard.pre_tool_use(payload), {})
        self.assertEqual(check.session_report_path(SESSION).read_bytes(), before)
        self.assertTrue(check.check_session(caller, SESSION))
        self.assertTrue(check.check_session(self.repo, SESSION, allow_withdrawal=False))
        self.assertTrue(check.check_session(
            caller, SESSION, completion_hook=True, allow_withdrawal=False,
            completion_summary=check.terminal_summary(paused)))
        for field, value in (("schema", "invalid"), ("session_id", REVIEWER)):
            malformed = copy.deepcopy(paused)
            malformed[field] = value
            check.write_report(check.session_report_path(SESSION), malformed)
            self.assertEqual(session_guard.pre_tool_use(payload)["permissionDecision"], "deny")
        check.write_report(check.session_report_path(SESSION), paused)
        payload["toolArgs"]["summary"] = "Everything delivered."
        self.assertEqual(session_guard.pre_tool_use(payload)["permissionDecision"], "deny")
        payload["toolArgs"]["summary"] = check.terminal_summary(paused)
        (self.repo / "provider.py").write_text("result = different.execute(request)\n")
        self.assertEqual(session_guard.pre_tool_use(payload)["permissionDecision"], "deny")

    def test_foreign_active_declaration_cannot_use_non_delivery_or_followup_to_escape(self):
        caller = self.root / "caller"
        caller.mkdir()
        subprocess.check_call(["git", "-C", str(caller), "init", "--quiet"])
        for state in ("prepared", "sealed"):
            self.report["state"] = state
            check.write_report(check.session_report_path(SESSION), self.report)
            for summary in (
                "Architrave handoff: NOT DELIVERED; no requirements accepted by this termination.",
                "Read-only follow-up (no new delivery acceptance): unrelated question",
            ):
                self.assertEqual(check.check_session(
                    caller, SESSION, completion_hook=True, completion_summary=summary),
                    ["delivery repository identity differs"])

    def test_completed_handoff_retires_only_after_exact_host_event_and_blocks_new_edits(self):
        import session_guard

        caller = self.root / "caller"
        caller.mkdir()
        subprocess.check_call(["git", "-C", str(caller), "init", "--quiet"])
        self.scoped()
        check.write_report(check.session_report_path(SESSION), self.report, create=True)
        result = self.command("--pause", "handoff", "--reason", "Implementation handed to its owner.",
                              "--evidence", str(self.proof))
        self.assertEqual(result.returncode, 0, result.stderr)
        paused = check.read_json(check.session_report_path(SESSION))
        completed_at = datetime.fromisoformat(paused["terminal"]["recorded_at"]) + timedelta(seconds=1)
        payload = {"sessionId": SESSION, "cwd": str(caller), "toolName": "task_complete",
                   "toolArgs": {"summary": "The improvement plan has five areas."}}
        terminal = {"type": "session.task_complete", "timestamp": completed_at.isoformat(),
                    "data": {"summary": "Unrelated task completion"}}
        self.write_log(SESSION, [*self.log, terminal])
        self.assertEqual(session_guard.pre_tool_use(payload)["permissionDecision"], "deny")
        first_plain = self.root / "first-plain"
        first_plain.mkdir()
        self.assertEqual(check.check_session(first_plain, SESSION, completion_hook=True,
                                             completion_summary=check.terminal_summary(paused)), [])
        self.assertTrue(check.check_session(first_plain, SESSION, completion_hook=True,
                                            completion_summary="The improvement plan has five areas."))
        terminal["data"]["summary"] = check.terminal_summary(paused)
        self.write_log(SESSION, [*self.log, terminal])
        self.assertEqual(session_guard.pre_tool_use(payload), {})
        plain = self.root / "plain-folder"
        plain.mkdir()
        payload["cwd"] = str(plain)
        self.assertEqual(session_guard.pre_tool_use(payload), {})
        payload["cwd"] = str(caller)
        for root in (self.repo, caller):
            payload["cwd"] = str(root)
            for summary in (
                "The improvement plan has five areas.",
                "Unrelated follow-up (prior scope remains NOT DELIVERED): Explanation.",
            ):
                payload["toolArgs"]["summary"] = summary
                result = subprocess.run(
                    [sys.executable, "-B", str(ROOT / "gates" / "session_guard.py"), "pre-tool-use"],
                    input=json.dumps(payload), cwd=root, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout), {})
        payload["cwd"] = str(caller)
        path = check.session_report_path(SESSION)
        before = path.read_bytes()
        recovered = self.command("--completion-summary")
        self.assertEqual(recovered.returncode, 0, recovered.stderr)
        self.assertTrue(recovered.stdout.startswith(
            "Unrelated follow-up (prior scope remains NOT DELIVERED): "), recovered.stdout)
        payload["toolArgs"]["summary"] = recovered.stdout.strip()
        self.assertEqual(session_guard.pre_tool_use(payload), {})
        self.assertEqual(path.read_bytes(), before)
        malformed_reports = []
        for field, value in (("owner_requests", []), ("reqs", []), ("repo", str(self.repo / "subdir"))):
            malformed = copy.deepcopy(paused)
            malformed[field] = value
            malformed_reports.append(malformed)
        missing_owners = copy.deepcopy(paused)
        missing_owners.pop("owner_requests")
        malformed_reports.append(missing_owners)
        for malformed in malformed_reports:
            check.write_report(check.session_report_path(SESSION), malformed)
            self.assertEqual(session_guard.pre_tool_use(payload)["permissionDecision"], "deny")
            self.assertEqual(self.command("--completion-summary").returncode, 2)
        check.write_report(check.session_report_path(SESSION), paused)
        (self.repo / "provider.py").write_text("changed_by_another_writer()\n")
        self.assertEqual(session_guard.pre_tool_use(payload), {})
        recovered = self.command("--completion-summary")
        self.assertEqual(recovered.returncode, 0, recovered.stderr)
        self.assertTrue(recovered.stdout.startswith(
            "Unrelated follow-up (prior scope remains NOT DELIVERED): "), recovered.stdout)
        payload["toolArgs"]["summary"] = "The improvement plan has five areas."
        self.assertEqual(session_guard.pre_tool_use(payload), {})
        for summary in (None, "", "   "):
            payload["toolArgs"]["summary"] = summary
            self.assertEqual(session_guard.pre_tool_use(payload)["permissionDecision"], "deny")
        payload["toolArgs"]["summary"] = "The improvement plan has five areas."
        for target in (self.repo / "provider.py", caller / "SPEC.md"):
            edit = {"type": "tool.execution_start",
                    "timestamp": (completed_at + timedelta(seconds=1)).isoformat(),
                    "data": {"toolName": "apply_patch", "arguments":
                             f"*** Begin Patch\n*** Update File: {target}\n+x\n*** End Patch"}}
            self.write_log(SESSION, [*self.log, terminal, edit])
            self.assertEqual(session_guard.pre_tool_use(payload)["permissionDecision"], "deny")
            recovered = subprocess.run(
                [sys.executable, "-B", str(ROOT / "gates" / "gate_runner.py"),
                 "delivery-audit", "--completion-summary", "--repo", str(self.repo), "--session", SESSION],
                cwd=caller, capture_output=True, text=True)
            self.assertEqual(recovered.returncode, 2, recovered.stdout)
        self.assertTrue(check.check_session(self.repo, SESSION, allow_withdrawal=False))
        self.assertEqual(self.command("--check").returncode, 2)

    def test_completion_summary_command_is_read_only_and_validates_paused_evidence(self):
        self.scoped()
        check.write_report(check.session_report_path(SESSION), self.report, create=True)
        self.assertEqual(self.command("--completion-summary").returncode, 2)
        paused = self.command("--pause", "handoff", "--reason", "Implementation handed to its owner.",
                              "--evidence", str(self.proof))
        self.assertEqual(paused.returncode, 0, paused.stderr)
        path = check.session_report_path(SESSION)
        before = path.read_bytes()
        summary = self.command("--completion-summary")
        self.assertEqual(summary.returncode, 0, summary.stderr)
        self.assertEqual(summary.stdout, paused.stdout)
        self.assertEqual(path.read_bytes(), before)
        foreign = self.command("--completion-summary", "--repo", str(ROOT))
        self.assertEqual(foreign.returncode, 2)
        self.assertEqual(path.read_bytes(), before)
        self.proof.write_text("changed evidence")
        invalid = self.command("--completion-summary")
        self.assertEqual(invalid.returncode, 2)
        self.assertNotIn("Architrave handoff: NOT DELIVERED", invalid.stdout)
        self.assertEqual(path.read_bytes(), before)

    def test_completed_cross_repository_handoff_can_prepare_new_owner_scope_without_resuming(self):
        caller = self.root / "caller"
        caller.mkdir()
        subprocess.check_call(["git", "-C", str(caller), "init", "--quiet"])
        (caller / "SPEC.md").write_text(SPEC)
        (caller / "provider.py").write_text("result = client.execute(request)\n")
        subprocess.check_call(["git", "-C", str(caller), "add", "."])
        subprocess.check_call([
            "git", "-C", str(caller), "-c", "user.name=Acceptance Test",
            "-c", "user.email=check@example.invalid", "-c", "commit.gpgsign=false",
            "commit", "--quiet", "-m", "New independent scope",
        ])
        self.scoped()
        check.write_report(check.session_report_path(SESSION), self.report, create=True)
        result = self.command("--pause", "handoff", "--reason", "Implementation handed to its owner.",
                              "--evidence", str(self.proof))
        self.assertEqual(result.returncode, 0, result.stderr)
        path = check.session_report_path(SESSION)
        paused_bytes = path.read_bytes()
        paused = check.read_json(path)
        completed_at = datetime.fromisoformat(paused["terminal"]["recorded_at"]) + timedelta(seconds=1)
        self.log.extend([
            {"type": "session.task_complete", "timestamp": completed_at.isoformat(),
             "data": {"summary": check.terminal_summary(paused)}},
            {"id": "new-owner", "type": "user.message",
             "timestamp": (completed_at + timedelta(seconds=1)).isoformat(),
             "data": {"content": "Implement the next independent repository task."}},
        ])
        self.write_log(SESSION, self.log)
        (self.repo / "provider.py").write_text("changed_by_another_writer()\n")
        malformed = copy.deepcopy(paused)
        malformed.pop("owner_requests")
        check.write_report(path, malformed)
        malformed_bytes = path.read_bytes()
        self.assertEqual(self.command("--prepare", "--repo", str(caller), "--reqs", "REQ-01",
                                      "--source", "provider.py", "--request", "new-owner").returncode, 2)
        self.assertEqual(path.read_bytes(), malformed_bytes)
        check.write_report(path, paused)
        denied = self.command("--prepare", "--repo", str(caller), "--reqs", "REQ-01",
                              "--source", "provider.py", "--request", "owner-event")
        self.assertEqual(denied.returncode, 2)
        self.assertEqual(path.read_bytes(), paused_bytes)
        prepared = self.command("--prepare", "--repo", str(caller), "--reqs", "REQ-01",
                                "--source", "provider.py", "--request", "new-owner")
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        self.assertEqual(path.with_name(
            f"architrave-delivery-{check.report_digest(paused)}.json").read_bytes(), paused_bytes)
        current = check.read_json(path)
        self.assertEqual(current["state"], "prepared")
        self.assertEqual(current["repo"], str(caller))
        self.assertEqual(current["owner_requests"][0]["event_id"], "new-owner")
        self.assertNotIn("terminal", current)
        self.assertTrue(check.check_session(caller, SESSION))

    def test_official_local_emulator_and_environment_selection_allowed(self):
        self.assertEqual(self.errors(), [])

    def test_flag_off_fake_or_saved_result_cannot_accept_real_request(self):
        for field, value in (("enabled", False), ("provider_invoked", False),
                             ("provider", "canned-provider"), ("result_mode", "readback"),
                             ("result_mode", "deterministic-test"), ("target", "cloud")):
            report = copy.deepcopy(self.report)
            report["observations"]["REQ-01"][field] = value
            self.assertTrue(self.errors(report), (field, value))

    def test_provider_and_result_must_match_same_run(self):
        self.report["observations"]["REQ-01"]["result_run_id"] = "previous-run"
        self.assertTrue(any("same run" in e for e in self.errors()))

    def test_changed_source_config_and_requirement_are_not_accepted(self):
        (self.repo / "provider.py").write_text("result = other.execute(request)\n")
        self.assertTrue(any("inventory changed" in e for e in self.errors()))
        (self.repo / "provider.py").write_text("result = client.execute(request)\n")
        self.config.write_text('{"provider":"other"}')
        self.assertTrue(any("configuration" in e for e in self.errors()))
        self.config.write_text('{"provider":"official-emulator","enabled":true}')
        (self.repo / "SPEC.md").write_text(SPEC.replace("Same-run provider and useful result", "UI responds"))
        self.assertTrue(any("requirements/acceptance changed" in e for e in self.errors()))

    def test_status_changes_do_not_invalidate_original_contract(self):
        (self.repo / "SPEC.md").write_text(SPEC.replace("| open | |", "| accepted | tool observation |"))
        self.assertEqual(self.errors(), [])

    def test_owner_provenance_not_transport_role(self):
        for patch in ({"source": "agent-child"}, {"transformedContent": "<cross_session_message>forwarded"},
                      {"content": "You have not yet marked the task as complete"}):
            entry = copy.deepcopy(self.log[0])
            entry["data"].update(patch)
            with self.assertRaises(ValueError):
                check.owner_reference("owner-event", [entry])

    def test_changed_owner_attachment_blocks(self):
        asset = self.root / "reference.svg"
        asset.write_text("<svg/>")
        self.log[0]["data"]["attachments"] = [{"type": "file", "path": str(asset)}]
        self.report["owner_requests"] = [check.owner_reference("owner-event", self.log)]
        self.write_log(SESSION, self.log)
        asset.write_text("<svg>different</svg>")
        self.assertTrue(any("owner reference" in e for e in self.errors()))

    def test_board_missing_or_unobserved_blocks(self):
        self.report["board"] = None
        self.assertTrue(any("board" in e for e in self.errors()))
        self.report["board"] = {"open_call_id": "open", "read_call_id": "missing"}
        self.assertTrue(any("board" in e for e in self.errors()))

    def test_explicit_failed_or_absent_canvas_is_not_displayed_success(self):
        self.tool("no-canvas", "open_canvas", {"canvasId": "browser"},
                  result="Host does not support a browser canvas", success=False)
        self.write_log(SESSION, self.log)
        self.report["board"] = {"unavailable": True, "displayed": False,
                                "reason": "Host rejected browser canvas", "tool_error_call_id": "no-canvas"}
        self.assertEqual(self.errors(), [])
        self.report["board"]["displayed"] = True
        self.assertTrue(any("displayed success" in e for e in self.errors()))
        self.report["board"] = {"unavailable": True, "displayed": False,
                                "reason": "No canvas tool in the host",
                                "basis": "host-tool-absent",
                                "capability_observation": "Host-advertised tool catalogue has no canvas API; reviewer must check."}
        self.assertEqual(self.errors(), [])

    def test_board_requires_exact_ids_and_early_observation(self):
        board = check.session_report_path(SESSION).parent / "program-board.html"
        board.write_text("<html>REQ-60</html>")
        for event in self.log:
            if event["type"] == "tool.execution_complete" and event["data"].get("toolCallId") == "read":
                event["data"]["result"] = {"content": "REQ-60"}
        narrowed = copy.deepcopy(self.report)
        narrowed["reqs"] = ["REQ-6"]
        self.assertTrue(check.board_errors(narrowed["board"], narrowed, self.log))
        board.write_text("<html>REQ-01</html>")
        for event in self.log:
            if event["type"] == "tool.execution_complete" and event["data"].get("toolCallId") == "read":
                event["data"]["result"] = {"content": "REQ-01"}
        self.log.append({"type": "tool.execution_start", "timestamp": "2026-01-01T10:00:30Z",
                         "data": {"toolName": "apply_patch", "arguments":
                                  f"*** Begin Patch\n*** Update File: {self.repo / 'provider.py'}\n+x\n*** End Patch"}})
        self.assertTrue(any("first recorded source edit" in e
                            for e in check.board_errors(self.report["board"], self.report, self.log)))

    def test_source_counts_not_visual_acceptance(self):
        expected = {"kind": "visual"}
        observed = {"kind": "visual", "outcome": "passed", "consumer": "document",
                    "width": 960, "rendered": False, "reference_compared": False, "coverage_checked": True}
        self.assertTrue(check.observation_errors(expected, observed))
        observed.update(rendered=True, reference_compared=True)
        self.assertEqual(check.observation_errors(expected, observed), [])

    def test_unclassified_or_missing_observation_blocks(self):
        self.report["expected"]["REQ-01"] = {"kind": "unclassified"}
        self.assertTrue(self.errors())
        self.report["observations"] = {}
        self.assertTrue(self.errors())

    def test_candidate_mentions_do_not_authorize(self):
        (self.repo / "provider.py").write_text("result = FakeProvider()\n")
        self.report["audit"] = audit.scan(self.repo, base=self.report["base_sha"], reqs=["REQ-01"])
        self.assertTrue(any("disposition" in e for e in self.errors()))
        key = self.report["audit"]["findings"][0]["id"]
        row = {"decision": "owner-requested", "purpose": "test data", "reachability": "unit",
               "effective_state": "candidate only", "reason": "explicit request", "owner_event_id": "invented"}
        self.report["dispositions"][key] = row
        self.assertTrue(any("permission" in e for e in self.errors()))
        row.update(decision="not-substitute", reason="This file is parser input, never a provider.")
        self.assertEqual(self.errors(), [])

    def test_review_must_bind_actual_report_digest(self):
        self.assertTrue(check.review_errors(self.report))
        sha = check.report_digest(self.report)
        self.report["review"] = {"session_id": REVIEWER, "sha256": sha}
        self.write_log(REVIEWER, [
            {"type": "subagent.selected", "data": {"agentName": "architrave:adversarial-judge"}},
            {"type": "assistant.turn_start", "data": {}},
            {"type": "session.task_complete", "data": {"summary": f"Verdict: PASS\nDelivery digest: {sha}\nUnit log specimen only."}},
        ])
        self.assertEqual(check.review_errors(self.report), [])
        self.report["observations"]["REQ-01"]["meaning"] += " changed"
        self.assertTrue(check.review_errors(self.report))

    def test_requirements_completion_requires_declared_delivery(self):
        (self.repo / "architrave.config.json").write_text(json.dumps({
            "kind": "knowledge", "build": "git diff --check", "test": "python checks.py"}))
        (self.repo / "SPEC.md").write_text(SPEC.replace("| open | |", "| accepted | observed |"))
        result = subprocess.run(
            [sys.executable, "-B", str(ROOT / "gates" / "gate_runner.py"),
             "requirements", "--done", "--repo", str(self.repo), "--delivery-session", SESSION],
            capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("delivery inspection blocked", result.stdout)

    def test_missing_failed_tools_and_forged_evidence_do_not_pass(self):
        self.report["observations"]["REQ-01"]["tool_call_id"] = "never-executed"
        self.assertTrue(self.errors())
        self.report["observations"]["REQ-01"]["tool_call_id"] = "check"
        self.proof.write_text("changed")
        self.assertTrue(self.errors())

    def test_amendment_needs_new_owner_and_preserves_old_scope(self):
        path = check.session_report_path(SESSION)
        check.write_report(path, self.report, create=True)
        before = path.read_bytes()
        command = [sys.executable, "-B", str(ROOT / "gates" / "gate_runner.py"),
                   "delivery-audit", "--amend", "--repo", str(self.repo), "--session", SESSION]
        repeated = subprocess.run([*command, "--request", "owner-event"], capture_output=True, text=True)
        self.assertEqual(repeated.returncode, 2)
        self.assertEqual(path.read_bytes(), before)
        self.log.append({"id": "owner-correction", "timestamp": "2026-01-02T10:00:00Z",
                         "type": "user.message", "data": {"content": "Revise the target to a source-only check."}})
        self.write_log(SESSION, self.log)
        (self.repo / "SPEC.md").write_text(SPEC.replace("Same-run provider and useful result", "Source-level check"))
        changed = subprocess.run([*command, "--request", "owner-correction"], capture_output=True, text=True)
        self.assertEqual(changed.returncode, 0, changed.stderr)
        updated = check.read_json(path)
        self.assertEqual(updated["history"][0]["requirements"], self.report["original_requirements"])
        self.assertEqual(updated["state"], "prepared")
        self.assertEqual(updated["observations"], {})
        self.assertIsNone(updated["review"])

    def test_prior_completion_cannot_retire_unreviewed_work(self):
        self.report["sealed_at"] = "2026-01-01T10:00:30Z"
        terminal = {"type": "session.task_complete", "timestamp": "2026-01-01T10:02:00Z",
                    "data": {"summary": "Older task result"}}
        self.assertFalse(check.host_completed(self.report, [*self.log, terminal]))
        self.report["state"] = "prepared"
        self.assertFalse(check.host_completed(self.report, [*self.log, terminal]))

    def test_older_tool_result_and_missing_visual_reference_block(self):
        self.log[0]["timestamp"] = "2026-01-02T10:00:00Z"
        self.report["owner_requests"] = [check.owner_reference("owner-event", self.log)]
        self.write_log(SESSION, self.log)
        self.assertTrue(any("earlier tool" in e for e in self.errors()))
        self.report["expected"]["REQ-01"] = {"kind": "visual", "reference_required": True}
        self.report["observations"]["REQ-01"].update(
            kind="visual", consumer="document", width=960, rendered=True,
            reference_compared=True, coverage_checked=True)
        self.assertTrue(any("visual reference" in e for e in self.errors()))

    def test_unrelated_observation_session_and_unlinked_artifact_block(self):
        self.report["observations"]["REQ-01"]["session_id"] = REVIEWER
        self.assertTrue(any("recorded child" in e for e in self.errors()))
        self.report["observations"]["REQ-01"].pop("session_id")
        for event in self.log:
            if event["type"] == "tool.execution_complete" and event["data"].get("toolCallId") == "check":
                event["data"]["result"] = {"content": str(self.proof)}
        self.write_log(SESSION, self.log)
        self.assertTrue(any("absent from the cited tool" in e for e in self.errors()))

    def test_owner_withdrawal_is_retained_and_not_delivery_acceptance(self):
        path = check.session_report_path(SESSION)
        check.write_report(path, self.report, create=True)
        self.log.append({"id": "withdraw", "timestamp": "2026-01-02T10:00:00Z",
                         "type": "user.message", "data": {"content": "Stop this scope."}})
        self.write_log(SESSION, self.log)
        result = subprocess.run(
            [sys.executable, "-B", str(ROOT / "gates" / "gate_runner.py"),
             "delivery-audit", "--withdraw", "--repo", str(self.repo), "--session", SESSION,
             "--request", "withdraw", "--reason", "Stop this scope."],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(check.read_json(path)["state"], "withdrawn")
        self.assertEqual(check.check_session(self.repo, SESSION), [])
        self.assertTrue(check.check_session(self.repo, SESSION, allow_withdrawal=False))
        (self.repo / "provider.py").write_text("new_work()\n")
        self.assertTrue(check.check_session(self.repo, SESSION))

    def test_new_requirements_change_source_binding_even_outside_selected_scope(self):
        before = self.report["audit"]["source_sha256"]
        (self.repo / "SPEC.md").write_text(SPEC.replace(
            "\n## Handoff", "| REQ-02 | New task | New behavior | owner | open | |\n\n## Handoff"))
        # Keep the new row in the same requirements table.
        text = (self.repo / "SPEC.md").read_text().replace("\n\n| REQ-02", "\n| REQ-02")
        (self.repo / "SPEC.md").write_text(text)
        self.assertNotEqual(before, audit.scan(self.repo, base=self.report["base_sha"], reqs=["REQ-01"])["source_sha256"])

    def test_completed_scope_rechecks_freshness_and_subdirectory_root(self):
        (self.repo / "SPEC.md").write_text(SPEC.replace("| open | |", "| accepted | observed |"))
        sha = check.report_digest(self.report)
        self.report["review"] = {"session_id": REVIEWER, "sha256": sha}
        self.write_log(REVIEWER, [
            {"type": "subagent.selected", "data": {"agentName": "architrave:adversarial-judge"}},
            {"type": "assistant.turn_start", "data": {}},
            {"type": "session.task_complete", "data": {"summary": f"Verdict: PASS\nDelivery digest: {sha}"}},
        ])
        self.log.append({"type": "session.task_complete", "timestamp": "2026-01-01T10:02:00Z",
                         "data": {"summary": "Completed the declared scope."}})
        self.write_log(SESSION, self.log)
        check.write_report(check.session_report_path(SESSION), self.report, create=True)
        subdir = self.repo / "subdir"
        subdir.mkdir()
        self.assertEqual(check.check_session(subdir, SESSION), [])
        self.assertEqual(self.command("--seal").returncode, 2)
        path = check.session_report_path(SESSION)
        before = path.read_bytes()
        recovered = self.command("--completion-summary")
        self.assertEqual(recovered.returncode, 0, recovered.stderr)
        self.assertTrue(recovered.stdout.startswith(
            "Read-only follow-up (no new delivery acceptance): "), recovered.stdout)
        self.assertEqual(check.check_session(
            subdir, SESSION, completion_hook=True, completion_summary=recovered.stdout.strip()), [])
        self.assertEqual(path.read_bytes(), before)
        (self.repo / "provider.py").write_text("result = different.execute(request)\n")
        self.assertTrue(check.check_session(subdir, SESSION))
        self.assertTrue(check.check_session(subdir, SESSION, completion_hook=True))
        self.assertEqual(check.check_session(
            subdir, SESSION, completion_hook=True,
            completion_summary="Read-only follow-up (no new delivery acceptance): Here is the explanation."), [])
        self.assertEqual(self.command("--completion-summary").returncode, 0)
        caller = self.root / "caller"
        caller.mkdir()
        subprocess.check_call(["git", "-C", str(caller), "init", "--quiet"])
        summary = "Read-only follow-up (no new delivery acceptance): Here is the explanation."
        self.assertEqual(check.check_session(
            caller, SESSION, completion_hook=True, completion_summary=summary), [])
        self.assertEqual(check.check_session(caller, SESSION), ["delivery repository identity differs"])
        for root in (self.repo, subdir, caller):
            for ordinary in (
                "The improvement plan has five areas.",
                "Read-only follow-up (no new delivery acceptance): Here is the explanation.",
            ):
                payload = {"session_id": SESSION, "cwd": str(root), "tool_name": "task_complete",
                           "tool_input": json.dumps({"summary": ordinary})}
                result = subprocess.run(
                    [sys.executable, "-B", str(ROOT / "gates" / "session_guard.py"), "pre-tool-use"],
                    input=json.dumps(payload), cwd=root, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout), {})
        self.assertTrue(check.check_session(
            subdir, SESSION, completion_hook=True, allow_withdrawal=False, completion_summary=summary))
        plain = self.root / "plain-folder"
        plain.mkdir()
        self.assertEqual(check.check_session(
            plain, SESSION, completion_hook=True, completion_summary="The improvement plan has five areas."), [])
        self.assertEqual(check.check_session(plain, SESSION, completion_hook=True,
                                             allow_withdrawal=False, completion_summary=summary),
                         ["delivery repository identity differs"])
        absolute_edit = {
            "type": "tool.execution_start", "timestamp": "2026-01-01T10:03:00Z",
            "data": {"toolName": "apply_patch", "arguments":
                     f"*** Begin Patch\n*** Update File: {caller / 'SPEC.md'}\n+x\n*** End Patch"},
        }
        for log in (self.log, [*self.log, absolute_edit]):
            self.write_log(SESSION, log)
            with mock_patch.dict(os.environ, {"GIT_DIR": str(self.root / "missing-gitdir")}):
                errors = check.check_session(
                    caller, SESSION, completion_hook=True, completion_summary=summary)
                self.assertEqual(len(errors), 1, errors)
                self.assertTrue(errors[0].startswith("delivery inspection blocked:"), errors)
        broken = self.root / "broken-caller"
        broken.mkdir()
        marker = broken / ".git"
        marker.write_text(f"gitdir: {self.root / 'missing-gitdir'}\n")
        for log in (self.log, [*self.log, {
            **absolute_edit,
            "data": {"toolName": "apply_patch", "arguments":
                     f"*** Begin Patch\n*** Update File: {broken / 'SPEC.md'}\n+x\n*** End Patch"},
        }]):
            self.write_log(SESSION, log)
            errors = check.check_session(
                broken, SESSION, completion_hook=True, completion_summary=summary)
            self.assertEqual(len(errors), 1, errors)
            self.assertTrue(errors[0].startswith("delivery inspection blocked:"), errors)
        marker.unlink()
        marker.mkdir()
        errors = check.check_session(
            broken, SESSION, completion_hook=True, completion_summary=summary)
        self.assertEqual(len(errors), 1, errors)
        self.assertTrue(errors[0].startswith("delivery inspection blocked:"), errors)
        self.write_log(SESSION, self.log)
        outside = self.root / "outside.py"
        for patch in (f"*** Update File: {outside}\n*** Move to: {self.repo / 'moved.py'}",
                      "*** Update File: ..\\README.md", "*** Add File: notes.py"):
            moved = {"type": "tool.execution_start", "timestamp": "2026-01-01T10:03:00Z",
                     "data": {"toolName": "apply_patch",
                              "arguments": f"*** Begin Patch\n{patch}\n+x\n*** End Patch"}}
            self.write_log(SESSION, [*self.log, moved])
            for root in (caller, plain):
                self.assertEqual(check.check_session(
                    root, SESSION, completion_hook=True, completion_summary=summary),
                    ["new source edits after host completion require a new owner-bound scope"])
        self.write_log(SESSION, self.log)
        for invalid in (None, "", "   "):
            self.assertTrue(check.check_session(
                caller, SESSION, completion_hook=True, completion_summary=invalid))
        self.assertEqual(path.read_bytes(), before)
        caller_edit = {"type": "tool.execution_start", "timestamp": "2026-01-01T10:03:00Z",
                       "data": {"toolName": "apply_patch", "arguments":
                                f"*** Begin Patch\n*** Update File: {caller / 'SPEC.md'}\n+x\n*** End Patch"}}
        self.write_log(SESSION, [*self.log, caller_edit])
        self.assertTrue(check.check_session(
            caller, SESSION, completion_hook=True, completion_summary=summary))
        recovered = subprocess.run(
            [sys.executable, "-B", str(ROOT / "gates" / "gate_runner.py"),
             "delivery-audit", "--completion-summary", "--repo", str(self.repo), "--session", SESSION],
            cwd=caller, capture_output=True, text=True)
        self.assertEqual(recovered.returncode, 2, recovered.stdout)
        self.write_log(SESSION, self.log)
        self.log.append({"type": "tool.execution_start", "timestamp": "2026-01-01T10:03:00Z",
                         "data": {"toolName": "apply_patch", "arguments":
                                  f"*** Begin Patch\n*** Update File: {self.repo / 'provider.py'}\n+x\n*** End Patch"}})
        self.write_log(SESSION, self.log)
        self.assertTrue(check.check_session(
            subdir, SESSION, completion_hook=True,
            completion_summary="Read-only follow-up (no new delivery acceptance): Claimed read-only despite edits."))
        self.assertTrue(check.check_session(
            caller, SESSION, completion_hook=True, completion_summary=summary))
        self.assertEqual(self.command("--completion-summary").returncode, 2)

    def test_amend_cannot_silently_drop_requirement(self):
        expanded = SPEC.replace("| owner | open | |\n", "| owner | open | |\n"
                               "| REQ-02 | Another behavior | Required result | owner | open | |\n")
        (self.repo / "SPEC.md").write_text(expanded)
        self.report["reqs"] = ["REQ-01", "REQ-02"]
        self.report["original_requirements"] = audit.requirement_contract(expanded, self.report["reqs"])
        check.write_report(check.session_report_path(SESSION), self.report, create=True)
        self.log.append({"id": "drop-request", "timestamp": "2026-01-02T10:00:00Z",
                         "type": "user.message", "data": {"content": "Withdraw REQ-02."}})
        self.write_log(SESSION, self.log)
        command = [sys.executable, "-B", str(ROOT / "gates" / "gate_runner.py"),
                   "delivery-audit", "--amend", "--repo", str(self.repo), "--session", SESSION,
                   "--request", "drop-request", "--reqs", "REQ-01"]
        refused = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(refused.returncode, 2)
        self.assertIn("--drop", refused.stderr)
        admitted = subprocess.run([*command, "--drop", "REQ-02"], capture_output=True, text=True)
        self.assertEqual(admitted.returncode, 0, admitted.stderr)
        self.assertIn("dropped=['REQ-02']", admitted.stdout)
        self.assertIn("Delivery digest:", admitted.stdout)

    def test_multiple_missing_proofs_are_all_reported(self):
        expanded = SPEC.replace("| owner | open | |\n", "| owner | open | |\n"
                               "| REQ-02 | Another behavior | Required result | owner | open | |\n")
        (self.repo / "SPEC.md").write_text(expanded)
        self.report["reqs"] = ["REQ-01", "REQ-02"]
        self.report["audit"] = audit.scan(self.repo, base=self.report["base_sha"], reqs=self.report["reqs"])
        self.report["original_requirements"] = self.report["audit"]["requirements"]
        self.report["expected"]["REQ-02"] = {"kind": "source"}
        self.report["observations"]["REQ-02"] = dict(self.observation(), kind="source")
        for row in self.report["observations"].values():
            row["proof"] = None
        errors = self.errors()
        self.assertTrue(any(e.startswith("REQ-01: proof inspection") for e in errors))
        self.assertTrue(any(e.startswith("REQ-02: proof inspection") for e in errors))


if __name__ == "__main__":
    unittest.main()
