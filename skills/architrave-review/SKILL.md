---
name: architrave-review
description: Explicitly run a read-only Architrave rubric review of a frozen proposal or implementation and return PASS, REVISE, or FAIL with evidence.
---

Prefer the host-native reviewer. When the host provides one (GitHub Copilot
`rubber-duck`, or `code-review` for diffs), run the semantic review through it
instead of launching `adversarial-judge`, so there's never a double review.
Pass the frozen review subject, acceptance criteria, `gates/rubric.md`, and
deterministic evidence, and require one PASS/REVISE/FAIL verdict with findings
by severity, uncovered specifications, and unstarted phases.

`adversarial-judge` (`architrave_judge` in Codex) stays the rubric source and
the fallback when no native reviewer exists. The Codex role is advisory and
inherits parent skills, MCP, and permission policy.

Record each result with `gate-record --type semantic --reviewer
host-native|architrave-judge --family <model family> --effort <requested>:<mapping>`.
For R3/R4 request `effort: high`, mapped only to what the host exposes (auto
tier or `reasoning_effort`), else none; never name a model. One independent
review suffices. Only when `review.crossFamily` is true (building Architrave
itself) does R3/R4 need two different families: get the second through a model
override on the same native reviewer when the host allows it, otherwise through
`adversarial-judge`. Never run two reviews of the same family; the runtime
rejects a duplicate same-family R3/R4 PASS (`DUPLICATE_REVIEW_FAMILY`).
