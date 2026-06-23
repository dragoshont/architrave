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
validate_phase_ledger() {
  local file="$run_dir/phase-ledger.md" active=0 rows=0 bad=0
  awk -F'|' '
    /^[|]/ {
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", $3)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", $4)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", $5)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", $6)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", $7)
      if ($2 == "Phase") {
        if ($3 != "Name" || $4 != "Status" || $5 != "Scope" || $6 != "Gate" || $7 != "Result") { print "BAD_HEADER" }
        next
      }
      if ($2 ~ /^---/) next
      if ($2 == "" && $3 == "") next
      rows++
      if ($4 !~ /^(not-started|in-progress|blocked|completed|skipped)$/) { print "BAD_STATUS:" $4; bad=1 }
      if ($4 == "in-progress") active++
      if ($2 !~ /^[0-9]+$/) { print "BAD_PHASE:" $2; bad=1 }
      if ($3 == "" || $5 == "" || $6 == "") { print "BAD_REQUIRED"; bad=1 }
    }
    END { print "ROWS=" rows; print "ACTIVE=" active; if (bad) exit 1 }
  ' "$file" >"$run_dir/.phase-ledger-check" || bad=1
  if grep -q '^BAD_HEADER' "$run_dir/.phase-ledger-check"; then echo "FAIL  phase ledger header must be Phase | Name | Status | Scope | Gate | Result"; bad=1; fi
  if grep -q '^BAD_STATUS:' "$run_dir/.phase-ledger-check"; then grep '^BAD_STATUS:' "$run_dir/.phase-ledger-check" | sed 's/^/FAIL  phase ledger invalid status /'; bad=1; fi
  if grep -q '^BAD_PHASE:' "$run_dir/.phase-ledger-check"; then grep '^BAD_PHASE:' "$run_dir/.phase-ledger-check" | sed 's/^/FAIL  phase ledger invalid phase /'; bad=1; fi
  if grep -q '^BAD_REQUIRED' "$run_dir/.phase-ledger-check"; then echo "FAIL  phase ledger rows require name, scope, and gate"; bad=1; fi
  rows="$(sed -n 's/^ROWS=//p' "$run_dir/.phase-ledger-check" | tail -1)"
  active="$(sed -n 's/^ACTIVE=//p' "$run_dir/.phase-ledger-check" | tail -1)"
  rm -f "$run_dir/.phase-ledger-check"
  if [ "${rows:-0}" -lt 1 ]; then echo "FAIL  phase ledger has no phase rows"; bad=1; fi
  if [ "${active:-0}" -gt 1 ]; then echo "FAIL  phase ledger has more than one in-progress phase"; bad=1; fi
  if [ "$bad" -eq 0 ]; then echo "ok    phase ledger structure"; else fail=1; fi
}
validate_phase_ledger
require_file deterministic-gates.md "deterministic gates"
require_file summary.json summary

if [ -s ".architrave/learning/repo-profile.md" ]; then echo "ok    repo profile .architrave/learning/repo-profile.md"; else echo "FAIL  missing/empty repo profile .architrave/learning/repo-profile.md"; fail=1; fi
if [ -s ".architrave/learning/repo-lessons.md" ]; then echo "ok    repo lessons .architrave/learning/repo-lessons.md"; else echo "FAIL  missing/empty repo lessons .architrave/learning/repo-lessons.md"; fail=1; fi

if jq -e '
  .schema == "architrave.run.v1" and
  (.runId | type == "string") and
  (.status | type == "string") and
  ((.phases // []) | type == "array") and
  ((.phases // []) | length >= 1) and
  (if .status == "in-progress" then ([ (.phases // [])[] | select(.status == "in-progress") ] | length == 1) else ([ (.phases // [])[] | select(.status == "in-progress") ] | length == 0) end) and
  all((.phases // [])[]; (.phase | type == "number") and (.name | type == "string" and length > 0) and (.status | IN("not-started", "in-progress", "blocked", "completed", "skipped")) and (.scope | type == "string") and (.gate | type == "string"))
' "$run_dir/summary.json" >/dev/null; then
  echo "ok    summary schema"
else
  echo "FAIL  invalid summary.json"; fail=1
fi

if [ "$fail" -eq 0 ]; then echo "ARCHITRAVE-RUN: PASS"; else echo "ARCHITRAVE-RUN: FAIL"; fi
exit "$fail"