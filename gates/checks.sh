#!/usr/bin/env sh
set -u
dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
for python in python3 python; do
  if command -v "$python" >/dev/null 2>&1; then exec "$python" "$dir/gate_runner.py" checks "$@"; fi
done
echo "checks: Python 3 is required. See https://www.python.org/downloads/" >&2; exit 2
