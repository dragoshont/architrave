#!/usr/bin/env sh
set -u
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
for python in python3 python; do
  if command -v "$python" >/dev/null 2>&1 && "$python" -c 'import sys; raise SystemExit(0 if sys.version_info[0] == 3 else 1)' >/dev/null 2>&1; then
    exec "$python" "$root/test-improvement.py" PromotionTests.test_dry_run_apply_and_picker PromotionTests.test_executable_check_or_explicit_prose_justification_required PromotionTests.test_invalid_target_missing_and_stale_lesson "$@"
  fi
done
echo "test-promote-lesson-picker: Python 3 is required. Install it with your package manager or from https://www.python.org/downloads/" >&2
exit 2
