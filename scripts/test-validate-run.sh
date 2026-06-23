#!/usr/bin/env bash
# Smoke tests for harness/validate-run.sh. These create temporary Architrave-like
# repos so the validator is tested against both valid and malformed run artifacts.
set -euo pipefail
cd "$(dirname "$0")/.."

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

make_repo() {
  local repo="$1"
  local run="$repo/.architrave/runs/test-run"
  mkdir -p "$run" "$repo/.architrave/learning"
  cp -R harness "$repo/harness"
  chmod +x "$repo"/harness/*.sh 2>/dev/null || true
  printf '{}\n' > "$repo/architrave.config.json"
  cat > "$repo/.architrave/learning/repo-profile.md" <<'MD'
# Repo Profile
MD
  cat > "$repo/.architrave/learning/repo-lessons.md" <<'MD'
# Repo Lessons
MD
  cat > "$run/intake.md" <<'MD'
# Intake

## Understanding
ok

## Acceptance Criteria
ok

## Grounding Sources
ok
MD
  cat > "$run/tournament.md" <<'MD'
# Tournament of Options

## Decision Matrix
ok
MD
  cat > "$run/recommended-plan.md" <<'MD'
# Recommended Plan

## Implementation Sequence
ok

## Test Strategy
ok
MD
  cat > "$run/phase-ledger.md" <<'MD'
# Phase Ledger

| Phase | Name | Status | Scope | Gate | Result |
|---:|---|---|---|---|---|
| 1 | Grounding | completed | Read source truth. | Evidence collected. | pass |
| 2 | Implementation | in-progress | Validate the harness. | Validator tests. | pending |

## Phase Transition Log
MD
  cat > "$run/deterministic-gates.md" <<'MD'
# Deterministic Gates

## checks
ok
MD
  cat > "$run/summary.json" <<'JSON'
{
  "schema": "architrave.run.v1",
  "runId": "test-run",
  "status": "in-progress",
  "artifacts": {
    "intake": ".architrave/runs/test-run/intake.md",
    "tournament": ".architrave/runs/test-run/tournament.md",
    "recommendedPlan": ".architrave/runs/test-run/recommended-plan.md",
    "phaseLedger": ".architrave/runs/test-run/phase-ledger.md",
    "deterministicGates": ".architrave/runs/test-run/deterministic-gates.md"
  },
  "phases": [
    { "phase": 1, "name": "Grounding", "status": "completed", "scope": "Read source truth.", "gate": "Evidence collected.", "result": "pass" },
    { "phase": 2, "name": "Implementation", "status": "in-progress", "scope": "Validate the harness.", "gate": "Validator tests.", "result": "pending" }
  ]
}
JSON
}

expect_pass() {
  local name="$1" repo="$2"
  if (cd "$repo" && harness/validate-run.sh .architrave/runs/test-run >/dev/null); then
    echo "ok   $name"
  else
    echo "FAIL $name expected pass" >&2
    exit 1
  fi
}

expect_fail() {
  local name="$1" repo="$2"
  if (cd "$repo" && harness/validate-run.sh .architrave/runs/test-run >/dev/null 2>&1); then
    echo "FAIL $name expected failure" >&2
    exit 1
  else
    echo "ok   $name"
  fi
}

valid="$tmp/valid"
make_repo "$valid"
expect_pass valid-run "$valid"

bad_status="$tmp/bad-status"
make_repo "$bad_status"
perl -0pi -e 's/\| 2 \| Implementation \| in-progress \|/| 2 | Implementation | doing |/' "$bad_status/.architrave/runs/test-run/phase-ledger.md"
expect_fail invalid-status "$bad_status"

bad_header="$tmp/bad-header"
make_repo "$bad_header"
perl -0pi -e 's/\| Phase \| Name \| Status \| Scope \| Gate \| Result \|/| Phase | Name | Status | Scope | Result |/' "$bad_header/.architrave/runs/test-run/phase-ledger.md"
expect_fail missing-column "$bad_header"

two_active="$tmp/two-active"
make_repo "$two_active"
perl -0pi -e 's/\| 1 \| Grounding \| completed \|/| 1 | Grounding | in-progress |/' "$two_active/.architrave/runs/test-run/phase-ledger.md"
expect_fail multiple-active "$two_active"

bad_summary="$tmp/bad-summary"
make_repo "$bad_summary"
jq '.phases[1].status = "doing"' "$bad_summary/.architrave/runs/test-run/summary.json" > "$bad_summary/.architrave/runs/test-run/summary.tmp" && mv "$bad_summary/.architrave/runs/test-run/summary.tmp" "$bad_summary/.architrave/runs/test-run/summary.json"
expect_fail invalid-summary-phase "$bad_summary"

terminal_active="$tmp/terminal-active"
make_repo "$terminal_active"
jq '.status = "passed"' "$terminal_active/.architrave/runs/test-run/summary.json" > "$terminal_active/.architrave/runs/test-run/summary.tmp" && mv "$terminal_active/.architrave/runs/test-run/summary.tmp" "$terminal_active/.architrave/runs/test-run/summary.json"
expect_fail terminal-summary-active-phase "$terminal_active"

progress_no_active="$tmp/progress-no-active"
make_repo "$progress_no_active"
jq '.phases[1].status = "completed"' "$progress_no_active/.architrave/runs/test-run/summary.json" > "$progress_no_active/.architrave/runs/test-run/summary.tmp" && mv "$progress_no_active/.architrave/runs/test-run/summary.tmp" "$progress_no_active/.architrave/runs/test-run/summary.json"
perl -0pi -e 's/\| 2 \| Implementation \| in-progress \|/| 2 | Implementation | completed |/' "$progress_no_active/.architrave/runs/test-run/phase-ledger.md"
expect_fail in-progress-summary-no-active-phase "$progress_no_active"