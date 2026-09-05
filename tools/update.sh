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
# Usage: tools/update.sh [--agents] [--codex] [TARGET_REPO_DIR]   (default: current directory)
set -euo pipefail

KIT="$(cd "$(dirname "$0")/.." && pwd)"
. "$KIT/tools/managed-paths.sh"

refresh_agents=0
refresh_codex=0
target_arg=""
for arg in "$@"; do
  case "$arg" in
    --agents)
      refresh_agents=1
      ;;
    --codex)
      refresh_codex=1
      ;;
    -h|--help)
      echo "Usage: tools/update.sh [--agents] [--codex] [TARGET_REPO_DIR]"
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
TARGET="$(cd "$TARGET" 2>/dev/null && pwd -P)" || { echo "update: target dir not found: ${1:-$PWD}" >&2; exit 1; }
[ "$TARGET" = "$KIT" ] && { echo "update: refusing to update the kit into itself" >&2; exit 1; }
managed_paths_init "$TARGET" update
managed_require_file architrave.config.json || { echo "update: $TARGET has no safe architrave.config.json — run tools/install.sh first" >&2; exit 1; }

command -v jq >/dev/null 2>&1 || { echo "update: jq is required to parse architrave.config.json safely" >&2; exit 2; }
jq -e 'type == "object"' "$TARGET/architrave.config.json" >/dev/null 2>&1 || {
  echo "update: invalid architrave.config.json (root must be a JSON object)" >&2
  exit 2
}
jq -e '[keys[] | select(ascii_downcase == "kind" and . != "kind")] | length == 0' "$TARGET/architrave.config.json" >/dev/null 2>&1 || {
  echo "update: invalid architrave.config.json (kind property is case-sensitive)" >&2
  exit 2
}
kind_exact_count="$(jq --stream -c 'select(length == 2 and (.[0] | length == 1) and .[0][0] == "kind")' "$TARGET/architrave.config.json" | wc -l | tr -d ' ')"
kind_nested_count="$(jq --stream -c 'select(length == 2 and (.[0] | length > 1) and .[0][0] == "kind")' "$TARGET/architrave.config.json" | wc -l | tr -d ' ')"
[ "$kind_exact_count" -le 1 ] && [ "$kind_nested_count" -eq 0 ] || {
  echo "update: invalid architrave.config.json (kind must occur at most once as a scalar)" >&2
  exit 2
}
kind="$(jq -er '
  if has("kind") then
    if .kind == "knowledge" then "knowledge" else error("unsupported kind") end
  else "application"
  end
' "$TARGET/architrave.config.json" 2>/dev/null)" || {
  echo "update: invalid architrave.config.json (kind must be absent or 'knowledge')" >&2
  exit 2
}

if [ "$refresh_codex" -eq 1 ]; then
  command -v python3 >/dev/null 2>&1 || { echo "update: --codex requires Python 3.11+" >&2; exit 2; }
  python3 "$KIT/tools/codex-roles.py" --kit "$KIT" --target "$TARGET" --preflight || exit $?
fi
ver="$(jq -er '.version | select(type == "string")' "$KIT/plugin.json")" || { echo "update: plugin version is invalid" >&2; exit 1; }
begin="<!-- architrave:begin -->"
end="<!-- architrave:end -->"

for source_tree in gates knowledge harness; do managed_assert_source_tree "$KIT/$source_tree" || exit 1; done
if [ "$refresh_agents" -eq 1 ]; then managed_assert_source_tree "$KIT/agents" || exit 1; fi
managed_assert_source_file "$KIT/templates/AGENTS.stanza.md" || exit 1
managed_assert_source_file "$KIT/plugin.json" || exit 1
if [ "$kind" = "application" ]; then
  for source_file in "$KIT"/constitution-*.md; do managed_assert_source_file "$source_file" || exit 1; done
fi

for tree in .github/hooks gates gates/hooks knowledge harness; do managed_preflight_tree "$tree" || exit 1; done
if [ "$refresh_agents" -eq 1 ]; then managed_preflight_tree .github/agents || exit 1; fi
for file in architrave.config.json .gitignore AGENTS.md constitution-apple.md constitution-windows.md \
  .github/hooks/design-guard.json gates/.kit-version; do
  managed_preflight_file "$file" || exit 1
done

