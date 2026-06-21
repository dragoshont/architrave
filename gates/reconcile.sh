#!/usr/bin/env bash
# Architrave — design<->code reconciliation gate. Regenerates platform code
# from the design tokens (config.tokenBuild) and reports drift vs committed code.
# Exit 0 = reconciled (or not applicable), 1 = DRIFT, 2 = error. Deps: jq, git.
set -uo pipefail
command -v jq >/dev/null 2>&1 || { echo "reconcile: 'jq' is required" >&2; exit 2; }

find_root() { local d="$PWD"; while [ "$d" != "/" ]; do [ -f "$d/architrave.config.json" ] && { printf '%s\n' "$d"; return 0; }; d="$(dirname "$d")"; done; return 1; }
root="$(find_root)" || { echo "reconcile: architrave.config.json not found" >&2; exit 2; }
cd "$root"
cfg() { jq -r --arg k "$1" '.[$k] // ""' architrave.config.json; }

tokens="$(cfg tokens)"; tokenBuild="$(cfg tokenBuild)"
if [ -z "$tokens" ] || [ -z "$tokenBuild" ]; then
  echo "reconcile: tokens/tokenBuild not configured — design<->code SSOT not wired yet; skipping (PASS)"; exit 0
fi
if ! command -v git >/dev/null 2>&1 || ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "reconcile: not a git work tree — run '$tokenBuild' and review changes manually; skipping"; exit 0
fi

echo "== regenerate from tokens: $tokenBuild =="
if ! eval "$tokenBuild"; then echo "reconcile: token build FAILED"; exit 2; fi

if git diff --quiet; then
  echo "reconcile: PASS — generated output matches committed code"
  exit 0
else
  echo "reconcile: DRIFT — committed code differs from the tokens SSOT:"
  git --no-pager diff --stat
  echo "Fix: regenerate from tokens and commit; or if the design legitimately changed, update tokens first, then code."
  exit 1
fi
