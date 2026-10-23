# Quality checks without automatic turn hooks

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
Targeted build/test and risk-scaled CI remain required, not full suites each turn.

Prose alone **does not guarantee identical automatic scheduling**. Assurance is
executable validators, explicit checkpoint evidence, focused coverage and
required CI. Architrave also registers no native tool-blocking hooks. Host
permissions and human approvals remain host-owned; explicitly invoked native
tools retain their admission, source and evidence checks.

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
