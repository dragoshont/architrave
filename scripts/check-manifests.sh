#!/usr/bin/env bash
# Architrave UI — meta-validation for the plugin/marketplace manifests + kit JSON.
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
  kit/uikit.config.schema.json
  kit/examples/phonodeck.uikit.json
  kit/examples/sideport.uikit.json
  kit/examples/tessera.uikit.json
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
[ "$(jq -r '.name' plugin.json)" = "architrave-ui" ] || err "plugin.json name != architrave-ui"
[ "$(jq -r '.name' .claude-plugin/plugin.json)" = "architrave-ui" ] || err ".claude-plugin/plugin.json name != architrave-ui"
for mf in .github/plugin/marketplace.json .claude-plugin/marketplace.json; do
  [ "$(jq -r '.name' "$mf")" = "architrave" ] || err "$mf marketplace name != architrave"
  [ "$(jq -r '.plugins[0].name' "$mf")" = "architrave-ui" ] || err "$mf plugin entry name != architrave-ui"
  [ "$(jq -r '.plugins[0].source' "$mf")" = "." ] || err "$mf plugin source != '.'"
done
[ "$fail" -eq "$nb" ] && ok "names consistent (marketplace=architrave, plugin=architrave-ui, source=.)"

echo "== examples conform to uikit.config.schema.json (ajv) =="
if command -v npx >/dev/null 2>&1; then
  for ex in kit/examples/*.uikit.json; do
    if npx --yes ajv-cli@5 validate -s kit/uikit.config.schema.json -d "$ex" >/dev/null 2>&1; then
      ok "schema: $ex"
    else
      err "schema violation: $ex"
      npx --yes ajv-cli@5 validate -s kit/uikit.config.schema.json -d "$ex" 2>&1 | sed 's/^/      /' | tail -6
    fi
  done
else
  echo "  • npx not found — skipping ajv schema check"
fi

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

echo
if [ "$fail" -eq 0 ]; then
  echo "PASS — manifests valid, versions in sync ($v)"
else
  echo "FAIL — fix the ✗ items above" >&2
fi
exit "$fail"
