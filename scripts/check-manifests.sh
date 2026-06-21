#!/usr/bin/env bash
# Architrave — meta-validation for the plugin/marketplace manifests + kit JSON.
# Because `main` IS the published artifact (marketplace source ".") a bad push breaks
# every consumer instantly — this is the gate that stops that. Runs locally and in CI
# (.github/workflows/validate.yml). Needs: jq, ruby (frontmatter), npx (ajv, optional).
#
# Usage: scripts/check-manifests.sh
set -uo pipefail
cd "$(dirname "$0")/.."

fail=0
err() { printf '  \033[31m✗\033[0m %s\n' "$*" >&2; fail=1; }
ok()  { printf '  \033[32m✓\033[0m %s\n' "$*"; }

echo "== JSON well-formed =="
json_files=(
  plugin.json
  .github/plugin/marketplace.json
  .claude-plugin/plugin.json
  .claude-plugin/marketplace.json
  kit/architrave.config.schema.json
  kit/examples/phonodeck.architrave.json
  kit/examples/sideport.architrave.json
  kit/examples/tessera.architrave.json
  kit/examples/design-map.stub.json
  kit/examples/tokens.web-shadcn.tokens.json
  harness/schemas/run-summary.schema.json
  benchmarks/scenarios.schema.json
  benchmarks/scenarios.json
)
for f in "${json_files[@]}"; do
  if jq -e . "$f" >/dev/null 2>&1; then ok "$f"; else err "invalid JSON: $f"; fi
done

echo "== version in sync (the Claude pin footgun) =="
# Version resolves plugin.json -> marketplace entry -> git SHA; a stale/differing
# value silently masks updates, so all six fields must be identical.
v=$(jq -r '.version // "MISSING"' plugin.json)
check_v() { # <file> <jq-path>
  local got; got=$(jq -r "$2 // \"MISSING\"" "$1")
  [ "$got" = "$v" ] || err "version drift: $1 $2 = $got (expected $v)"
}
[ "$v" != "MISSING" ] || err "plugin.json .version is missing"
check_v .claude-plugin/plugin.json '.version'
check_v .github/plugin/marketplace.json '.metadata.version'
check_v .github/plugin/marketplace.json '.plugins[0].version'
check_v .claude-plugin/marketplace.json '.metadata.version'
check_v .claude-plugin/marketplace.json '.plugins[0].version'
[ "$fail" -eq 0 ] && ok "all 6 version fields = $v"

echo "== name consistency =="
nb=$fail
[ "$(jq -r '.name' plugin.json)" = "architrave" ] || err "plugin.json name != architrave"
[ "$(jq -r '.name' .claude-plugin/plugin.json)" = "architrave" ] || err ".claude-plugin/plugin.json name != architrave"
for mf in .github/plugin/marketplace.json .claude-plugin/marketplace.json; do
  [ "$(jq -r '.name' "$mf")" = "architrave" ] || err "$mf marketplace name != architrave"
  [ "$(jq -r '.plugins[0].name' "$mf")" = "architrave" ] || err "$mf plugin entry name != architrave"
  [ "$(jq -r '.plugins[0].source' "$mf")" = "." ] || err "$mf plugin source != '.'"
done
[ "$fail" -eq "$nb" ] && ok "names consistent (marketplace=architrave, plugin=architrave, source=.)"

echo "== examples conform to architrave.config.schema.json (ajv) =="
if command -v npx >/dev/null 2>&1; then
  for ex in kit/examples/*.architrave.json; do
    if npx --yes ajv-cli@5 validate -s kit/architrave.config.schema.json -d "$ex" >/dev/null 2>&1; then
      ok "schema: $ex"
    else
      err "schema violation: $ex"
      npx --yes ajv-cli@5 validate -s kit/architrave.config.schema.json -d "$ex" 2>&1 | sed 's/^/      /' | tail -6
    fi
  done
else
  echo "  • npx not found — skipping ajv schema check"
fi

echo "== benchmark scenarios conform to schema (ajv) =="
if command -v npx >/dev/null 2>&1; then
  if npx --yes ajv-cli@5 validate -s benchmarks/scenarios.schema.json -d benchmarks/scenarios.json >/dev/null 2>&1; then
    ok "schema: benchmarks/scenarios.json"
  else
    err "schema violation: benchmarks/scenarios.json"
    npx --yes ajv-cli@5 validate -s benchmarks/scenarios.schema.json -d benchmarks/scenarios.json 2>&1 | sed 's/^/      /' | tail -8
  fi
else
  echo "  • npx not found — skipping benchmark scenario schema check"
fi

echo "== no legacy config name references =="
legacy_tmp="$(mktemp)"
legacy_name="ui""kit"
legacy_plugin="architrave""-ui"
if rg --hidden -n "${legacy_name}[.]config|[.]${legacy_name}[.]json|${legacy_name} config|${legacy_plugin}" \
    --glob '!node_modules' --glob '!.git' --glob '!assets/*.png' . >"$legacy_tmp" 2>/dev/null; then
  err "legacy config name references remain"
  sed 's/^/      /' "$legacy_tmp" | head -20
else
  ok "no legacy config references"
fi
rm -f "$legacy_tmp"

echo "== agent frontmatter (YAML parses + has name/description) =="
if command -v ruby >/dev/null 2>&1; then
  for a in agents/*.agent.md; do
    if ruby -ryaml -e '
      parts = File.read(ARGV[0]).split("---", 3)
      abort "no frontmatter" if parts.length < 3
      d = YAML.safe_load(parts[1])
      %w[name description].each { |k| abort "missing #{k}" if d[k].to_s.strip.empty? }
    ' "$a" 2>/dev/null; then ok "$a"; else err "frontmatter problem: $a"; fi
  done
else
  echo "  • ruby not found — skipping frontmatter check"
fi

echo "== knowledge packs present =="
for k in apple microsoft web backend design-tokens learning-loop yagni; do
  [ -s "knowledge/$k.md" ] && ok "knowledge/$k.md" || err "missing knowledge/$k.md"
done

echo "== python syntax =="
if python3 -m py_compile scripts/bench-architrave.py scripts/judge-bench.py scripts/summarize-bench.py >/dev/null 2>&1; then
  ok "benchmark python scripts"
else
  err "python syntax problem in benchmark scripts"
  python3 -m py_compile scripts/bench-architrave.py scripts/judge-bench.py scripts/summarize-bench.py 2>&1 | sed 's/^/      /' | tail -12
fi

echo
if [ "$fail" -eq 0 ]; then
  echo "PASS — manifests valid, versions in sync ($v)"
else
  echo "FAIL — fix the ✗ items above" >&2
fi
exit "$fail"
