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

tree_snapshot() {
  local root="$1" entry relative
  while IFS= read -r entry; do
    relative="${entry#$root/}"
    if [ -L "$entry" ]; then printf 'link %s -> %s\n' "$relative" "$(readlink "$entry")"
    elif [ -d "$entry" ]; then printf 'dir  %s\n' "$relative"
    elif [ -f "$entry" ]; then printf 'file %s %s\n' "$relative" "$(shasum -a 256 "$entry" | awk '{print $1}')"
    else printf 'other %s\n' "$relative"
    fi
  done < <(find "$root" -mindepth 1 -print | LC_ALL=C sort)
}

expect_unchanged_failure() {
  local expected="$1" target="$2" external="$3" before_target before_external after_target after_external
  shift 3
  before_target="$(tree_snapshot "$target")"
  before_external="$(tree_snapshot "$external")"
  expect_code "$expected" "$@"
  after_target="$(tree_snapshot "$target")"
  after_external="$(tree_snapshot "$external")"
  [ "$before_target" = "$after_target" ] || { echo "FAIL failed command changed target: $*" >&2; exit 1; }
  [ "$before_external" = "$after_external" ] || { echo "FAIL failed command changed external sentinel: $*" >&2; exit 1; }
}

mkdir "$tmp/application" "$tmp/knowledge" "$tmp/legacy-knowledge" "$tmp/preserved"
tools/install.sh "$tmp/application" >/dev/null
[ ! -e "$tmp/application/harness/__pycache__" ] || { echo "FAIL installer copied Python cache files" >&2; exit 1; }
jq -e '.platform == "web" and .stack == "react" and (.kind | not)' "$tmp/application/architrave.config.json" >/dev/null
[ -f "$tmp/application/.github/agents/ui-visual.agent.md" ] || { echo "FAIL application profile missing UI agents" >&2; exit 1; }
[ -f "$tmp/application/.github/agents/tournament-analyst.agent.md" ] || { echo "FAIL application profile missing Tournament Analyst" >&2; exit 1; }
ls "$tmp/application"/constitution-*.md >/dev/null 2>&1 || { echo "FAIL application profile missing constitutions" >&2; exit 1; }
[ ! -e "$tmp/application/.codex" ] || { echo "FAIL default installer created Codex assets" >&2; exit 1; }
echo "ok    installer default application profile (full crew + constitutions, no Codex)"

rm "$tmp/application/.github/agents/ui-visual.agent.md" "$tmp/application/constitution-apple.md"
chmod 644 "$tmp/application/gates/checks.sh"
tools/update.sh --agents "$tmp/application" >/dev/null
[ ! -e "$tmp/application/harness/__pycache__" ] || { echo "FAIL updater copied Python cache files" >&2; exit 1; }
[ -f "$tmp/application/.github/agents/ui-visual.agent.md" ] || { echo "FAIL application update did not restore full crew" >&2; exit 1; }
[ -f "$tmp/application/constitution-apple.md" ] || { echo "FAIL application update did not restore constitutions" >&2; exit 1; }
[ -x "$tmp/application/gates/checks.sh" ] || { echo "FAIL application update did not restore packaged executable mode" >&2; exit 1; }
echo "ok    updater preserves legacy application full-profile behavior"

git -C "$tmp/knowledge" init -q
tools/install.sh --profile knowledge "$tmp/knowledge" >/dev/null
cmp -s kit/examples/knowledge.architrave.json "$tmp/knowledge/architrave.config.json" || { echo "FAIL knowledge scaffold differs from canonical example" >&2; exit 1; }
cmp -s gates/hooks/design-guard.json "$tmp/knowledge/.github/hooks/design-guard.json" || { echo "FAIL installer did not create active POSIX hook" >&2; exit 1; }
npx --yes ajv-cli@5 validate --spec=draft7 -s kit/architrave.config.schema.json -d "$tmp/knowledge/architrave.config.json" >/dev/null
git -C "$tmp/knowledge" add .
(cd "$tmp/knowledge" && ./gates/checks.sh >/dev/null)
echo "ok    installer knowledge scaffold validates and passes gates"

for a in architrave adversarial-judge tournament-analyst product-research runtime-observer; do
  [ -f "$tmp/knowledge/.github/agents/$a.agent.md" ] || { echo "FAIL knowledge missing $a agent" >&2; exit 1; }
