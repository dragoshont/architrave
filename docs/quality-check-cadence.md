# Quality cadence and scoped session hooks

## Current task workflow

The SPEC/REQ completion barrier is retired. Copilot registers only startup
guidance and advisory read/search loop detection. Retained `pre-tool-use`
commands return `{}` without reading or changing old declarations, including
when their requirements file has moved. They do not grant permission or prove
delivery; normal host permissions, owner stops and truthful verification remain.
Use `tasks.md` for current work. Do not recreate SPEC.md or repair old evidence
just to close a turn.

Architrave does not install or refresh automatic PostToolUse quality commands.
**Executable logic remains:** profile/config validity, existing configured
design-source/map/token JSON validity and configured product-copy rules.
Missing optional references remain non-blocking.

Agents and the lead skill MUST explicitly run:

```text
python gates\gate_runner.py quality-gate
```

Run after relevant config, referenced design JSON or configured product-copy
changes, and final integration. Retain actual exit/output proof; mandatory
failure blocks completion. Use the supported Python interpreter/native paths.
Targeted build/test and configured verification remain required, not full suites
each turn. Honor an owner's no-CI directive; local evidence is not a hosted run.

Prose alone **does not guarantee identical automatic scheduling**. Assurance is
executable validators, explicit checkpoint evidence, focused coverage and
required configured checks. Host permissions and human approvals remain
host-owned; explicitly invoked native tools retain their admission, source and
evidence checks.

## Compact default-session bootstrap

The Copilot plugin's `plugin.json` references root `hooks.json`. Its command
registrations are `sessionStart` and a read/search-only `postToolUse` matcher,
both running `gates/session_guard.py`. No `task_complete` matcher is registered.
`sessionStart` returns only `additionalContext` (at most 140 words), pointing
to that installed kit's skill and canonical lead paths. It does not inject the
whole contract, submit a prompt, start a board, change permissions or write
state. The default agent loads details on demand.

For non-trivial direct or coordinated work the lead uses tasks.md and opens
one tasks board when available (`docs/program-board.md`). Read-only/trivial work
and assigned children/reviewers do not start recursive boards. An unavailable
canvas is reported, not replaced with invented observations or an approval gate.

## Automatic repeated-investigation detection

The `postToolUse` hook observes successful `view`/`read_file`, `glob`,
`grep`/`rg`, `web_fetch`, `web_search` and `semantic_code_search` results.
On the fourth identical request/result within the latest 24 observed reads or
searches it returns **only** `additionalContext`. Copilot appends this nudge to
the tool result on the same turn; the original result remains unchanged.
Interleaved reads count, and changed output resets the count for that request.
A different query or range is a different request. An edit or file touch does
not by itself prove progress or reset the detector.

The same hook receives `powershell`/`bash` results but ignores ordinary commands.
Only a standalone `Start-Sleep -Seconds/-Milliseconds <number>` or
`sleep <duration>` is an additional signal. The first such observation can
emit an advisory to report readiness and yield for an ownership/host message,
not manufacture activity with more shell sleeps. Durations and output text
share one wait fingerprint so changing them cannot produce repeated reminders.
The existing 24-observation window and 12-observation cooldown bound both kinds
of signal. Necessary deliberate backoff and condition-based readiness polling
remain valid; the hook never cancels a real command or changes permissions.

The reminder directs the agent to reuse findings and take the next authorized
action, or name the exact missing fact or hold. It explicitly preserves necessary
research, read-only assignments, owner stops and host permissions. It never
denies tools, forces code, invents approval stages, marks work complete or starts
another turn. Four repetitions is a heuristic signal, not proof of a stall or
a deadline to produce code.

One reminder is emitted per unchanged request/result while retained in the
window, with at least 12 observed reads/searches between reminders. This avoids
turning the remedy into another reminder loop. The per-session cache is
`<COPILOT_HOME>/session-state/<uuid>/files/architrave-loop.json`, accompanied by
a stable `.lock` file. Only SHA-256 fingerprints of cwd, agent identity, tool,
arguments and result are retained, not their plaintext. Different sessions,
working directories and agent identities do not share repetition counts.
The cache retains at most 24 observations and 24 reminder fingerprints;
atomic replacement and OS locking serialize concurrent hook processes.
It survives session resume and compaction without reading transcripts, touching
repository files or changing canonical Run/delivery state.

Malformed input, an unreadable/corrupt cache or lock contention beyond two
seconds produces an explicit, input-redacted monitoring-unavailable advisory,
not a denial. The command has a five-second host timeout. These failures do not
silently establish that a session is making progress.

This is bounded repetition/wait detection, **not semantic supervision**. Ordinary shell
commands, unknown tools, changing read output, different read arguments and model-only
planning loops are not detected. A host may disable or skip hooks, and the model
may ignore a nudge. An installed plugin must actually load this registration;
building a new archive does not refresh already-running sessions. Process tests
prove the packaged detector and protocol, not live-host loading or agent recovery.

## Legacy explicit delivery checks (not registered as hooks)

The following describes the retained optional `delivery-audit` commands and
their historical completion policy. It is not the current task workflow, does
not run automatically, and is not required for `task_complete`.

