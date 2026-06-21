#!/usr/bin/env bash
# Architrave — deterministic gate runner (the "code-graded" layer that
# complements the semantic Adversarial Judge). Reads architrave.config.json and runs
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

# Repo root = nearest ancestor containing architrave.config.json.
find_root() {
  local d="$PWD"
  while [ "$d" != "/" ]; do
    [ -f "$d/architrave.config.json" ] && { printf '%s\n' "$d"; return 0; }
    d="$(dirname "$d")"
  done
  return 1
}
root="$(find_root)" || { echo "checks: architrave.config.json not found (run inside a repo that adopted Architrave)" >&2; exit 2; }
cd "$root"

cfg() { jq -r --arg k "$1" '.[$k] // ""' architrave.config.json; }

# F4 drift nudge: warn (non-blocking) if this repo's copied kit assets are older
# than the locally installed plugin. Silent when it can't tell (cloud / offline /
# plugin not installed). Best-effort — never affects the exit code.
kit_drift_nudge() {
  local stamp="" ref="" plug="" plugdir="" older
  stamp="$(cat gates/.kit-version 2>/dev/null || true)"
  for plug in "$HOME"/.copilot/installed-plugins/*/architrave/plugin.json \
              "$HOME"/.claude/plugins/*/*/architrave/plugin.json; do
    [ -f "$plug" ] || continue
    ref="$(jq -r '.version // empty' "$plug" 2>/dev/null || true)"
    plugdir="$(dirname "$plug")"
    break
  done
  [ -n "$ref" ] || return 0
  [ "$stamp" = "$ref" ] && return 0
  older="$(awk -v a="${stamp:-0.0.0}" -v b="$ref" 'BEGIN{split(a,A,".");split(b,B,".");for(i=1;i<=3;i++){x=A[i]+0;y=B[i]+0;if(x<y){print 1;exit}if(x>y){print 0;exit}}print 0}')"
  if [ -z "$stamp" ] || [ "$older" = "1" ]; then
    echo "⚠  Architrave kit assets are stale (repo: ${stamp:-unstamped}, plugin: v$ref) — gates/knowledge won't auto-update." >&2
    echo "   Refresh:  \"$plugdir/tools/update.sh\" \"$root\"" >&2
  fi
}

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

echo "== Architrave checks (root: $root) =="
validate_json "architrave.config.json" "config   "
validate_json "$(cfg designMap)"  "designMap"
validate_json "$(cfg tokens)"     "tokens   "

if [ "$quick" -eq 1 ]; then
  if [ "$fail" -eq 0 ]; then echo "CHECKS (quick): PASS"; else echo "CHECKS (quick): FAIL"; fi
  exit "$fail"
fi

kit_drift_nudge

run_step() {
  local name="$1" cmd
  cmd="$(cfg "$2")"
  if [ -z "$cmd" ]; then echo "skip  $name (not configured)"; return 0; fi
  echo "== $name: $cmd =="
  if eval "$cmd"; then
    echo "ok    $name"
  else
    echo "FAIL  $name"
    if [[ "$cmd" =~ npm[[:space:]]+--prefix[[:space:]]+([^[:space:]]+)[[:space:]]+run ]]; then
      prefix="${BASH_REMATCH[1]}"
      if [ -f "$prefix/package.json" ] && [ ! -d "$prefix/node_modules" ]; then
        echo "hint  $prefix/node_modules is missing — run: npm --prefix $prefix ci   (or npm --prefix $prefix install)" >&2
      fi
    fi
    fail=1
  fi
}
run_step generate generate
run_step build    build
run_step test     test

if [ "$fail" -eq 0 ]; then echo "CHECKS: PASS"; else echo "CHECKS: FAIL"; fi
exit "$fail"
