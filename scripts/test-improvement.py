#!/usr/bin/env python3
"""Focused, dependency-free improvement/learning fixtures; scratch stays in repo."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
import improvement
from validate_learning import validate


def python_command(code: str) -> str:
    argv = [sys.executable, "-c", code]
    return subprocess.list2cmdline(argv) if os.name == "nt" else shlex.join(argv)


class LearningFixture(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / (".learning-fixture-" + uuid.uuid4().hex)
        self.learning = self.root / ".architrave/learning"
        self.learning.mkdir(parents=True)
        (self.learning / "repo-profile.md").write_text("# Profile\n", encoding="utf-8")
        self.lessons("| L1 | Use the quick gate. | test | 2 | yes | docs | candidate | python check.py | |")
        (self.root / "check.py").write_text("print('checked')\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.root)

    def lessons(self, *rows):
        (self.learning / "repo-lessons.md").write_text(
            "# Lessons\n\n| ID | Lesson | Evidence | Occurrences | Validated | Proposed Target | Status | Executable Check | prose-justification |\n"
            "|---|---|---|---:|---|---|---|---|---|\n" + "\n".join(rows) + "\n", encoding="utf-8")

    def cli(self, *args, code=0, launcher=None):
        argv = [sys.executable, str(ROOT / "harness/improvement.py")]
        if launcher:
            argv = (["pwsh", "-NoProfile", "-File", str(ROOT / f"harness/{launcher}.ps1")]
                    if os.name == "nt" else ["bash", str(ROOT / f"harness/{launcher}.sh")])
        result = subprocess.run([*argv, *args, "--repo", str(self.root)], capture_output=True, text=True)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    def propose(self, kind="test", target="check.py", identifier="P1", before=None, after=None):
        return self.cli("propose", "--id", identifier, "--source-lesson", "L1", "--kind", kind,
                        "--target", target, "--summary", "Prevent repeated failure",
                        "--before-command", before or python_command("print('before'); raise SystemExit(7)"),
                        "--after-command", after or python_command("print('after')"))

    def checks(self, identifier="P1", before_code=1, after_code=0):
        self.cli("check", identifier, "--phase", "before", code=before_code)
        self.cli("check", identifier, "--phase", "after", code=after_code)

    def rows(self):
        return improvement.load_proposals(self.root)


class ImprovementTests(LearningFixture):
    def test_propose_check_approve_and_list(self):
        self.propose()
        self.assertEqual(self.rows()[0]["evidence"], {})
        self.cli("approve", "P1", "--by", "Human", code=2)
        self.cli("check", "P1", "--phase", "after", code=2)
        self.checks()
        self.cli("approve", "P1", "--by", "Human")
        row = self.rows()[0]
        self.assertEqual(row["status"], "approved")
        self.assertEqual(row["approver"], "Human")
        self.assertEqual(row["evidence"]["before"]["exit_code"], 7)
        self.assertIn("after", row["evidence"]["after"]["tail"])
        listed = self.cli("list", launcher="improvement").stdout
        self.assertEqual(json.loads(listed), row)
        self.cli("check", "P1", "--phase", "before", code=2)
        self.cli("approve", "P1", "--by", "Other", code=2)

    def test_baseline_and_failed_after(self):
        self.propose(before=python_command("print('baseline')"), after=python_command("raise SystemExit(3)"))
        self.checks(before_code=0, after_code=1)
        self.cli("approve", "P1", "--by", "Human", code=2)
        self.assertEqual(self.rows()[0]["evidence"]["before"]["exit_code"], 0)

    def test_passing_baseline_is_approvable(self):
        self.propose(before=python_command("print('baseline')"))
        self.checks(before_code=0)
        self.cli("approve", "P1", "--by", "Human")

    def test_rerun_before_invalidates_after_and_target_changes(self):
        self.propose()
        self.checks()
        (self.root / "check.py").write_text("print('changed')\n", encoding="utf-8")
        self.cli("approve", "P1", "--by", "Human", code=2)
        self.cli("check", "P1", "--phase", "after")
        self.cli("check", "P1", "--phase", "before", code=1)
        self.assertNotIn("after", self.rows()[0]["evidence"])
        self.cli("approve", "P1", "--by", "Human", code=2)

    def test_global_instruction_owner_approval(self):
        for number, target in enumerate(("AGENTS.md", "agents/lead.agent.md", ".github/copilot-instructions.md")):
            identifier = f"P{number}"
            self.propose(kind="instruction", target=target, identifier=identifier)
            self.checks(identifier)
            self.cli("approve", identifier, "--by", "Owner", code=2)
            self.cli("approve", identifier, "--by", "Owner", "--owner-approved")
            self.assertTrue(self.rows()[-1]["owner_approved"])

    def test_windows_style_global_path_requires_owner(self):
        self.propose(kind="instruction", target="agents\\lead.agent.md")
        self.checks()
        self.cli("approve", "P1", "--by", "Human", code=2)

    def test_scoped_instruction_needs_no_owner_override(self):
        self.propose(kind="instruction", target=".github/instructions/local.instructions.md")
        self.checks()
        self.cli("approve", "P1", "--by", "Human")

    def test_invalid_proposals_and_paths(self):
        base = ["propose", "--id", "P1", "--source-lesson", "L1", "--kind", "test", "--summary", "fix",
                "--before-command", "true", "--after-command", "true"]
        for target in ("../escape", "/escape", "C:\\escape", "..\\escape", "\\escape"):
            self.cli(*base, "--target", target, code=2)
        self.cli("propose", "--kind", "test", "--target", "check.py", "--summary", "fix",
                 "--before-command", "true", "--after-command", "true", code=2)
        self.propose()
        self.cli(*base, "--target", "check.py", code=2)
        self.cli("approve", "missing", "--by", "Human", code=2)
        self.cli("check", "P1", "--phase", "before", "--command", "changed", code=2)
        self.cli("check", "P1", "--phase", "before", "--timeout", "0", code=2)

    @unittest.skipIf(os.name == "nt", "symlink creation requires host privilege")
    def test_symlink_paths_cannot_escape(self):
        outside = self.root.parent
        (self.root / "outside").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            improvement.repo_path(self.root, "outside/escape.md")
        (self.root / "AGENTS.md").write_text("# Global guidance\n")
        (self.root / "alias.md").symlink_to(self.root / "AGENTS.md")
        self.assertTrue(improvement.global_instruction(self.root, "alias.md"))
        (self.root / "AGENTS.md").unlink()
        (self.root / "AGENTS.md").symlink_to(self.root / "check.py")
        self.assertTrue(improvement.global_instruction(self.root, "AGENTS.md"))
        (self.learning / "improvements.jsonl").symlink_to(ROOT / "plugin.json")
        self.assertTrue(any("escapes repo" in error for error in validate(self.root)[1]))

    def test_output_tail_redaction_and_timeout(self):
        # Construct synthetic material at runtime rather than placing a token in source.
        (self.root / "output.py").write_text("print('x' * 4000); print('gh' + 'p_' + 'a' * 30)\n")
        command = subprocess.list2cmdline([sys.executable, "output.py"]) if os.name == "nt" else shlex.join([sys.executable, "output.py"])
        self.propose(before=command, after=python_command("import time; time.sleep(0.2)"))
        self.cli("check", "P1", "--phase", "before")
        tail = self.rows()[0]["evidence"]["before"]["tail"]
        self.assertLessEqual(len(tail), 2000)
        self.assertIn("[REDACTED]", tail)
        self.cli("check", "P1", "--phase", "after", "--timeout", "0.05", code=1)
        self.assertEqual(self.rows()[0]["evidence"]["after"]["exit_code"], 124)
        self.cli("approve", "P1", "--by", "Human", code=2)

    def test_prune_register_emits_only_unreviewed_stubs_idempotently(self):
        (self.learning / "harness-assumptions.md").write_text(
            "# Harness assumptions\n\n| Rule | Model Limitation | Last Reviewed Model | Target |\n"
            "|---|---|---|---|\n| Retry guard | Repeats failures | old-model | check.py |\n"
            "| Scoped rule | Forgets scope | new-model | docs/rule.md |\n", encoding="utf-8")
        original = (self.root / "check.py").read_bytes()
        output = self.cli("prune-review", "--model", "new-model").stdout
        self.assertIn("Retry guard", output)
        self.assertNotIn("Scoped rule", output)
        self.assertEqual(len(self.rows()), 1)
        row = self.rows()[0]
        self.assertEqual((row["kind"], row["status"]), ("retire", "proposed"))
        self.assertEqual(row["evidence"], {})
        self.cli("prune-review", "--model", "new-model")
        self.assertEqual(len(self.rows()), 1)
        self.cli("approve", row["id"], "--by", "Human", code=2)
        self.cli("check", row["id"], "--phase", "before", "--command", python_command("print('baseline')"))
        self.cli("check", row["id"], "--phase", "after", "--command", python_command("print('eval')"))
        self.cli("approve", row["id"], "--by", "Human")
        self.assertEqual((self.root / "check.py").read_bytes(), original)


class PromotionTests(LearningFixture):
    def test_dry_run_apply_and_picker(self):
        self.cli("--lesson", "L1", "--target", "docs/guide.md", launcher="promote-lesson")
        self.assertFalse((self.root / "docs/guide.md").exists())
        self.cli("--index", "1", "--target", "docs/guide.md", "--apply", launcher="promote-lesson-picker")
        self.assertIn("Use the quick gate.", (self.root / "docs/guide.md").read_text())
        self.cli("--lesson", "Use the quick gate.", "--target", "docs/guide.md", "--apply", launcher="promote-lesson")
        self.assertEqual((self.root / "docs/guide.md").read_text().count("## Promoted Lessons"), 1)

    def test_executable_check_or_explicit_prose_justification_required(self):
        self.lessons("| L1 | Use the quick gate. | test | 2 | yes | docs | candidate | | |")
        self.cli("--lesson", "L1", "--target", "docs/guide.md", launcher="promote-lesson", code=2)
        self.cli("--index", "1", "--target", "docs/guide.md", launcher="promote-lesson-picker", code=2)
        self.lessons("| L1 | Use the quick gate. | test | 2 | yes | docs | candidate | | Human-only UX judgment |")
        self.cli("--lesson", "L1", "--target", "docs/guide.md", launcher="promote-lesson")

    def test_invalid_target_missing_and_stale_lesson(self):
        for target in ("../escape.md", "..\\escape.md", "C:\\escape.md", "\\escape.md", "file.txt"):
            self.cli("promote-lesson", "--lesson", "L1", "--target", target, code=2)
        self.cli("promote-lesson", "--target", "docs/guide.md", code=2)
        self.cli("promote-lesson", "--lesson", "not a candidate", "--target", "docs/guide.md", code=2)
        self.cli("promote-lesson-picker", "--index", "0", "--target", "docs/guide.md", code=2)
        self.cli("promote-lesson-picker", "--index", "99", "--target", "docs/guide.md", code=2)
        self.lessons("| L1 | UNVALIDATED: Use the quick gate. | test | 2 | yes | docs | candidate | python check.py | |")
        self.cli("promote-lesson", "--lesson", "L1", "--target", "docs/guide.md", code=2)


class ValidationTests(LearningFixture):
    def test_validator_launcher(self):
        argv = (["pwsh", "-NoProfile", "-File", str(ROOT / "harness/validate-learning.ps1")]
                if os.name == "nt" else ["bash", str(ROOT / "harness/validate-learning.sh")])
        result = subprocess.run([*argv, str(self.root)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ARCHITRAVE-LEARNING: PASS", result.stdout)

    def test_existing_profile_and_link_checks(self):
        self.assertFalse(validate(self.root)[1])
        profile = self.learning / "repo-profile.md"
        profile.write_text("# Profile\n[missing](docs/nope.md)\n")
        self.assertTrue(any("missing link" in error for error in validate(self.root)[1]))
        profile.unlink()
        self.assertTrue(any("missing/empty" in error for error in validate(self.root)[1]))

    def test_optional_improvements_valid_malformed_and_secret(self):
        self.propose()
        self.assertFalse(validate(self.root)[1])
        path = self.learning / "improvements.jsonl"
        path.write_text("not JSON\n")
        self.assertTrue(any("malformed" in error for error in validate(self.root)[1]))
        secret = "gh" + "p_" + "a" * 30
        path.write_text(json.dumps({"summary": secret}) + "\n")
        self.assertTrue(any("secret" in error for error in validate(self.root)[1]))
        path.write_text("")
        self.assertTrue(validate(self.root)[1])

    def test_optional_assumptions_valid_malformed_and_secret(self):
        path = self.learning / "harness-assumptions.md"
        path.write_text("# Assumptions\n| Rule | Model Limitation | Last Reviewed Model | Target |\n"
                        "|---|---|---|---|\n| Guard | Repetition | model-a | check.py |\n")
        self.assertFalse(validate(self.root)[1])
        path.write_text("# No table\n")
        self.assertTrue(any("malformed" in error for error in validate(self.root)[1]))
        path.write_text("# Assumptions\n" + "gh" + "p_" + "a" * 30)
        self.assertTrue(any("secret" in error for error in validate(self.root)[1]))

    def test_merged_and_rejected_dispositions(self):
        self.propose()
        self.checks()
        self.cli("approve", "P1", "--by", "Human")
        row = self.rows()[0]
        row["status"] = "merged"
        improvement.save_proposals(self.root, [row])
        self.assertFalse(validate(self.root)[1])
        row["status"] = "rejected"
        improvement.save_proposals(self.root, [row])
        self.assertFalse(validate(self.root)[1])

    def test_contract_rejects_duplicate_bad_evidence_and_forged_approval(self):
        self.propose()
        valid = self.rows()[0]
        path = self.learning / "improvements.jsonl"
        for mutate in (
            lambda row: row.update(status="approved", approver="Human"),
            lambda row: row.update(status="unknown"),
            lambda row: row.update(source_lessons=[], failure_fingerprint=""),
            lambda row: row.update(evidence={"after": {}}),
            lambda row: row.update(evidence={"before": {"command": "changed", "exit_code": 0, "tail": "", "target_digest": "missing"}}),
        ):
            row = copy.deepcopy(valid)
            mutate(row)
            path.write_text(json.dumps(row) + "\n")
            self.assertTrue(validate(self.root)[1])
        path.write_text((json.dumps(valid) + "\n") * 2)
        self.assertTrue(any("duplicate" in error for error in validate(self.root)[1]))


if __name__ == "__main__":
    unittest.main()
