#!/usr/bin/env bash
# Architrave UI — deterministic gate runner (the "code-graded" layer that
# complements the semantic Adversarial Judge). Reads uikit.config.json and runs
# the configured generate/build/test, plus validates the designMap + tokens JSON.
#
#   gates/checks.sh            # full: JSON validity + generate + build + test
#   gates/checks.sh --quick    # fast: JSON validity only (used by hooks / Stop gate)
#
# Exit 0 = PASS, non-zero = FAIL. Dependency: jq.
set -uo pipefail

command -v jq >/dev/null 2>&1 || { echo "checks: 'jq' is required (macOS: brew install jq · Windows: winget install jqlang.jq)" >&2; exit 2; }

quick=0
[ "${1:-}" = "--quick" ] && quick=1

# Repo root = nearest ancestor containing uikit.config.json.
find_root() {
  local d="$PWD"
  while [ "$d" != "/" ]; do
    [ -f "$d/uikit.config.json" ] && { printf '%s\n' "$d"; return 0; }
    d="$(dirname "$d")"
  done
  return 1
}
root="$(find_root)" || { echo "checks: uikit.config.json not found (run inside a repo that adopted Architrave UI)" >&2; exit 2; }
cd "$root"

cfg() { jq -r --arg k "$1" '.[$k] // ""' uikit.config.json; }

fail=0
validate_json() {
  local f="$1" label="$2"
  [ -n "$f" ] || return 0
  if [ -f "$f" ]; then
    if jq empty "$f" >/dev/null 2>&1; then echo "ok    $label $f"; else echo "FAIL  $label $f (invalid JSON)"; fail=1; fi
  else
    echo "warn  $label $f (missing)"
  fi
}

echo "== Architrave UI checks (root: $root) =="
validate_json "uikit.config.json" "config   "
validate_json "$(cfg designMap)"  "designMap"
validate_json "$(cfg tokens)"     "tokens   "

if [ "$quick" -eq 1 ]; then
  if [ "$fail" -eq 0 ]; then echo "CHECKS (quick): PASS"; else echo "CHECKS (quick): FAIL"; fi
  exit "$fail"
fi

run_step() {
  local name="$1" cmd
  cmd="$(cfg "$2")"
  if [ -z "$cmd" ]; then echo "skip  $name (not configured)"; return 0; fi
  echo "== $name: $cmd =="
  if eval "$cmd"; then echo "ok    $name"; else echo "FAIL  $name"; fail=1; fi
}
run_step generate generate
run_step build    build
run_step test     test

if [ "$fail" -eq 0 ]; then echo "CHECKS: PASS"; else echo "CHECKS: FAIL"; fi
exit "$fail"
