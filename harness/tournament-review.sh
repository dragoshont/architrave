#!/usr/bin/env sh
set -u
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
for python in python3 python; do
  if command -v "$python" >/dev/null 2>&1 && "$python" -c 'import sys; raise SystemExit(0 if sys.version_info[0] == 3 else 1)' >/dev/null 2>&1; then
    exec "$python" "$root/architrave_cli.py" tournament-review "$@"
  fi
done
echo "tournament-review: Python 3 is required. Install it with your package manager or from https://www.python.org/downloads/" >&2
exit 2
