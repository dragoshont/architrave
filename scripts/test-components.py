#!/usr/bin/env python3
"""Component map gate against throwaway git checkouts (fixture, not live evidence)."""

from __future__ import annotations

import json
import re
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
        home = getattr(self, "copilot_home", self.base / "no-copilot")
        process = subprocess.run(
            [sys.executable, str(RUNNER), "requirements", "--repo", str(self.hub), *flags],
            capture_output=True, text=True, check=False, env=dict(os.environ, COPILOT_HOME=str(home)),
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
        narrowed = example.replace("| C-01 | supersede |", "| C-02 | narrow | REQ-01 | Owner asked X; doing Y |\n| C-01 | supersede |")
        code, out = self.requirements(narrowed, "--done")
        self.assertIn("narrow corrections lack owner acknowledgement: C-02", out)
        code, out = self.requirements(narrowed.replace("doing Y", "doing Y; owner not acknowledged"), "--done")
        self.assertIn("lack owner acknowledgement: C-02", out)
        code, out = self.requirements(narrowed.replace("doing Y", 'doing Y; owner acknowledged: "fine, Y"'), "--done")
        self.assertNotIn("lack owner acknowledgement", out)

    def test_lane_table_enforces_single_live_owner_caps_and_supersede(self):
        header = ("\n| Lane | Repo | Project ID | Branch | Push target | REQ IDs | Depends on | Session ID | "
                  "Assignment ID | State | Mutable paths | Heavy build | Preflight | Preflight evidence | "
                  "Preflight reported | Owner-only decisions | Superseded by |\n" + "|---" * 17 + "|\n")

        def lane(name, state, reqs, paths, heavy="no", sup="-", decisions="[]", dep="-"):
            return (f"| {name} | me/app | p1 | b | private | {reqs} | {dep} | 6b5186b6-ee1d-49cf-9807-3f23139b3444 | a | {state} | {paths} | "
                    f"{heavy} | ok | - | no | {decisions} | {sup} |\n")

        example = EXAMPLE.read_text()
        good = example + header + lane("L1", "running", "REQ-01", "src/ui", "yes") + lane("L2", "stopped", "REQ-01", "src/ui")
        code, out = self.requirements(good)
        self.assertEqual(code, 0, out)
        bad = (example + header + lane("L1", "running", "REQ-01", "src", "yes") + lane("L2", "running", "REQ-01,REQ-99", "src/ui", "yes")
               + lane("L3", "running", "REQ-04", "docs") + lane("L4", "running", "-", "x") + lane("L5", "superseded", "-", "-") + lane("L7", "running", "-", "-", dep="L5")
               + lane("L6", "paused", "-", "-", decisions="{}").replace("6b5186b6-ee1d-49cf-9807-3f23139b3444", "6b5186b6"))
        code, out = self.requirements(bad)
        self.assertEqual(code, 1, out)
        for text in ("REQ-01 is owned by live lanes L1 and L2", "lanes L1 and L2 both own me/app:src/ui",
                     "unknown REQ-99", "5 running lanes exceed workers.maxParallel=3", "lane L7 is running before dependency L5 is done (superseded)", "heavy-build slot held by several",
                     "L5 is superseded without", "L6 state 'paused'", "L6 'Owner-only decisions' is not a JSON array", "L6 session ID '6b5186b6' is not a full"):
            self.assertIn(text, out)

    def test_evidence_decision_finding_chain_across_repos_fails_closed(self):
        backend = checkout(self.base / "backend", "git@github.com:me/backend.git")
        (backend / "api.md").write_text("v1 route\n")
        git(backend, "add", "api.md")
        git(backend, "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", "v1")
        cited = subprocess.run(["git", "-C", str(backend), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        (self.hub / "architrave.config.json").write_text(json.dumps({
            "kind": "knowledge", "build": "true", "test": "true", "requirements": "SPEC.md",
            "components": [{"name": "backend", "repo": "me/backend", "path": "../backend"}]}))
        ledger = f"""# Program
| ID | Requirement | Acceptance | Owner | Status | Evidence |
|---|---|---|---|---|---|
| REQ-01 | Reuse backend route per D-1 | `make e2e` passes | app-lane | accepted | commit {cited} |

| ID | Question | Source | Claim | Author | Status | Reviewed by |
|---|---|---|---|---|---|---|
| E-1 | Can the app reuse the route? | backend@{cited}:api.md | v1 route exists | research-a | supported | review-b |
| E-2 | Vendor limits | https://example.com/limits (retrieved 2026-10-26) | 10 rps | research-a | unverified | - |

| ID | Decision | Rejected | Evidence | Status |
|---|---|---|---|---|
| D-1 | Reuse the backend route | New service: duplicate state | E-1 | active |

| ID | Severity | Target | Finding | Raised by | Disposition | Verified by | Evidence |
|---|---|---|---|---|---|---|---|
| F-1 | high | REQ-01 | Route lacks auth | judge | fixed | judge | `make e2e` at {cited} |

## Handoff
Next: ship
Failed approaches: none
Verify: `make e2e`
"""

        def run(text, *flags):
            (self.hub / "SPEC.md").write_text(text)
            process = subprocess.run([sys.executable, str(RUNNER), "requirements", "--repo", str(self.hub), *flags],
                                     capture_output=True, text=True, check=False)
            return process.returncode, process.stdout + process.stderr

        code, out = run(ledger)
        self.assertEqual(code, 0, out)
        (backend / "api.md").write_text("v2 route, auth required\n")
        git(backend, "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qam", "v2")
        code, out = run(ledger)
        self.assertEqual(code, 1)
        self.assertIn("E-1 source backend:api.md changed since", out)
        stale = ledger.replace("| research-a | supported | review-b |", "| research-a | stale | review-b |")
        code, out = run(stale)
        self.assertIn("D-1 is active but rests on E-1 (stale); set it to reconsider", out)
        code, out = run(stale.replace("| E-1 | active |", "| E-1 | reconsider |"))
        self.assertIn("REQ-01 is accepted on D-1, which is reconsider", out)
        broken = (ledger.replace("| review-b |", "| research-a |")
                  .replace("| judge | fixed | judge | `make e2e` at " + cited + " |", "| judge | fixed | app-lane | agreed by two agents |")
                  .replace("| New service: duplicate state |", "| - |")
                  .replace("(retrieved 2026-10-26)", ""))
        code, out = run(broken)
        for text in ("E-1 is supported without an independent reviewer", "D-1 records no rejected alternatives",
                     "F-1 is fixed without verifiable evidence", "F-1 high finding needs verification by someone other",
                     "E-2 web source needs a retrieval date"):
            self.assertIn(text, out)
        opened = stale.replace("| reconsider |", "| active |").replace("| stale | review-b |", "| supported | review-b |")
        opened = opened.replace("| judge | fixed | judge |", "| judge | open | - |")
        git(backend, "-c", "user.email=a@b", "-c", "user.name=a", "revert", "--no-edit", "HEAD")
        code, out = run(opened, "--done")
        self.assertIn("REQ-01 is accepted while high finding F-1 is open", out)
        self.assertIn("open serious findings: F-1", out)
        code, out = run(opened.replace("| open | - | `make e2e`", "| deferred | - | `make e2e`"))
        self.assertIn("F-1 high finding is deferred without a quoted owner acknowledgement", out)
        code, out = run(opened.replace("| open | - | `make e2e`", '| deferred | - | owner acknowledged: "after beta" `make e2e`'))
        self.assertEqual(code, 0, out)

    def test_review_notes_have_a_format_and_block_acceptance_on_revise(self):
        example = EXAMPLE.read_text()
        row = "commit abc1234, test log ci/123"
        code, out = self.requirements(example.replace(row, row + "; review: judge PASS"))
        self.assertEqual(code, 0, out)
        code, out = self.requirements(example.replace(row, row + "; review: judge REVISE"))
        self.assertIn("is accepted on a REVISE review", out)
        code, out = self.requirements(example.replace(row, row + "; review: judge REVISE; review: judge PASS"))
        self.assertEqual(code, 0, out)
        code, out = self.requirements(example.replace(row, row + "; review: looked fine"))
        self.assertIn("review note must read", out)
        code, out = self.requirements(example.replace(row, row + ", review: judge FAIL"))
        self.assertIn("is accepted on a FAIL review", out)
        code, out = self.requirements(example.replace(row, row + "; review: judge PASS; review: judge REVISE"))
        self.assertIn("is accepted on a REVISE review", out)
        owner = re.search(r"\| REQ-02 \|[^|]*\|[^|]*\| ([^|]+?) \|", example).group(1)
        code, out = self.requirements(example.replace(row, row + f"; review: {owner} PASS"))
        self.assertIn("is not independent of the owner", out)
        code, out = self.requirements(example.replace(row, row + "; review: 1 FAIL"))
        self.assertIn("review note must read", out)
        lane = ("\n| Lane | Repo | Project ID | Branch | Push target | REQ IDs | Depends on | Session ID | Assignment ID | State | "
                "Mutable paths | Heavy build | Preflight | Preflight evidence | Preflight reported | Owner-only decisions | Superseded by |\n"
                + "|---" * 17 + "|\n| L1 | me/app | p | b | private | REQ-02 | - | - | - | done | src | no | ok | - | no | [] | - |\n")
        code, out = self.requirements(example + lane, "--done")
        self.assertIn("lane L1 (done) lacks a PASS review on REQ-02", out)
        code, out = self.requirements(example.replace(row, row + "; review: judge PASS") + lane, "--done")
        self.assertNotIn("lacks a PASS review", out)
        stopped = lane.replace("| done |", "| stopped |")
        code, out = self.requirements(example + stopped, "--done")
        self.assertIn("lane L1 (stopped) lacks a PASS review on REQ-02", out)
        closed = lane.replace("| REQ-02 |", "| REQ-03 |")
        code, out = self.requirements(example + closed, "--done")
        self.assertNotIn("lacks a PASS review on REQ-03", out)

    def test_review_note_naming_a_session_is_checked_against_its_log(self):
        self.copilot_home = self.base / "copilot"
        def session(sid, agent, *said):
            folder = self.copilot_home / "session-state" / sid
            folder.mkdir(parents=True)
            events = [{"type": "session.start", "data": {"selectedModel": "claude-x"}},
                      {"type": "subagent.selected", "data": {"agentName": agent}},
                      {"type": "assistant.turn_start", "data": {}}]
            events += [{"type": "assistant.message", "data": {"content": text}} for text in said]
            (folder / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")
        good = "342c39ea-ac1f-42f2-84c8-687165d62ead"
        session(good, "architrave:adversarial-judge", "**PASS** with notes")
        session("1bbbbbbb-1111-2222-3333-444444444444", "architrave:adversarial-judge",
                "A PASS needs all criteria met.\nVerdict: REVISE")
        session("2ccccccc-1111-2222-3333-444444444444", "architrave:backend-implementer", "**PASS**")
        session("3ddddddd-1111-2222-3333-444444444444", "my-prejudged-implementer", "**PASS**")
        example = EXAMPLE.read_text()
        row = "commit abc1234, test log ci/123"
        code, out = self.requirements(example.replace(row, row + f"; review: {good} PASS"))
        self.assertEqual(code, 0, out)
        code, out = self.requirements(example.replace(row, row + "; review: 1bbbbbbb-1111-2222-3333-444444444444 PASS"))
        self.assertIn("last reported REVISE, not PASS", out)
        self.assertIn("fresh reviewer session for each delivery", out)
        for spoof in ("2ccccccc-1111-2222-3333-444444444444", "3ddddddd-1111-2222-3333-444444444444"):
            code, out = self.requirements(example.replace(row, row + f"; review: {spoof} PASS"))
            self.assertIn("not a reviewer role", out)
        code, out = self.requirements(example.replace(row, row + f"; review: {good}. PASS"))
        self.assertIn("review note must read", out)
        lane = ("\n| Lane | Repo | Project ID | Branch | Push target | REQ IDs | Depends on | Session ID | Assignment ID | State | "
                "Mutable paths | Heavy build | Preflight | Preflight evidence | Preflight reported | Owner-only decisions | Superseded by |\n"
                + "|---" * 17 + "|\n| L1 | me/app | p | b | private | REQ-02 | - | - | - | done | src | no | ok | - | no | [] | - |\n")
        code, out = self.requirements(example.replace(row, row + "; review: judge PASS") + lane, "--done")
        self.assertIn("lane L1 (done) lacks a PASS review on REQ-02", out, "unverifiable notes do not count where logs exist")
        code, out = self.requirements(example.replace(row, row + f"; review: {good} PASS") + lane, "--done")
        self.assertNotIn("lacks a PASS review", out)
        code, out = self.requirements(example.replace(row, row + "; review: deadbeef-0000-0000-0000-000000000000 PASS") + lane, "--done")
        self.assertIn("lacks a PASS review on REQ-02", out, "a session not logged here is unverified")
        self.assertIn("lane L1 is done without the session that did the work", out)
        for lane_session, expected in (("4eeeeeee-1111-2222-3333-444444444444", True), (good, False)):
            code, out = self.requirements(example.replace(row, row + f"; review: {good} PASS")
                                          + lane.replace("| - | - | done |", f"| {lane_session} | - | done |"), "--done")
            self.assertEqual("is not logged on this machine" in out, expected, out)

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

class ReviewVerification(unittest.TestCase):
    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("gate_runner_unit", RUNNER)
        self.gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.gate)
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.old = os.environ.get("COPILOT_HOME")
        os.environ["COPILOT_HOME"] = str(self.home)

    def tearDown(self):
        if self.old is None:
            os.environ.pop("COPILOT_HOME", None)
        else:
            os.environ["COPILOT_HOME"] = self.old
        self.tmp.cleanup()

    def log(self, sid, events):
        folder = self.home / "session-state" / sid
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")

    def test_role_is_the_kickoff_agent_and_prefix_folders_do_not_match(self):
        sid = "aaaaaaaa-1111-2222-3333-444444444444"
        self.log(sid, [{"type": "assistant.turn_start", "data": {}},
                       {"type": "subagent.selected", "data": {"agentName": "architrave:adversarial-judge"}},
                       {"type": "assistant.message", "data": {"content": "Verdict: PASS"}}])
        self.assertEqual(self.gate.review_session(sid, "PASS")[0], "contradicted", "a mid-session switch is not the role")
        self.log("bbbbbbbb-1111-2222-3333-444444444444-decoy", [
            {"type": "subagent.selected", "data": {"agentName": "architrave:adversarial-judge"}},
            {"type": "assistant.message", "data": {"content": "Verdict: PASS"}}])
        self.assertEqual(self.gate.review_session("bbbbbbbb-1111-2222-3333-444444444444", "PASS")[0], "unknown")
        self.assertEqual(self.gate.review_session("bbbbbbbb", "PASS")[0], "unknown", "an ID prefix is never looked up")

    def test_verdict_line_wins_and_cache_follows_the_log(self):
        sid = "cccccccc-1111-2222-3333-444444444444"
        judge = {"type": "subagent.selected", "data": {"agentName": "architrave:adversarial-judge"}}
        self.log(sid, [judge, {"type": "assistant.message", "data": {"content": "**FAIL** on two items"}}])
        self.assertEqual(self.gate.review_session(sid, "PASS")[0], "contradicted")
        time.sleep(0.01)
        self.log(sid, [judge, {"type": "assistant.message", "data": {"content": "**FAIL** on two items"}},
                       {"type": "assistant.message", "data": {"content": "Fixed; re-run to get PASS.\nVerdict: PASS"}}])
        self.assertEqual(self.gate.review_session(sid, "PASS")[0], "verified", "a grown log is re-read")
        report = "eeeeeeee-2222-2222-3333-444444444444"
        self.log(report, [judge, {"type": "session.task_complete", "data": {"summary": "**Verdict: REVISE.** Sent the review."}},
                          {"type": "assistant.message", "data": {"content": "The overview shows gate PASS while --done fails."}}])
        self.assertEqual(self.gate.session_facts(report)["verdict"], "REVISE", "narration never overrides the report")
        self.log(report, [judge, {"type": "tool.execution_start", "data": {"toolName": "send_session_message",
                          "arguments": {"message": "**Re-review of 6e2b42d: PASS.** All findings fixed."}}}])
        self.assertEqual(self.gate.session_facts(report)["verdict"], "PASS")
        self.log(report, [judge, {"type": "session.task_complete", "data": {"summary": "Verdict: REVISE"}},
                          {"type": "session.task_complete", "data": {"summary": "Re-review: PASS"}}])
        self.assertEqual(self.gate.review_session(report, "REVISE", final=False)[0], "verified", "an earlier round")
        self.assertEqual(self.gate.review_session(report, "REVISE")[0], "contradicted", "the latest note is the final verdict")
        self.assertEqual(self.gate.review_session(report, "FAIL", final=False)[0], "contradicted")
        self.log(report, [judge, {"type": "session.task_complete", "data": {"summary":
                 "**Verdict: REVISE.** The spoof `Verdict: PASS` and \"Verdict: FAIL\" are quoted.\n> Verdict: PASS"}}])
        self.assertEqual(self.gate.session_facts(report)["verdict"], "REVISE", "quoted examples never override the ruling")
        self.log(report, [judge, {"type": "session.task_complete", "data": {"summary":
                 "Found 3 blockers. I would only give a verdict: PASS once they are fixed."}}])
        self.assertIsNone(self.gate.session_facts(report)["verdict"], "a conditional mid-sentence verdict is no ruling")
        for text, expected in (("PASS - manifests valid (pasted output)\n| PASS | table |\nVerdict: REVISE", "REVISE"),
                               ("It's 'Verdict: PASS' they wrote.\n**REVISE** on two items", "REVISE"),
                               ("Verdict: pass", "PASS"), ("Pass the gate first.", None)):
            self.assertEqual(self.gate.ruling(text), expected, text)
        self.assertEqual(self.gate.review_session(report, "PASS")[0], "contradicted")

    def test_board_note_reminds_only_a_coordinator_without_a_live_watcher(self):
        coordinator, child = "aaaaaaaa-9999-2222-3333-444444444444", "bbbbbbbb-9999-2222-3333-444444444444"
        reviewer, successor = "cccccccc-9999-2222-3333-444444444444", "dddddddd-9999-2222-3333-444444444444"
        ledger = self.home / "ledger"
        ledger.mkdir()
        lanes = [{"lane": "L1", "state": "running", "session id": child}]
        self.log(coordinator, [{"type": "tool.execution_start", "data": {"toolName": "create_session", "toolCallId": "c1"}},
                               {"type": "tool.execution_complete", "data": {"toolCallId": "c1", "result": f"Created session 'L1' (id: {child})"}}])
        self.log(successor, [{"type": "tool.execution_start", "data": {"toolName": "send_session_message",
                                                                       "arguments": {"session_id": child, "message": "report to me"}}}])
        self.log(reviewer, [{"type": "user.message", "data": {"content": f"review lane session {child}"}},
                            {"type": "tool.execution_start", "data": {"toolName": "bash", "toolCallId": "b1"}},
                            {"type": "tool.execution_complete", "data": {"toolCallId": "b1", "result": f"Created session 'L1' (id: {child})"}}])
        sibling = "eeeeeeee-9999-2222-3333-444444444444"
        self.log(sibling, [{"type": "tool.execution_start", "data": {"toolName": "send_session_message",
                                                                     "arguments": {"session_id": child, "message": "your build is ready"}}}])
        lanes = lanes + [{"lane": "L2", "state": "running", "session id": sibling}]
        self.log(child, [{"type": "session.start", "data": {}}])
        old = os.environ.get("COPILOT_AGENT_SESSION_ID")
        try:
            for session, expected in ((coordinator, True), (successor, True), (reviewer, False), (child, False), (sibling, False)):
                os.environ["COPILOT_AGENT_SESSION_ID"] = session
                self.assertEqual(bool(self.gate.board_note(lanes, ledger)), expected, session)
            os.environ["COPILOT_AGENT_SESSION_ID"] = coordinator
            note = self.gate.board_note(lanes, ledger)
            self.assertIn("2 lanes running", note)
            self.assertIn("1 lane running", self.gate.board_note(lanes[:1], ledger))
            self.assertIn(f"--ledger {ledger}", note)
            self.assertIn(str(Path(RUNNER).resolve().parents[1] / "harness" / "program_board.py"), note)
            output = self.home / "board.html"
            output.write_text("x")
            pointer = self.home / "session-state" / coordinator / "files" / self.gate.BOARD_POINTER
            pointer.parent.mkdir(parents=True)
            live = {"pid": os.getpid(), "output": str(output), "ledger": str(ledger), "interval": 120}
            pointer.write_text(json.dumps(live))
            self.assertIsNone(self.gate.board_note(lanes, ledger), "a live, fresh watcher for this ledger satisfies it")
            self.assertIsNotNone(self.gate.board_note(lanes, self.home), "a board for another ledger does not")
            os.utime(output, (time.time() - 3600, time.time() - 3600))
            self.assertIsNotNone(self.gate.board_note(lanes, ledger), "a stale output means a dead or failing watcher")
            os.utime(output, None)
            pointer.write_text(json.dumps(dict(live, pid=2 ** 22 + 12345)))
            self.assertIsNotNone(self.gate.board_note(lanes, ledger), "a dead watcher does not")
            self.assertIsNone(self.gate.board_note([dict(lane, state="done") for lane in lanes], ledger))
            self.assertTrue(self.gate.pid_alive(os.getpid()))
            self.assertFalse(self.gate.pid_alive(0))
            self.assertFalse(self.gate.pid_alive(2 ** 22 + 12345))
        finally:
            if old is None:
                os.environ.pop("COPILOT_AGENT_SESSION_ID", None)
            else:
                os.environ["COPILOT_AGENT_SESSION_ID"] = old

    def test_cross_family_and_parallel_cap(self):
        lane_sid, review_sid = "dddddddd-1111-2222-3333-444444444444", "eeeeeeee-1111-2222-3333-444444444444"
        self.log(lane_sid, [{"type": "session.start", "data": {"selectedModel": "claude-opus-5.5"}}])
        self.log(review_sid, [{"type": "session.start", "data": {"selectedModel": "claude-sonnet-5"}},
                              {"type": "subagent.selected", "data": {"agentName": "architrave:adversarial-judge"}},
                              {"type": "assistant.message", "data": {"content": "Verdict: PASS"}}])
        lane = {"req ids": "REQ-01", "state": "done", "session id": lane_sid}
        reqs = {"REQ-01": {"status": "accepted", "evidence": f"commit abc; review: {review_sid} PASS"}}
        self.assertEqual(self.gate.lane_review_gaps(lane, reqs, strict=True), [])
        self.assertEqual(self.gate.lane_review_gaps(lane, reqs, strict=True, cross_family=True), ["REQ-01 (same model family)"])
        unlogged = dict(lane, **{"session id": "-"})
        self.assertIn("cross-family unverifiable", self.gate.lane_review_gaps(unlogged, reqs, strict=True, cross_family=True)[0])
        self.log(lane_sid, [{"type": "session.start", "data": {"selectedModel": "gpt-6-sol"}}])
        self.assertEqual(self.gate.lane_review_gaps(lane, reqs, strict=True, cross_family=True), [])
        self.log(lane_sid, [{"type": "session.start", "data": {"selectedModel": "gpt-6-sol"}},
                            {"type": "session.model_change", "data": {"newModel": "claude-opus-5.5"}}])
        self.assertEqual(self.gate.lane_review_gaps(lane, reqs, strict=True, cross_family=True), ["REQ-01 (same model family)"],
                         "a mid-session switch to the reviewer's family counts")
        self.log(lane_sid, [{"type": "session.start", "data": {"selectedModel": "auto"}}])
        self.assertIn("unverifiable", self.gate.lane_review_gaps(lane, reqs, strict=True, cross_family=True)[0], "auto may route anywhere")
        self.log(review_sid, [{"type": "subagent.selected", "data": {"agentName": "architrave:adversarial-judge"}},
                              {"type": "assistant.message", "data": {"content": "Verdict: PASS"}}])
        self.assertIn("cross-family unverifiable", self.gate.lane_review_gaps(lane, reqs, strict=True, cross_family=True)[0])
        for value, expected in ((5, (5, None)), (25, (20, None))):
            self.assertEqual(self.gate.parallel_cap({"workers": {"maxParallel": value}}), expected)
        for bad in (0, -1, True, "8"):
            self.assertIsNotNone(self.gate.parallel_cap({"workers": {"maxParallel": bad}})[1], bad)


if __name__ == "__main__":
    unittest.main()
