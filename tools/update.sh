#!/usr/bin/env bash
# Architrave UI — refresh an adopted repo's COPIED kit assets (gates + knowledge +
# the AGENTS.md grounding stanza) to match THIS kit, and re-stamp the version.
#
# Why this exists: a plugin update (`copilot plugin update` / `claude plugin
# marketplace update`) refreshes the AGENTS only. But `tools/install.sh` also
# copies the gates + knowledge packs INTO each repo (so the gates can execute and
# the cloud agent — which has no plugin — can read them). Those copies do NOT
# auto-update, so after you bump the plugin, run this in each adopted repo.
#
# It never touches uikit.config.json and never re-adds per-repo .github/agents.
#
# Usage: tools/update.sh [TARGET_REPO_DIR]   (default: current directory)
set -uo pipefail

KIT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${1:-$PWD}"
TARGET="$(cd "$TARGET" 2>/dev/null && pwd)" || { echo "update: target dir not found: ${1:-$PWD}" >&2; exit 1; }
[ "$TARGET" = "$KIT" ] && { echo "update: refusing to update the kit into itself" >&2; exit 1; }
[ -f "$TARGET/uikit.config.json" ] || { echo "update: $TARGET has no uikit.config.json — run tools/install.sh first" >&2; exit 1; }

if command -v jq >/dev/null 2>&1; then
  ver="$(jq -r '.version // "0.0.0"' "$KIT/plugin.json")"
else
  ver="$(grep -m1 '"version"' "$KIT/plugin.json" | sed -E 's/.*"([0-9]+\.[0-9]+\.[0-9]+)".*/\1/')"
fi
begin="<!-- architrave-ui:begin -->"
end="<!-- architrave-ui:end -->"

echo "Architrave UI → refreshing assets in: $TARGET (kit v${ver:-?})"
mkdir -p "$TARGET/gates/hooks" "$TARGET/knowledge"

# Gates — copied because they EXECUTE in the repo (hook + cloud agent run them).
cp "$KIT"/gates/checks.sh "$KIT"/gates/checks.ps1 \
   "$KIT"/gates/reconcile.sh "$KIT"/gates/reconcile.ps1 \
   "$KIT"/gates/quality-gate.sh "$KIT"/gates/quality-gate.ps1 \
   "$KIT"/gates/backend-checks.sh "$KIT"/gates/backend-checks.ps1 \
   "$KIT"/gates/rubric.md "$TARGET/gates/"
cp "$KIT"/gates/hooks/*.json "$TARGET/gates/hooks/"
chmod +x "$TARGET"/gates/*.sh "$TARGET"/gates/*.ps1 2>/dev/null || true
echo "  ✓ gates refreshed"

# Knowledge packs — copied so the cloud agent (no plugin) can read them.
cp "$KIT"/knowledge/*.md "$TARGET/knowledge/"
echo "  ✓ knowledge refreshed (apple · microsoft · web · backend · design-tokens)"

# AGENTS.md grounding stanza — idempotent (replace the managed block, else append).
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
echo "  ✓ AGENTS.md stanza refreshed"

# Version stamp — lets gates/checks.sh detect future drift.
printf '%s\n' "${ver:-0.0.0}" > "$TARGET/gates/.kit-version"
echo "  ✓ stamped gates/.kit-version = ${ver:-0.0.0}"
echo "Done. (uikit.config.json and .github/agents left untouched.)"
