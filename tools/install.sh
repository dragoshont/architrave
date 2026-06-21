#!/usr/bin/env bash
# Architrave UI installer — grounds a target repo so the kit works across every
# Copilot surface (CLI, the Copilot app, VS Code, and the cloud agent):
#   • copies the five agents into .github/agents/   (discovery location)
#   • copies the gates (sh + ps1 + rubric + hooks) into gates/
#   • scaffolds uikit.config.json                   (retargeting config)
#   • injects the Architrave UI stanza into AGENTS.md (reaches the cloud agent)
#   • drops .github/workflows/copilot-setup-steps.yml (cloud-agent gate deps)
#   • wires the POSIX PostToolUse hook into .github/hooks/
#
# Usage: tools/install.sh [TARGET_REPO_DIR]      (default: current directory)
# For local agents you ALSO install the plugin once:
#   copilot plugin marketplace add dragoshont/architrave-ui
#   copilot plugin install architrave-ui@architrave
set -uo pipefail

KIT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${1:-$PWD}"
TARGET="$(cd "$TARGET" 2>/dev/null && pwd)" || { echo "install: target dir not found: ${1:-$PWD}" >&2; exit 1; }
[ "$TARGET" = "$KIT" ] && { echo "install: refusing to install the kit into itself" >&2; exit 1; }

begin="<!-- architrave-ui:begin -->"
end="<!-- architrave-ui:end -->"

echo "Architrave UI → installing into: $TARGET"
mkdir -p "$TARGET/.github/agents" "$TARGET/.github/hooks" "$TARGET/.github/workflows" "$TARGET/gates/hooks"

# 1) Agents — the discovery location read by CLI / app / VS Code / cloud agent.
cp "$KIT"/agents/*.agent.md "$TARGET/.github/agents/"
echo "  ✓ agents → .github/agents/ ($(ls "$KIT"/agents/*.agent.md | wc -l | tr -d ' ') files)"

# 2) Gates — sh + ps1 pairs, rubric, and hook configs (run repo-relative).
cp "$KIT"/gates/checks.sh "$KIT"/gates/checks.ps1 \
   "$KIT"/gates/reconcile.sh "$KIT"/gates/reconcile.ps1 \
   "$KIT"/gates/quality-gate.sh "$KIT"/gates/quality-gate.ps1 \
   "$KIT"/gates/backend-checks.sh "$KIT"/gates/backend-checks.ps1 \
   "$KIT"/gates/rubric.md "$TARGET/gates/"
cp "$KIT"/gates/hooks/*.json "$TARGET/gates/hooks/"
chmod +x "$TARGET"/gates/*.sh "$TARGET"/gates/*.ps1 2>/dev/null || true
echo "  ✓ gates → gates/ (checks · reconcile · quality-gate · backend-checks, .sh + .ps1, + rubric)"

# 2b) Knowledge packs — the Platform Design agent reads these per config.platform.
mkdir -p "$TARGET/knowledge"
cp "$KIT"/knowledge/*.md "$TARGET/knowledge/"
echo "  ✓ knowledge → knowledge/ (apple · microsoft · web · backend · design-tokens)"

# 3) uikit.config.json — scaffold only if absent (never clobber).
if [ ! -f "$TARGET/uikit.config.json" ]; then
  cat > "$TARGET/uikit.config.json" <<'JSON'
{
  "platform": "web",
  "stack": "react",
  "designSource": { "type": "storybook", "path": ".storybook", "url": "http://localhost:6006" },
  "designMap": "docs/design/ui-map.json",
  "tokens": "tokens/tokens.json",
  "applyTo": ["src/**"],
  "build": "npm run build",
  "test": "npm test"
}
JSON
  echo "  ✓ scaffolded uikit.config.json  ← EDIT to match this repo"
else
  echo "  • uikit.config.json already present — left as-is"
fi

# 4) AGENTS.md stanza — idempotent (replace the managed block, else append).
ag="$TARGET/AGENTS.md"
tmp="$(mktemp)"
if [ -f "$ag" ] && grep -qF "$begin" "$ag"; then
  awk -v b="$begin" -v e="$end" '$0==b{drop=1} drop&&$0==e{drop=0;next} !drop{print}' "$ag" > "$tmp"
elif [ -f "$ag" ]; then
  cat "$ag" > "$tmp"
else
  printf '# AGENTS.md\n' > "$tmp"
fi
{ printf '\n%s\n' "$begin"; cat "$KIT/templates/AGENTS.stanza.md"; printf '%s\n' "$end"; } >> "$tmp"
mv "$tmp" "$ag"
echo "  ✓ AGENTS.md stanza injected/refreshed"

# 5) PostToolUse hook (POSIX). On Windows, install.ps1 wires the .ps1 variant.
cp "$KIT/gates/hooks/design-guard.json" "$TARGET/.github/hooks/design-guard.json"
echo "  ✓ .github/hooks/design-guard.json (PostToolUse JSON guard)"

# 6) copilot-setup-steps.yml — only if absent (so the cloud agent can run gates).
setup="$TARGET/.github/workflows/copilot-setup-steps.yml"
if [ ! -f "$setup" ]; then
  cp "$KIT/templates/copilot-setup-steps.yml" "$setup"
  echo "  ✓ .github/workflows/copilot-setup-steps.yml"
else
  echo "  • copilot-setup-steps.yml present — merge jq install manually"
fi

# 7) Version stamp — lets gates/checks.sh detect when these copied assets go stale.
if command -v jq >/dev/null 2>&1; then ver="$(jq -r '.version // "0.0.0"' "$KIT/plugin.json")"; else ver="$(grep -m1 '"version"' "$KIT/plugin.json" | sed -E 's/.*"([0-9]+\.[0-9]+\.[0-9]+)".*/\1/')"; fi
printf '%s\n' "${ver:-0.0.0}" > "$TARGET/gates/.kit-version"
echo "  ✓ stamped gates/.kit-version = ${ver:-0.0.0}"

cat <<EOF

Done. Next steps:
  1. Edit uikit.config.json to match this repo (platform/stack/designSource/tokens/build/test).
  2. Install the agents for local Copilot surfaces (CLI + app + VS Code):
       copilot plugin marketplace add dragoshont/architrave-ui
       copilot plugin install architrave-ui@architrave
  3. (Optional, React Storybook) Wire the live Storybook MCP so agents reuse real
     components instead of reinventing — then set designSource.mcp to the URL:
       npx storybook add @storybook/addon-mcp
       npx mcp-add --type http --url "http://localhost:6006/mcp" --scope project
  4. Run the Architrave agent for a non-trivial UI change.

After you later update the plugin, refresh this repo's copied gates + knowledge
(they don't auto-update; leaves uikit.config.json untouched):
       "$KIT/tools/update.sh" "$TARGET"
EOF
