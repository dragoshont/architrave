#!/usr/bin/env bash
# Pick a candidate lesson row from repo-lessons.md and delegate to promote-lesson.
set -uo pipefail

index=""
target=""
apply=0
repo="$PWD"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --index) index="${2:-}"; shift 2 ;;
    --target) target="${2:-}"; shift 2 ;;
    --apply) apply=1; shift ;;
    --repo) repo="${2:-}"; shift 2 ;;
    -h|--help) echo "Usage: harness/promote-lesson-picker.sh --index N --target PATH.md [--apply] [--repo DIR]"; exit 0 ;;
    *) echo "promote-lesson-picker: unknown argument $1" >&2; exit 2 ;;
  esac
done

cd "$repo" 2>/dev/null || { echo "promote-lesson-picker: repo dir not found: $repo" >&2; exit 2; }
[ -n "$index" ] || { echo "promote-lesson-picker: --index is required" >&2; exit 2; }
[ -n "$target" ] || { echo "promote-lesson-picker: --target is required" >&2; exit 2; }
case "$index" in *[!0-9]*|"") echo "promote-lesson-picker: --index must be a positive integer" >&2; exit 2 ;; esac
[ "$index" -gt 0 ] || { echo "promote-lesson-picker: --index must be a positive integer" >&2; exit 2; }

lessons=".architrave/learning/repo-lessons.md"
[ -s "$lessons" ] || { echo "promote-lesson-picker: missing $lessons" >&2; exit 2; }
lesson="$(awk -F'|' -v want="$index" '
  /^\|/ && $2 !~ /^[[:space:]]*(-+|Lesson)[[:space:]]*$/ {
    count++
    if (count == want) { gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2); print $2; exit }
  }
' "$lessons")"
[ -n "$lesson" ] || { echo "promote-lesson-picker: candidate index not found: $index" >&2; exit 2; }

args=(--lesson "$lesson" --target "$target")
[ "$apply" -eq 1 ] && args+=(--apply)
harness/promote-lesson.sh "${args[@]}"