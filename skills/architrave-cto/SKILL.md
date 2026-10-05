---
name: architrave-cto
description: CTO checklist for an Architrave Run. Use at Run start, at each checkpoint, and on any stall to keep the work outcome-driven and lean and to issue one concise correction.
---

Check the Run against each item. Report only the items that are off, then give
one correction: objective, last evidence, blocker, next cheapest action.

1. **Outcome over ceremony.** Judge by the user-visible criterion ("login
   works"), not by CI, pin, receipt, or review counts. If N commits or turns
   (default 3) do not touch the failing path, escalate `STALLED_PRIMARY_CRITERION`
   and steer back to that path.
2. **Reference parity first.** Before rewriting working code, diff it against
   the known-working reference and prove parity on the real flow. Hardening
   comes after parity. (Xodus lost two days by not diffing the upstream login.)
3. **Lenient third-party parsing, specific diagnostics.** Ignore unknown fields
   and messages from third-party protocols; fail only on malformed data that is
   actually needed. Every failure names its step and reason (redacted); never
   collapse distinct causes into one generic code.
4. **Lean.** Generated orchestration stays at least 80% smaller than v0.11.0.
   No model-class guidance. Apply YAGNI. No precaution overload, and no new
   verifiers, receipts, or pins for small R0/R1 fixes.
5. **Real product quality.** No mock data or scaffolding in shipping code. Never
   fabricate PASS, auth, or login evidence. The approved design (for example
   Figma) is the shipping UI. Internal spec, status, or evidence language never
   appears in product UI.
6. **Plain talk.** Talk to the owner in plain sentences. No walls of hashes,
   PIDs, or receipts, and no compressed status shorthand.
7. **Approvals persist.** "Touch everything you need" or an approved deploy
   needs no new hold. A graceful-quit failure escalates to SIGTERM after a
   timeout. `ask_user` being unavailable does not mean the user is absent when
   the latest message already gave direction.
8. **No false blockers.** There is no CPU or build lease, so run builds in
   parallel. Clear stale checkpoints instead of waiting on them.
9. **Respect boundaries.** Stop immediately on an explicit stop. Humans handle
   credentials, MFA, and Keychain. Keep privacy and repository boundaries.
10. **Ship it.** Commit and push to GitHub, tag, let release CI publish, and
    reinstall on every host.
11. **Know limits early.** Runs are repo-local: qualify the app repo in its own
    Run instead of stretching another repo's Run.
12. **Push back before building.** Before any new scope, feature, or release
    item, give a KEEP/CUT/DEFER verdict with a one-line reason and record it
    on the task (`task-add --pushback VERDICT:reason`). Ask: Does it spawn paid
    agent work? Does it duplicate an existing tool or host-native feature? Is it
    preview-only or unavailable to some users? Can it be measured from real
    signals? Is there a smaller or do-nothing option? Does it grow the generated
    footprint? Do community signals show the pain is real? This is done inline
    with no extra agent. Use the tournament only when risk is material; it must
    include "do nothing" and "smallest viable" options.
