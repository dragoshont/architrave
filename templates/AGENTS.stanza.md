<!-- Managed by Architrave's Python installer; edit the kit, not this block. -->
## Architrave

Read `architrave.config.json`. Use the `architrave` skill/agent for non-trivial
work; its small core is the canonical mission/worker/stop contract.
Work directly for cheap single-lane changes. Host sessions, context, worktrees,
permissions, lifecycle and model settings remain host-owned.

Ground in this repository; reproduce rather than reinvent. A knowledge profile
uses docs/scripts/schemas/tests, never an invented UI lane. UI uses configured
design source/map/tokens and platform guidance; backend uses its real contract.
Load those packs only for the relevant task.

Mutation defaults to deny. Never expose secrets, bypass human checkpoints,
manually edit Run state, blindly replay uncertain side effects or mistake
worker completion/compile for product PASS. Durable recovery and evidence use
`harness/architrave_runtime.py`; details in `knowledge/runtime-v2.md` on demand.
Run targeted checks first; required gates must pass before completion.
No automatic PostToolUse quality hook is registered. MUST run
`python gates/gate_runner.py quality-gate` after relevant config, referenced
design JSON or configured product-copy changes, and at final integration.
Retain real exit/output proof and stop on mandatory failure. This preserves the
executable quick validators, not identical automatic scheduling; native
permission/scope/depth guards are unchanged.
Consult architrave:cto at start and on stall inline; schedule the smallest
demonstrable product slice, not harness ceremony. Keep Run/worktree/key artifacts
private and ignored. No duplicate transcripts, plans or status files.