done
[ "$(find "$tmp/knowledge/.github/agents" -type f -name '*.agent.md' | wc -l | tr -d ' ')" = "5" ] || { echo "FAIL knowledge agent count changed" >&2; exit 1; }
[ ! -f "$tmp/knowledge/.github/agents/ui-visual.agent.md" ] || { echo "FAIL knowledge should not install UI agents" >&2; exit 1; }
[ ! -f "$tmp/knowledge/.github/agents/backend-planner.agent.md" ] || { echo "FAIL knowledge should not install backend agents" >&2; exit 1; }
if ls "$tmp/knowledge"/constitution-*.md >/dev/null 2>&1; then echo "FAIL knowledge should not install constitutions" >&2; exit 1; fi
grep -qxF '.architrave/runs/' "$tmp/knowledge/.gitignore" || { echo "FAIL knowledge should ignore .architrave/runs/" >&2; exit 1; }
grep -qxF '.architrave/worktrees/' "$tmp/knowledge/.gitignore" || { echo "FAIL knowledge should ignore .architrave/worktrees/" >&2; exit 1; }
grep -qxF '.architrave/runtime.key' "$tmp/knowledge/.gitignore" || { echo "FAIL knowledge should ignore .architrave/runtime.key" >&2; exit 1; }
echo "ok    installer knowledge profile is lean (five-agent crew, no constitutions, runs/worktrees ignored)"

before="$(shasum -a 256 "$tmp/knowledge/architrave.config.json" | awk '{print $1}')"
tools/install.sh --profile knowledge "$tmp/knowledge" >/dev/null
after="$(shasum -a 256 "$tmp/knowledge/architrave.config.json" | awk '{print $1}')"
[ "$before" = "$after" ] || { echo "FAIL installer clobbered existing knowledge config" >&2; exit 1; }
[ "$(grep -cxF '.architrave/runs/' "$tmp/knowledge/.gitignore")" -eq 1 ] || { echo "FAIL installer duplicated .architrave/runs/ rule" >&2; exit 1; }
[ "$(grep -cxF '.architrave/worktrees/' "$tmp/knowledge/.gitignore")" -eq 1 ] || { echo "FAIL installer duplicated .architrave/worktrees/ rule" >&2; exit 1; }
[ "$(grep -cxF '.architrave/runtime.key' "$tmp/knowledge/.gitignore")" -eq 1 ] || { echo "FAIL installer duplicated .architrave/runtime.key rule" >&2; exit 1; }
echo "ok    installer knowledge profile idempotent"

tools/update.sh --agents "$tmp/knowledge" >/dev/null
cmp -s gates/hooks/design-guard.json "$tmp/knowledge/.github/hooks/design-guard.json" || { echo "FAIL updater did not refresh active POSIX hook" >&2; exit 1; }
[ ! -f "$tmp/knowledge/.github/agents/ui-visual.agent.md" ] || { echo "FAIL updater re-bloated knowledge repo" >&2; exit 1; }
git -C "$tmp/knowledge" diff --check
echo "ok    updater refreshes active POSIX hook and keeps knowledge repo lean"

mkdir "$tmp/codex-posix"
tools/install.sh --profile knowledge --codex "$tmp/codex-posix" >/dev/null
[ "$(find "$tmp/codex-posix/.codex/agents" -type f -name '*.toml' | wc -l | tr -d ' ')" = "2" ] || { echo "FAIL Codex role count" >&2; exit 1; }
[ -f "$tmp/codex-posix/.codex/config.toml" ] || { echo "FAIL Codex config missing" >&2; exit 1; }
[ ! -e "$tmp/codex-posix/.agents/skills" ] || { echo "FAIL installer copied plugin skills into project" >&2; exit 1; }
before_roles="$(find "$tmp/codex-posix/.codex" -type f -exec shasum -a 256 {} \; | sort | shasum -a 256 | awk '{print $1}')"
tools/update.sh --codex "$tmp/codex-posix" >/dev/null
after_roles="$(find "$tmp/codex-posix/.codex" -type f -exec shasum -a 256 {} \; | sort | shasum -a 256 | awk '{print $1}')"
[ "$before_roles" = "$after_roles" ] || { echo "FAIL Codex update is not idempotent" >&2; exit 1; }
echo "ok    POSIX Codex roles install/update without project skills"

