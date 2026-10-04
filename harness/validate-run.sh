#!/usr/bin/env bash
# Validate a compact Run v2 or a legacy compact Run v1 summary.
set -euo pipefail

run_dir="${1:-}"
if [ -z "$run_dir" ]; then
  run_dir="$(ls -1dt .architrave/runs/* 2>/dev/null | head -1 || true)"
fi
[ -n "$run_dir" ] && [ -d "$run_dir" ] || { echo "validate-run: run dir not found" >&2; exit 2; }

if [ -f "$run_dir/run.json" ]; then
  command -v python3 >/dev/null 2>&1 || { echo "validate-run: Python 3 is required for Run v2" >&2; exit 2; }
  exec python3 "$(dirname "$0")/validate_run_v2.py" "$run_dir"
fi

command -v jq >/dev/null 2>&1 || { echo "validate-run: jq is required" >&2; exit 2; }
if jq -e '
  .schema == "architrave.run.v1" and
  (.runId | type == "string" and length > 0) and
  (.status | IN("in-progress", "blocked", "passed", "revised", "failed"))
' "$run_dir/summary.json" >/dev/null 2>&1; then
  echo "ARCHITRAVE-RUN: PASS"
  exit 0
fi
echo "ARCHITRAVE-RUN: FAIL" >&2
exit 1