echo "Architrave → refreshing assets in: $TARGET (kit v${ver:-?})"
for directory in .github/hooks gates/hooks knowledge harness; do managed_ensure_dir "$directory" || exit 1; done

if [ "$refresh_agents" -eq 1 ]; then
  managed_ensure_dir .github/agents || exit 1
  managed_preflight_tree .github/agents || exit 1
  if [ "$kind" = "knowledge" ]; then
    for source in "$KIT"/agents/*.agent.md; do
      name="${source##*/}"
      case "$name" in
        architrave.agent.md|adversarial-judge.agent.md|tournament-analyst.agent.md|product-research.agent.md|runtime-observer.agent.md) ;;
        *) managed_safe_remove ".github/agents/$name" || exit 1 ;;
      esac
    done
    for a in architrave adversarial-judge tournament-analyst product-research runtime-observer; do
      managed_safe_replace "$KIT/agents/$a.agent.md" ".github/agents/$a.agent.md" || exit 1
    done
    echo "  ✓ agents refreshed (knowledge crew: architrave · adversarial-judge · tournament-analyst · product-research · runtime-observer)"
  else
    for source_file in "$KIT"/agents/*.agent.md; do
      managed_safe_replace "$source_file" ".github/agents/${source_file##*/}" || exit 1
    done
    echo "  ✓ agents refreshed ($(ls "$KIT"/agents/*.agent.md | wc -l | tr -d ' ') files)"
  fi
else
  echo "  • agents left unchanged (use --agents to refresh .github/agents/)"
fi

# Gates — copied because they EXECUTE in the repo (hook + cloud agent run them).
for source_file in checks.sh checks.ps1 reconcile.sh reconcile.ps1 quality-gate.sh quality-gate.ps1 \
  backend-checks.sh backend-checks.ps1 rubric.md; do
  managed_safe_replace "$KIT/gates/$source_file" "gates/$source_file" || exit 1
done
managed_copy_tree "$KIT/gates/hooks" gates/hooks || exit 1
echo "  ✓ gates refreshed"

# Active workspace hook. POSIX updater installs the POSIX command variant.
managed_safe_replace "$KIT/gates/hooks/design-guard.json" .github/hooks/design-guard.json || {
  echo "update: failed to refresh active workspace hook" >&2
  exit 1
}
echo "  ✓ active workspace hook refreshed"

# Knowledge packs — copied so the cloud agent (no plugin) can read them.
managed_copy_tree "$KIT/knowledge" knowledge || exit 1
echo "  ✓ knowledge refreshed (apple · microsoft · web · backend · operations-ux · design-tokens · execution-policy · learning-loop · yagni · runtime-v2)"

# Platform constitution(s) - application profile only; knowledge updates remove managed copies.
if [ "$kind" = "knowledge" ]; then
  managed_safe_remove constitution-apple.md || exit 1
  managed_safe_remove constitution-windows.md || exit 1
  echo "  ✓ constitution removed/skipped (knowledge profile: no native-app UI)"
else
  for source_file in "$KIT"/constitution-*.md; do
    managed_safe_replace "$source_file" "${source_file##*/}" || exit 1
  done
  echo "  ✓ constitution refreshed (constitution-*.md; Apple + Windows native-app synthesis)"
fi

# Audit harness.
managed_copy_tree "$KIT/harness" harness || exit 1
echo "  ✓ harness refreshed"

# Agent session run artifacts are local by default; learning files stay tracked.
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
  echo "  ✓ .gitignore updated (runs, worktrees, and runtime key stay local)"
fi

# AGENTS.md grounding stanza — idempotent (replace the managed block, else append).
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
echo "  ✓ AGENTS.md stanza refreshed"

# Version stamp — lets gates/checks.sh detect future drift.
if [ "$refresh_codex" -eq 1 ]; then
  python3 "$KIT/tools/codex-roles.py" --kit "$KIT" --target "$TARGET" || exit $?
fi

version_stage="$(mktemp)" || exit 1
printf '%s\n' "${ver:-0.0.0}" > "$version_stage"
chmod 644 "$version_stage"
managed_safe_replace "$version_stage" gates/.kit-version || { rm -f "$version_stage"; exit 1; }
rm -f "$version_stage"
echo "  ✓ stamped gates/.kit-version = ${ver:-0.0.0}"
echo "Done. (architrave.config.json left untouched.)"
