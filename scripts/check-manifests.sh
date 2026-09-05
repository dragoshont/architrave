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
  .codex-plugin/plugin.json
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
  gates/hooks/design-guard.json
  gates/hooks/design-guard.windows.json
  harness/schemas/run-summary.schema.json
  harness/schemas/run-v2.schema.json
  harness/schemas/event-v2.schema.json
  benchmarks/scenarios.schema.json
  benchmarks/results.schema.json
  benchmarks/scenarios.json
  benchmarks/routing-scenarios.json
  kit/examples/runtime-v2.architrave.json
  benchmarks/fixtures/tessera-shaped/architrave.config.json
  benchmarks/fixtures/tessera-shaped/runtime/release-state.json
  benchmarks/fixtures/tessera-shaped/deploy/release.json
  benchmarks/fixtures/tessera-shaped/deploy/live.json
)
for f in "${json_files[@]}"; do
  if jq -e . "$f" >/dev/null 2>&1; then ok "$f"; else err "invalid JSON: $f"; fi
done

echo "== version in sync (the Claude pin footgun) =="
# Version resolves plugin.json -> marketplace entry -> git SHA; a stale/differing
# value silently masks updates, so all seven fields must be identical.
v=$(jq -r '.version // "MISSING"' plugin.json)
check_v() { # <file> <jq-path>
  local got; got=$(jq -r "$2 // \"MISSING\"" "$1")
  [ "$got" = "$v" ] || err "version drift: $1 $2 = $got (expected $v)"
}
[ "$v" != "MISSING" ] || err "plugin.json .version is missing"
check_v .claude-plugin/plugin.json '.version'
check_v .codex-plugin/plugin.json '.version'
check_v .github/plugin/marketplace.json '.metadata.version'
check_v .github/plugin/marketplace.json '.plugins[0].version'
check_v .claude-plugin/marketplace.json '.metadata.version'
check_v .claude-plugin/marketplace.json '.plugins[0].version'
[ "$fail" -eq 0 ] && ok "all 7 version fields = $v"

echo "== name consistency =="
nb=$fail
[ "$(jq -r '.name' plugin.json)" = "architrave" ] || err "plugin.json name != architrave"
[ "$(jq -r '.name' .claude-plugin/plugin.json)" = "architrave" ] || err ".claude-plugin/plugin.json name != architrave"
[ "$(jq -r '.name' .codex-plugin/plugin.json)" = "architrave" ] || err ".codex-plugin/plugin.json name != architrave"
[ "$(jq -r '.skills' .codex-plugin/plugin.json)" = "./skills/" ] || err ".codex-plugin/plugin.json skills != './skills/'"
[ "$(jq -r 'has("agents")' .codex-plugin/plugin.json)" = "false" ] || err ".codex-plugin/plugin.json must not contain unsupported agents field"
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
  for scenarios in benchmarks/scenarios.json benchmarks/routing-scenarios.json; do
    if npx --yes ajv-cli@5 validate -s benchmarks/scenarios.schema.json -d "$scenarios" >/dev/null 2>&1; then
      ok "schema: $scenarios"
    else
      err "schema violation: $scenarios"
      npx --yes ajv-cli@5 validate -s benchmarks/scenarios.schema.json -d "$scenarios" 2>&1 | sed 's/^/      /' | tail -8
    fi
  done
else
  echo "  • npx not found — skipping benchmark scenario schema check"
fi

echo "== LongBuild fixture config and scenario references =="
if command -v npx >/dev/null 2>&1 &&
   npx --yes ajv-cli@5 validate -s kit/architrave.config.schema.json -d benchmarks/fixtures/tessera-shaped/architrave.config.json >/dev/null 2>&1; then
  ok "schema: Tessera-shaped fixture config"
else
  err "Tessera-shaped fixture config schema violation"
fi