mkdir -p "$tmp/codex-collision/.codex"
printf '%s\n' '[agents.architrave_judge]' 'description = "user-owned"' > "$tmp/codex-collision/.codex/config.toml"
collision_before="$(shasum -a 256 "$tmp/codex-collision/.codex/config.toml" | awk '{print $1}')"
expect_code 2 tools/install.sh --profile knowledge --codex "$tmp/codex-collision"
collision_after="$(shasum -a 256 "$tmp/codex-collision/.codex/config.toml" | awk '{print $1}')"
[ "$collision_before" = "$collision_after" ] || { echo "FAIL Codex collision changed config" >&2; exit 1; }
[ ! -e "$tmp/codex-collision/architrave.config.json" ] || { echo "FAIL Codex collision wrote default assets before preflight" >&2; exit 1; }
echo "ok    Codex collision fails before writes"

tools/install.sh --codex "$tmp/legacy-knowledge" >/dev/null
jq '.kind = "knowledge"' "$tmp/legacy-knowledge/architrave.config.json" > "$tmp/legacy-config.json"
mv "$tmp/legacy-config.json" "$tmp/legacy-knowledge/architrave.config.json"
printf '%s\n' 'custom agent' > "$tmp/legacy-knowledge/.github/agents/custom.agent.md"
printf '%s\n' '*.local' > "$tmp/legacy-knowledge/.gitignore"
tools/update.sh --codex "$tmp/legacy-knowledge" >/dev/null
[ -f "$tmp/legacy-knowledge/.github/agents/ui-visual.agent.md" ] || { echo "FAIL updater pruned agents without --agents" >&2; exit 1; }
[ -f "$tmp/legacy-knowledge/.github/agents/custom.agent.md" ] || { echo "FAIL updater removed custom agent" >&2; exit 1; }
if ls "$tmp/legacy-knowledge"/constitution-*.md >/dev/null 2>&1; then echo "FAIL updater left legacy constitutions" >&2; exit 1; fi
grep -qxF '*.local' "$tmp/legacy-knowledge/.gitignore" || { echo "FAIL updater changed unrelated ignore content" >&2; exit 1; }
[ "$(grep -cxF '.architrave/runs/' "$tmp/legacy-knowledge/.gitignore")" -eq 1 ] || { echo "FAIL updater should add one runs ignore rule" >&2; exit 1; }
[ "$(grep -cxF '.architrave/worktrees/' "$tmp/legacy-knowledge/.gitignore")" -eq 1 ] || { echo "FAIL updater should add one worktrees ignore rule" >&2; exit 1; }
tools/update.sh --agents --codex "$tmp/legacy-knowledge" >/dev/null
for a in architrave adversarial-judge tournament-analyst product-research runtime-observer; do
  [ -f "$tmp/legacy-knowledge/.github/agents/$a.agent.md" ] || { echo "FAIL migrated knowledge missing $a agent" >&2; exit 1; }
done
[ "$(find "$tmp/legacy-knowledge/.github/agents" -type f -name '*.agent.md' | wc -l | tr -d ' ')" = "6" ] || { echo "FAIL migrated knowledge should contain five managed agents plus custom agent" >&2; exit 1; }
[ ! -f "$tmp/legacy-knowledge/.github/agents/ui-visual.agent.md" ] || { echo "FAIL updater left legacy UI agent" >&2; exit 1; }
[ ! -f "$tmp/legacy-knowledge/.github/agents/backend-planner.agent.md" ] || { echo "FAIL updater left legacy backend agent" >&2; exit 1; }
[ -f "$tmp/legacy-knowledge/.github/agents/custom.agent.md" ] || { echo "FAIL updater removed custom agent during refresh" >&2; exit 1; }
[ "$(find "$tmp/legacy-knowledge/.codex/agents" -type f -name '*.toml' | wc -l | tr -d ' ')" = "2" ] || { echo "FAIL migration changed Codex role count" >&2; exit 1; }
echo "ok    Codex update migrates legacy knowledge repo and preserves custom assets"

