#!/usr/bin/env bash
# Architrave — meta-validation for the plugin/marketplace manifests + kit JSON.
# Because `main` IS the published artifact (marketplace source ".") a bad push breaks
# every consumer instantly — this is the gate that stops that. Runs locally and in CI
# (.github/workflows/validate.yml). Needs: jq, ruby (frontmatter), npx (ajv, optional).
#
# Usage: scripts/check-manifests.sh [--scan-only]
set -uo pipefail
cd "$(dirname "$0")/.."

scan_only=0
case "${1:-}" in
  "") ;;
  --scan-only) scan_only=1 ;;
  *) echo "usage: scripts/check-manifests.sh [--scan-only]" >&2; exit 2 ;;
esac

fail=0
err() { printf '  \033[31m✗\033[0m %s\n' "$*" >&2; fail=1; }
ok()  { printf '  \033[32m✓\033[0m %s\n' "$*"; }
scan_repo() { # <pattern> <output-file>
  local pattern="$1" output="$2" scan_status
  if [ "${ARCHITRAVE_FORCE_GREP:-0}" != "1" ] && command -v rg >/dev/null 2>&1; then
    rg --hidden -n "$pattern" --glob '!node_modules' --glob '!.git' --glob '!assets/*.png' . >"$output" 2>"$output.error"
  else
    grep -R -n -E --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.architrave \
      --exclude='*.png' --exclude='*.jpg' --exclude='*.jpeg' --exclude='*.webp' \
      "$pattern" . >"$output" 2>"$output.error"
  fi
  scan_status=$?
  if [ "$scan_status" -gt 1 ]; then
    sed 's/^/      /' "$output.error" >&2
  fi
  rm -f "$output.error"
  return "$scan_status"
}
run_repo_scans() {
  local legacy_tmp mcp_secret_tmp legacy_name legacy_plugin
  legacy_tmp="$(mktemp)"
  legacy_name="ui""kit"
  legacy_plugin="architrave""-ui"
  echo "== no legacy config name references =="
  scan_repo "${legacy_name}[.]config|[.]${legacy_name}[.]json|${legacy_name} config|${legacy_plugin}" "$legacy_tmp"
  case "$?" in
    0) err "legacy config name references remain"; sed 's/^/      /' "$legacy_tmp" | head -20 ;;
    1) ok "no legacy config references" ;;
    *) err "legacy config scan failed" ;;
  esac
  rm -f "$legacy_tmp"

  mcp_secret_tmp="$(mktemp)"
  echo "== no MCP bearer/auth material committed =="
  scan_repo 'mcp-[A-Za-z0-9_-]{12,}|Authorization[=:]Bearer[[:space:]]+mcp-' "$mcp_secret_tmp"
  case "$?" in
    0) err "possible MCP bearer token/auth material committed"; sed 's/^/      /' "$mcp_secret_tmp" | head -20 ;;
    1) ok "no MCP-looking bearer tokens or auth headers" ;;
    *) err "MCP bearer/auth scan failed" ;;
  esac
  rm -f "$mcp_secret_tmp"
}

if [ "$scan_only" -eq 1 ]; then
  run_repo_scans
  exit "$fail"
fi

