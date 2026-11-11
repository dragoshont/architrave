<!-- Managed by Architrave; edit the kit. -->
## Architrave

For non-trivial work use the `architrave` skill or adopted
`.github/agents/architrave.agent.md`, not both copies.
That lead contract owns delegation, verification and stop rules.
If copied alone, follow repository instructions without claiming adoption.
Read-only questions and trivial edits need no board or sidebar.

Development loop: one case, acceptance/design, focused checks, authorized commit;
inspect facts and hold consequential unresolved choices for a scoped decision; all code
ready, then two independent reviews; fix findings via task corrections before
authorized deployment; restore case/phase after interruptions.

Use `python harness/architrave_cli.py state` (`docs/lifecycle-state.md`):
import tasks.md after ownership reconciliation, then use state as sole authority.
Read scoped context before dispatch/resume; preserve owner-goal coverage, sources and acceptance.
Statuses are blank, In progress and Code ready.
Do not create SPEC.md, REQ rows or delivery declarations for routine work.
Open/read one tasks board when available (`docs/program-board.md`).
Report unavailable/denied canvas without blocking independent authorized work;
children/reviewers reuse parent scope.
Build behavior first; show evidence.
Host permissions and scoped grants/holds remain binding; infrastructure/runtime
mutation defaults to deny. Preserve secrets and uncertain-side-effect recovery.
Copilot hooks bootstrap and nudge repeated-read loops; completion is not gated by SPEC.
no automatic PostToolUse quality hooks.