if command -v pwsh >/dev/null 2>&1; then
  mkdir "$tmp/codex-powershell"
  pwsh -NoProfile -File tools/install.ps1 "$tmp/codex-powershell" -Profile knowledge -Codex >/dev/null
  diff -r "$tmp/codex-posix/.codex" "$tmp/codex-powershell/.codex" >/dev/null || { echo "FAIL POSIX/PowerShell Codex outputs differ" >&2; exit 1; }
  [ ! -e "$tmp/codex-powershell/.agents/skills" ] || { echo "FAIL PowerShell installer copied project skills" >&2; exit 1; }
  echo "ok    POSIX and PowerShell Codex role outputs match"
fi

mkdir -p "$tmp/path-agents/.github" "$tmp/external-agents"
printf '%s\n' '{"kind":"knowledge","build":"true","test":"true"}' > "$tmp/path-agents/architrave.config.json"
printf '%s\n' 'outside agent sentinel' > "$tmp/external-agents/ui-visual.agent.md"
ln -s "$tmp/external-agents" "$tmp/path-agents/.github/agents"
expect_unchanged_failure 1 "$tmp/path-agents" "$tmp/external-agents" tools/update.sh --agents "$tmp/path-agents"

mkdir "$tmp/path-knowledge" "$tmp/external-knowledge"
printf '%s\n' 'outside knowledge sentinel' > "$tmp/external-knowledge/sentinel.md"
ln -s "$tmp/external-knowledge" "$tmp/path-knowledge/knowledge"
expect_unchanged_failure 1 "$tmp/path-knowledge" "$tmp/external-knowledge" tools/install.sh --profile knowledge "$tmp/path-knowledge"

mkdir -p "$tmp/path-harness/harness" "$tmp/external-harness"
printf '%s\n' '{"kind":"knowledge","build":"true","test":"true"}' > "$tmp/path-harness/architrave.config.json"
printf '%s\n' 'outside harness sentinel' > "$tmp/external-harness/sentinel.json"
ln -s "$tmp/external-harness" "$tmp/path-harness/harness/schemas"
expect_unchanged_failure 1 "$tmp/path-harness" "$tmp/external-harness" tools/update.sh "$tmp/path-harness"

mkdir "$tmp/path-ignore" "$tmp/external-ignore"
printf '%s\n' 'outside ignore sentinel' > "$tmp/external-ignore/gitignore"
ln -s "$tmp/external-ignore/gitignore" "$tmp/path-ignore/.gitignore"
expect_unchanged_failure 1 "$tmp/path-ignore" "$tmp/external-ignore" tools/install.sh --profile knowledge "$tmp/path-ignore"
echo "ok    POSIX managed paths reject external directory and file links without writes"

mkdir "$tmp/path-syntax"
expect_code 1 /bin/bash -c '. "$1"; managed_paths_init "$2" test && managed_ensure_dir "../escape"' _ tools/managed-paths.sh "$tmp/path-syntax"
expect_code 1 /bin/bash -c '. "$1"; managed_paths_init "$2" test && managed_preflight_file "/absolute"' _ tools/managed-paths.sh "$tmp/path-syntax"
[ ! -e "$tmp/escape" ] || { echo "FAIL managed path helper created an escaping directory" >&2; exit 1; }
echo "ok    POSIX managed paths reject absolute and escaping relative paths"

mkdir "$tmp/path-unicode"
printf '%s\n' 'unicode sentinel' > "$tmp/unicode-source"
/bin/bash -c '. "$1"; managed_paths_init "$2" test && managed_ensure_dir "unicodé" && managed_safe_replace "$3" "unicodé/naïve.md"' _ tools/managed-paths.sh "$tmp/path-unicode" "$tmp/unicode-source"
grep -qxF 'unicode sentinel' "$tmp/path-unicode/unicodé/naïve.md" || { echo "FAIL managed path helper did not preserve Unicode path content" >&2; exit 1; }
echo "ok    POSIX managed paths support Unicode directory and file names"

mkdir "$tmp/path-fifo"
mkfifo "$tmp/path-fifo/.gitignore"
expect_code 1 tools/install.sh --profile knowledge "$tmp/path-fifo"
[ -p "$tmp/path-fifo/.gitignore" ] || { echo "FAIL installer replaced unsafe FIFO target" >&2; exit 1; }
expect_code 1 /bin/bash -c '. "$1"; managed_assert_source_file /dev/null' _ tools/managed-paths.sh
echo "ok    POSIX managed files reject FIFO and device-node entry types"

