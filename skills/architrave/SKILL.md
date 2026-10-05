---
name: architrave
description: Use for non-trivial repository changes that need config-first intake, option analysis, phased implementation, deterministic gates, and independent semantic review. Do not use for a one-line mechanical edit or a question that needs no repository change.
---

Run the repository's Architrave workflow as the lead conductor.

1. Read `AGENTS.md`, `architrave.config.json`, and `knowledge/runtime-v2.md`.
   Consult architrave:cto at start and on stall (or apply the `architrave-cto`
   checklist when the host cannot nest agents).
2. Create or resume canonical `architrave.run.v2`; do not manually edit Run
   state or events. Treat the phase ledger as a projection. Declare the failing
   user-visible criterion with `--primary-criterion`/`primary-set`.
3. Under `approved-program`, continue dependency-ready, in-scope tasks without
   asking at internal phase boundaries. Stop only for policy, failure, resource,
   or typed external checkpoints.
4. Apply YAGNI without weakening diagnosis, validation, security,
   accessibility, recovery, capability truth, or real product evidence.
5. Request `architrave_tournament` only for explicit tournaments or material
   architectural, security, migration, data-loss, infrastructure, runtime, or
   recurring-failure risk.
6. Route bounded WorkPackets through the native worker adapter and isolated
   worktrees. Worker `done` is candidate completion; the coordinator gates it.
7. Scale gates by R0-R4. Complete R3/R4 semantic gates require independent GPT
   and Claude families; R4 also requires security/policy review.
8. Mutation is default-deny. An explicit scoped Run grant may authorize deploy
   or runtime mutation; record checkpoint, receipt, and live verification.