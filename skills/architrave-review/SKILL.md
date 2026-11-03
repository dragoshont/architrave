---
name: architrave-review
description: Explicitly run a read-only Architrave rubric review of a frozen proposal or implementation and return PASS, REVISE, or FAIL with evidence.
---

For a session/run performance review, use `docs/session-audit.md`: collect
explicitly selected real host sessions (optionally one turn) with
`python "<kit-root>\harness\architrave_cli.py" session-audit collect`, assess
original goals, quality, tokens and approach using the packet's review prompt,
then save the source-bound advisory analysis with `session-audit record` for
the existing scoped board. Resolve kit root from this loaded skill (`../..`).
Keep private packets in host session files. Internal invocation uses the same
path at a task boundary; no extra supervisor, automatic every-turn audit,
instruction changes, permission changes or new completion gate.

The review remains read-only. If the owner explicitly approves applying a
chosen finding, the existing lead applies critical-path recovery from
`knowledge/execution-policy.md`, using the current goal, exact hold and next
observable action. Reuse the owning session and host messaging, not another
coordinator. Verify subsequent execution separately from sending the correction;
an audit finding or approval never expands existing operation permissions.

Prefer the host-native reviewer for a proposal/implementation review. When the host provides one (GitHub Copilot
`rubber-duck`, or `code-review` for diffs), run the semantic review through it
instead of launching `adversarial-judge`, so there's never a double review.
Pass the frozen review subject, original owner messages and attached reference assets,
acceptance criteria, `gates/rubric.md`, and deterministic evidence.
Require one PASS/REVISE/FAIL verdict with findings
by severity and uncovered requested criteria. Use the rubric's compact output;
do not repeat the contract or score irrelevant dimensions.
Compare reference identity, intended rendered width and component coverage
separately from prose; unavailable sources remain unverified, not satisfied by
an agent-narrowed SPEC. Do not start a recursive program board or redeclare
the parent's scope.

`adversarial-judge` (`architrave_judge` in Codex) stays the rubric source and
the fallback when no native reviewer exists. The Codex role is advisory and
inherits parent skills, MCP, and permission policy.

For an adopted canonical Run, record its result with `gate-record --type semantic --reviewer
host-native|architrave-judge --family <model family> --effort <requested>:<mapping>`.
For ordinary direct work, return the review in conversation; do not create a
Run, receipt or report solely to record a review. This does not waive required
source-bound admission for an existing Run or authorized external operation.
For R3/R4 request `effort: high`, mapped only to what the host exposes (auto
tier or `reasoning_effort`), else none; never name a model. One independent
review suffices. Only when `review.crossFamily` is true (building Architrave
itself) does R3/R4 need two different families: get the second through a model
override on the same native reviewer when the host allows it, otherwise through
`adversarial-judge`. Never run two reviews of the same family; the runtime
rejects a duplicate same-family R3/R4 PASS (`DUPLICATE_REVIEW_FAMILY`).
