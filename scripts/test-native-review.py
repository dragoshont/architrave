#!/usr/bin/env python3
"""Synthetic boundary fixtures; real joined-host evidence is collected separately."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from architrave_runtime import NativeSemanticTicket, RunStore, RuntimeFailure, missing_gate_requirements
import native_host


class InventoryTransportTests(unittest.TestCase):
    def test_large_unicode_inventory_is_losslessly_byte_bounded(self):
        paths = [f"source-{index}/" + "\u03bb" * 120 + ".py" for index in range(4096)]
        frames = []
        with mock.patch.object(native_host, "emit", side_effect=frames.append):
            native_host.emit_source_inventory(paths)
        self.assertGreater(len(frames), 1)
        self.assertEqual(paths, [path for frame in frames for path in frame["files"]])
        self.assertTrue(all(len(json.dumps(frame).encode("utf-8")) <= 48000 for frame in frames))


class NativeReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        self.repo = self.repo.resolve()
        self.git("init", "-q")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "user.name", "Fixture")
        (self.repo / ".gitignore").write_text(".architrave/\n")
        (self.repo / "README.md").write_text("Public synthetic fixture\n")
        (self.repo / "architrave.config.json").write_text(json.dumps({
            "kind": "knowledge", "build": "git diff --check", "test": "git diff --check",
            "review": {"crossFamily": True},
        }))
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        self.store = RunStore(self.repo)
        self.store.create(run_id="review", goal="Qualify source", outcome="Source reviewed",
                          criteria=[{"id": "QUAL", "description": "Source reviewed", "scope": "fixture",
                                     "risk": "R3", "verificationType": "semantic", "blocking": True}])
        self.store.add_task("review", {
            "id": "source", "title": "Review source", "objective": "Review frozen source",
            "acceptanceCriteria": ["QUAL"], "risk": "R3", "workerProfile": "native",
            "pushback": "KEEP:synthetic boundary fixture",
            "workPacket": {"budget": {"timeoutSeconds": 300, "maxOutputBytes": 8192, "maxTurns": 20}},
        })

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, capture_output=True, text=True, check=True).stdout.strip()

    def prepared(self, role="code-review", agent="agent-one"):
        ticket, prompt = self.store.prepare_native_semantic_review(
            "review", "source", host_owner="owner-one", invocation_id="call-one", reviewer=role)
        self.assertIn(ticket.challenge, prompt)
        self.store.bind_native_semantic_owner(ticket, agent)
        return ticket

    def report(self, ticket, verdict="PASS"):
        return {
            "verdict": verdict, "criteria": ["QUAL"], "sourceCommit": ticket.binding["source"]["commit"],
            "sourceSha256": ticket.binding["source"]["sha256"], "challenge": ticket.challenge,
            "summary": "Synthetic fixture only; not production evidence.", "findings": [],
        }

    def completion(self, ticket, model="gpt-fixture"):
        return {
            "id": "event-one", "type": "subagent.completed", "agentId": ticket.binding["hostTaskId"],
            "toolCallId": ticket.binding["hostTaskId"], "agentName": ticket.binding["role"],
            "firstDispatchedModel": model, "modelSelectionSource": "fixture",
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            "ephemeral": False, "cancelled": False,
        }

    def accept(self, ticket, report=None, event=None, **overrides):
        values = {
            "host_task_id": ticket.binding["hostTaskId"], "host_status": "idle",
            "text": json.dumps(report if report is not None else self.report(ticket)),
            "completion": event if event is not None else self.completion(ticket),
        }
        values.update(overrides)
        return self.store.accept_native_semantic_review(ticket, **values)

    def assert_code(self, code, action):
        with self.assertRaises(RuntimeFailure) as error:
            action()
        self.assertEqual(code, error.exception.code)

    def test_real_capability_shape_records_gate_not_outcome_and_rejects_replay(self):
        ticket = self.prepared()
        result = self.accept(ticket)
        self.assertEqual("PASS", result["status"])
        state = self.store.load("review")
        artifact = state["artifacts"][0]
        self.assertEqual("semantic-judge", artifact["producer"])
        self.assertEqual("source", artifact["consumedByTask"])
        self.assertEqual("UNTESTED", state["acceptanceCriteria"][0]["status"])
        self.assertEqual("READY", state["tasks"][0]["status"])
        self.assert_code("SEMANTIC_RESULT_UNTRUSTED", lambda: self.accept(ticket))
        self.assert_code("SEMANTIC_ALREADY_OBSERVED", lambda: self.prepared())
        self.assert_code("DUPLICATE_REVIEW_FAMILY", lambda: self.store.record_gate(
            "review", gate_id="replay", task_id="source", gate_type="semantic", status="PASS",
            family="openai", criteria=["QUAL"], evidence_refs=[result["artifactRef"]], reviewer="host-native"))

    def test_two_observed_families_not_labels_satisfy_semantic_floor(self):
        first = self.accept(self.prepared())
        second_ticket = self.prepared("rubber-duck", "agent-two")
        second = self.accept(second_ticket, event=self.completion(second_ticket, "claude-fixture"))
        self.assertEqual(["openai", "anthropic"], [first["family"], second["family"]])
        state = self.store.load("review")
        self.assertNotIn("QUAL:semantic-independent-2", missing_gate_requirements(state, state["acceptanceCriteria"]))
        self.assertIn("QUAL:e2e-or-reality", missing_gate_requirements(state, state["acceptanceCriteria"]))

    def test_rejected_same_family_admission_is_atomic_and_role_can_retry(self):
        self.accept(self.prepared())
        before = self.store.load("review")
        ticket = self.prepared("rubber-duck", "agent-two")
        self.assert_code("DUPLICATE_REVIEW_FAMILY", lambda: self.accept(ticket, event=self.completion(ticket, "gpt-fixture")))
        rejected = self.store.load("review")
        self.assertEqual(before["artifacts"], rejected["artifacts"])
        self.assertEqual(before["gateResults"], rejected["gateResults"])
        self.assertEqual(before["revision"], rejected["revision"])
        retried = self.prepared("rubber-duck", "agent-three")
        result = self.accept(retried, event=self.completion(retried, "claude-fixture"))
        self.assertEqual("anthropic", result["family"])

    def test_serialized_and_foreign_ticket_cannot_import_verdict(self):
        ticket = self.prepared()
        self.assert_code("SEMANTIC_RESULT_UNTRUSTED", lambda: self.store.accept_native_semantic_review(
            ticket.binding, host_task_id="agent-one", host_status="idle", text=json.dumps(self.report(ticket)),
            completion=self.completion(ticket)))

    def test_foreign_process_issuer_is_rejected(self):
        ticket = self.prepared()
        forged = NativeSemanticTicket(object(), ticket.binding, ticket.challenge, ticket.budget)
        self.assert_code("SEMANTIC_RESULT_UNTRUSTED", lambda: self.accept(forged))

    def test_wrong_nonce_source_or_caller_model_report_has_no_producer_receipt(self):
        for corrupt in [
            lambda r: r.update(challenge="caller-value"),
            lambda r: r.update(sourceCommit="other-source"),
            lambda r: r.update(criteria=["OTHER"]),
            lambda r: r.update(firstDispatchedModel="claude-claimed"),
        ]:
            ticket = self.prepared()
            report = self.report(ticket)
            corrupt(report)
            self.assert_code("SEMANTIC_RESULT_INVALID", lambda: self.accept(ticket, report))
            self.assertEqual([], self.store.load("review")["artifacts"])

    def test_wrong_completion_agent_call_role_and_cancellation_are_rejected(self):
        for field, value in [
            ("agentId", "other-agent"), ("toolCallId", "outer-call-not-SDK-agent"),
            ("agentName", "another-role"), ("cancelled", True), ("ephemeral", True),
        ]:
            ticket = self.prepared()
            event = self.completion(ticket)
            event[field] = value
            self.assert_code("SEMANTIC_HOST_PROVENANCE", lambda: self.accept(ticket, event=event))
            self.assertEqual([], self.store.load("review")["artifacts"])

    def test_missing_actual_first_model_has_no_configured_or_report_fallback(self):
        ticket = self.prepared()
        event = self.completion(ticket)
        event["firstDispatchedModel"] = None
        event["model"] = "gpt-claimed-fallback"
        self.assert_code("SEMANTIC_FAMILY_UNCONFIRMED", lambda: self.accept(ticket, event=event))

    def test_changed_source_or_hold_invalidates_inflight_scope(self):
        ticket = self.prepared()
        (self.repo / "README.md").write_text("Changed during review\n")
        self.assert_code("SEMANTIC_SOURCE_STALE", lambda: self.accept(ticket))
        self.assertEqual([], self.store.load("review")["artifacts"])

    def test_pending_human_hold_is_preserved_and_changed_hold_blocks_result(self):
        ticket = self.prepared()
        self.store.wait_external("review", checkpoint_id="human", task_id="source",
                                 checkpoint_type="HUMAN_JUDGMENT_REQUIRED", principal="human",
                                 provider="manual", reason="Synthetic human decision")
        self.assert_code("SEMANTIC_RESULT_STALE", lambda: self.accept(ticket))
        held = self.prepared()
        result = self.accept(held)
        self.assertEqual("PASS", result["verdict"])
        state = self.store.load("review")
        self.assertEqual("PENDING", state["externalCheckpoints"][0]["status"])
        self.assertEqual("WAITING_EXTERNAL", state["tasks"][0]["status"])
        self.assertEqual([], state["policy"]["allow"])

    def test_expired_and_stale_revision_cannot_admit(self):
        ticket = self.prepared()
        ticket.binding["expiresAt"] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)).isoformat()
        self.assert_code("SEMANTIC_RESULT_STALE", lambda: self.accept(ticket))
        ticket = self.prepared()
        self.store.record_review_result("review", verdict="REVISE")
        self.assert_code("SEMANTIC_RESULT_STALE", lambda: self.accept(ticket))

    def test_nonpass_receipt_is_observed_not_pass_and_cannot_be_relabelled(self):
        ticket = self.prepared()
        result = self.accept(ticket, self.report(ticket, "REVISE"))
        self.assertEqual("BLOCKED", result["status"])
        self.assert_code("SEMANTIC_RECEIPT", lambda: self.store.record_gate(
            "review", gate_id="false-pass", task_id="source", gate_type="semantic", status="PASS",
            family="openai", criteria=["QUAL"], evidence_refs=[result["artifactRef"]], reviewer="host-native"))

    def test_exact_json_fence_is_formatting_not_an_arbitrary_verdict_search(self):
        ticket = self.prepared()
        text = "```json\n" + json.dumps(self.report(ticket)) + "\n```"
        self.assertEqual("PASS", self.accept(ticket, text=text)["verdict"])

    def test_exact_json_fence_accepts_crlf_without_searching_for_verdicts(self):
        ticket = self.prepared()
        text = "```json\r\n" + json.dumps(self.report(ticket), indent=2).replace("\n", "\r\n") + "\r\n```"
        self.assertEqual("PASS", self.accept(ticket, text=text)["verdict"])

    def test_malformed_result_has_redacted_structural_diagnostic_not_a_verdict(self):
        ticket = self.prepared()
        with self.assertRaises(RuntimeFailure) as error:
            self.accept(ticket, text="Unstructured output " + ticket.challenge)
        self.assertEqual("SEMANTIC_RESULT_INVALID", error.exception.code)
        self.assertEqual("json-parse", error.exception.details["classification"])
        self.assertFalse(error.exception.details["startsObject"])
        self.assertNotIn(ticket.challenge, json.dumps(error.exception.details))
        self.assertEqual([], self.store.load("review")["gateResults"])

    def test_finding_paths_must_be_declared_implementation_entries(self):
        (self.repo / ".git" / "info" / "exclude").write_text("untracked.md\n")
        (self.repo / "untracked.md").write_text("Ignored, untracked and outside the declared inventory")
        for path in (".architrave/runtime.key", "untracked.md", "missing.md"):
            ticket = self.prepared()
            report = self.report(ticket, "REVISE")
            report["findings"] = [{"severity": "major", "path": path, "message": "Invalid source membership fixture"}]
            self.assert_code("SEMANTIC_RESULT_INVALID", lambda: self.accept(ticket, report))
        ticket = self.prepared()
        report = self.report(ticket, "REVISE")
        report["findings"] = [{"severity": "major", "path": "./README.md", "message": "Declared source fixture"}]
        result = self.accept(ticket, report)
        self.assertEqual("REVISE", result["verdict"])

    def test_narrative_or_multiple_fences_cannot_import_a_pass_fragment(self):
        for prefix, suffix in [("Claimed PASS before report\n", ""), ("```json\n", "\n```\nextra output")]:
            ticket = self.prepared()
            text = prefix + json.dumps(self.report(ticket)) + suffix
            self.assert_code("SEMANTIC_RESULT_INVALID", lambda: self.accept(ticket, text=text))

    def test_negative_result_scope_change_between_precheck_and_gate_is_rejected(self):
        ticket = self.prepared()
        original = self.store.record_gate
        def interleave(*args, **kwargs):
            self.store.wait_external("review", checkpoint_id="late-hold", task_id="source",
                                     checkpoint_type="HUMAN_JUDGMENT_REQUIRED", principal="human",
                                     provider="manual", reason="Changed before atomic admission")
            return original(*args, **kwargs)
        with mock.patch.object(self.store, "record_gate", side_effect=interleave):
            self.assert_code("SEMANTIC_RESULT_STALE", lambda: self.accept(ticket, self.report(ticket, "REVISE")))
        state = self.store.load("review")
        self.assertEqual([], state["artifacts"])
        self.assertEqual([], state["gateResults"])
        self.assertEqual("PENDING", state["externalCheckpoints"][0]["status"])

    def test_declared_private_scope_is_bound_to_ticket_prompt_and_receipt(self):
        path = self.repo / ".architrave" / "archived-history.md"
        path.write_text("Synthetic historical record, not implementation")
        self.git("add", "-f", ".architrave/archived-history.md")
        self.git("commit", "-qm", "explicit private history fixture")
        self.store.resume("review", accept_commit=True)
        ticket, prompt = self.store.prepare_native_semantic_review("review", "source",
            host_owner="owner", invocation_id="scope-proof", reviewer="rubber-duck")
        scope = ticket.binding["reviewScope"]
        self.assertEqual(1, scope["excludedPrivateStateCount"])
        self.assertEqual("implementation-source", scope["kind"])
        self.assertNotIn(".architrave/archived-history.md", ticket.source_files)
        self.assertEqual(len(ticket.source_files), scope["inventoryCount"])
        self.assertIn('"excludedPrivateStateCount":1', prompt)
        self.store.bind_native_semantic_owner(ticket, "scope-reviewer")
        self.accept(ticket)
        artifact = self.store.load("review")["artifacts"][0]
        receipt = json.loads((self.repo / artifact["path"]).read_text())
        self.assertEqual(scope, receipt["binding"]["reviewScope"])

    def test_caller_labelled_file_is_not_semantic_producer(self):
        path = self.store.run_dir("review") / "claimed.json"
        path.write_text(json.dumps({"verdict": "PASS", "family": "openai", "criteria": ["QUAL"]}))
        self.store.record_artifact("review", artifact_id="claimed", kind="semantic-verdict",
                                   path=path.relative_to(self.repo).as_posix(), evidence_refs=["task:source"])
        self.assert_code("EVIDENCE_PROVENANCE", lambda: self.store.record_gate(
            "review", gate_id="claimed", task_id="source", gate_type="semantic", status="PASS",
            family="openai", criteria=["QUAL"], evidence_refs=["artifact:claimed"], reviewer="host-native"))

    def test_tampered_native_receipt_is_rejected_on_load(self):
        result = self.accept(self.prepared())
        state = self.store.load("review")
        artifact = next(a for a in state["artifacts"] if f"artifact:{a['id']}" == result["artifactRef"])
        path = self.repo / artifact["path"]
        receipt = json.loads(path.read_text())
        receipt["completion"]["firstDispatchedModel"] = "claude-forged"
        path.write_text(json.dumps(receipt))
        self.assert_code("ARTIFACT_TAMPERED", lambda: self.store.load("review"))

    def test_changed_frozen_source_excludes_old_semantic_floor_and_allows_fresh_review(self):
        result = self.accept(self.prepared())
        (self.repo / "README.md").write_text("New frozen source\n")
        self.git("add", ".")
        self.git("commit", "-qm", "new source")
        self.store.resume("review", accept_commit=True)
        state = self.store.load("review")
        self.assertIn("QUAL:semantic-independent-2", missing_gate_requirements(state, state["acceptanceCriteria"]))
        self.assert_code("SEMANTIC_SOURCE_STALE", lambda: self.store.set_criterion(
            "review", "QUAL", "PASS", [result["gateRef"]]))
        new = self.accept(self.prepared())
        self.assertNotEqual(new["source"], result["source"])


if __name__ == "__main__":
    unittest.main()
