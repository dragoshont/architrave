#!/usr/bin/env sh
set -u
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
for python in python3 python; do
  if command -v "$python" >/dev/null 2>&1 && "$python" -c 'import sys' >/dev/null 2>&1; then
    exec "$python" "$root/scripts/test-review-launchers.py" "$@"
  fi
done
echo "test-review-launchers: Python 3 is required. See https://www.python.org/downloads/" >&2
exit 2
