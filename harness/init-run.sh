#!/usr/bin/env bash
# Initialize one compact legacy Run v1 record. New work should use Run v2.
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
mkdir -p "$run_dir" .architrave/learning

if [ ! -f "$run_dir/summary.json" ]; then
  cat > "$run_dir/summary.json" <<JSON
{"schema":"architrave.run.v1","runId":"$run_id","status":"in-progress","startedAt":"$(date -u +%Y-%m-%dT%H:%M:%SZ)","note":"Legacy compact record; migrate to Run v2 for state transitions and evidence."}
JSON
fi
printf '%s\n' "$run_dir"
