#!/usr/bin/env bash
# Promote an approved lesson into a repo-local Markdown guidance file.
# Dry-run by default; use --apply for writes. Runs validate-learning first.
set -uo pipefail

apply=0
lesson=""
target=""
heading="Promoted Lessons"
repo="$PWD"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --apply) apply=1; shift ;;
    --lesson) lesson="${2:-}"; shift 2 ;;
    --target) target="${2:-}"; shift 2 ;;
    --heading) heading="${2:-}"; shift 2 ;;
    --repo) repo="${2:-}"; shift 2 ;;
    -h|--help)
      echo "Usage: harness/promote-lesson.sh --lesson TEXT --target PATH.md [--heading NAME] [--apply] [--repo DIR]"
      exit 0
      ;;
    *) echo "promote-lesson: unknown argument $1" >&2; exit 2 ;;
  esac
done

cd "$repo" 2>/dev/null || { echo "promote-lesson: repo dir not found: $repo" >&2; exit 2; }
[ -n "$lesson" ] || { echo "promote-lesson: --lesson is required" >&2; exit 2; }
[ -n "$target" ] || { echo "promote-lesson: --target is required" >&2; exit 2; }
case "$target" in
  /*|../*|*/../*) echo "promote-lesson: target must be repo-relative and stay inside the repo" >&2; exit 2 ;;
  *.md|AGENTS.md) : ;;
  *) echo "promote-lesson: target must be a Markdown file" >&2; exit 2 ;;
esac

if [ -x harness/validate-learning.sh ]; then
  harness/validate-learning.sh >/dev/null || exit 1
else
  echo "promote-lesson: harness/validate-learning.sh not found or not executable" >&2
  exit 2
fi

entry="- ${lesson}"
if [ "$apply" -ne 1 ]; then
  echo "DRY RUN: would append to $target under heading '$heading':"
  echo "$entry"
  exit 0
fi

mkdir -p "$(dirname "$target")"
touch "$target"
if ! grep -qE "^##[[:space:]]+${heading//\/\\}$" "$target"; then
  { [ -s "$target" ] && printf '\n'; printf '## %s\n\n' "$heading"; } >> "$target"
fi
printf '%s\n' "$entry" >> "$target"
echo "promoted lesson to $target"