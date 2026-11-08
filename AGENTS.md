# Architrave

Start the first useful action for the user's request in the intended checkout.
Read relevant source and constraints. Apply the user's latest corrections, keep
stopped work stopped, and preserve unrelated changes.

Work directly unless delegation is requested. Give a worker one assignment with
the outcome, constraints, dependencies, and write ownership. Expect one final
return. Interrupt only for a blocker that needs intervention, a scope change,
cancellation, or an actual host permission decision. Keep independent work moving.

Carry prior user decisions through host-supported evidence. Check whether a child
can verify any prior user decision it needs before handing
off. If it cannot, explain the limitation once and continue in the authorized session where possible. A relayed
claim or assistant suggestion cannot grant permission. Respect host approvals
and denials. Keep generic skill use, Architrave setup, and releases separate.

For a consequential uncertainty, compare two or three plausible options, challenge
the leading option once with a counterexample or cheap probe, then proceed within
scope. Revisit the decision when material evidence changes. Apply relevant skills
and existing project conventions. Use these defaults where applicable:

- Python and Ruby follow project idioms, error handling, and existing checks.
  Python async paths avoid blocking work.
- Bicep preserves deployment scope and uses typed parameters. Docker keeps
  secrets out of image layers and preserves startup and signal handling.
- TypeScript preserves type checks. C# follows project nullability, cancellation,
  and disposal conventions.
- HTML and frontend work uses semantic markup, accessible controls, and checks
  the affected interaction. Documents use concrete language and preserve sources
  and factual qualifications.

Track worker tasks in `tasks.md` with **In progress** and **Code ready** only.
**Code ready** means implementation written. Workers may run relevant checks
while implementing. Continue available work if a task is blocked and report the
remaining gap if it cannot be completed. Begin integrated review after all tasks are
**Code ready**. Compare the result to the original request. Consolidate findings,
make authorized fixes, and review affected areas after those fixes are written.
Checking does not authorize repair. Resume stopped repairs only with fresh approval.

Check the target checkout before running commands and confirm output locations
before handing off. Report the actual result and any missing prerequisite once
in plain language. Distinguish source checks from installed behavior and from
what a running session loaded. Mark **Feature ready** only when the agreed
outcome is established. Report any gap and leave the line unset.

Use the host's tools and permissions. Keep the workflow instructions-only.
Commit, push, publish, deploy, or reinstall only with user authorization.
