#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

command -v npx >/dev/null 2>&1 || { echo "test-config-profiles: npx is required" >&2; exit 2; }

schema="kit/architrave.config.schema.json"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

validate() {
  npx --yes ajv-cli@5 validate --spec=draft7 -s "$schema" -d "$1" >/dev/null 2>&1
}

expect_pass() {
  local name="$1" file="$2"
  validate "$file" || { echo "FAIL  $name should pass" >&2; exit 1; }
  echo "ok    $name"
}

expect_fail() {
  local name="$1" file="$2"
  if validate "$file"; then echo "FAIL  $name should fail" >&2; exit 1; fi
  echo "ok    $name rejected"
}

cp kit/examples/knowledge.architrave.json "$tmp/knowledge.json"
expect_pass knowledge-positive "$tmp/knowledge.json"

jq 'del(.build)' "$tmp/knowledge.json" > "$tmp/missing-build.json"
expect_fail knowledge-missing-build "$tmp/missing-build.json"
jq 'del(.test)' "$tmp/knowledge.json" > "$tmp/missing-test.json"
expect_fail knowledge-missing-test "$tmp/missing-test.json"
jq '.kind = "automation"' "$tmp/knowledge.json" > "$tmp/unknown-kind.json"
expect_fail knowledge-unknown-kind "$tmp/unknown-kind.json"

for field in platform stack designSource designMap tokens tokenBuild knowledgePack applyTo generate screenshot backend iac ops; do
  case "$field" in
    platform) value='"web"' ;;
    stack) value='"other"' ;;
    designSource) value='{"type":"design-doc","path":"README.md"}' ;;
    designMap) value='"map.json"' ;;
    tokens) value='"tokens.json"' ;;
    tokenBuild) value='"echo tokens"' ;;
    knowledgePack) value='"web"' ;;
    applyTo) value='["**"]' ;;
    generate) value='"echo generate"' ;;
    screenshot) value='"echo screenshot"' ;;
    backend|iac|ops) value='{}' ;;
  esac
  jq --arg field "$field" --argjson value "$value" '. + {($field): $value}' "$tmp/knowledge.json" > "$tmp/forbidden-$field.json"
  expect_fail "knowledge-forbids-$field" "$tmp/forbidden-$field.json"
done

expect_pass legacy-phonodeck kit/examples/phonodeck.architrave.json
expect_pass legacy-sideport kit/examples/sideport.architrave.json
expect_pass legacy-tessera kit/examples/tessera.architrave.json
jq 'del(.platform)' kit/examples/sideport.architrave.json > "$tmp/legacy-missing-platform.json"
expect_fail legacy-missing-platform "$tmp/legacy-missing-platform.json"

echo "CONFIG-PROFILES: PASS"