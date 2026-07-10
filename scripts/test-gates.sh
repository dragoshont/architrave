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
grep -q 'knowledge profile config valid' <<<"$quality"
echo "GATES: PASS"