#!/usr/bin/env python3
"""Execute audit counterexamples, not a grader of agent/domain correctness."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
from threading import Event
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "benchmarks/fixtures/domain-audit"
SPEC = importlib.util.spec_from_file_location("domain_audit_review", FIXTURE / "review.py")
assert SPEC and SPEC.loader
REVIEW = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = REVIEW
SPEC.loader.exec_module(REVIEW)


class AuditSubstrate(unittest.TestCase):
    def test_completion_cannot_substitute_for_obligations_counterexample(self):
        review = REVIEW.Review(frozenset({"safety"}), execution="done")
        self.assertIsNone(review.begin_approval(True))
        self.assertTrue(review.approve_from_workflow(True))
        self.assertEqual(review.status, "approved")
        self.assertFalse(review.required.issubset(review.evidence))

    def test_positive_path_and_actor_boundary(self):
        review = REVIEW.Review(frozenset({"safety"}), {"safety"})
        self.assertIsNone(review.begin_approval(False))
        version = review.begin_approval(True)
        self.assertIsNotNone(version)
        self.assertTrue(review.finish_approval(version))
        self.assertEqual(review.status, "approved")

    def test_revocation_races_real_approval_path_counterexample(self):
        review = REVIEW.Review(frozenset({"safety"}), {"safety"})
        checked, revoked = Event(), Event()

        def approve():
            version = review.begin_approval(True)
            self.assertIsNotNone(version)
            checked.set()
            self.assertTrue(revoked.wait(5), "revocation did not execute")
            return version, review.finish_approval(version)

        def revoke():
            self.assertTrue(checked.wait(5), "approval did not reach evidence check")
            review.revoke("safety")
            revoked.set()

        with ThreadPoolExecutor(max_workers=2) as pool:
            approval, revocation = pool.submit(approve), pool.submit(revoke)
            revocation.result(timeout=10)
            version, accepted = approval.result(timeout=10)
        self.assertNotEqual(review.version, version)
        self.assertTrue(accepted)
        self.assertEqual(review.status, "approved")
        self.assertFalse(review.required.issubset(review.evidence))

    @unittest.skipUnless(shutil.which("node"), "Node unavailable: TypeScript execution not qualified")
    def test_functional_typescript_and_external_semantics(self):
        script = """
import assert from 'node:assert/strict';
const {canApprove, workflowState, legacyApproval} = await import(process.argv[1]);
assert.equal(canApprove(['safety'], new Set(), true), false);
assert.equal(canApprove(['safety'], new Set(['safety']), false), false);
assert.equal(canApprove(['safety'], new Set(['safety']), true), true);
assert.deepEqual(workflowState('done'), {kind:'execution', state:'completed'});
assert.deepEqual(workflowState('vendor-new'), {kind:'unknown', sourceStatus:'vendor-new'});
assert.equal(legacyApproval('vendor-new'), 'approved');
assert.equal(legacyApproval('done'), 'approved');
"""
        result = subprocess.run(
            [shutil.which("node"), "--experimental-strip-types", "--input-type=module",
             "-e", script, (FIXTURE / "status.ts").as_uri()],
            text=True, capture_output=True, timeout=30, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
