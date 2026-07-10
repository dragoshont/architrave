#!/usr/bin/env bash
# Architrave — refresh an adopted repo's COPIED kit assets (gates + knowledge + harness + constitution +
# the AGENTS.md grounding stanza) to match THIS kit, and re-stamp the version.
#
# Why this exists: a plugin update (`copilot plugin update` / `claude plugin
# marketplace update`) refreshes only the locally installed plugin. But `tools/install.sh`
# also copies agents, gates, knowledge packs, the platform constitution, and harness INTO each repo (so the gates
# can execute and the cloud agent — which has no plugin — can read them). Those copies
# do NOT auto-update, so after you bump the plugin, run this in each adopted repo.
#
# It never touches architrave.config.json. By default it does not touch .github/agents;
# pass --agents to refresh the Architrave-managed copied agent files after archiving
# bespoke repo agents to avoid split authority.
#
# Usage: tools/update.sh [--agents] [TARGET_REPO_DIR]   (default: current directory)
set -euo pipefail

KIT="$(cd "$(dirname "$0")/.." && pwd)"

refresh_agents=0
target_arg=""
for arg in "$@"; do
  case "$arg" in
    --agents)
      refresh_agents=1
      ;;
    -h|--help)
      echo "Usage: tools/update.sh [--agents] [TARGET_REPO_DIR]"
      exit 0
      ;;
    *)
      if [ -n "$target_arg" ]; then
        echo "update: unexpected extra argument: $arg" >&2
        exit 2
      fi
      target_arg="$arg"
      ;;
  esac
done

TARGET="${target_arg:-$PWD}"
TARGET="$(cd "$TARGET" 2>/dev/null && pwd)" || { echo "update: target dir not found: ${1:-$PWD}" >&2; exit 1; }
[ "$TARGET" = "$KIT" ] && { echo "update: refusing to update the kit into itself" >&2; exit 1; }
[ -f "$TARGET/architrave.config.json" ] || { echo "update: $TARGET has no architrave.config.json — run tools/install.sh first" >&2; exit 1; }

if command -v jq >/dev/null 2>&1; then
  ver="$(jq -r '.version // "0.0.0"' "$KIT/plugin.json")"
else
  ver="$(grep -m1 '"version"' "$KIT/plugin.json" | sed -E 's/.*"([0-9]+\.[0-9]+\.[0-9]+)".*/\1/')"
fi
begin="<!-- architrave:begin -->"
end="<!-- architrave:end -->"

echo "Architrave → refreshing assets in: $TARGET (kit v${ver:-?})"
mkdir -p "$TARGET/.github/hooks" "$TARGET/gates/hooks" "$TARGET/knowledge" "$TARGET/harness"

if [ "$refresh_agents" -eq 1 ]; then
  mkdir -p "$TARGET/.github/agents"
  cp "$KIT"/agents/*.agent.md "$TARGET/.github/agents/"
  echo "  ✓ agents refreshed ($(ls "$KIT"/agents/*.agent.md | wc -l | tr -d ' ') files)"
else
  echo "  • agents left unchanged (use --agents to refresh .github/agents/)"
fi

# Gates — copied because they EXECUTE in the repo (hook + cloud agent run them).
cp "$KIT"/gates/checks.sh "$KIT"/gates/checks.ps1 \
   "$KIT"/gates/reconcile.sh "$KIT"/gates/reconcile.ps1 \
   "$KIT"/gates/quality-gate.sh "$KIT"/gates/quality-gate.ps1 \
   "$KIT"/gates/backend-checks.sh "$KIT"/gates/backend-checks.ps1 \
   "$KIT"/gates/rubric.md "$TARGET/gates/"
cp "$KIT"/gates/hooks/*.json "$TARGET/gates/hooks/"
chmod +x "$TARGET"/gates/*.sh "$TARGET"/gates/*.ps1 2>/dev/null || true
echo "  ✓ gates refreshed"

# Active workspace hook. POSIX updater installs the POSIX command variant.
cp "$KIT/gates/hooks/design-guard.json" "$TARGET/.github/hooks/design-guard.json" || {
  echo "update: failed to refresh active workspace hook" >&2
  exit 1
}
echo "  ✓ active workspace hook refreshed"

# Knowledge packs — copied so the cloud agent (no plugin) can read them.
cp "$KIT"/knowledge/*.md "$TARGET/knowledge/"
echo "  ✓ knowledge refreshed (apple · microsoft · web · backend · operations-ux · design-tokens · learning-loop · yagni)"

# Platform constitution(s) — copied so the cloud agent (no plugin) can read the deep native-app synthesis.
cp "$KIT"/constitution-*.md "$TARGET/" 2>/dev/null && echo "  ✓ constitution refreshed (constitution-*.md; Apple + Windows native-app synthesis)" || true

# Audit harness.
cp -R "$KIT"/harness/* "$TARGET/harness/"
chmod +x "$TARGET"/harness/*.sh 2>/dev/null || true
echo "  ✓ harness refreshed"

# AGENTS.md grounding stanza — idempotent (replace the managed block, else append).
ag="$TARGET/AGENTS.md"
tmp="$(mktemp)"
if [ -f "$ag" ]; then
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
mv "$tmp" "$ag"
echo "  ✓ AGENTS.md stanza refreshed"

# Version stamp — lets gates/checks.sh detect future drift.
printf '%s\n' "${ver:-0.0.0}" > "$TARGET/gates/.kit-version"
echo "  ✓ stamped gates/.kit-version = ${ver:-0.0.0}"
echo "Done. (architrave.config.json left untouched.)"
