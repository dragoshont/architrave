#!/usr/bin/env sh
set -u
dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
for python in python3 python; do
  if command -v "$python" >/dev/null 2>&1 && "$python" -c 'import sys; raise SystemExit(0 if sys.version_info[0] == 3 else 1)' >/dev/null 2>&1; then exec "$python" "$dir/gate_runner.py" backend-checks "$@"; fi
done
echo "backend-checks: Python 3 is required. See https://www.python.org/downloads/" >&2; exit 2
