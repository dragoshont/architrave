# Handover — PR `feat/lean-knowledge-install`

**For:** the next session picking up / reviewing / merging this PR (incl. the in-flight Codex work owner)
**From:** Architrave session, 2026-07-21
**Branch:** `feat/lean-knowledge-install` @ `9a60f9b`, plus reviewed **uncommitted hardening** — local, not pushed
**Base:** `2638741` (the clean `main` tip = v0.10.3), deliberately **not** the dirty in-flight tree
**Worktree:** `~/Repo/architrave-lean-install`
**Tracking issue:** [dragoshont/architrave#7](https://github.com/dragoshont/architrave/issues/7)
**Status:** reconciled into the dirty `main` Codex/Tournament worktree; deterministic and dual-family semantic gates pass. Still uncommitted, not pushed, and not released.

---

## 1. TL;DR — what this PR brings

Makes the `kind: knowledge` install **lean** and stops agent **session logs** from leaking:

1. **#1 Lean knowledge install** — knowledge repos no longer get the native-app constitutions or the UI/backend agent crew they never use.
2. **#2 Existing-adopter migration** — update removes only kit-packaged agents outside the knowledge crew when agent refresh is explicit, removes the two managed constitutions, and preserves custom agents.
3. **#3 gitignore `.architrave/runs/`** — install and update ignore agent session run artifacts in the adopted repo by default (they can capture repo content); `.architrave/learning/` stays tracked.

Motivation: installing into a stats/docs/benchmark repo currently drops `constitution-apple.md` + `constitution-windows.md` and 8 irrelevant UI/backend agents on disk (and in the agent picker), and leaves `.architrave/runs/` in untracked limbo where a "commit all" can publish session logs. (Both surfaced from a real adoption in `apprenticeops`.)

## 2. Exactly what changed (7 implementation files; this handover is the eighth tracked file)

| File | Change |
|---|---|
| `tools/install.sh`, `tools/install.ps1` | `--profile knowledge` installs only the knowledge crew; skips constitutions; adds the `.gitignore` rule (rule is profile-agnostic) |
| `tools/update.sh`, `tools/update.ps1` | infer profile from the adopted repo's `architrave.config.json` `kind`; knowledge update adds the ignore rule and removes managed constitutions; explicit agent refresh removes only packaged non-crew agents and preserves target-only agents |
| `scripts/test-installers.sh`, `.ps1` | assert application and fresh-knowledge behavior plus migration from a legacy full install, opt-in agent cleanup, custom-agent preservation, constitution removal, ignore idempotence, and unrelated `.gitignore` preservation |
| `CHANGELOG.md` | `[Unreleased]` Changed + Added entries |

**Knowledge crew installed after reconciliation** = `architrave`, `adversarial-judge`, `tournament-analyst`, `product-research`, `runtime-observer`.
**Skipped for knowledge** = `ui-visual`, `ux-architect`, `platform-design`, `operations-ux`, `service-architect`, `backend-planner`, `backend-implementer`, `infra-engineer` + both constitutions.

## 3. How it was verified

- `bash -n tools/install.sh tools/update.sh scripts/test-installers.sh` → clean
- `bash scripts/test-installers.sh` → **PASS** (all assertions incl. the new lean/gitignore/update ones)
- `pwsh -NoProfile -File scripts/test-installers.ps1` → **PASS** with the mirrored migration and preservation assertions
- Combined legacy migration with `--agents --codex` → **PASS**; five managed agents + custom agent + two Codex roles survive as expected
- `bash scripts/check-manifests.sh` → **PASS**, all 7 version fields in sync at `0.10.3` (no bump — see §6)
- `python3 scripts/test-codex-roles.py` → **PASS**
- `python3 scripts/test-codex-runtime.py` (non-live) → **PASS**
- `bash scripts/test-review-launchers.sh` → **PASS**
- `git diff --check` → clean
- Phase 1 and Phase 2 dual pre-implementation judges → **PASS**
- Phase 1 and Phase 2 dual post-implementation judges → **PASS**

## 4. Reconciliation with the in-flight Codex work — completed locally

On 2026-07-21 the lean behavior was applied directly to the dirty `main` worktree's Codex/ChatGPT + Tournament Analyst feature, preserving the existing Codex preflight and generated-role paths. The combined implementation remains uncommitted. These were the overlap files:

- `tools/install.sh`, `tools/install.ps1`, `tools/update.sh`, `tools/update.ps1` — both edit the agent-copy region.
- `scripts/test-installers.sh` (`.ps1`) — both add assertions.
- `CHANGELOG.md` — both add `[Unreleased]` entries (combine them).

**Decisions made:**
1. `tournament-analyst` is in the five-agent knowledge crew.
2. Codex preflight remains before any writes; profile inference happens after preflight and before profile-dependent writes.
3. Agent cleanup is package-derived and requires explicit refresh; target-only agents survive. Managed constitutions are removed for knowledge, and update adds the run-log ignore rule.
4. The paired fixtures exercise the combined legacy migration with Codex roles, rather than testing the features only in isolation.

## 5. How to take it forward

```bash
# inspect the integrated tree
cd ~/Repo/architrave && git status --short && git diff --stat
bash scripts/test-installers.sh
pwsh -NoProfile -File scripts/test-installers.ps1
bash scripts/check-manifests.sh

# review and commit the combined Codex + lean work before any push;
# git push does not include uncommitted work

# cleanup later (branch persists)
git worktree remove ~/Repo/architrave-lean-install
```

## 6. Guardrails (do not skip)

- **`main` is the published plugin artifact** — a bad push breaks every consumer. Do **not** push to `main`; land via PR + review.
- **No version bump here.** Release bumps all 7 version fields via `scripts/bump-version.sh <X.Y.Z>` then tags `vX.Y.Z` (the release pipeline gates on tag == manifest version).
- Keep `check-manifests.sh` + `test-installers.{sh,ps1}` green.

## 7. Proposed follow-ups (in issue #7, not in this PR)

- **#3 Advisory / lightweight lane** — a documented mode so trivial/read-only turns skip the full Intake → Tournament → Phase-Ledger → dual-judge ceremony (behavioral change to `architrave.agent.md`; its own PR).
- Optionally slim the copied `knowledge/*.md` packs for knowledge repos (kept full here to avoid breaking agent references — needs a reference audit first).

---

*This handover is PR-scoped context; drop it from the final squash/merge if you don't want it in `main`. Nothing here was pushed.*
