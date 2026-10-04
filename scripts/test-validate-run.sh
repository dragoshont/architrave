#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

make_repo() {
  local repo="$1"
  mkdir -p "$repo/.architrave/runs/test-run"
  cp -R harness "$repo/harness"
  printf '{"schema":"architrave.run.v1","runId":"test-run","status":"in-progress"}\n' \
    > "$repo/.architrave/runs/test-run/summary.json"
}

legacy="$tmp/legacy"
make_repo "$legacy"
(cd "$legacy" && harness/validate-run.sh .architrave/runs/test-run >/dev/null)
echo "ok   compact legacy run"

printf '{"schema":"architrave.run.v1","runId":"","status":"in-progress"}\n' \
  > "$legacy/.architrave/runs/test-run/summary.json"
if (cd "$legacy" && harness/validate-run.sh .architrave/runs/test-run >/dev/null 2>&1); then
  echo "FAIL invalid compact legacy run passed" >&2
  exit 1
fi
echo "ok   invalid compact legacy run"

v2="$tmp/v2"
mkdir -p "$v2"
cp -R harness "$v2/harness"
printf '{}\n' > "$v2/architrave.config.json"
git -C "$v2" init -q
git -C "$v2" config user.email architrave@example.invalid
git -C "$v2" config user.name 'Architrave Test'
git -C "$v2" add .
git -C "$v2" commit -qm fixture
(cd "$v2" && python3 harness/architrave_runtime.py run --run-id test-run \
  --goal 'Validate compact Run v2.' --outcome 'Run files remain valid.' >/dev/null)
(cd "$v2" && harness/validate-run.sh .architrave/runs/test-run >/dev/null)
test -f "$v2/.architrave/runs/test-run/recovery.json"
test ! -e "$v2/.architrave/runs/test-run/phase-ledger.md"
test ! -e "$v2/.architrave/runs/test-run/summary.json"
test ! -d "$v2/.architrave/runs/test-run/snapshots"
echo "ok   compact v2 run"
