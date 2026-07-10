#!/usr/bin/env bash
# Architrave — lightweight quick gate. Validates the design
# map / tokens JSON fast and reminds that the FULL gates + Adversarial Judge must
# pass before declaring done. NOT a full build (hooks must stay fast).
# Exit 0 = ok to stop, 2 = BLOCKING (invalid JSON).
# --hook-json emits only the VS Code/Claude/Copilot hook JSON contract on stdout.
set -uo pipefail
dir="$(cd "$(dirname "$0")" && pwd)"
hook_json=0
case "${1:-}" in
  "") ;;
  --hook-json) hook_json=1 ;;
  *) echo "usage: gates/quality-gate.sh [--hook-json]" >&2; exit 2 ;;
esac

check_output="$("$dir/checks.sh" --quick 2>&1)"
check_status=$?
if [ "$check_status" -eq 0 ]; then
  if [ "$hook_json" -eq 1 ]; then
    printf '%s' '{"continue":true}'
    exit 0
  fi
  printf '%s\n' "$check_output"
  if [ "$(jq -r '.kind // ""' "$dir/../architrave.config.json" 2>/dev/null)" = "knowledge" ]; then
    echo "quality-gate: knowledge profile config valid. Before declaring done, confirm: gates/checks.sh (build+test) green and an Adversarial Judge PASS."
  else
    echo "quality-gate: design JSON valid. Before declaring done, confirm: gates/checks.sh (generate+build+test) green, gates/reconcile.sh reconciled, and an Adversarial Judge PASS."
  fi
  exit 0
else
  if [ "$hook_json" -eq 1 ]; then
    printf '%s\n' "$check_output" >&2
  else
    printf '%s\n' "$check_output"
  fi
  echo "quality-gate: BLOCKING — configured JSON validation failed. Fix before stopping." >&2
  exit 2
fi