echo "== generated Run v2 and event schema conformance =="
if command -v npx >/dev/null 2>&1; then
  runtime_schema_tmp="$(mktemp -d)"
  git -C "$runtime_schema_tmp" init -q
  git -C "$runtime_schema_tmp" config user.email architrave@example.invalid
  git -C "$runtime_schema_tmp" config user.name 'Architrave Schema Test'
  printf '# schema fixture\n' > "$runtime_schema_tmp/README.md"
  git -C "$runtime_schema_tmp" add README.md
  git -C "$runtime_schema_tmp" commit -qm fixture
  if python3 harness/architrave_runtime.py --repo "$runtime_schema_tmp" run \
      --run-id schema-fixture --goal 'Validate schema.' --outcome 'Generated state conforms.' >/dev/null 2>&1 &&
     npx --yes ajv-cli@5 validate -s harness/schemas/run-v2.schema.json \
      -d "$runtime_schema_tmp/.architrave/runs/schema-fixture/run.json" --strict=false >/dev/null 2>&1; then
    jq -c . "$runtime_schema_tmp/.architrave/runs/schema-fixture/events.jsonl" > "$runtime_schema_tmp/event.json"
    if npx --yes ajv-cli@5 validate -s harness/schemas/event-v2.schema.json \
        -d "$runtime_schema_tmp/event.json" --strict=false >/dev/null 2>&1; then
      ok "runtime-generated Run and event conform to v2 schemas"
    else
      err "runtime-generated event violates event-v2.schema.json"
    fi
  else
    err "runtime-generated Run violates run-v2.schema.json"
  fi
  rm -rf "$runtime_schema_tmp"
else
  echo "  • npx not found — skipping generated Run v2 schema conformance"
fi
if python3 scripts/bench-architrave.py --validate >/dev/null 2>&1; then
  ok "pinned repositories and frozen LongBuild fixtures"
else
  err "benchmark repository/fixture references failed"
  python3 scripts/bench-architrave.py --validate 2>&1 | sed 's/^/      /' | tail -16
fi
if (cd benchmarks/fixtures/tessera-shaped && python3 tests/verify.py >/dev/null 2>&1); then
  err "Tessera-shaped fixture baseline unexpectedly passes"
else
  ok "Tessera-shaped fixture baseline is intentionally unresolved"
fi

echo "== managed installer path safety =="
if [ -f tools/managed-paths.sh ] && [ -f tools/ManagedPaths.ps1 ] &&
  [ -f scripts/test-managed-paths.ps1 ] &&
   bash -n tools/managed-paths.sh tools/install.sh tools/update.sh &&
   grep -q 'managed_paths_init' tools/install.sh && grep -q 'managed_paths_init' tools/update.sh &&
   grep -q 'Initialize-ManagedPaths' tools/install.ps1 && grep -q 'Initialize-ManagedPaths' tools/update.ps1; then
  ok "paired managed-path helpers wired into install/update"
else
  err "managed-path helper pair missing, invalid, or not wired into every installer/updater"
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

echo "== Codex skills and generated roles =="
if command -v ruby >/dev/null 2>&1; then
  for skill in skills/*/SKILL.md; do
    if ruby -ryaml -e '
      parts = File.read(ARGV[0]).split("---", 3)
      abort "no frontmatter" if parts.length < 3
      d = YAML.safe_load(parts[1])
      %w[name description].each { |k| abort "missing #{k}" if d[k].to_s.strip.empty? }
    ' "$skill" 2>/dev/null; then ok "$skill"; else err "skill frontmatter problem: $skill"; fi
  done
  for metadata in skills/*/agents/openai.yaml; do
    if ruby -ryaml -e 'd=YAML.safe_load(File.read(ARGV[0])); abort "missing interface" unless d["interface"].is_a?(Hash); abort "missing policy" unless d["policy"].is_a?(Hash)' "$metadata" 2>/dev/null; then ok "$metadata"; else err "skill metadata problem: $metadata"; fi
  done
else
  echo "  • ruby not found — skipping skill YAML checks"
