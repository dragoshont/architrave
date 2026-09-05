---
name: architrave-review
description: Explicitly run a read-only Architrave rubric review of a frozen proposal or implementation and return PASS, REVISE, or FAIL with evidence.
---

Request `architrave_judge` with the frozen review subject, acceptance criteria,
`gates/rubric.md`, and deterministic evidence. The Codex role is advisory and
inherits parent skills, MCP, and permission policy.

Require findings by severity, uncovered specifications, unstarted phases, and
one terminal verdict. A Codex result never substitutes for the bounded external
GPT and Claude judge-family results required by Architrave.