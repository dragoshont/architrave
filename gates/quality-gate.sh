#!/usr/bin/env bash
# Architrave — lightweight quick gate. Validates the design
# map / tokens JSON fast and reminds that the FULL gates + Adversarial Judge must
# pass before declaring done. NOT a full build (hooks must stay fast).
# Exit 0 = ok to stop, 2 = BLOCKING (invalid JSON).
set -uo pipefail
dir="$(cd "$(dirname "$0")" && pwd)"
if "$dir/checks.sh" --quick; then
  echo "quality-gate: design JSON valid. Before declaring done, confirm: gates/checks.sh (generate+build+test) green, gates/reconcile.sh reconciled, and an Adversarial Judge PASS."
  exit 0
else
  echo "quality-gate: BLOCKING — design map/tokens JSON is invalid. Fix before stopping." >&2
  exit 2
fi
