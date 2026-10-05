---
name: architrave-tournament
description: Explicitly compare implementation options for an Architrave run when the user requests a tournament or the lead workflow identifies architectural, security, migration, data-loss, infrastructure, runtime, or recurring-failure risk.
---

Request `architrave_tournament` with the user request, numbered acceptance
criteria, governing repository sources, constraints, evidence, and unresolved
assumptions.

Require two to four options with benefits, drawbacks, blast radius, durability,
security/data risk, complexity, and verification burden. The options always
include a "do nothing" baseline and a "smallest viable" option alongside the
others, typed as `DO_NOTHING` and `SMALLEST_VIABLE`, plus `winner` and
`winnerBeatsDoNothing` (`tournament-review --result` checks the shape). Return one recommended plan, explicit non-goals, and why the chosen
option beats doing nothing. The result is advisory; it does not authorize edits
or runtime mutation.