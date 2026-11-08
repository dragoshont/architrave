# Resuming From an Existing Ledger

Part of superpowers:subagent-driven-development. This plan's workspace
already has a ledger at `<workspace>/progress.md`.

Read the committed requirements Handoff and git log first. This ledger is
only a cache: validate its task/commit references against REQ Evidence before
using them. Fold newer uncommitted work into REQ Evidence/Handoff and commit;
do not discard it or dispatch from a conflicting cache.

If the ledger's first line names your plan file and the committed evidence
agrees, tasks with a `Task <N>: complete` line are DONE — do not re-dispatch them; resume at the first
task without one. A task whose last line is a fix round is mid-loop:
resume the loop at the next round. A ledger whose first line names a
different plan file — or a stray ledger at the old flat path
`.superpowers/sdd/progress.md` — is another plan's progress: leave it in
place. Rebuild only your plan's optional cache from the committed Handoff,
never a second source of truth.
