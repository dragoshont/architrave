#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
repo="$tmp/repo"
mkdir -p "$repo/gates"
cp gates/*.sh gates/rubric.md "$repo/gates/"
cat > "$repo/architrave.config.json" <<'JSON'
{
  "kind": "knowledge",
  "build": "printf build > build.ran",
  "test": "printf test > test.ran"
}
JSON

quick="$(cd "$repo" && ./gates/checks.sh --quick)"
grep -q 'profile knowledge: UI design JSON validation not applicable' <<<"$quick"
(cd "$repo" && ./gates/checks.sh >/dev/null)
[ -f "$repo/build.ran" ] && [ -f "$repo/test.ran" ]
reconcile="$(cd "$repo" && ./gates/reconcile.sh)"
grep -q 'UI design reconciliation not applicable for knowledge profile' <<<"$reconcile"
quality="$(cd "$repo" && ./gates/quality-gate.sh)"
grep -q 'profile knowledge: UI design JSON validation not applicable' <<<"$quality"
grep -q 'knowledge profile config valid' <<<"$quality"
(
  cd "$repo"
  ./gates/quality-gate.sh --hook-json >"$tmp/hook-success.out" 2>"$tmp/hook-success.err"
)
[ "$(cat "$tmp/hook-success.out")" = '{"continue":true}' ]
[ "$(wc -c < "$tmp/hook-success.out" | tr -d ' ')" = "17" ]
[ ! -s "$tmp/hook-success.err" ]

printf '{' > "$repo/architrave.config.json"
set +e
(cd "$repo" && ./gates/quality-gate.sh --hook-json) >"$tmp/hook-fail.out" 2>"$tmp/hook-fail.err"
hook_status=$?
set -e
[ "$hook_status" -eq 2 ]
[ ! -s "$tmp/hook-fail.out" ]
grep -q 'quality-gate: BLOCKING' "$tmp/hook-fail.err"
echo "GATES: PASS"