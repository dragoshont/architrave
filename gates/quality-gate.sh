#!/usr/bin/env bash
# Architrave — lightweight quick gate. Validates the design
# map / tokens JSON fast and reminds that the FULL gates + Adversarial Judge must
# pass before declaring done. NOT a full build (hooks must stay fast).
# Exit 0 = ok to stop, 2 = BLOCKING (invalid JSON).
set -uo pipefail
dir="$(cd "$(dirname "$0")" && pwd)"
if "$dir/checks.sh" --quick; then
  if [ "$(jq -r '.kind // ""' "$dir/../architrave.config.json" 2>/dev/null)" = "knowledge" ]; then
    echo "quality-gate: knowledge profile config valid. Before declaring done, confirm: gates/checks.sh (build+test) green and an Adversarial Judge PASS."
  else
    echo "quality-gate: design JSON valid. Before declaring done, confirm: gates/checks.sh (generate+build+test) green, gates/reconcile.sh reconciled, and an Adversarial Judge PASS."
  fi
  exit 0
else
  echo "quality-gate: BLOCKING — configured JSON validation failed. Fix before stopping." >&2
  exit 2
fi
