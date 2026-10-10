<!-- Managed by Architrave's Python installer; edit the kit, not this block. -->
## Architrave

Read `architrave.config.json` when present. The plugin works without repo
initialization; if this stanza is copied without the rest of the kit, ground
work directly in repository instructions and sources, and do not assume gates
or durable Run support are installed. Use the `architrave` skill/agent for
non-trivial work; its small core is the canonical mission/worker/stop contract.
Work directly for cheap single-lane changes. Host sessions, context, worktrees,
permissions, lifecycle and model settings remain host-owned.
For independent implementation tracks on a non-trivial task, prefer coordinated
sidebar sessions when the host exposes them; give each a disjoint owned scope
and integrate/verify in the parent. If unavailable, use the client's native
subagent tool for a bounded independent packet when available. Keep one-trace
or shared-patch work direct.

Ground in this repository; reproduce rather than reinvent. A knowledge profile
uses docs/scripts/schemas/tests, never an invented UI lane. UI uses configured
design source/map/tokens and platform guidance; backend uses its real contract.
Load those packs only for the relevant task.

Infrastructure/runtime mutation defaults to deny; source edits follow the
user's mandate and host permissions. Never expose secrets, bypass human checkpoints,
manually edit Run state, blindly replay uncertain side effects or mistake
worker completion/compile for product PASS. With adopted durable support,
recovery and evidence use
`harness/architrave_runtime.py`; details in `knowledge/runtime-v2.md` on demand.
Run targeted checks first; required gates must pass before completion.
No automatic PostToolUse quality hook is registered. In an adopted repo, MUST run
`python gates/gate_runner.py quality-gate` after relevant config, referenced
design JSON or configured product-copy changes, and at final integration.
Retain real exit/output proof and stop on mandatory failure. This preserves the
executable quick validators, not identical automatic scheduling. Architrave
registers no tool-blocking hooks; host permissions remain host-owned and explicit
native tool admission/source/evidence checks remain.
Consult architrave:cto at start and on stall inline; schedule the smallest
demonstrable product slice, not harness ceremony. Keep Run/worktree/key artifacts
private and ignored. No duplicate transcripts, plans or status files.
