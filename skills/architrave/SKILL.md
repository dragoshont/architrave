---
name: architrave
description: "Spec-driven supervision for non-trivial repository changes: repository requirements with testable acceptance first, direct work or bounded native children traced to REQs, durable policy/evidence and risk-scaled verification. Not for a one-line edit or a read-only question."
---

Resolve the plugin root from this skill's reported directory (`../..`), not cwd
or guessed caches. Read `agents/architrave.agent.md` there once, unless that
contract is already loaded. It is the canonical lead contract; do not load both
plugin and adopted copies. Repository instructions and the user's mandate apply.

Work is spec-driven: record the request as REQ rows with testable acceptance in
the requirements file (config `requirements`, else `SPEC.md`), trace work to
them, and finish only when they are accepted.

Plugin-only use does not require repo initialization. Read
`architrave.config.json` when present; missing adoption is not a reason to
create config, gates or Runs. Do not preload every pack: use the lead contract's
disclosure table only for the operation at hand.