The adapter locates the declaration only at the current session's
`<COPILOT_HOME>/session-state/<uuid>/files/architrave-delivery.json`;
`COPILOT_HOME` defaults to `~/.copilot`. File presence declares non-trivial
work. There is no `active=false` escape: both `prepared` and `sealed`
`architrave.delivery.v1` reports reach `delivery_check.check_session(repo, uuid)`.
Completion of active work requires current accepted sealed evidence. This is
an evidence artifact, not another requirements ledger.

New declarations carry explicit source/dependency paths. Closure via
`requirements --done --delivery-session <uuid>` checks that slice and its relevant
blockers, not unrelated REQs/lanes; unscoped `--done` keeps program-wide meaning.
Relevant config/docs and source drift still invalidate evidence. Legacy declarations
without source paths retain full-repository freshness. Unchanged amendments can
retain per-REQ evidence and original owner cutoffs, but never aggregate review.

The checker may retire a sealed scope only with `sealed_at`, a verified
digest-bound reviewer PASS and a later actual `session.task_complete` event.
A new non-trivial declaration archives that completed report; active declarations
cannot be overwritten. An earlier unrelated completion or an author-written
inactive flag cannot retire prepared/unreviewed work.
For later read-only follow-ups the hook accepts ordinary nonempty summaries;
legacy follow-up labels are optional, not another completion prerequisite.
It still rejects recorded edits after original completion. It does not rerun historical acceptance merely due to
unrelated checkout churn. Explicit delivery checks still revalidate all bound
evidence; the hook-only exception grants no new delivery acceptance or authority.

An active declaration can instead use `delivery-audit --pause blocked|waiting|handoff`
with a one-line reason and actual `--evidence` files. This is an honest non-delivery
terminal, never acceptance. The hook requires the exact printed non-delivery summary
and unchanged source/owner/evidence identities, so a successful-delivery summary
cannot accompany a pause. Automatic reminders leave it paused. `--resume` is a
deliberate same-scope transition; changed scope requires a newer owner-bound amendment.
`--seal` alone cannot escape a pause. See `docs/delivery-authenticity.md` for fields
and limits; no state transition changes host permissions or repository REQ status.

No declaration returns `{}` without importing the checker. An existing
malformed/unreadable report, missing or stale required evidence (including
scoped board observation), or import/checker failure denies `task_complete`
with `permissionDecision: "deny"` and `permissionDecisionReason`. Failures name
the operation and exception type/OS error code without echoing raw inputs or
exception messages that might contain secrets. Accepted evidence returns `{}`,
not `allow`: normal host permissions still apply. The hook never denies
unrelated tools, treats summary text as delivery evidence, rewrites results, logs
prompts, grants permission or edits global user configuration.

This is a **scoped acceptance barrier, not complete enforcement**. It cannot
ensure every non-trivial task self-declares, prevent an agent with file access
from forging/removing local evidence, or govern a host that skips completion
tools or disables hooks. Copilot command errors fail closed for `preToolUse`,
but **command timeouts fail open**, including policy hooks; warnings do not
constitute acceptance. No `agentStop`/`subagentStop` forced-continuation loop,
generic PostToolUse quality polling or automatic permission approval is used.
Retain explicit verification and the `requirements --delivery-session` boundary.
Explicit edit events can expose renewed mutation after completion; arbitrary
shell effects and undeclared work are not inferred. A read-only summary is a
claim constrained by observed events, not a permission barrier around every tool.

## Host compatibility

This package targets **Copilot command hooks**, not Claude hook semantics.
The registered camelCase events accept `sessionId`/`toolName`; the adapter also
understands Copilot's PascalCase aliases with `session_id`/`tool_name`.
Those aliases still use Copilot's top-level output schema. Claude uses nested
hook registrations and `hookSpecificOutput`; snake-case input support is not
Claude compatibility. The Claude manifest has no hook registration, and no
`hooks/hooks.json` default-discovery file is added. Other hosts retain the
installed stanza/skill guidance without a claimed completion barrier.

Copilot expands `${PLUGIN_ROOT}` in the packaged `bash`/`powershell` command
paths before invocation. These are interpreter commands, not new shell
entrypoint files or guessed cache paths. Python must already be available;
the adapter never installs it. Plugin load, host hook support and actual
fresh-session bootstrap must be checked on the target host after installation.
Protocol-shaped subprocess checks and explicit checker-result unit tests prove
adapter behavior only, not live-host loading or provider execution.

Hook output contract rechecked 2026-11-09 for `postToolUse`/`additionalContext`;
other compatibility sources checked 2026-10-29:
[Copilot hooks reference](https://docs.github.com/en/copilot/reference/hooks-reference),
[Copilot plugin reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference),
[Microsoft's client-specific hook paths and substitutions](https://github.com/microsoft/GitHub-Copilot-for-Azure/blob/main/docs/hooks.md),
and [Claude hooks reference](https://code.claude.com/docs/en/hooks).

## Installer safety

Install and update leave user-owned hooks and host permissions untouched.

Installer ownership is held on an OS-locked descriptor through initialization,
commit and recovery. Empty, partial or unreadable ownership requires manual
recovery, never a guessed dead PID. Known dead ownership is reclaimed in place
only while locked and after file-identity/content checks; each owner publishes a
nonce. Changed ownership is preserved, not blindly unlinked or used to roll back
another transaction.
Create-only scaffolds keep that intent through commit and rollback. Publication
uses atomic no-clobber linking; a late-created config/setup file is preserved
and fails the transaction explicitly. Rollback removes only the unchanged
transaction-owned creation, not a competing destination.
