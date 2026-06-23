#!/usr/bin/env bash
# Architrave audit harness — validate run artifacts exist and are parseable.
# Usage: harness/validate-run.sh [.architrave/runs/<run-id>]
set -euo pipefail

run_dir="${1:-}"
if [ -z "$run_dir" ]; then
  latest="$(ls -1dt .architrave/runs/* 2>/dev/null | head -1 || true)"
  run_dir="$latest"
fi

[ -n "$run_dir" ] && [ -d "$run_dir" ] || { echo "validate-run: run dir not found" >&2; exit 2; }
command -v jq >/dev/null 2>&1 || { echo "validate-run: jq is required" >&2; exit 2; }

fail=0
require_file() {
  local file="$run_dir/$1" label="$2"
  if [ -s "$file" ]; then echo "ok    $label $file"; else echo "FAIL  missing/empty $label $file"; fail=1; fi
}

require_heading() {
  local file="$run_dir/$1" heading="$2"
  if grep -qE "^##[[:space:]]+$heading" "$file" 2>/dev/null; then echo "ok    heading '$heading' in $file"; else echo "FAIL  heading '$heading' missing in $file"; fail=1; fi
}

require_file intake.md intake
require_heading intake.md Understanding
require_heading intake.md "Acceptance Criteria"
require_heading intake.md "Grounding Sources"
require_file tournament.md tournament
require_heading tournament.md "Decision Matrix"
require_file recommended-plan.md "recommended plan"
require_heading recommended-plan.md "Implementation Sequence"
require_heading recommended-plan.md "Test Strategy"
require_file phase-ledger.md "phase ledger"
if grep -qE '^\|[[:space:]]*Phase[[:space:]]*\|' "$run_dir/phase-ledger.md" 2>/dev/null; then echo "ok    phase ledger table"; else echo "FAIL  phase ledger table missing in $run_dir/phase-ledger.md"; fail=1; fi
require_file deterministic-gates.md "deterministic gates"
require_file summary.json summary

if [ -s ".architrave/learning/repo-profile.md" ]; then echo "ok    repo profile .architrave/learning/repo-profile.md"; else echo "FAIL  missing/empty repo profile .architrave/learning/repo-profile.md"; fail=1; fi
if [ -s ".architrave/learning/repo-lessons.md" ]; then echo "ok    repo lessons .architrave/learning/repo-lessons.md"; else echo "FAIL  missing/empty repo lessons .architrave/learning/repo-lessons.md"; fail=1; fi

if jq -e '.schema == "architrave.run.v1" and (.runId | type == "string") and (.status | type == "string") and ((.phases // []) | type == "array")' "$run_dir/summary.json" >/dev/null; then
  echo "ok    summary schema"
else
  echo "FAIL  invalid summary.json"; fail=1
fi

if [ "$fail" -eq 0 ]; then echo "ARCHITRAVE-RUN: PASS"; else echo "ARCHITRAVE-RUN: FAIL"; fi
exit "$fail"