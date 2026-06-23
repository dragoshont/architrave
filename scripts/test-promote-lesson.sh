#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

make_repo() {
  local repo="$1"
  mkdir -p "$repo/.architrave/learning" "$repo/harness"
  cp harness/validate-learning.sh harness/promote-lesson.sh "$repo/harness/"
  chmod +x "$repo"/harness/*.sh
  cat > "$repo/.architrave/learning/repo-profile.md" <<'MD'
# Repo Profile
MD
  cat > "$repo/.architrave/learning/repo-lessons.md" <<'MD'
# Repo Lessons
MD
}

repo="$tmp/repo"; make_repo "$repo"
(cd "$repo" && harness/promote-lesson.sh --lesson "Use the quick gate before release." --target docs/guide.md >/tmp/promote-dry.txt)
[ ! -e "$repo/docs/guide.md" ] || { echo "FAIL dry run wrote target" >&2; exit 1; }
grep -q 'DRY RUN' /tmp/promote-dry.txt && echo 'ok   dry-run'
(cd "$repo" && harness/promote-lesson.sh --lesson "Use the quick gate before release." --target docs/guide.md --apply >/dev/null)
grep -q 'Use the quick gate before release.' "$repo/docs/guide.md" && echo 'ok   apply'
if (cd "$repo" && harness/promote-lesson.sh --target docs/guide.md >/dev/null 2>&1); then echo 'FAIL missing lesson expected failure' >&2; exit 1; else echo 'ok   missing-lesson'; fi
if (cd "$repo" && harness/promote-lesson.sh --lesson nope --target ../escape.md >/dev/null 2>&1); then echo 'FAIL invalid target expected failure' >&2; exit 1; else echo 'ok   invalid-target'; fi