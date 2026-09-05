#!/usr/bin/env bash
# Architrave installer — grounds a target repo so the kit works across every
# Copilot surface (CLI, the Copilot app, VS Code, and the cloud agent):
#   • copies the agent crew into .github/agents/    (discovery location)
#   • copies the gates (sh + ps1 + rubric + hooks) into gates/
#   • copies the audit harness into harness/
#   • scaffolds architrave.config.json                   (retargeting config)
#   • injects the Architrave stanza into AGENTS.md  (reaches the cloud agent)
#   • drops .github/workflows/copilot-setup-steps.yml (cloud-agent gate deps)
#   • wires the POSIX PostToolUse hook into .github/hooks/
#
# Usage: tools/install.sh [--profile application|knowledge] [--codex] [TARGET_REPO_DIR]
#        default profile: application; default target: current directory
# For local agents you ALSO install the plugin once:
#   copilot plugin marketplace add dragoshont/architrave
#   copilot plugin install architrave@architrave
set -uo pipefail

KIT="$(cd "$(dirname "$0")/.." && pwd)"
. "$KIT/tools/managed-paths.sh" || exit 1
profile="application"
install_codex=0
target_arg=""
usage() {
  echo "Usage: tools/install.sh [--profile application|knowledge] [--codex] [TARGET_REPO_DIR]"
}
while [ "$#" -gt 0 ]; do
  case "$1" in
    --profile)
      shift
      [ "$#" -gt 0 ] || { echo "install: --profile requires application or knowledge" >&2; exit 2; }
      profile="$1"
      ;;
    --profile=*)
      profile="${1#--profile=}"
      [ -n "$profile" ] || { echo "install: --profile requires application or knowledge" >&2; exit 2; }
      ;;
    --codex)
      install_codex=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --*)
      echo "install: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      [ -z "$target_arg" ] || { echo "install: unexpected extra argument: $1" >&2; usage >&2; exit 2; }
      target_arg="$1"
      ;;
  esac
  shift
done
case "$profile" in
  application|knowledge) ;;
  *) echo "install: unknown profile '$profile' (expected application or knowledge)" >&2; exit 2 ;;
esac

TARGET="${target_arg:-$PWD}"
TARGET="$(cd "$TARGET" 2>/dev/null && pwd -P)" || { echo "install: target dir not found: ${target_arg:-$PWD}" >&2; exit 1; }
[ "$TARGET" = "$KIT" ] && { echo "install: refusing to install the kit into itself" >&2; exit 1; }
managed_paths_init "$TARGET" install || exit 1

if [ "$install_codex" -eq 1 ]; then
  command -v python3 >/dev/null 2>&1 || { echo "install: --codex requires Python 3.11+" >&2; exit 2; }
  python3 "$KIT/tools/codex-roles.py" --kit "$KIT" --target "$TARGET" --preflight || exit $?
fi

begin="<!-- architrave:begin -->"
end="<!-- architrave:end -->"

for source_tree in agents gates knowledge harness; do
  managed_assert_source_tree "$KIT/$source_tree" || exit 1
done
for source_file in templates/AGENTS.stanza.md templates/copilot-setup-steps.yml plugin.json; do
  managed_assert_source_file "$KIT/$source_file" || exit 1
done
if [ "$profile" = "application" ]; then
  for source_file in "$KIT"/constitution-*.md; do managed_assert_source_file "$source_file" || exit 1; done
else
  managed_assert_source_file "$KIT/kit/examples/knowledge.architrave.json" || exit 1
fi

for tree in .github/agents .github/hooks .github/workflows gates gates/hooks knowledge harness; do
  managed_preflight_tree "$tree" || exit 1
done
for file in architrave.config.json .gitignore AGENTS.md constitution-apple.md constitution-windows.md \
  .github/hooks/design-guard.json .github/workflows/copilot-setup-steps.yml gates/.kit-version; do
  managed_preflight_file "$file" || exit 1
done

echo "Architrave → installing into: $TARGET"
for directory in .github/agents .github/hooks .github/workflows gates/hooks knowledge harness; do
  managed_ensure_dir "$directory" || exit 1
done

# 1) Agents — knowledge repos get only the crew their lane uses; applications get all.
if [ "$profile" = "knowledge" ]; then
  for a in architrave adversarial-judge tournament-analyst product-research runtime-observer; do
    managed_safe_replace "$KIT/agents/$a.agent.md" ".github/agents/$a.agent.md" || exit 1
  done
  echo "  ✓ agents → .github/agents/ (knowledge crew: architrave · adversarial-judge · tournament-analyst · product-research · runtime-observer)"
else
  for source_file in "$KIT"/agents/*.agent.md; do
    managed_safe_replace "$source_file" ".github/agents/${source_file##*/}" || exit 1
  done
  echo "  ✓ agents → .github/agents/ ($(ls "$KIT"/agents/*.agent.md | wc -l | tr -d ' ') files)"
fi