echo "== JSON well-formed =="
json_files=(
  plugin.json
  .github/plugin/marketplace.json
  .claude-plugin/plugin.json
  .claude-plugin/marketplace.json
  kit/architrave.config.schema.json
  kit/examples/knowledge.architrave.json
  kit/examples/phonodeck.architrave.json
  kit/examples/sideport.architrave.json
  kit/examples/tessera.architrave.json
  kit/examples/design-map.stub.json
  kit/examples/tokens.web-shadcn.tokens.json
  harness/schemas/run-summary.schema.json
  benchmarks/scenarios.schema.json
  benchmarks/results.schema.json
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

echo "== repository profile fixtures =="
if scripts/test-config-profiles.sh >/dev/null 2>&1; then
  ok "knowledge and legacy schema profiles"
else
  err "config profile fixtures failed"
  scripts/test-config-profiles.sh 2>&1 | sed 's/^/      /' | tail -24
fi
if scripts/test-installers.sh >/dev/null 2>&1; then
  ok "application and knowledge installer profiles"
else
  err "installer profile fixtures failed"
  scripts/test-installers.sh 2>&1 | sed 's/^/      /' | tail -24
fi
if scripts/test-gates.sh >/dev/null 2>&1; then
  ok "knowledge profile gate messages and execution"
else
  err "POSIX gate profile fixtures failed"
  scripts/test-gates.sh 2>&1 | sed 's/^/      /' | tail -24
fi
if scripts/test-manifest-scanner.sh >/dev/null 2>&1; then
  ok "manifest scanner clean and positive grep-fallback paths"
else
  err "manifest scanner fixtures failed"
  scripts/test-manifest-scanner.sh 2>&1 | sed 's/^/      /' | tail -24
fi

run_repo_scans

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
for k in apple microsoft web backend operations-ux design-tokens learning-loop yagni; do
  [ -s "knowledge/$k.md" ] && ok "knowledge/$k.md" || err "missing knowledge/$k.md"
done

echo "== python syntax =="
if python3 -m py_compile scripts/bench-architrave.py scripts/judge-bench.py scripts/summarize-bench.py >/dev/null 2>&1; then
  ok "benchmark python scripts"
else
  err "python syntax problem in benchmark scripts"
  python3 -m py_compile scripts/bench-architrave.py scripts/judge-bench.py scripts/summarize-bench.py 2>&1 | sed 's/^/      /' | tail -12
fi

echo "== harness validator fixtures =="
if scripts/test-validate-run.sh >/dev/null 2>&1; then
  ok "harness/validate-run.sh positive and negative fixtures"
else
  err "harness validator fixture tests failed"
  scripts/test-validate-run.sh 2>&1 | sed 's/^/      /' | tail -20
fi
if command -v pwsh >/dev/null 2>&1; then
  if pwsh -NoProfile -File scripts/test-validate-run.ps1 >/dev/null 2>&1; then
    ok "harness/validate-run.ps1 positive and negative fixtures"
  else
    err "PowerShell harness validator fixture tests failed"
    pwsh -NoProfile -File scripts/test-validate-run.ps1 2>&1 | sed 's/^/      /' | tail -20
  fi
else
  echo "  • pwsh not found — skipping PowerShell harness validator fixtures"
fi

echo "== learning validator fixtures =="
if scripts/test-validate-learning.sh >/dev/null 2>&1; then
  ok "harness/validate-learning.sh positive and negative fixtures"
else
  err "learning validator fixture tests failed"
  scripts/test-validate-learning.sh 2>&1 | sed 's/^/      /' | tail -20
fi
if command -v pwsh >/dev/null 2>&1; then
  if pwsh -NoProfile -File scripts/test-validate-learning.ps1 >/dev/null 2>&1; then
    ok "harness/validate-learning.ps1 positive and negative fixtures"
  else
    err "PowerShell learning validator fixture tests failed"
    pwsh -NoProfile -File scripts/test-validate-learning.ps1 2>&1 | sed 's/^/      /' | tail -20
  fi
else
  echo "  • pwsh not found — skipping PowerShell learning validator fixtures"
fi

echo "== lesson promotion fixtures =="
if scripts/test-promote-lesson.sh >/dev/null 2>&1; then
  ok "harness/promote-lesson.sh dry-run/apply/error fixtures"
else
  err "lesson promotion fixture tests failed"
  scripts/test-promote-lesson.sh 2>&1 | sed 's/^/      /' | tail -20
fi
if command -v pwsh >/dev/null 2>&1; then
  if pwsh -NoProfile -File scripts/test-promote-lesson.ps1 >/dev/null 2>&1; then
    ok "harness/promote-lesson.ps1 dry-run/apply/error fixtures"
  else
    err "PowerShell lesson promotion fixture tests failed"
    pwsh -NoProfile -File scripts/test-promote-lesson.ps1 2>&1 | sed 's/^/      /' | tail -20
  fi
else
  echo "  • pwsh not found — skipping PowerShell lesson promotion fixtures"
fi
if scripts/test-promote-lesson-picker.sh >/dev/null 2>&1; then
  ok "harness/promote-lesson-picker.sh candidate-row fixtures"
else
  err "lesson promotion picker fixture tests failed"
  scripts/test-promote-lesson-picker.sh 2>&1 | sed 's/^/      /' | tail -20
fi
if command -v pwsh >/dev/null 2>&1; then
  if pwsh -NoProfile -File scripts/test-promote-lesson-picker.ps1 >/dev/null 2>&1; then
    ok "harness/promote-lesson-picker.ps1 candidate-row fixtures"
  else
    err "PowerShell lesson promotion picker fixture tests failed"
    pwsh -NoProfile -File scripts/test-promote-lesson-picker.ps1 2>&1 | sed 's/^/      /' | tail -20
  fi
else
  echo "  • pwsh not found — skipping PowerShell lesson promotion picker fixtures"
fi

echo "== PowerShell gate fixtures =="
if command -v pwsh >/dev/null 2>&1; then
  if pwsh -NoProfile -File scripts/test-gates.ps1 >/dev/null 2>&1; then
    ok "gates/*.ps1 smoke fixtures"
  else
    err "PowerShell gate fixture tests failed"
    pwsh -NoProfile -File scripts/test-gates.ps1 2>&1 | sed 's/^/      /' | tail -20
  fi
else
  echo "  • pwsh not found — skipping PowerShell gate fixtures"
fi

echo "== stale learning fixtures =="
if scripts/test-mark-stale-learning.sh >/dev/null 2>&1; then
  ok "harness/mark-stale-learning.sh dry-run/apply fixtures"
else
  err "stale learning fixture tests failed"
  scripts/test-mark-stale-learning.sh 2>&1 | sed 's/^/      /' | tail -20
fi
if command -v pwsh >/dev/null 2>&1; then
  if pwsh -NoProfile -File scripts/test-mark-stale-learning.ps1 >/dev/null 2>&1; then
    ok "harness/mark-stale-learning.ps1 dry-run/apply fixtures"
  else
    err "PowerShell stale learning fixture tests failed"
    pwsh -NoProfile -File scripts/test-mark-stale-learning.ps1 2>&1 | sed 's/^/      /' | tail -20
  fi
else
  echo "  • pwsh not found — skipping PowerShell stale learning fixtures"
fi

echo "== semantic learning fixtures =="
if scripts/test-semantic-learning.sh >/dev/null 2>&1; then
  ok "harness/semantic-learning-review.sh + apply-semantic-learning-findings.sh fixtures"
else
  err "semantic learning fixture tests failed"
  scripts/test-semantic-learning.sh 2>&1 | sed 's/^/      /' | tail -24
fi
if command -v pwsh >/dev/null 2>&1; then
  if pwsh -NoProfile -File scripts/test-semantic-learning.ps1 >/dev/null 2>&1; then
    ok "harness/semantic-learning-review.ps1 + apply-semantic-learning-findings.ps1 fixtures"
  else
    err "PowerShell semantic learning fixture tests failed"
    pwsh -NoProfile -File scripts/test-semantic-learning.ps1 2>&1 | sed 's/^/      /' | tail -24
  fi
else
  echo "  • pwsh not found — skipping PowerShell semantic learning fixtures"
fi

echo
if [ "$fail" -eq 0 ]; then
  echo "PASS — manifests valid, versions in sync ($v)"
else
  echo "FAIL — fix the ✗ items above" >&2
fi
exit "$fail"
