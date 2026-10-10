# Quality checks without automatic turn hooks

0.14.1 no longer installs or refreshes an automatic PostToolUse quality command.
**Executable logic remains:** profile/config validity, existing configured
design-source/map/token JSON validity and configured product-copy rules.
Optional/missing-reference behavior and public shell/PowerShell/`--hook-json`
quality-gate compatibility are unchanged.

Agents and the lead skill MUST explicitly run:

```text
python gates\gate_runner.py quality-gate
```

Run after relevant config, referenced design JSON or configured product-copy
changes, and final integration. Retain actual exit/output proof; mandatory
failure blocks completion. Use the supported Python interpreter/native paths.
Targeted build/test and risk-scaled CI remain required, not full suites each turn.

Prose alone **does not guarantee identical automatic scheduling**. Assurance is
executable validators, explicit checkpoint evidence, focused coverage and
required CI. Architrave also registers no native tool-blocking hooks. Host
permissions and human approvals remain host-owned; explicitly invoked native
tools retain their admission, source and evidence checks.

## Post-release hooks-only owner update

Only the affected owner runs this at a safe boundary after published kit/new
instructions are available; never interrupt another product/auth/game lane:

```text
python <published-kit>\tools\install_update.py retire-hooks --dry-run <adopted-repo>
python <published-kit>\tools\install_update.py retire-hooks <adopted-repo>
```

Preview lists each path/action and guarded recognized-content hash. Apply retires
only complete definitions exactly matching recognized legacy POSIX/Windows
Architrave commands. Product/source, config, authentication, other hooks and
host permissions are untouched. Edits to inspected definitions cause transaction
rollback, not removal of newer custom data; repeated calls are idempotent.
Hooks absent during planning are checked after the transaction's asset writes.
A newly created hook is preserved and reported `MANUAL_ACTION_REQUIRED` (exit 2)
by install, update and hooks-only retirement. Absence assertions never write,
back up or remove that hook, including during recovery.
If a recognized hook is concurrently removed before quarantine, retirement
accepts the already-achieved absence only after rechecking both original and
quarantine paths. A newly present replacement or quarantine entry is not
silently treated as success.

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

Retirement atomically quarantines the actual hook inode before checking its
bytes. A mismatch restores the actual inode only if the active target is absent;
newer targets are never overwritten. Quarantined inodes remain under
`.architrave/install-retired-hooks/` so writes through already-open handles are
retained rather than deleted by transaction cleanup. Inspect reported retained
paths at the owner boundary; a rename is not a claim of immutable content.
Each archive gets a create-only, flushed local ignore guard before the inode is
moved. That guard remains through rollback/recovery, including hooks-only use in
older repositories without the root ignore rule. Root ignore files and
concurrent custom edits are untouched; conflicting archive-local ignore rules
stop retention/recovery rather than being overwritten. Retained data is ignored
by Git, not an immutable or same-user security boundary.

Custom/mixed/unknown or malformed/duplicate-field JSON is preserved and reported
`MANUAL_ACTION_REQUIRED` (exit 2); the owner must inspect it, not blindly delete.
Full install/update uses the same retirement safety. Exact legacy definitions
are recognized in installer code only; no hook templates are packaged.

Verify registration absence, executable quick-check PASS, and host-loaded
instructions/hooks through supported reload/new-turn observation. File removal
alone is not loaded-context proof. Record kit version/hash, target/action list,
check exit/output and loaded observation, never custom contents or credentials.
