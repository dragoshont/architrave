# Laptop-reset recovery — architrave

Captured: 2026-09-30

This is an archival preservation branch, not a reviewed integration branch.
It preserves meaningful dirty worktrees and makes every local branch tip and
registered worktree HEAD reachable from one remote ref. Existing worktrees and
indexes were not switched, staged, cleaned, or committed.

## Recovery ref

- Source repository: `/Users/dragoshont/Repo/architrave`
- Original origin: `https://github.com/dragoshont/architrave.git`
- Recovery storage: `repository origin`
- Push target: `https://github.com/dragoshont/architrave.git`
- Remote ref: `recovery/laptop-reset-20260930`
- Dirty snapshots preserved: 1
- Registered worktrees inspected: 2
- Local branch tips retained: 3

## Restore

Clone the original repository, then add/fetch the recovery location:

```bash
git clone https://github.com/dragoshont/architrave.git architrave
cd architrave
git remote add reset-recovery https://github.com/dragoshont/architrave.git
git fetch reset-recovery recovery/laptop-reset-20260930
git switch -c recovered-laptop-reset FETCH_HEAD
```

The recovery branch tree represents the primary checkout snapshot when it was
dirty, otherwise its current HEAD, plus these recovery documents. To restore a
different dirty worktree, select its `snapshot_commit` from
`RECOVERY_SNAPSHOTS.tsv` and create a branch at that commit.

## Analysis policy

Each registered worktree was inspected independently. Meaningful source,
configuration, documentation, evidence, and binary product assets were kept.
Only clearly disposable local caches were omitted: `.DS_Store`, Xcode/SwiftPM
user workspace state, the untracked Aletheia `.build-tests` tree, and Vite test
cache entries under `node_modules/.vite`. See `RECOVERY_ANALYSIS.tsv` for the
decision and counts for every worktree.

## Safety

No build, test, deployment, reconcile, restart, or runtime mutation was run.
The combined archival tree is heterogeneous WIP and must not be deployed or
merged as a unit. Review each snapshot against its recorded base. Snapshot
commits preserve final file content, not the original staged/unstaged split.

High-confidence private-key/token patterns were checked in changed text files.
This is not a formal secret audit. Ignored caches, credentials, runtime
sessions, and files outside Git status are not guaranteed to be preserved.
