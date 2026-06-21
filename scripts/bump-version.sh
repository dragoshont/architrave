#!/usr/bin/env bash
# Architrave UI — single-command version bump across every manifest (one source of truth).
# Both Copilot and Claude treat a *changed* version string as "an update is available";
# a static version means installed users never re-fetch. So bump here, then tag to release.
#
# Usage: scripts/bump-version.sh <X.Y.Z>
#   then: ./scripts/check-manifests.sh
#         git commit -am "Release vX.Y.Z" && git tag vX.Y.Z && git push origin main --tags
set -euo pipefail
cd "$(dirname "$0")/.."

new="${1:-}"
case "$new" in
  [0-9]*.[0-9]*.[0-9]*) : ;;
  *) echo "usage: scripts/bump-version.sh <X.Y.Z>   (semver, no leading 'v')" >&2; exit 1 ;;
esac

set_field() { # <file> <jq-path>
  local f="$1" path="$2" tmp
  tmp=$(mktemp)
  jq --indent 2 "$path = \"$new\"" "$f" > "$tmp" && mv "$tmp" "$f"
  echo "  • $f $path → $new"
}

# Copilot manifests
set_field plugin.json '.version'
set_field .github/plugin/marketplace.json '.metadata.version'
set_field .github/plugin/marketplace.json '.plugins[0].version'
# Claude manifests
set_field .claude-plugin/plugin.json '.version'
set_field .claude-plugin/marketplace.json '.metadata.version'
set_field .claude-plugin/marketplace.json '.plugins[0].version'

echo
echo "Bumped to $new. Next:"
echo "  ./scripts/check-manifests.sh"
echo "  git commit -am \"Release v$new\" && git tag v$new && git push origin main --tags"
