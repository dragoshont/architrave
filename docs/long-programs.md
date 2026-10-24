# Long programs, in plain language

This page explains how Architrave keeps work on track, from a one-hour task to a
multi-week, multi-session build, and why. Since 0.20.0 this is the default for
every non-trivial task, not a special long-program mode: the requirements file
is the spec. It summarises the research behind versions 0.18.0–0.20.0 (sources
at the end).

## The problem we hit

A multi-week program ran across 6–8 sessions and went wrong. The requirements
lived in one session's private notes. Several sessions kept their own competing
lists. Changes the owner made mid-flight were said in chat and then forgotten
when the conversation was compressed. Sessions went stale and had to be
restarted, and work was duplicated.

Every serious team that publishes on long-running agents (Anthropic, OpenAI,
Thoughtworks/Martin Fowler, Cognition) describes the same cure:

1. **Keep the plan in a file in the repository, not in anyone's memory.**
2. **Give every item a test that decides "done", one the agent cannot argue past.**
3. **Leave a short handoff note so the next session starts in minutes.**
4. **Let one writer own each piece of work; escalate conflicts to a human.**

## What Architrave now does

### One requirements file (the "ledger")

Architrave reads `SPEC.md` at the repository root when it contains a REQ table
(`| ID | ... | Status |`), or the file named by `"requirements"` in
`architrave.config.json`. A prose `SPEC.md` is left alone. The file is a simple markdown table
(copy `kit/examples/requirements.md`). A small task needs one to three rows;
read-only questions and one-line edits need none. `checks` and `quality-gate`
validate the file whenever it exists, and a Run refuses tasks that are not bound
to open REQ ids and refuses to finish while they are not accepted.

| ID | Requirement | Acceptance | Owner | Status | Evidence |
|---|---|---|---|---|---|
| REQ-01 | Library lists owned titles | `make test-library` passes | ui-lane | in-progress | |

- **Acceptance** says how to prove it. No acceptance, no dispatch.
- **Status** is one of `open`, `claimed`, `in-progress`, `blocked`, `accepted`,
  `superseded` or `withdrawn`.
- **Accepted needs evidence**: a commit, a test log or a screenshot path.

Check it any time:

```sh
python gates/gate_runner.py requirements
```

### Changes of mind are recorded, not just said

When you change your mind ("actually, make the grid adaptive"), the agent adds a
**correction row** before doing anything:

| ID | Type | Target | Change |
|---|---|---|---|
| C-01 | supersede | REQ-03 → REQ-04 | fixed columns replaced by adaptive grid |

Types are `add`, `revise`, `retract` and `supersede`. A requirement can only be
marked superseded or withdrawn if a correction explains why. This is the fix for
"I told it last week and it forgot". Research shows that summaries of a long
conversation keep only a fraction of side instructions, so chat alone is not
enough.

### No duplicate workers

Before a new helper session starts on some requirements, the coordinator runs:

```sh
python gates/gate_runner.py requirements --claim REQ-01,REQ-04 --owner ui-lane
```

