# Quality cadence and scoped session hooks

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

The Copilot plugin's `plugin.json` references root `hooks.json`. Its only
registrations are command `sessionStart` and an exact `preToolUse`
`^task_complete$` matcher, both running `gates/session_guard.py`.
`sessionStart` returns only `additionalContext` (at most 140 words), pointing
to that installed kit's skill and canonical lead paths. It does not inject the
whole contract, submit a prompt, start a board, change permissions or write
state. The default agent loads details on demand.

For non-trivial direct or coordinated work the lead records REQs, declares
session scope, then opens and reads one scoped existing program board before
implementation (`docs/program-board.md`). Read-only/trivial work and assigned
children/reviewers do not start recursive boards. An unavailable or denied
canvas must be reported, not replaced with invented observations.

## Scoped completion barrier

The adapter locates the declaration only at the current session's
`<COPILOT_HOME>/session-state/<uuid>/files/architrave-delivery.json`;
`COPILOT_HOME` defaults to `~/.copilot`. File presence declares non-trivial
work. There is no `active=false` escape: both `prepared` and `sealed`
`architrave.delivery.v1` reports reach `delivery_check.check_session(repo, uuid)`.
Completion of active work requires current accepted sealed evidence. This is
an evidence artifact, not another requirements ledger.

The checker may retire a sealed scope only with `sealed_at`, a verified
digest-bound reviewer PASS and a later actual `session.task_complete` event.
A new non-trivial declaration archives that completed report; active declarations
cannot be overwritten. An earlier unrelated completion or an author-written
inactive flag cannot retire prepared/unreviewed work.

No declaration returns `{}` without importing the checker. An existing
malformed/unreadable report, missing or stale required evidence (including
scoped board observation), or import/checker failure denies `task_complete`
with `permissionDecision: "deny"` and `permissionDecisionReason`. Failures name
the operation and exception type/OS error code without echoing raw inputs or
exception messages that might contain secrets. Accepted evidence returns `{}`,
not `allow`: normal host permissions still apply. The hook never denies
unrelated tools, reads tool arguments as acceptance, rewrites results, logs
prompts, grants permission or edits global user configuration.

This is a **scoped acceptance barrier, not complete enforcement**. It cannot
ensure every non-trivial task self-declares, prevent an agent with file access
from forging/removing local evidence, or govern a host that skips completion
tools or disables hooks. Copilot command errors fail closed for `preToolUse`,
but **command timeouts fail open**, including policy hooks; warnings do not
constitute acceptance. No `agentStop`/`subagentStop` forced-continuation loop,
generic PostToolUse quality polling or automatic permission approval is used.
Retain explicit verification and the `requirements --delivery-session` boundary.

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

Contract sources checked 2026-10-29:
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