# 2) Gates — sh + ps1 pairs, rubric, and hook configs (run repo-relative).
for source_file in checks.sh checks.ps1 reconcile.sh reconcile.ps1 quality-gate.sh quality-gate.ps1 \
  backend-checks.sh backend-checks.ps1 rubric.md; do
  managed_safe_replace "$KIT/gates/$source_file" "gates/$source_file" || exit 1
done
managed_copy_tree "$KIT/gates/hooks" gates/hooks || exit 1
echo "  ✓ gates → gates/ (checks · reconcile · quality-gate · backend-checks, .sh + .ps1, + rubric)"

# 2b) Knowledge packs — platform, backend, operations UX, token, learning, and YAGNI rule bases.
managed_copy_tree "$KIT/knowledge" knowledge || exit 1
echo "  ✓ knowledge → knowledge/ (apple · microsoft · web · backend · operations-ux · design-tokens · execution-policy · learning-loop · yagni · runtime-v2)"

# 2b-ii) Platform constitution(s) — application profile only.
if [ "$profile" = "knowledge" ]; then
  echo "  • constitution-*.md skipped (knowledge profile: no native-app UI)"
else
  for source_file in "$KIT"/constitution-*.md; do
    managed_safe_replace "$source_file" "${source_file##*/}" || exit 1
  done
  echo "  ✓ constitution → constitution-*.md (deep native-app synthesis; Apple + Windows)"
fi

# 2c) Audit harness — durable run artifacts + optional semantic review helpers.
managed_copy_tree "$KIT/harness" harness || exit 1
echo "  ✓ harness → harness/ (init-run · validate-run · semantic-review · semantic learning recovery)"

# 3) architrave.config.json — scaffold only if absent (never clobber).
if [ ! -f "$TARGET/architrave.config.json" ]; then
  if [ "$profile" = "knowledge" ]; then
    managed_safe_create "$KIT/kit/examples/knowledge.architrave.json" architrave.config.json || exit 1
  else
    config_stage="$(mktemp)" || exit 1
    cat > "$config_stage" <<'JSON'
{
  "platform": "web",
  "stack": "react",
  "designSource": { "type": "storybook", "path": ".storybook", "url": "http://localhost:6006" },
  "designMap": "docs/design/ui-map.json",
  "tokens": "tokens/tokens.json",
  "applyTo": ["src/**"],
  "build": "npm run build",
  "test": "npm test",
  "learning": {
    "runArtifactsPath": ".architrave/runs",
    "repoProfilePath": ".architrave/learning/repo-profile.md",
    "lessonsPath": ".architrave/learning/repo-lessons.md",
    "capture": ["run-artifacts", "gate-results", "judge-verdicts", "runtime-evidence", "repo-profile", "lessons"],
    "redactionPolicy": "no-secrets",
    "staleFactPolicy": "validate-before-use",
    "promotionPolicy": "approval-required",
    "promoteAfterOccurrences": 2,
    "promoteTargets": ["architrave.config.json", "AGENTS.md", ".github/instructions", "docs"]
  }
}
JSON
    chmod 644 "$config_stage"
    managed_safe_create "$config_stage" architrave.config.json || { rm -f "$config_stage"; exit 1; }
    rm -f "$config_stage"
  fi
  echo "  ✓ scaffolded architrave.config.json (profile: $profile)  ← EDIT build/test and paths to match this repo"
else
  echo "  • architrave.config.json already present — left as-is"
fi

# 3b) Agent session run artifacts are local by default; learning files stay tracked.
gi="$TARGET/.gitignore"
missing_ignore=0
for ignore_rule in .architrave/runs/ .architrave/worktrees/ .architrave/runtime.key .architrave/resources.lock; do
  if [ ! -f "$gi" ] || ! grep -qxF "$ignore_rule" "$gi"; then missing_ignore=1; fi
done
if [ "$missing_ignore" -eq 0 ]; then
  echo "  • .gitignore already ignores Architrave private runtime files"
else
  gi_stage="$(mktemp)" || exit 1
  if [ -f "$gi" ]; then managed_require_file .gitignore || { rm -f "$gi_stage"; exit 1; }; cat "$gi" > "$gi_stage"; fi
  printf '\n# Architrave: private run evidence and isolated worker trees stay local.\n' >> "$gi_stage"
  for ignore_rule in .architrave/runs/ .architrave/worktrees/ .architrave/runtime.key .architrave/resources.lock; do
    grep -qxF "$ignore_rule" "$gi_stage" || printf '%s\n' "$ignore_rule" >> "$gi_stage"
  done
  chmod 644 "$gi_stage"
  managed_safe_replace "$gi_stage" .gitignore || { rm -f "$gi_stage"; exit 1; }
  rm -f "$gi_stage"
  echo "  ✓ .gitignore → ignoring runs, worktrees, and runtime key"
fi

