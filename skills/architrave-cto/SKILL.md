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

## On-demand feasibility reset: should we continue?

Trigger only on owner request or an established stall/repeated-failure/budget
signal. Quiet parent activity, mtimes and elapsed time alone are not triggers.
Apply inline: no periodic reviewer, extra model call or fixed review duration.

1. Pause only the implicated lane through supported host steering/cancellation;
   wait for the real owner to settle. Preserve candidates, artifacts, human
   prompts and uncertain-side-effect recovery. Never fake cancellation with
   resume or replay an action. The API refuses active lane leases.
2. Snapshot objective, actual product delta, failed hypotheses, blocker/dependency
   chain, evidence and remaining budget through existing `feasibility-record`.
   No new report. Reported delta is not observed product proof; unavailable
   context, credits or host telemetry is unknown, not zero.
3. Estimate a finite time/turn/output window from uncertainty, risk, dependency
   depth, available evidence and the next discriminating test's cost. Record
   ceilings and ONE-line rationale before starting. Explicit owner
   deadlines/ceilings win; remaining task/parent/global budgets only lower them.
   No universal ninety-minute allowance, reset clocks, silent extensions or
   invented credit headroom. Python clamps; the agent chooses the estimate.
4. Compare **continue / smallest viable / pivot / park** using KEEP/CUT/DEFER and
   existing tournament vocabulary (DO_NOTHING/SMALLEST_VIABLE when needed).
   Record **CONTINUE | BOUNDED_GO | PIVOT | PARK**, evidence, exact next step,
   revisit condition and uncertainty. Pivot requires scoped task/authorized
   objective correction; strategy changes never grant unrelated mutation.
5. Optional ONE independent scoped native review when fresh judgment helps;
   optional ONE discriminating POC with hypothesis, expected observable result,
   finite resources and stop criterion. Neither is mandatory. Both spend the
   same window. No architecture expansion, auth bypass or unsafe defaults.
6. Verify skeptical findings: no overstated zero progress, universal no-go,
   fixture-as-product success or provider failure from human prompt timeout.
   Re-estimate only for substantive evidence/scope changes within the original
   ceiling/deadline. Unchanged evidence cannot renew the window. At expiry stop,
   synthesize **partial** result, retained evidence, blocker and revisit condition.

Direct work keeps this decision in conversation and uses host budget controls,
not a qualification Run. Durable reset dispatch is serial; observed child turns
and retained output bytes accumulate. Missing finished-owner turns block another
dispatch, never imply zero spend. Global Run `turns` are a separate transition
proxy, not model turns. Host cancellation/generation limits remain host-owned;
missing controls are an explicit limitation. Never add a scheduler to compensate.
