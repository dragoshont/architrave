#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

expect_code() {
  local expected="$1"; shift
  set +e
  "$@" >/dev/null 2>&1
  local actual=$?
  set -e
  [ "$actual" -eq "$expected" ] || { echo "FAIL expected exit $expected, got $actual: $*" >&2; exit 1; }
}

mkdir "$tmp/application" "$tmp/knowledge" "$tmp/preserved"
tools/install.sh "$tmp/application" >/dev/null
jq -e '.platform == "web" and .stack == "react" and (.kind | not)' "$tmp/application/architrave.config.json" >/dev/null
echo "ok    installer default application profile"

git -C "$tmp/knowledge" init -q
tools/install.sh --profile knowledge "$tmp/knowledge" >/dev/null
cmp -s kit/examples/knowledge.architrave.json "$tmp/knowledge/architrave.config.json" || { echo "FAIL knowledge scaffold differs from canonical example" >&2; exit 1; }
npx --yes ajv-cli@5 validate --spec=draft7 -s kit/architrave.config.schema.json -d "$tmp/knowledge/architrave.config.json" >/dev/null
git -C "$tmp/knowledge" add .
(cd "$tmp/knowledge" && ./gates/checks.sh >/dev/null)
echo "ok    installer knowledge scaffold validates and passes gates"

before="$(shasum -a 256 "$tmp/knowledge/architrave.config.json" | awk '{print $1}')"
tools/install.sh --profile knowledge "$tmp/knowledge" >/dev/null
after="$(shasum -a 256 "$tmp/knowledge/architrave.config.json" | awk '{print $1}')"
[ "$before" = "$after" ] || { echo "FAIL installer clobbered existing knowledge config" >&2; exit 1; }
echo "ok    installer knowledge profile idempotent"

printf '%s\n' '{"sentinel":true}' > "$tmp/preserved/architrave.config.json"
tools/install.sh --profile knowledge "$tmp/preserved" >/dev/null
jq -e '.sentinel == true' "$tmp/preserved/architrave.config.json" >/dev/null
echo "ok    installer preserves existing config"

expect_code 2 tools/install.sh --profile
expect_code 2 tools/install.sh --profile unknown "$tmp/preserved"
tools/install.sh --help | grep -q -- '--profile application|knowledge'
echo "ok    installer help and profile errors"
echo "INSTALLERS: PASS"