# Long programs, in plain language

This page explains how Architrave keeps a long, multi-session build on track and
why. It summarises the research behind version 0.18.0 (sources at the end).

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

Set `"requirements": "SPEC.md"` in `architrave.config.json`. The file is a simple
markdown table (copy `kit/examples/requirements.md`):

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
instructions. You can run up to 8 helpers (`workers.maxParallel`, default 3).

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

### "Done" means done

```sh
python gates/gate_runner.py requirements --done
```

This passes only when every active requirement is accepted with evidence.
Progress is measured by accepted requirements, not by how many check-ins or
reports were produced.

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

Architrave ships these well-maintained public skills, unchanged and with their
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