# 4) AGENTS.md stanza — idempotent (replace the managed block, else append).
ag="$TARGET/AGENTS.md"
tmp="$(mktemp)"
managed_preflight_file AGENTS.md || { rm -f "$tmp"; exit 1; }
if [ -f "$ag" ]; then
  managed_require_file AGENTS.md || { rm -f "$tmp"; exit 1; }
  cat "$ag" > "$tmp"
else
  printf '# AGENTS.md\n' > "$tmp"
fi
tmp2="$(mktemp)"
awk -v b="$begin" -v e="$end" '
  $0==b {drop=1; next}
  drop && $0==e {drop=0; next}
  !drop {print}
' "$tmp" > "$tmp2"
mv "$tmp2" "$tmp"
{ printf '\n%s\n' "$begin"; cat "$KIT/templates/AGENTS.stanza.md"; printf '%s\n' "$end"; } >> "$tmp"
chmod 644 "$tmp"
managed_safe_replace "$tmp" AGENTS.md || { rm -f "$tmp"; exit 1; }
rm -f "$tmp"
echo "  ✓ AGENTS.md stanza injected/refreshed"

# 5) PostToolUse hook (POSIX). On Windows, install.ps1 wires the .ps1 variant.
managed_safe_replace "$KIT/gates/hooks/design-guard.json" .github/hooks/design-guard.json || exit 1
echo "  ✓ .github/hooks/design-guard.json (PostToolUse JSON guard)"

# 6) copilot-setup-steps.yml — only if absent (so the cloud agent can run gates).
setup="$TARGET/.github/workflows/copilot-setup-steps.yml"
if [ ! -f "$setup" ]; then
  managed_safe_create "$KIT/templates/copilot-setup-steps.yml" .github/workflows/copilot-setup-steps.yml || exit 1
  echo "  ✓ .github/workflows/copilot-setup-steps.yml"
else
  echo "  • copilot-setup-steps.yml present — merge jq install manually"
fi

# 7) Version stamp — lets gates/checks.sh detect when these copied assets go stale.
if [ "$install_codex" -eq 1 ]; then
  python3 "$KIT/tools/codex-roles.py" --kit "$KIT" --target "$TARGET" || exit $?
fi

if command -v jq >/dev/null 2>&1; then ver="$(jq -r '.version // "0.0.0"' "$KIT/plugin.json")"; else ver="$(grep -m1 '"version"' "$KIT/plugin.json" | sed -E 's/.*"([0-9]+\.[0-9]+\.[0-9]+)".*/\1/')"; fi
version_stage="$(mktemp)" || exit 1
printf '%s\n' "${ver:-0.0.0}" > "$version_stage"
chmod 644 "$version_stage"
managed_safe_replace "$version_stage" gates/.kit-version || { rm -f "$version_stage"; exit 1; }
rm -f "$version_stage"
echo "  ✓ stamped gates/.kit-version = ${ver:-0.0.0}"

cat <<EOF

Done. Next steps:
  1. Edit architrave.config.json to match this repo (profile: $profile).
  2. Install the agents for local Copilot surfaces (CLI + app + VS Code):
      copilot plugin marketplace add dragoshont/architrave
      copilot plugin install architrave@architrave
EOF
if [ "$profile" = "application" ]; then
cat <<EOF
  3. (Optional, React Storybook) Wire the live Storybook MCP so agents reuse real
     components instead of reinventing — then set designSource.mcp to the URL:
       npx storybook add @storybook/addon-mcp
       npx mcp-add --type http --url "http://localhost:6006/mcp" --scope project
  4. (Optional, real product/UI references) Wire Mobbin MCP (browser OAuth, no API key)
     as a local client config:
       npx mcp-add --name mobbin --type http --url "https://api.mobbin.com/mcp" \
         --scope global --clients "copilot cli,vscode,claude code"
  5. (Optional, self-hosted web search) Wire SearXNG MCP pointed at your own instance;
     keep private instance URLs/credentials out of Git and architrave.config.json:
       npx mcp-add --name searxng --type stdio --command npx --args "-y,mcp-searxng" \
         --env "SEARXNG_URL=https://searxng.your-host.example" --scope global \
         --clients "copilot cli,vscode,claude code"
  6. Run the Architrave agent for a non-trivial change.
EOF
else
cat <<EOF
  3. Run gates/checks.sh and edit the knowledge profile's build/test commands if needed.
  4. Start a new agent session and ask Architrave to summarize the configured repository profile.
EOF
fi
cat <<EOF

After you later update the plugin, refresh this repo's copied gates + harness + knowledge + constitution
(they don't auto-update; leaves architrave.config.json and .github/agents untouched by default):
       "$KIT/tools/update.sh" "$TARGET"
Use "$KIT/tools/update.sh" --agents "$TARGET" only when you deliberately want
to refresh copied Architrave agents after archiving bespoke repo agents.
Use "$KIT/tools/update.sh" --codex "$TARGET" to refresh only the generated
Codex roles and managed role registrations. Skills come from the plugin only.
EOF
