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

mkdir "$tmp/application" "$tmp/knowledge" "$tmp/legacy-knowledge" "$tmp/preserved"
tools/install.sh "$tmp/application" >/dev/null
jq -e '.platform == "web" and .stack == "react" and (.kind | not)' "$tmp/application/architrave.config.json" >/dev/null
[ -f "$tmp/application/.github/agents/ui-visual.agent.md" ] || { echo "FAIL application profile missing UI agents" >&2; exit 1; }
[ -f "$tmp/application/.github/agents/backend-planner.agent.md" ] || { echo "FAIL application profile missing backend agents" >&2; exit 1; }
ls "$tmp/application"/constitution-*.md >/dev/null 2>&1 || { echo "FAIL application profile missing constitutions" >&2; exit 1; }
echo "ok    installer default application profile (full crew + constitutions)"

git -C "$tmp/knowledge" init -q
tools/install.sh --profile knowledge "$tmp/knowledge" >/dev/null
cmp -s kit/examples/knowledge.architrave.json "$tmp/knowledge/architrave.config.json" || { echo "FAIL knowledge scaffold differs from canonical example" >&2; exit 1; }
cmp -s gates/hooks/design-guard.json "$tmp/knowledge/.github/hooks/design-guard.json" || { echo "FAIL installer did not create active POSIX hook" >&2; exit 1; }
npx --yes ajv-cli@5 validate --spec=draft7 -s kit/architrave.config.schema.json -d "$tmp/knowledge/architrave.config.json" >/dev/null
git -C "$tmp/knowledge" add .
(cd "$tmp/knowledge" && ./gates/checks.sh >/dev/null)
echo "ok    installer knowledge scaffold validates and passes gates"

# knowledge profile is lean: orchestrator + judge present; UI/backend agents + constitutions absent; runs ignored
[ -f "$tmp/knowledge/.github/agents/architrave.agent.md" ] || { echo "FAIL knowledge missing orchestrator agent" >&2; exit 1; }
[ -f "$tmp/knowledge/.github/agents/adversarial-judge.agent.md" ] || { echo "FAIL knowledge missing judge agent" >&2; exit 1; }
[ ! -f "$tmp/knowledge/.github/agents/ui-visual.agent.md" ] || { echo "FAIL knowledge should not install UI agents" >&2; exit 1; }
[ ! -f "$tmp/knowledge/.github/agents/backend-planner.agent.md" ] || { echo "FAIL knowledge should not install backend agents" >&2; exit 1; }
[ ! -f "$tmp/knowledge/.github/agents/infra-engineer.agent.md" ] || { echo "FAIL knowledge should not install infra agents" >&2; exit 1; }
if ls "$tmp/knowledge"/constitution-*.md >/dev/null 2>&1; then echo "FAIL knowledge should not install constitutions" >&2; exit 1; fi
grep -qxF '.architrave/runs/' "$tmp/knowledge/.gitignore" || { echo "FAIL knowledge should gitignore .architrave/runs/" >&2; exit 1; }
echo "ok    installer knowledge profile is lean (crew trimmed, no constitutions, runs ignored)"

before="$(shasum -a 256 "$tmp/knowledge/architrave.config.json" | awk '{print $1}')"
tools/install.sh --profile knowledge "$tmp/knowledge" >/dev/null
after="$(shasum -a 256 "$tmp/knowledge/architrave.config.json" | awk '{print $1}')"
[ "$before" = "$after" ] || { echo "FAIL installer clobbered existing knowledge config" >&2; exit 1; }
[ "$(grep -cxF '.architrave/runs/' "$tmp/knowledge/.gitignore")" -eq 1 ] || { echo "FAIL installer should keep one .architrave/runs/ ignore rule" >&2; exit 1; }
echo "ok    installer knowledge profile idempotent"

