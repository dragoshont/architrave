#!/usr/bin/env python3
"""Component map gate against throwaway git checkouts (fixture, not live evidence)."""

from __future__ import annotations

import json
import os
import time
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

    def test_spec_md_is_the_default_requirements_file_and_checks_validate_it(self):
        (self.hub / "architrave.config.json").write_text(json.dumps(
            {"kind": "knowledge", "build": "true", "test": "true"}))

        def gate(*args):
            process = subprocess.run([sys.executable, str(RUNNER), *args, "--repo", str(self.hub)],
                                     capture_output=True, text=True, check=False)
            return process.returncode, process.stdout + process.stderr

        code, out = gate("requirements")
        self.assertEqual(code, 0, out)
        self.assertIn("no SPEC.md - skipping", out)
        (self.hub / "SPEC.md").write_text(EXAMPLE.read_text())
        code, out = gate("requirements")
        self.assertEqual(code, 0, out)
        self.assertIn("ARCHITRAVE-REQUIREMENTS: PASS", out)
        self.assertEqual(gate("checks", "--quick")[0], 0)
        (self.hub / "SPEC.md").write_text("# Notes\n- REQ-01\n")
        self.assertIn("no requirements table", gate("requirements")[1])
        (self.hub / "SPEC.md").write_text("| ID | Requirement | Status |\n|---|---|---|\n| REQ-01 | x | bogus |\n")
        code, out = gate("checks", "--quick")
        self.assertEqual(code, 1, out)
        code, out = gate("quality-gate")
        self.assertEqual(code, 2, out)

    def test_claim_records_ownership_and_second_lane_cannot_claim(self):
        example = EXAMPLE.read_text()
        code, out = self.requirements(example, "--claim", "REQ-04", "--owner", "first")
        self.assertEqual(code, 0, out)
        spec = self.hub / "SPEC.md"
        claimed = spec.read_text()
        self.assertIn("| first | claimed |", claimed)
        self.assertIn("commit before dispatch", out)
        code, out = self.requirements(claimed, "--claim", "REQ-04", "--owner", "second")
        self.assertEqual(code, 1, out)
        self.assertIn("already owned by first", out)
        self.assertEqual(spec.read_text(), claimed)
        for flags in (("--claim", "REQ-04,REQ-77", "--owner", "first"),
                      ("--claim", "REQ-04"), ("--claim", "", "--owner", "first"),
                      ("--claim", "REQ-04", "--owner", "bad|owner"),
                      ("--claim", "REQ-04", "--owner", "bad\nowner")):
            code, out = self.requirements(example, *flags)
            self.assertNotEqual(code, 0, out)
            self.assertEqual(spec.read_text(), example)

    def test_handoff_expected_commit_rejects_stale_successor(self):
        commit = ("-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm")
        git(self.hub, "init", "-q", "-b", "main")
        self.requirements(EXAMPLE.read_text())
        git(self.hub, "add", ".")
        git(self.hub, *commit, "initial")
        sibling = self.base / "successor"
        git(self.hub, "worktree", "add", "-qb", "successor", str(sibling))
        spec = self.hub / "SPEC.md"
        spec.write_text(spec.read_text() + "\nPredecessor handoff\n")
        git(self.hub, "add", "SPEC.md")
        git(self.hub, *commit, "handoff")
        expected = subprocess.check_output(["git", "-C", str(self.hub), "rev-parse", "HEAD"],
                                           text=True).strip()

        def gate(path, *flags):
            p = subprocess.run([sys.executable, str(RUNNER), "requirements", "--repo", str(path),
                                *flags], capture_output=True, text=True)
            return p.returncode, p.stdout + p.stderr

        self.assertEqual(gate(sibling, "--handoff")[0], 0, "legacy check cannot detect stale successor")
        code, out = gate(sibling, "--handoff", "--expect", expected)
        self.assertEqual(code, 1, out)
        self.assertIn("does not contain expected handoff commit", out)
        for invalid in ("f" * 40, "--all", "HEAD", ""):
            code, out = gate(self.hub, "--handoff", f"--expect={invalid}")
            self.assertEqual(code, 1, out)
        self.assertEqual(gate(self.hub, "--expect", expected)[0], 1, "--expect requires --handoff")
        self.assertEqual(gate(self.hub, "--handoff", "--expect", expected)[0], 0)
        git(self.hub, *commit, "descendant", "--allow-empty")
        self.assertEqual(gate(self.hub, "--handoff", "--expect", expected)[0], 0)
        # A different root commit is known locally, but not part of this checkout's history.
        git(sibling, "checkout", "-q", "--orphan", "unrelated")
        git(sibling, *commit, "unrelated")
        unrelated = subprocess.check_output(["git", "-C", str(sibling), "rev-parse", "HEAD"],
                                            text=True).strip()
        self.assertEqual(gate(self.hub, "--handoff", "--expect", unrelated)[0], 1)

    def test_evidence_and_product_dirt_are_semantic_not_ledger_proof(self):
        git(self.hub, "init", "-q", "-b", "main")
        accepted = EXAMPLE.read_text().replace("| in-progress | |", "| accepted | trust me |").replace(
            "| | open | |", "| | accepted | trust me |")
        self.assertEqual(self.requirements(accepted, "--done")[0], 0)
        git(self.hub, "add", ".")
        git(self.hub, "-c", "user.name=t", "-c", "user.email=t@example.invalid",
            "commit", "-qm", "unverified evidence")
        (self.hub / "product.py").write_text("raise RuntimeError('unfinished product')\n")
        code, out = self.requirements(accepted, "--handoff")
        self.assertEqual(code, 0, out)  # CTO must verify source/criterion; ledger parsing cannot.

    def test_explicit_requirements_operations_fail_without_a_ledger(self):
        config = self.hub / "architrave.config.json"
        config.write_text("{}")
        for text in (None, "# Prose only\n"):
            if text is not None:
                (self.hub / "SPEC.md").write_text(text)
            for flags in (("--claim", "REQ-63", "--owner", "X"), ("--done",), ("--handoff",),
                          ("--claim", "", "--owner", "X")):
                with self.subTest(text=text, flags=flags):
                    process = subprocess.run(
                        [sys.executable, str(RUNNER), "requirements", "--repo", str(self.hub), *flags],
                        capture_output=True, text=True, check=False,
                    )
                    self.assertEqual(process.returncode, 1, process.stdout + process.stderr)
                    self.assertIn("no requirements ledger resolves", process.stdout)
                    self.assertIn(str(self.hub.resolve()), process.stdout)
                    self.assertIn(str(config.resolve()), process.stdout)
                    self.assertIn("ARCHITRAVE-REQUIREMENTS: FAIL", process.stdout)
                    self.assertNotIn("skipping", process.stdout)

    def test_handoff_needs_committed_requirements_and_no_stranded_worktree_ledger(self):
        commit = ("-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m")
        git(self.hub, "init", "-q", "-b", "main")
        code, out = self.requirements(EXAMPLE.read_text(), "--handoff")
        self.assertEqual(code, 1, out)
        self.assertIn("never been committed", out)
        git(self.hub, "add", "SPEC.md", "architrave.config.json")
        git(self.hub, *commit, "spec")
        stamp = int(subprocess.run(["git", "-C", str(self.hub), "log", "-1", "--format=%at"],
                                   capture_output=True, text=True, check=True).stdout)

        def handoff(checkout=self.hub):
            process = subprocess.run([sys.executable, str(RUNNER), "requirements", "--repo", str(checkout),
                                      "--handoff"], capture_output=True, text=True, check=False)
            return process.returncode, process.stdout + process.stderr

        def ledger(checkout, plan, mtime, slug="SPEC"):
            workspace = checkout / ".superpowers" / "sdd" / slug
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "plan-path").write_text(plan + "\n")
            path = workspace / "progress.md"
            path.write_text(f"# SDD ledger - plan: {plan}\nTask 1: complete\n")
            os.utime(path, (mtime, mtime))
            return path

        self.assertEqual(handoff()[0], 0)
        spec = self.hub / "SPEC.md"
        spec.write_text(spec.read_text() + "\n")
        code, out = handoff()
        self.assertEqual(code, 1, out)
        self.assertIn("SPEC.md has uncommitted changes", out)
        git(self.hub, "checkout", "--", "SPEC.md")

        stale = ledger(self.hub, "SPEC.md", stamp - 60)
        code, out = handoff()
        self.assertEqual(code, 0, out)
        self.assertIn("scratch, not newer than SPEC.md@", out)
        os.utime(stale, (stamp + 120, stamp + 120))
        code, out = handoff()
        self.assertEqual(code, 1, out)
        self.assertIn("holds progress not in committed SPEC.md@", out)
        self.assertIn("ARCHITRAVE-REQUIREMENTS: FAIL", out)
        self.assertEqual(self.requirements(spec.read_text())[0], 0, "plain check stays unaffected")

        git(self.hub, "add", "-f", str(stale))
        git(self.hub, *commit, "track ledger")
        code, out = handoff()
        self.assertEqual(code, 0, out)
        self.assertIn("(tracked, not newer", out)
        stale.write_text(stale.read_text() + "Task 2: complete\n")
        self.assertEqual(handoff()[0], 1)
        git(self.hub, "checkout", "--", str(stale))

        ledger(self.hub, "docs/other-plan.md", stamp + 600, slug="other-plan")
        self.assertEqual(handoff()[0], 0, "another plan's ledger is not this hand-off's state")

        sibling = self.base / "successor"
        git(self.hub, "worktree", "add", "-q", "-b", "successor", str(sibling), "HEAD~1")
        newer = ledger(sibling, "SPEC.md", stamp + 600)
        code, out = handoff()
        self.assertEqual(code, 0, out)
        self.assertIn(f"warn  {newer.resolve()} on successor changed after its SPEC.md@", out)
        self.assertIn("never start a second ledger", out)
        code, out = handoff(sibling)
        self.assertEqual(code, 1, out)
        self.assertIn("holds progress not in committed", out)

        # Each worktree is judged by its own branch's requirements commit, not the caller's newer one.
        spec.write_text(spec.read_text() + "\n")
        git(self.hub, "add", "SPEC.md")
        later = stamp + 3600
        subprocess.run(["git", "-C", str(self.hub), *commit, "fold later"], check=True, capture_output=True,
                       env={**os.environ, "GIT_AUTHOR_DATE": f"@{later} +0000",
                            "GIT_COMMITTER_DATE": f"@{later} +0000"})
        code, out = handoff()
        self.assertEqual(code, 0, out)
        self.assertIn("on successor changed after its SPEC.md@", out)

        # Amend/rebase rewrite committer time; author time keeps an unfolded ledger visible.
        os.utime(stale, (later - 60, later - 60))
        git(self.hub, "rm", "-q", "--cached", str(stale))
        spec.write_text(spec.read_text() + "\n")
        git(self.hub, "add", "SPEC.md")
        subprocess.run(["git", "-C", str(self.hub), *commit, "rebased"], check=True, capture_output=True,
                       env={**os.environ, "GIT_AUTHOR_DATE": f"@{stamp} +0000",
                            "GIT_COMMITTER_DATE": f"@{later + 60} +0000"})
        code, out = handoff()
        self.assertEqual(code, 1, out)
        self.assertIn("delete the folded scratch", out)
        os.utime(stale, (stamp - 60, stamp - 60))
        future = int(time.time()) + 86400
        spec.write_text(spec.read_text() + "\n")
        git(self.hub, "add", "SPEC.md")
        subprocess.run(["git", "-C", str(self.hub), *commit, "skewed"], check=True, capture_output=True,
                       env={**os.environ, "GIT_AUTHOR_DATE": f"@{future} +0000"})
        code, out = handoff()
        self.assertEqual(code, 1, "a future author time cannot hide a ledger: " + out)
        stale.unlink()
        self.assertEqual(handoff()[0], 0)

    def test_parent_config_does_not_silently_claim_child_requirements(self):
        config = self.hub / "architrave.config.json"
        config.write_text("{}")
        child = self.hub / "project"
        child.mkdir()
        ledger = child / "SPEC.md"
        ledger.write_text(EXAMPLE.read_text())
        before = ledger.read_bytes()
        for flags in (("--claim", "REQ-01", "--owner", "X"), ("--done",), ()):
            with self.subTest(flags=flags):
                process = subprocess.run(
                    [sys.executable, str(RUNNER), "requirements", "--repo", str(child), *flags],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(process.returncode, 1 if flags else 0, process.stdout + process.stderr)
                if flags:
                    self.assertIn(str(config.resolve()), process.stdout)
                    self.assertIn(str(ledger.resolve()), process.stdout)
                    self.assertIn("parent config", process.stdout)
                    self.assertIn("not selected", process.stdout)
                else:
                    self.assertIn("skipping (PASS)", process.stdout)
                self.assertEqual(ledger.read_bytes(), before)

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


    def test_failing_recipe_prints_tail_and_keeps_full_log(self):
        noisy = python_command("-c \"import sys; [print('line', i) for i in range(100)]; sys.exit(3)\"")
        config = {"kind": "knowledge", "build": noisy, "test": "true"}
        (self.hub / "architrave.config.json").write_text(json.dumps(config))
        process = subprocess.run(
            [sys.executable, str(RUNNER), "checks", "--repo", str(self.hub)],
            capture_output=True, text=True, check=False,
        )
        out = process.stdout + process.stderr
        self.assertEqual(process.returncode, 1, out)
        self.assertIn("line 99", out)
        self.assertNotIn("line 5\n", out)
        log = out.split("full log: ", 1)[1].split(")", 1)[0]
        self.assertIn("line 0\n", Path(log).read_text())
        Path(log).unlink()

    def test_hostile_component_name_still_logs_failure(self):
        fail = python_command("-c \"import sys; print('boom'); sys.exit(4)\"")
        (self.hub / "architrave.config.json").write_text(json.dumps({"kind": "knowledge", "build": "true", "test": "true",
            "components": [{"name": "api/core\\x", "repo": "o/r", "path": str(self.hub), "build": fail, "test": fail}]}))
        process = subprocess.run([sys.executable, str(RUNNER), "components", "--repo", str(self.hub)],
                                 capture_output=True, text=True, check=False)
        out = process.stdout + process.stderr
        self.assertNotIn("Traceback", out)
        if "full log: " in out:
            log = Path(out.split("full log: ", 1)[1].split(")", 1)[0])
            self.assertTrue(log.name.startswith("api-core-x-"), log.name)
            self.assertIn("boom", log.read_text())

    def test_failure_logs_are_rotated(self):
        sys.path.insert(0, str(RUNNER.parent))
        import gate_runner
        directory = Path(gate_runner.gate_log_dir())
        for index in range(gate_runner.GATE_LOG_KEEP + 5):
            (directory / f"rotation-test-{index}.log").write_text("x")
        gate_runner.gate_log_dir()
        self.assertLess(len(list(directory.glob("*.log"))), gate_runner.GATE_LOG_KEEP)
        for leftover in directory.glob("rotation-test-*.log"):
            leftover.unlink()

if __name__ == "__main__":
    unittest.main()
