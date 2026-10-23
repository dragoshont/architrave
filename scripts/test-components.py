#!/usr/bin/env python3
"""Component map gate against throwaway git checkouts (fixture, not live evidence)."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "gates" / "gate_runner.py"
EXAMPLE = ROOT / "kit" / "examples" / "requirements.md"


def git(path: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


def checkout(path: Path, origin: str) -> Path:
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "main")
    git(path, "remote", "add", "origin", origin)
    return path


def python_command(args):
    if sys.platform == "win32":
        return "& '" + sys.executable.replace("'", "''") + "' " + args
    return f'"{sys.executable}" ' + args


class ComponentGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.hub = self.base / "hub"
        self.hub.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def run_gate(self, components, *flags, requirements="SPEC.md"):
        config = {"kind": "knowledge", "build": "true", "test": "true", "components": components}
        if requirements:
            config["requirements"] = requirements
            if requirements == "SPEC.md":
                (self.hub / "SPEC.md").write_text(EXAMPLE.read_text())
        (self.hub / "architrave.config.json").write_text(json.dumps(config))
        process = subprocess.run(
            [sys.executable, str(RUNNER), "components", "--repo", str(self.hub), *flags],
            capture_output=True, text=True, check=False,
        )
        return process.returncode, process.stdout + process.stderr

    def test_matching_checkout_passes_and_reports_unsecured_work(self):
        engine = checkout(self.base / "engine", "git@github.com:me/engine.git")
        (engine / "x").write_text("x")
        code, out = self.run_gate([{"name": "engine", "repo": "me/engine", "path": "../engine"}])
        self.assertEqual(code, 0, out)
        self.assertIn("warn  engine: main, 0 unpushed commits, 1 changed files", out)

    def test_origin_mismatch_and_local_path_origin_fail(self):
        checkout(self.base / "bridge", "https://github.com/me/old-name.git")
        checkout(self.base / "fork", str(self.base / "elsewhere"))
        code, out = self.run_gate([
            {"name": "bridge", "repo": "me/new-name", "path": "../bridge"},
            {"name": "fork", "repo": "me/fork", "path": "../fork"},
        ])
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL  bridge: main pushes to origin=https://github.com/me/old-name.git (expected me/new-name)", out)
        self.assertIn("FAIL  fork: main pushes to origin=", out)

    def test_multi_component_program_requires_repo_requirements_file(self):
        checkout(self.base / "engine", "git@github.com:me/engine.git")
        checkout(self.base / "app", "git@github.com:me/app.git")
        pair = [{"name": "engine", "repo": "me/engine", "path": "../engine"},
                {"name": "app", "repo": "me/app", "path": "../app"}]
        code, out = self.run_gate(pair, requirements=None)
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL  requirements: several components are mapped", out)
        code, out = self.run_gate(pair, requirements="MISSING.md")
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL  requirements: MISSING.md is missing or empty", out)
        scratch = self.base / ".copilot" / "session-state" / "x" / "files"
        scratch.mkdir(parents=True)
        (scratch / "ledger.md").write_text("REQ-01")
        code, out = self.run_gate(pair, requirements=str(scratch / "ledger.md"))
        self.assertEqual(code, 1, out)
        self.assertIn("is agent session scratch", out)
        code, out = self.run_gate(pair)
        self.assertEqual(code, 0, out)
        self.assertIn("ok    requirements: SPEC.md", out)

    def requirements(self, text, *flags):
        (self.hub / "SPEC.md").write_text(text)
        (self.hub / "architrave.config.json").write_text(json.dumps(
            {"kind": "knowledge", "build": "true", "test": "true", "requirements": "SPEC.md"}))
        process = subprocess.run(
            [sys.executable, str(RUNNER), "requirements", "--repo", str(self.hub), *flags],
            capture_output=True, text=True, check=False,
        )
        return process.returncode, process.stdout + process.stderr

    def test_requirements_file_needs_table_acceptance_evidence_corrections_and_handoff(self):
        example = EXAMPLE.read_text()
        code, out = self.requirements(example)
        self.assertEqual(code, 0, out)
        self.assertIn("ARCHITRAVE-REQUIREMENTS: PASS", out)
        code, out = self.requirements("# Requirements\n- REQ-01\n")
        self.assertEqual(code, 1)
        self.assertIn("no requirements table", out)
        self.assertIn("'Next:'", out)
        broken = (example
                  .replace("| `make test-library` passes; owned count matches service |", "| |")
                  .replace("commit abc1234, test log ci/123", "")
                  .replace("| C-01 | supersede | REQ-03 → REQ-04 |", "| C-01 | tweak | REQ-09 |")
                  .replace("Failed approaches: forcing a refresh on appear re-triggered the loop (reverted in def5678).",
                           "Failed approaches:"))
        code, out = self.requirements(broken)
        self.assertEqual(code, 1)
        for text in ("REQ-01 has no testable acceptance", "REQ-02 is accepted without evidence",
                     "REQ-03 is superseded but no correction", "type 'tweak'", "unknown REQ-09",
                     "'Failed approaches:'"):
            self.assertIn(text, out)

    def test_requirements_claim_refuses_duplicate_or_closed_lanes_and_done_needs_acceptance(self):
        example = EXAMPLE.read_text()
        code, out = self.requirements(example, "--claim", "REQ-01", "--owner", "ui-lane")
        self.assertEqual(code, 0, out)
        self.assertIn("acceptance: `make test-library`", out)
        code, out = self.requirements(example, "--claim", "REQ-04", "--owner", "new-lane")
        self.assertEqual(code, 0, out)
        code, out = self.requirements(example, "--claim", "REQ-01", "--owner", "other-lane")
        self.assertEqual(code, 1)
        self.assertIn("already owned by ui-lane", out)
        code, out = self.requirements(example, "--claim", "REQ-03,REQ-02,REQ-77", "--owner", "x")
        self.assertIn("REQ-03: status is superseded", out)
        self.assertIn("REQ-02: status is accepted", out)
        self.assertIn("REQ-77: not in", out)
        code, out = self.requirements(example, "--done")
        self.assertEqual(code, 1)
        self.assertIn("2 active REQs are not accepted: REQ-01, REQ-04", out)

    def test_private_push_remote_passes(self):
        engine = checkout(self.base / "engine", "https://github.com/me/public-fork.git")
        git(engine, "remote", "add", "private", "https://github.com/me/engine-private.git")
        git(engine, "config", "branch.main.pushRemote", "private")
        code, out = self.run_gate([{"name": "engine", "repo": "me/engine-private", "path": "../engine"}])
        self.assertEqual(code, 0, out)
        self.assertIn("ok    engine: main", out)

    def test_session_scratch_fails(self):
        scratch = checkout(self.base / ".copilot" / "session-state" / "abc" / "files" / "engine", "git@github.com:me/engine.git")
        code, out = self.run_gate([{"name": "engine", "repo": "me/engine", "path": str(scratch)}])
        self.assertEqual(code, 1, out)
        self.assertIn("is agent session scratch", out)

    def test_branch_pushing_to_upstream_fails(self):
        engine = checkout(self.base / "engine", "https://github.com/me/engine.git")
        git(engine, "remote", "add", "up", "https://github.com/org/engine.git")
        git(engine, "config", "remote.pushDefault", "up")
        code, out = self.run_gate([{"name": "engine", "repo": "me/engine", "path": "../engine", "upstream": "org/engine"}])
        self.assertEqual(code, 1, out)
        self.assertIn("(read-only upstream; expected me/engine)", out)

    def test_invalid_map_fails(self):
        code, out = self.run_gate([
            {"name": "a", "repo": "me/a", "upstream": "me/a"},
            {"name": "a", "repo": "bad"},
            {"name": "b", "repo": "me/b", "consumes": ["missing"]},
        ])
        self.assertEqual(code, 1, out)
        for text in ("repo must not be its read-only upstream", "duplicate component a", "repo must be owner/name", "consumes unknown component missing"):
            self.assertIn(text, out)

    def test_service_runs_before_ui_and_failure_skips_ui(self):
        checkout(self.base / "app", "https://github.com/me/app.git")
        components = [{"name": "app", "repo": "me/app", "path": "../app"}]
        app = self.base / "app"
        (app / "mark.py").write_text("import sys\nif sys.argv[1] == 'fail':\n    raise SystemExit(3)\nopen('order', 'a').write(sys.argv[1])\n")
        components[0]["service"] = python_command("mark.py s")
        components[0]["ui"] = python_command("mark.py u")
        code, out = self.run_gate(components, "--test")
        self.assertEqual(code, 0, out)
        self.assertEqual((self.base / "app" / "order").read_text(), "su")
        components[0]["service"] = python_command("mark.py fail")
        code, out = self.run_gate(components, "--test")
        self.assertEqual(code, 1, out)
        self.assertIn("skip  app ui (service failed)", out)
        self.assertEqual((self.base / "app" / "order").read_text(), "su")

    def test_ui_without_service_fails(self):
        checkout(self.base / "app", "https://github.com/me/app.git")
        code, out = self.run_gate([{"name": "app", "repo": "me/app", "path": "../app", "ui": "true"}], "--test")
        self.assertEqual(code, 1, out)
        self.assertIn("ui tests need a service test first", out)
        code, out = self.run_gate([{"name": "app", "repo": "me/app", "ui": "true"}], "--test")
        self.assertEqual(code, 1, out)
        self.assertIn("ui tests need a service test first", out)

    def test_configured_tests_without_path_fail_only_with_test(self):
        components = [{"name": "app", "repo": "me/app", "service": "true"}]
        self.assertEqual(self.run_gate(components)[0], 0)
        code, out = self.run_gate(components, "--test")
        self.assertEqual(code, 1, out)
        self.assertIn("no local path to run them in", out)

    def test_every_push_url_must_match(self):
        engine = checkout(self.base / "engine", "https://github.com/me/engine.git")
        git(engine, "remote", "set-url", "--add", "--push", "origin", "https://github.com/me/engine.git")
        git(engine, "remote", "set-url", "--add", "--push", "origin", "git@github.com:org/engine.git")
        code, out = self.run_gate([{"name": "engine", "repo": "me/engine", "path": "../engine", "upstream": "org/engine"}])
        self.assertEqual(code, 1, out)
        self.assertIn("(read-only upstream; expected me/engine)", out)

    def test_github_url_forms(self):
        sys.path.insert(0, str(RUNNER.parent))
        try:
            from gate_runner import github_name
        finally:
            sys.path.pop(0)
        for url in ("https://github.com/Me/Engine.git", "HTTPS://GITHUB.COM/Me/Engine.GIT/", "git@github.com:me/engine",
                    "ssh://git@github.com:22/me/engine.git", "https://token@github.com/me/engine"):
            self.assertEqual(github_name(url), "me/engine", url)
        for url in ("https://notgithub.com/me/engine.git", "https://github.com.evil.io/me/engine", "/srv/me/engine",
                    "https://github.com/../engine", "https://github.com/me/engine/extra"):
            self.assertIsNone(github_name(url), url)

    def test_dot_segments_rejected(self):
        code, out = self.run_gate([{"name": "a", "repo": "../repo"}, {"name": "b", "repo": "me/.."}])
        self.assertEqual(code, 1, out)
        self.assertEqual(out.count("repo must be owner/name"), 2, out)

    def test_absent_map_skips(self):
        (self.hub / "architrave.config.json").write_text(json.dumps({"kind": "knowledge", "build": "true", "test": "true"}))
        process = subprocess.run([sys.executable, str(RUNNER), "components", "--repo", str(self.hub)], capture_output=True, text=True)
        self.assertEqual(process.returncode, 0)
        self.assertIn("none configured", process.stdout)


if __name__ == "__main__":
    unittest.main()
