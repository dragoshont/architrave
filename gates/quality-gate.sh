#!/usr/bin/env sh
set -u
dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
for python in python3 python; do
  if command -v "$python" >/dev/null 2>&1; then exec "$python" "$dir/gate_runner.py" quality-gate "$@"; fi
done
echo "quality-gate: Python 3 is required. See https://www.python.org/downloads/" >&2; exit 2