mkdir "$tmp/hardlink-ignore"
printf '%s\n' 'outside hard-link sentinel' > "$tmp/external-hardlink"
ln "$tmp/external-hardlink" "$tmp/hardlink-ignore/.gitignore"
external_before="$(shasum -a 256 "$tmp/external-hardlink" | awk '{print $1}')"
tools/install.sh --profile knowledge "$tmp/hardlink-ignore" >/dev/null
external_after="$(shasum -a 256 "$tmp/external-hardlink" | awk '{print $1}')"
[ "$external_before" = "$external_after" ] || { echo "FAIL installer modified external hard-linked file" >&2; exit 1; }
grep -qxF '.architrave/runs/' "$tmp/hardlink-ignore/.gitignore" || { echo "FAIL installer did not replace target hard link safely" >&2; exit 1; }
echo "ok    POSIX managed file replacement does not mutate external hard links"

mkdir "$tmp/no-jq-bin" "$tmp/no-jq-target" "$tmp/no-jq-external"
ln -s "$(command -v dirname)" "$tmp/no-jq-bin/dirname"
printf '%s\n' '{' '  "kind":' '  "knowledge",' '  "build": "true",' '  "test": "true"' '}' > "$tmp/no-jq-target/architrave.config.json"
printf '%s\n' 'no-jq sentinel' > "$tmp/no-jq-external/sentinel"
expect_unchanged_failure 2 "$tmp/no-jq-target" "$tmp/no-jq-external" /usr/bin/env PATH="$tmp/no-jq-bin" /bin/bash tools/update.sh "$tmp/no-jq-target"

mkdir "$tmp/malformed-config" "$tmp/malformed-external" "$tmp/nonobject-config" "$tmp/nonobject-external" "$tmp/duplicate-kind" "$tmp/duplicate-external" "$tmp/case-kind" "$tmp/case-external" "$tmp/unsupported-kind" "$tmp/unsupported-external"
printf '%s\n' '{"kind":' > "$tmp/malformed-config/architrave.config.json"
printf '%s\n' 'malformed sentinel' > "$tmp/malformed-external/sentinel"
expect_unchanged_failure 2 "$tmp/malformed-config" "$tmp/malformed-external" tools/update.sh "$tmp/malformed-config"
printf '%s\n' '[]' > "$tmp/nonobject-config/architrave.config.json"
printf '%s\n' 'nonobject sentinel' > "$tmp/nonobject-external/sentinel"
expect_unchanged_failure 2 "$tmp/nonobject-config" "$tmp/nonobject-external" tools/update.sh "$tmp/nonobject-config"
printf '%s\n' '{"kind":"application","kind":"knowledge","build":"true","test":"true"}' > "$tmp/duplicate-kind/architrave.config.json"
printf '%s\n' 'duplicate sentinel' > "$tmp/duplicate-external/sentinel"
expect_unchanged_failure 2 "$tmp/duplicate-kind" "$tmp/duplicate-external" tools/update.sh "$tmp/duplicate-kind"
printf '%s\n' '{"Kind":"knowledge","build":"true","test":"true"}' > "$tmp/case-kind/architrave.config.json"
printf '%s\n' 'case sentinel' > "$tmp/case-external/sentinel"
expect_unchanged_failure 2 "$tmp/case-kind" "$tmp/case-external" tools/update.sh "$tmp/case-kind"
printf '%s\n' '{"kind":"application","build":"true","test":"true"}' > "$tmp/unsupported-kind/architrave.config.json"
printf '%s\n' 'unsupported sentinel' > "$tmp/unsupported-external/sentinel"
expect_unchanged_failure 2 "$tmp/unsupported-kind" "$tmp/unsupported-external" tools/update.sh "$tmp/unsupported-kind"
echo "ok    POSIX updater rejects missing jq, malformed/non-object JSON and ambiguous/unsupported kind before writes"

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
tools/install.sh --help | grep -q -- '--profile application|knowledge.*--codex'
echo "ok    installer help and profile errors"
echo "INSTALLERS: PASS"