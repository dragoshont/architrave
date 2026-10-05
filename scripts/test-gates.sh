#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
repo="$tmp/repo"
mkdir -p "$repo/gates" "$repo/harness"
cp gates/*.sh gates/rubric.md "$repo/gates/"
cp gates/gate_runner.py "$repo/gates/"
cp harness/platform_launch.py "$repo/harness/"
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

mkdir -p "$repo/strings"
printf '{"signIn": "Sign in with Microsoft"}\n' > "$repo/strings/en.json"
cat > "$repo/architrave.config.json" <<'JSON'
{
  "kind": "knowledge",
  "build": "printf build > build.ran",
  "test": "printf test > test.ran",
  "productCopy": { "paths": ["strings/*.json"] }
}
JSON
(cd "$repo" && ./gates/checks.sh --quick | grep -q 'ok    product copy (1 files)')
printf '{"status": "Registry only - not certified"}\n' > "$repo/strings/en.json"
set +e
copy_out="$(cd "$repo" && ./gates/checks.sh --quick)"
copy_status=$?
set -e
[ "$copy_status" -eq 1 ]
grep -q "strings/en.json:1: 'Registry only'" <<<"$copy_out"
echo "GATES: PASS"