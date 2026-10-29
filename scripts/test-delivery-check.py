#!/usr/bin/env python3
"""Acceptance-decision checks on protocol data, not provider/runtime acceptance."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

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
        (self.repo / "provider.py").write_text("result = different.execute(request)\n")
        self.assertTrue(any("prepare a new" in e for e in check.check_session(subdir, SESSION)))

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