tools/update.sh --agents "$tmp/knowledge" >/dev/null
cmp -s gates/hooks/design-guard.json "$tmp/knowledge/.github/hooks/design-guard.json" || { echo "FAIL updater did not refresh active POSIX hook" >&2; exit 1; }
[ ! -f "$tmp/knowledge/.github/agents/ui-visual.agent.md" ] || { echo "FAIL updater --agents re-bloated knowledge repo with UI agents" >&2; exit 1; }
git -C "$tmp/knowledge" diff --check
echo "ok    updater refreshes active POSIX hook and keeps knowledge repo lean"

tools/install.sh "$tmp/legacy-knowledge" >/dev/null
jq '.kind = "knowledge"' "$tmp/legacy-knowledge/architrave.config.json" > "$tmp/legacy-config.json"
mv "$tmp/legacy-config.json" "$tmp/legacy-knowledge/architrave.config.json"
printf '%s\n' 'custom agent' > "$tmp/legacy-knowledge/.github/agents/custom.agent.md"
printf '%s\n' '*.local' > "$tmp/legacy-knowledge/.gitignore"
tools/update.sh "$tmp/legacy-knowledge" >/dev/null
[ -f "$tmp/legacy-knowledge/.github/agents/ui-visual.agent.md" ] || { echo "FAIL updater pruned agents without --agents" >&2; exit 1; }
[ -f "$tmp/legacy-knowledge/.github/agents/custom.agent.md" ] || { echo "FAIL updater removed custom agent" >&2; exit 1; }
if ls "$tmp/legacy-knowledge"/constitution-*.md >/dev/null 2>&1; then echo "FAIL updater left legacy constitutions in knowledge repo" >&2; exit 1; fi
[ "$(grep -cxF '.architrave/runs/' "$tmp/legacy-knowledge/.gitignore")" -eq 1 ] || { echo "FAIL updater should keep one .architrave/runs/ ignore rule" >&2; exit 1; }
grep -qxF '*.local' "$tmp/legacy-knowledge/.gitignore" || { echo "FAIL updater changed unrelated .gitignore content" >&2; exit 1; }
tools/update.sh --agents "$tmp/legacy-knowledge" >/dev/null
[ ! -f "$tmp/legacy-knowledge/.github/agents/ui-visual.agent.md" ] || { echo "FAIL updater left legacy UI agent in knowledge repo" >&2; exit 1; }
[ ! -f "$tmp/legacy-knowledge/.github/agents/backend-planner.agent.md" ] || { echo "FAIL updater left legacy backend agent in knowledge repo" >&2; exit 1; }
[ -f "$tmp/legacy-knowledge/.github/agents/custom.agent.md" ] || { echo "FAIL updater removed custom agent" >&2; exit 1; }
[ "$(grep -cxF '.architrave/runs/' "$tmp/legacy-knowledge/.gitignore")" -eq 1 ] || { echo "FAIL updater should keep one .architrave/runs/ ignore rule" >&2; exit 1; }
echo "ok    updater migrates legacy knowledge repo and preserves custom files"

mkdir "$tmp/update-failure"
printf '%s\n' '{"kind":"knowledge","build":"true","test":"true"}' > "$tmp/update-failure/architrave.config.json"
mkdir -p "$tmp/update-failure/.github"
printf '%s\n' 'not-a-directory' > "$tmp/update-failure/.github/hooks"
expect_code 1 tools/update.sh "$tmp/update-failure"
echo "ok    updater hook delivery fails closed"

printf '%s\n' '{"sentinel":true}' > "$tmp/preserved/architrave.config.json"
tools/install.sh --profile knowledge "$tmp/preserved" >/dev/null
jq -e '.sentinel == true' "$tmp/preserved/architrave.config.json" >/dev/null
echo "ok    installer preserves existing config"

expect_code 2 tools/install.sh --profile
expect_code 2 tools/install.sh --profile unknown "$tmp/preserved"
tools/install.sh --help | grep -q -- '--profile application|knowledge'
echo "ok    installer help and profile errors"
echo "INSTALLERS: PASS"