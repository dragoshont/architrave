#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))

from architrave_runtime import RunStore, RuntimeFailure
from invariant_engine import cli, evaluate, load_config


class InvariantEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        (self.repo / "src/core").mkdir(parents=True)
        (self.repo / "src/providers").mkdir(parents=True)
        (self.repo / "README.md").write_text("# Fixture\n", encoding="utf-8")
        self.config = {
            "invariants": {
                "requiredFiles": ["README.md"],
                "forbiddenPatterns": [{"pattern": "FORBIDDEN", "paths": ["src/**/*.ts"]}],
                "forbiddenDependencies": [{"from": "src/core/**/*.ts", "to": "src/providers/**"}],
            },
            "evaluation": {"controlAudit": True},
            "applyTo": ["src/**/*.tsx"],
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_config(self) -> None:
        (self.repo / "architrave.config.json").write_text(json.dumps(self.config), encoding="utf-8")

    def codes(self) -> list[str]:
        return [item["code"] for item in evaluate(self.repo, self.config)["violations"]]

    def test_clean_repository_passes(self) -> None:
        (self.repo / "src/core/clean.ts").write_text("export const value = 1;\n", encoding="utf-8")
        self.assertEqual("pass", evaluate(self.repo, self.config)["status"])

    def test_required_file_and_forbidden_pattern_fail(self) -> None:
        (self.repo / "README.md").unlink()
        (self.repo / "src/core/bad.ts").write_text("const value = 'FORBIDDEN';\n", encoding="utf-8")
        codes = self.codes()
        self.assertIn("REQUIRED_FILE_MISSING", codes)
        self.assertIn("FORBIDDEN_PATTERN", codes)

    def test_relative_dependency_is_resolved_against_source(self) -> None:
        (self.repo / "src/core/dependency.ts").write_text("import { x } from '../providers/x';\n", encoding="utf-8")
        result = evaluate(self.repo, self.config)
        violation = next(item for item in result["violations"] if item["code"] == "FORBIDDEN_DEPENDENCY")
        self.assertEqual("src/providers/x", violation["resolved"])

    def test_python_import_forms_are_attributed_to_imported_module(self) -> None:
        self.config["invariants"]["forbiddenDependencies"] = [
            {"from": "src/core/**/*.py", "to": "forbidden.module"}
        ]
        (self.repo / "src/core/import_module.py").write_text(
            "import forbidden.module\n", encoding="utf-8"
        )
        (self.repo / "src/core/import_value.py").write_text(
            "from forbidden.module import value\n", encoding="utf-8"
        )

        violations = [
            item
            for item in evaluate(self.repo, self.config)["violations"]
            if item["code"] == "FORBIDDEN_DEPENDENCY"
        ]
        self.assertEqual(2, len(violations))
        self.assertEqual(
            {"forbidden.module"},
            {item["dependency"] for item in violations},
        )

    def test_required_boundary_denies_unknown_import(self) -> None:
        self.config["invariants"]["requiredBoundaries"] = [
            {"path": "src/core/**/*.ts", "allowedImports": ["src/core/**", "safe-package"]}
        ]
        (self.repo / "src/core/boundary.ts").write_text("import value from 'unsafe-package';\n", encoding="utf-8")
        self.assertIn("BOUNDARY_IMPORT_DENIED", self.codes())

    def test_control_audit_detects_dead_controls(self) -> None:
        (self.repo / "src/view.tsx").write_text("export const View = () => <a href=\"#\">Open</a>;\n", encoding="utf-8")
        result = evaluate(self.repo, self.config)
        violation = next(item for item in result["violations"] if item["code"] == "DEAD_CONTROL")
        self.assertEqual("placeholder-link", violation["kind"])

    def test_invalid_regex_fails_explicitly(self) -> None:
        self.config["invariants"]["forbiddenPatterns"] = [{"pattern": "[", "paths": ["src/**"]}]
        with self.assertRaisesRegex(RuntimeFailure, "invalid forbidden regex"):
            evaluate(self.repo, self.config)

    def test_config_loader_rejects_non_object(self) -> None:
        (self.repo / "architrave.config.json").write_text("[]\n", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeFailure, "JSON object"):
            load_config(self.repo)

    def test_declared_invariants_block_run_until_recorded_pass(self) -> None:
        self.write_config()
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.email", "architrave@example.invalid"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.name", "Architrave Test"], cwd=self.repo, check=True)
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "fixture"], cwd=self.repo, check=True)
        store = RunStore(self.repo)
        state = store.create(
            goal="Enforce declared invariants.",
            outcome="The invariant gate passes.",
            criteria=[
                {
                    "id": "INV-001",
                    "description": "Declared invariants pass.",
                    "scope": "repository",
                    "risk": "R0",
                    "verificationType": "deterministic",
                    "status": "UNTESTED",
                    "evidenceRefs": [],
                    "blocking": True,
                }
            ],
        )
        verifying, completed = store.verify(state["runId"])
        self.assertFalse(completed)
        self.assertEqual("VERIFYING", verifying["status"])
        self.assertEqual(0, cli(["--repo", str(self.repo), "--run-id", state["runId"]]))
        store.set_criterion(state["runId"], "INV-001", "PASS", [f"gate:invariants-{state['runId']}"])
        completed_state, completed = store.verify(state["runId"])
        self.assertTrue(completed)
        self.assertEqual("COMPLETED", completed_state["status"])

    def test_invariant_gate_name_without_invariant_provenance_cannot_pass(self) -> None:
        self.write_config()
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.email", "architrave@example.invalid"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.name", "Architrave Test"], cwd=self.repo, check=True)
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "fixture"], cwd=self.repo, check=True)
        store = RunStore(self.repo)
        state = store.create(
            goal="Reject spoofed invariant gates.",
            outcome="Only invariant-engine evidence satisfies policy.",
            criteria=[
                {
                    "id": "INV-001",
                    "description": "Invariant engine passes.",
                    "scope": "repository",
                    "risk": "R0",
                    "verificationType": "deterministic",
                    "status": "UNTESTED",
                    "evidenceRefs": [],
                    "blocking": True,
                }
            ],
        )
        note = store.run_dir(state["runId"]) / "spoof.json"
        note.write_text('{"status":"pass","exitCode":0,"command":"spoof"}\n', encoding="utf-8")
        store._record_deterministic_result(
            state["runId"],
            artifact_id="spoofed-deterministic",
            path=note.relative_to(store.repository).as_posix(),
            evidence_refs=[],
        )
        store.record_gate(
            state["runId"],
            gate_id=f"invariants-{state['runId']}",
            task_id=None,
            gate_type="deterministic",
            status="PASS",
            evidence_refs=["artifact:spoofed-deterministic"],
        )
        store.set_criterion(state["runId"], "INV-001", "PASS", [f"gate:invariants-{state['runId']}"])
        verifying, completed = store.verify(state["runId"])
        self.assertFalse(completed)
        self.assertEqual("VERIFYING", verifying["status"])


if __name__ == "__main__":
    unittest.main(verbosity=2)