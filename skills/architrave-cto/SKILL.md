---
name: architrave-cto
description: Apply the CTO checklist inline at Run start, checkpoint or stall. Return only a concise correction; do not spawn a CTO merely for ceremony.
---

Check inline. Report only what is off, then one correction: objective, last
verified evidence, blocker, next cheapest useful action.

- **Outcome over ceremony:** prove the owner's criterion, not CI/artifact counts.
  Declare its path; three unrelated results/commits raise
  `STALLED_PRIMARY_CRITERION`. Compare an identified working reference first.
- **Lean:** direct work first, <=3 active children, depth one, exclusive mutable
  ownership, compact returns. KEEP/CUT/DEFER verdict with one reason before new
  scope. No daemon, scheduler, provider SDK or transcript layer.
- **Truth:** distinguish observed product/native-host behavior from fixtures,
  hypotheses and unavailable telemetry. Ignore irrelevant third-party fields;
  specific redacted diagnostics for malformed required data.
- **Stop:** two identical failure fingerprints without new evidence stop the
  lane. No unchanged full-gate reruns or review swarms; batch findings. Stop
  spawning at the global budget; cancel superseded owners through the host.
- **Safety:** scoped grants, target identity, human authentication/consent holds,
  receipts and uncertain-side-effect recovery remain mandatory. No secrets.
  Approved operations need no repeated phase approval. Explicit stop is final.
- **Ship:** smallest useful product slice; risk-scaled checks and independent
  review. Commit/push validated scope; publish/tag only with release authority.
  Install only on authorized hosts. Plain owner status, not opaque IDs.

Deep Run, primary-stall, recovery and policy behavior is deterministic Python;
load `knowledge/runtime-v2.md` only when those operations are needed.
