#!/usr/bin/env sh
set -u

TOOLS_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P) || exit 1
if command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; raise SystemExit(0 if sys.version_info[0] == 3 else 1)' >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1 && python -c 'import sys; raise SystemExit(0 if sys.version_info[0] == 3 else 1)' >/dev/null 2>&1; then
  PYTHON=python
else
  echo "Architrave requires Python 3. Download it from https://www.python.org/downloads/ and retry." >&2
  exit 2
fi

exec "$PYTHON" "$TOOLS_DIR/install_update.py" update --entrypoint posix "$@"
