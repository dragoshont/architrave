#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
repo="$tmp/repo"
mkdir -p "$repo/.architrave/learning" "$repo/harness"
cp harness/validate-learning.sh harness/promote-lesson.sh harness/promote-lesson-picker.sh "$repo/harness/"
chmod +x "$repo"/harness/*.sh
printf '# Repo Profile\n' > "$repo/.architrave/learning/repo-profile.md"
cat > "$repo/.architrave/learning/repo-lessons.md" <<'MD'
# Lessons

| Lesson | Evidence | Occurrences | Validated | Proposed Target | Status |
|---|---|---:|---|---|---|
| Run quick gates before release | test | 2 | yes | docs | candidate |
| Keep secrets out of artifacts | test | 2 | yes | docs | candidate |
MD
(cd "$repo" && harness/promote-lesson-picker.sh --index 2 --target docs/guide.md >/tmp/picker-dry.txt)
grep -q 'Keep secrets out of artifacts' /tmp/picker-dry.txt && echo 'ok   picker-dry-run'
(cd "$repo" && harness/promote-lesson-picker.sh --index 1 --target docs/guide.md --apply >/dev/null)
grep -q 'Run quick gates before release' "$repo/docs/guide.md" && echo 'ok   picker-apply'
if (cd "$repo" && harness/promote-lesson-picker.sh --index 99 --target docs/guide.md >/dev/null 2>&1); then echo 'FAIL missing index expected failure' >&2; exit 1; else echo 'ok   picker-missing-index'; fi