#!/usr/bin/env bash
# Architrave audit harness — initialize durable artifacts for one agent run.
# Usage: harness/init-run.sh [run-id]
set -euo pipefail

find_root() {
  local d="$PWD"
  while [ "$d" != "/" ]; do
    [ -f "$d/architrave.config.json" ] && { printf '%s\n' "$d"; return 0; }
    d="$(dirname "$d")"
  done
  return 1
}

root="$(find_root)" || { echo "init-run: architrave.config.json not found" >&2; exit 2; }
cd "$root"

run_id="${1:-$(date -u +%Y%m%dT%H%M%SZ)}"
run_dir=".architrave/runs/$run_id"
learning_dir=".architrave/learning"
mkdir -p "$run_dir" "$learning_dir"

create_if_missing() {
  local file="$1" title="$2" body="$3"
  if [ ! -f "$file" ]; then
    {
      printf '# %s\n\n' "$title"
      printf '%s\n' "$body"
    } > "$file"
  fi
}

create_if_missing "$run_dir/intake.md" "Intake" $'## Understanding\n\n## Acceptance Criteria\n\n## Grounding Sources\n\n## Assumptions\n\n## Blocking Questions'
create_if_missing "$run_dir/tournament.md" "Tournament of Options" $'## Option A — Minimal Safe Fix\n\n## Option B — Proper Architectural Fix\n\n## Option C — Defer / Ask More\n\n## Decision Matrix\n\n## Winner'
create_if_missing "$run_dir/recommended-plan.md" "Recommended Plan" $'## Summary\n\n## Implementation Sequence\n\n## Test Strategy\n\n## Rollback / Recovery\n\n## Human Approval Needed'
create_if_missing "$run_dir/phase-ledger.md" "Phase Ledger" $'| Phase | Name | Status | Scope | Gate | Result |\n|---:|---|---|---|---|---|\n| 0 | Intake / Grounding | in-progress | Define the request, acceptance criteria, and sources of truth. | Intake + tournament recorded | pending |\n\n## Phase Transition Log'
create_if_missing "$run_dir/deterministic-gates.md" "Deterministic Gates" $'## checks\n\n## backend-checks\n\n## reconcile\n\n## other'
create_if_missing "$run_dir/judge-pre.md" "Judge Gate 1" $'## Verdict\n\n## Findings'
create_if_missing "$run_dir/judge-post.md" "Judge Gate 2" $'## Verdict\n\n## Findings'
create_if_missing "$run_dir/runtime-observer.md" "Runtime Observer" $'## Sources Used\n\n## Observed State\n\n## Mismatches\n\n## Human Approval Items'

if [ ! -f "$run_dir/summary.json" ]; then
  cat > "$run_dir/summary.json" <<JSON
{
  "schema": "architrave.run.v1",
  "runId": "$run_id",
  "status": "in-progress",
  "startedAt": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "artifacts": {
    "intake": "$run_dir/intake.md",
    "tournament": "$run_dir/tournament.md",
    "recommendedPlan": "$run_dir/recommended-plan.md",
    "phaseLedger": "$run_dir/phase-ledger.md",
    "deterministicGates": "$run_dir/deterministic-gates.md",
    "judgePre": "$run_dir/judge-pre.md",
    "judgePost": "$run_dir/judge-post.md",
    "runtimeObserver": "$run_dir/runtime-observer.md"
  },
  "learning": {
    "repoProfile": "$learning_dir/repo-profile.md",
    "repoLessons": "$learning_dir/repo-lessons.md",
    "candidateLessons": 0,
    "promotionsProposed": 0
  },
  "phases": [
    {
      "phase": 0,
      "name": "Intake / Grounding",
      "status": "in-progress",
      "scope": "Define the request, acceptance criteria, and sources of truth.",
      "gate": "Intake + tournament recorded",
      "result": "pending"
    }
  ]
}
JSON
fi

if [ ! -f "$learning_dir/repo-lessons.md" ]; then
  cat > "$learning_dir/repo-lessons.md" <<'MD'
# Architrave Repo Lessons

Candidate lessons learned while implementing in this repo. Keep this file short.
Each entry needs evidence and validation before promotion. Do not store secrets.
Promote repeated, stable lessons into `architrave.config.json`, `AGENTS.md`, `.github/instructions/`, or docs after review.

## Candidate Lessons

| Lesson | Evidence | Occurrences | Validated | Proposed Target | Status |
|---|---|---:|---|---|---|

MD
fi

if [ ! -f "$learning_dir/repo-profile.md" ]; then
  cat > "$learning_dir/repo-profile.md" <<'MD'
# Architrave Repo Profile

Concise, validated repository description for future Architrave runs. Keep this high-signal and cite evidence; move detailed rules into docs or path-scoped instructions.

## Purpose

## Surfaces And Lanes

## Source Of Truth

## Build And Test

## Architecture Map

## Recurring Gotchas

## Validated Facts

| Fact | Evidence | Last Checked |
|---|---|---|

## Last Reviewed

MD
fi

echo "$run_dir"