fi
if python3 - <<'PY' >/dev/null 2>&1
from pathlib import Path
import tomllib
config = tomllib.loads(Path('.codex/config.toml').read_text())
assert set(config['agents']) == {'architrave_tournament', 'architrave_judge'}
roles = sorted(Path('.codex/agents').glob('*.toml'))
assert len(roles) == 2
for path in roles:
    data = tomllib.loads(path.read_text())
    assert data['model'] == 'gpt-5.6-sol'
    assert data['model_reasoning_effort'] == 'max'
    assert data['sandbox_mode'] == 'read-only'
    assert not ({'model_provider', 'model_providers', 'mcp_servers', 'skills', 'approval_policy'} & data.keys())
PY
then ok "Codex registration and two advisory read-only roles"; else err "Codex TOML contract failed"; fi
if python3 scripts/generate-codex-agents.py --check >/dev/null 2>&1; then ok "generated Codex roles match canonical agents"; else err "generated Codex role drift"; fi
if [ -e .agents/skills ]; then err "project skill copies must not exist; skills are plugin-only"; else ok "no duplicate project skill source"; fi

echo "== Codex adapter fixtures =="
if python3 scripts/test-codex-roles.py >/dev/null 2>&1; then ok "Codex role transaction fixtures"; else err "Codex role transaction fixtures failed"; fi
if scripts/test-review-launchers.sh >/dev/null 2>&1; then ok "bounded semantic/tournament launcher fixtures"; else err "review launcher fixtures failed"; fi
if python3 scripts/test-codex-runtime.py >/dev/null 2>&1; then ok "disposable plugin/role/MCP structural runtime"; else err "Codex structural runtime fixtures failed"; fi

echo "== knowledge packs present =="
for k in apple microsoft web backend operations-ux design-tokens execution-policy learning-loop yagni runtime-v2; do
  [ -s "knowledge/$k.md" ] && ok "knowledge/$k.md" || err "missing knowledge/$k.md"
done

echo "== python syntax =="
if python3 -m py_compile \
  harness/architrave_runtime.py harness/worker_adapters.py harness/invariant_engine.py \
  harness/legibility.py harness/workspaces.py harness/validate_run_v2.py \
  scripts/bench-architrave.py scripts/judge-bench.py scripts/summarize-bench.py \
  scripts/test-benchmark-tools.py \
  scripts/test-codex-runtime.py scripts/fixtures/codex_fake.py \
  scripts/test-runtime-v2.py scripts/test-worker-adapters.py scripts/test-invariant-engine.py \
  scripts/test-legibility.py scripts/test-workspaces.py scripts/test-longbuild-runtime.py \
  scripts/test-benchmark-runtime.py \
  benchmarks/fixtures/tessera-shaped/server/*.py benchmarks/fixtures/tessera-shaped/plugin/*.py \
  benchmarks/fixtures/tessera-shaped/scripts/*.py benchmarks/fixtures/tessera-shaped/tests/*.py >/dev/null 2>&1; then
  ok "runtime, benchmark, fixture, and test Python scripts"
else
  err "python syntax problem in runtime/benchmark scripts"
fi
if python3 scripts/test-benchmark-tools.py >/dev/null 2>&1; then
  ok "adaptive benchmark fixtures"
else
  err "adaptive benchmark fixtures failed"
  python3 scripts/test-benchmark-tools.py 2>&1 | sed 's/^/      /' | tail -24
fi

echo "== durable Run v2 control-plane fixtures =="
for test_script in \
  scripts/test-runtime-v2.py \
  scripts/test-worker-adapters.py \
  scripts/test-invariant-engine.py \
  scripts/test-legibility.py \
  scripts/test-workspaces.py \
  scripts/test-longbuild-runtime.py \
  scripts/test-benchmark-runtime.py; do
  if python3 "$test_script" >/dev/null 2>&1; then
    ok "$test_script"
  else
    err "$test_script failed"
    python3 "$test_script" 2>&1 | sed 's/^/      /' | tail -20
  fi
done

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
