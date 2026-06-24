#!/usr/bin/env bash
# Mark learning lines with broken local Markdown links as unvalidated.
set -uo pipefail
apply=0
repo="$PWD"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --apply) apply=1; shift ;;
    --repo) repo="${2:-}"; shift 2 ;;
    -h|--help) echo "Usage: harness/mark-stale-learning.sh [--apply] [--repo DIR]"; exit 0 ;;
    *) echo "mark-stale-learning: unknown argument $1" >&2; exit 2 ;;
  esac
done
cd "$repo" 2>/dev/null || { echo "mark-stale-learning: repo dir not found: $repo" >&2; exit 2; }

files=(.architrave/learning/repo-profile.md .architrave/learning/repo-lessons.md)
changed=0
for file in "${files[@]}"; do
  [ -f "$file" ] || continue
  tmp="$(mktemp)"
  while IFS= read -r line || [ -n "$line" ]; do
    stale=0
    while IFS= read -r target; do
      case "$target" in http://*|https://*|mailto:*|""|'#'*) continue ;; esac
      path="${target%%#*}"; path="${path//%20/ }"
      case "$path" in /*|../*|*/../*) stale=1; continue ;; esac
      [ -n "$path" ] && [ ! -e "$path" ] && stale=1
    done < <(printf '%s\n' "$line" | grep -oE '\[[^]]+\]\(([^)]+)\)' | sed -E 's/.*\(([^)]+)\).*/\1/')
    if [ "$stale" -eq 1 ] && [[ "$line" != *"UNVALIDATED:"* ]]; then
      changed=1
      if [ "$apply" -eq 1 ]; then printf '%s\n' "UNVALIDATED: $line" >> "$tmp"; else printf '%s\n' "would mark $file: $line"; printf '%s\n' "$line" >> "$tmp"; fi
    else
      printf '%s\n' "$line" >> "$tmp"
    fi
  done < "$file"
  if [ "$apply" -eq 1 ]; then mv "$tmp" "$file"; else rm -f "$tmp"; fi
done
if [ "$changed" -eq 0 ]; then echo "mark-stale-learning: no stale local learning links found"; fi