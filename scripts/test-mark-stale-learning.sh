#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
repo="$tmp/repo"
mkdir -p "$repo/.architrave/learning" "$repo/harness" "$repo/docs"
cp harness/mark-stale-learning.sh "$repo/harness/"
chmod +x "$repo/harness/mark-stale-learning.sh"
printf '# Present\n' > "$repo/docs/present.md"
cat > "$repo/.architrave/learning/repo-profile.md" <<'MD'
# Profile
Valid [present](docs/present.md)
Broken [missing](docs/missing.md)
MD
printf '# Lessons\n' > "$repo/.architrave/learning/repo-lessons.md"
(cd "$repo" && harness/mark-stale-learning.sh >/tmp/stale-dry.txt)
grep -q 'would mark' /tmp/stale-dry.txt && ! grep -q 'UNVALIDATED' "$repo/.architrave/learning/repo-profile.md" && echo 'ok   stale-dry-run'
(cd "$repo" && harness/mark-stale-learning.sh --apply >/dev/null)
grep -q 'UNVALIDATED: Broken' "$repo/.architrave/learning/repo-profile.md" && echo 'ok   stale-apply'