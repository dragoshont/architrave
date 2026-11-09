---
name: architrave
description: "Spec-driven supervision for non-trivial repository changes: testable requirements, direct work or bounded children, and risk-scaled verification. Not for one-line edits or read-only questions."
---

Resolve the plugin root from this skill's reported directory (`../..`), not cwd
or guessed caches. Read `agents/architrave.agent.md` there once, unless that
contract is already loaded. It is the canonical lead contract; do not load both
plugin and adopted copies. Repository instructions and the user's mandate apply.
Use the lead's **Development loop** and restore its phase after interruptions.

Work is spec-driven: record owner outcomes as REQs with observable acceptance in config `requirements`
(else `SPEC.md`); finish with accepted evidence. Follow **Specifications** in
`knowledge/execution-policy.md`.

Declare scope and open and read one scoped program board before implementation
(`docs/program-board.md`), including direct work. Assigned
children/reviewers reuse their parent's scope.

Never add an approval stage or re-ask to proceed with authorized work unless
the owner requests it. Honor actual host permissions and explicit stops; do
not extend grants to uncovered operations.

Plugin-only use does not require repo initialization. Read
`architrave.config.json` if present; never create config, gates or Runs for
missing adoption. Do not preload every pack; load only relevant sources.
