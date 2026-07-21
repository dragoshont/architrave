# Handover — PR `feat/lean-knowledge-install`

**For:** the next session picking up / reviewing / merging this PR (incl. the in-flight Codex work owner)
**From:** Architrave session, 2026-07-21
**Branch:** `feat/lean-knowledge-install` @ `987c529` — **local, not pushed**
**Base:** `2638741` (the clean `main` tip = v0.10.3), deliberately **not** the dirty in-flight tree
**Worktree:** `~/Repo/architrave-lean-install`
**Tracking issue:** [dragoshont/architrave#7](https://github.com/dragoshont/architrave/issues/7)
**Status:** implemented + gated locally; awaiting review, reconciliation with the Codex feature, and release.

---

## 1. TL;DR — what this PR brings

Makes the `kind: knowledge` install **lean** and stops agent **session logs** from leaking:

1. **#1 Lean knowledge install** — knowledge repos no longer get the native-app constitutions or the UI/backend agent crew they never use.
2. **#2 gitignore `.architrave/runs/`** — installers ignore agent session run artifacts in the adopted repo by default (they can capture repo content); `.architrave/learning/` stays tracked.

Motivation: installing into a stats/docs/benchmark repo currently drops `constitution-apple.md` + `constitution-windows.md` and 8 irrelevant UI/backend agents on disk (and in the agent picker), and leaves `.architrave/runs/` in untracked limbo where a "commit all" can publish session logs. (Both surfaced from a real adoption in `apprenticeops`.)

## 2. Exactly what changed (7 files, +154 / −23)

| File | Change |
|---|---|
| `tools/install.sh`, `tools/install.ps1` | `--profile knowledge` installs only the knowledge crew; skips constitutions; adds the `.gitignore` rule (rule is profile-agnostic) |
| `tools/update.sh`, `tools/update.ps1` | infer profile from the adopted repo's `architrave.config.json` `kind`; `--agents`/`-Agents` refresh stays lean + skips constitutions for `kind: knowledge` |
| `scripts/test-installers.sh`, `.ps1` | assert: application keeps full crew + constitutions; knowledge is lean (orchestrator+judge present, UI/backend agents + constitutions absent, runs ignored); `update --agents` keeps knowledge lean |
| `CHANGELOG.md` | `[Unreleased]` Changed + Added entries |

**Knowledge crew installed** = `architrave`, `adversarial-judge`, `product-research`, `runtime-observer`.
**Skipped for knowledge** = `ui-visual`, `ux-architect`, `platform-design`, `operations-ux`, `service-architect`, `backend-planner`, `backend-implementer`, `infra-engineer` + both constitutions.

## 3. How it was verified

- `bash -n tools/install.sh tools/update.sh scripts/test-installers.sh` → clean
- `bash scripts/test-installers.sh` → **PASS** (all assertions incl. the new lean/gitignore/update ones)
- `bash scripts/check-manifests.sh` → **PASS**, versions in sync at `0.10.3` (no bump — see §6)
- `git diff --check` → clean
- **PowerShell not run** (no `pwsh` on this Mac). `install.ps1`/`update.ps1`/`test-installers.ps1` were mirrored + syntax-reviewed only → **let Windows CI confirm**.

## 4. ⚠️ Reconciliation with the in-flight Codex work (read before merging)

The `main` working tree has a large **uncommitted** feature (Codex/ChatGPT plugin + Tournament Analyst, ~16 modified files). This branch is based off the clean tip *before* it, so **these files overlap and will conflict on merge**:

- `tools/install.sh`, `tools/install.ps1`, `tools/update.sh`, `tools/update.ps1` — both edit the agent-copy region.
- `scripts/test-installers.sh` (`.ps1`) — both add assertions.
- `CHANGELOG.md` — both add `[Unreleased]` entries (combine them).

**Two concrete decisions for the merger:**
1. **Add `tournament-analyst` to the knowledge crew?** This branch's crew list predates that agent. `tournament-analyst` is an analysis/judge helper (not UI/backend), so it very likely **belongs** in the knowledge crew — update the 4-name list in `install.sh`/`install.ps1`/`update.sh`/`update.ps1` (and the test assertions) when merging.
2. Re-apply the lean/gitignore logic on top of the Codex installer changes (the intent is small and localized: gate the agent glob + constitution copy on profile/`kind`, add the `.gitignore` step).

## 5. How to take it forward

```bash
# inspect
cd ~/Repo/architrave-lean-install && git show --stat
bash scripts/test-installers.sh && bash scripts/check-manifests.sh

# push + PR when ready (from anywhere in the repo; push acts on the ref, not the dirty tree)
git push -u origin feat/lean-knowledge-install
gh pr create --repo dragoshont/architrave --base main --head feat/lean-knowledge-install \
  --title "Lean knowledge install + gitignore .architrave/runs" --body "Closes #7"

# cleanup later (branch persists)
git worktree remove ~/Repo/architrave-lean-install
```

## 6. Guardrails (do not skip)

- **`main` is the published plugin artifact** — a bad push breaks every consumer. Do **not** push to `main`; land via PR + review.
- **No version bump here.** Release bumps all 6 version fields via `scripts/bump-version.sh <X.Y.Z>` then tag `vX.Y.Z` (the release pipeline gates on tag == manifest version). This is a **Changed** entry → a minor bump at release time; coordinate the number with the Codex feature so they don't collide.
- Keep `check-manifests.sh` + `test-installers.{sh,ps1}` green.

## 7. Proposed follow-ups (in issue #7, not in this PR)

- **#3 Advisory / lightweight lane** — a documented mode so trivial/read-only turns skip the full Intake → Tournament → Phase-Ledger → dual-judge ceremony (behavioral change to `architrave.agent.md`; its own PR).
- Optionally slim the copied `knowledge/*.md` packs for knowledge repos (kept full here to avoid breaking agent references — needs a reference audit first).

---

*This handover is PR-scoped context; drop it from the final squash/merge if you don't want it in `main`. Nothing here was pushed.*
