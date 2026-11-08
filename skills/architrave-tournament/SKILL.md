---
name: architrave-tournament
description: Explicitly compare implementation options when the user requests a tournament, or when viable options genuinely differ on material architecture, security, migration, data-loss, infrastructure or runtime risk, or a recurring failure needs a discriminating recovery. Not for routine bounded work.
---

Use the current host's visible `architrave:tournament-analyst` role for an
authorized comparison. Supply the user request, acceptance criteria, governing
repository sources, constraints, evidence and unresolved assumptions. If the
role is unavailable, report that boundary; there is no separate tournament tool
or agent CLI fallback.

Require two to four options with benefits, drawbacks, blast radius, durability,
security/data risk, complexity, and verification burden. The options always
include a "do nothing" baseline and a "smallest viable" option alongside the
others, typed as `DO_NOTHING` and `SMALLEST_VIABLE`, plus `winner` and
`winnerBeatsDoNothing`, `task` (the original decision task id) and `source`
(the compared revision). Return one recommended plan, explicit non-goals, and
why the chosen
option beats doing nothing.

The optional `python "<kit-root>/harness/architrave_cli.py" tournament-review
--result <json> --task <id> --source <rev>` checks result shape and supplied
bindings only. It cannot authenticate the analyst, verify tradeoffs or authorize
another attempt. Keep the original task's budget and failure identity in the
existing owning host/Run; do not create a separate allowance ledger or reset a
budget by renaming the task. The retired `--allowance` flag refuses without
writing files. Turn the observed recommendation into one disposition and next
action within existing authority. Automatic cross-successor comparison
accounting remains unqualified.