The command refuses if another lane already owns one of those items, or if it is
already accepted, superseded or withdrawn. When it passes, its output (each
item's acceptance test plus any corrections) becomes the start of the helper's
instructions. It writes the owner and changes `open` to `claimed`, preserving
already active statuses. The single coordinator commits that change before
dispatch; this is not a cross-branch lock. A second lane on that committed
ledger fails. An adopted Run still owns its own cross-worktree reservations.
You can run up to 8 helpers (`workers.maxParallel`, default 3).

### A handoff note instead of a lost conversation

The file ends with a `## Handoff` section of three lines:

```
Next: what to do next
Failed approaches: what was tried and did not work, and why
Verify: the command that shows the current state
```

The gate fails if any line is empty. A fresh session reads this note and the git
log, runs `Verify`, and picks one requirement. Restarting a stale session then
costs minutes instead of hours, and nobody retries a dead end.

Before a coordinator hands over to a fresh session, commit the requirements file
and run:

```sh
python gates/gate_runner.py requirements --handoff
```

It fails if the file has uncommitted changes, or if this checkout's git-ignored
SDD ledger (`.superpowers/sdd/*/progress.md`) recorded progress after the last
commit of the file, and it warns about such a ledger in another worktree. The
successor starts from that commit, runs
`python gates/gate_runner.py requirements --handoff --expect <predecessor-sha>`,
and continues the same file. `--expect` requires that commit in HEAD's ancestry
(unknown, unrelated and stale commits fail); it does not prove semantic evidence.
Notes kept only in one worktree are lost or duplicated when work moves
to another worktree or branch; Anthropic's harness, Spec Kit, Kiro, Codex
ExecPlans and beads all keep this state in committed files for that reason.

### A small kickoff, grounded in current work

Link the Architrave contract rather than copying its workflow, verification and
permission rules. Supply the objective, requirements entry point, component refs
and project-specific decisions. Keep component identity in the existing map and
requirements/Handoff: canonical repository, execution side/process, non-default
working branch/base and safe write remote. The components gate checks local push
targets; it does not resolve GitHub renames or prove which implementation ran.

On restart, verify those refs and acceptance evidence. Historical audits remain
provenance, not current runtime proof. Name a working precursor separately from
its intended generated/product replacement, and bind evidence to the path that
actually ran. Existing real-flow parity rules protect the baseline.

Retire only assigned schedules whose work is accepted, superseded or whose
owner is archived, through authorized host controls; preserve source/evidence
and do not revive retired monitors. See the Context section of
`knowledge/execution-policy.md` for identity, evidence and lifecycle boundaries.
Saving or replacing a session automation prompt resets its next run time; edit the schedule rarely.

### "Done" means done

```sh
python gates/gate_runner.py requirements --done
```

This passes only when every active requirement is accepted with evidence.
Progress is measured by accepted requirements, not by how many check-ins or
reports were produced. The gate checks non-empty evidence, not its truth:
CTO oversight verifies current source/commit and primary-criterion observations;
accepted-count growth alone proves nothing.

### Conflicts go to the owner

If two instructions conflict, or a test turns out to be wrong, the item is
marked `blocked` and comes back to you with a concrete question. Helpers do not
quietly negotiate it away between themselves.

### Code beats notes

If the requirements file and the actual code or tests disagree, the code and
test output win. The agent fixes one of them and records a correction, instead
of following a stale note.

### Learning that sticks

When the same mistake happens twice, Architrave prefers to turn the lesson into a
check (a gate, test or acceptance line) rather than another paragraph of
instructions. Research found that executable rules beat written advice, and
that long instruction files cost more without helping much. Agents may
*propose* new skills or rules, but a change only merges with a before/after test
and your approval. Rules that a newer model no longer needs get removed.

## Bundled third-party skills

Architrave ships these well-maintained public skills with their
licences. The README lists sources and licences.

- `verification-before-completion` and `systematic-debugging` from
  [obra/superpowers](https://github.com/obra/superpowers) (MIT): evidence before
  claims, root cause before fixes.
- `skill-creator` and `webapp-testing` from
  [anthropics/skills](https://github.com/anthropics/skills) (Apache-2.0): skill
  evaluation and browser end-to-end testing.
- The `converge` idea from [github/spec-kit](https://github.com/github/spec-kit)
  (MIT) is mirrored here by `requirements --done`.

It also ships `subagent-driven-development` and `writing-skills` (obra/superpowers,
MIT). Avoid unbounded "keep looping until done" plugins, and audit any other
third-party skill before installing it.
The SDD Setup/resuming guidance is locally adapted to make its scratch ledger a cache
subordinate to the committed requirements Handoff.

## Sources

- Anthropic, *Effective harnesses for long-running agents* (2025-11-26); *Building
  a C compiler with parallel Claudes* (2026-02-05); *Harness design for
  long-running apps* (2026-03-24); *Multi-agent systems* (2026-08-13);
  *Equipping agents with Agent Skills* (2025-10-16).
- OpenAI, *Harness engineering* (2026-02-11); *Run long-horizon tasks with Codex*.
- martinfowler.com: Böckeler, *Harness engineering* (2026-04-02); Morris, *Humans
  and agents* (2026-03-04); *An accidental blackboard* (2026-09-02); *Are
  harnesses worth the cost?* (2026-10-13).
- Cognition, *Multi-agents working* (2026-04-22).
- arXiv: interruption handling (2604.00892), constraint loss under compaction
  (2606.22528, 2608.11242), coordination via claims (2608.23740), escalation
  channels (2608.29460), executable lessons (2609.32965), instruction-file cost
  (2602.11988, 2610.30571), skill selection and safety (2610.18522, 2608.21929).
