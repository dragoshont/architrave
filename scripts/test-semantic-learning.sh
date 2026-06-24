#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
repo="$tmp/repo"
mkdir -p "$repo/.architrave/learning" "$repo/harness" "$repo/docs"
cp harness/semantic-learning-review.sh harness/apply-semantic-learning-findings.sh "$repo/harness/"
chmod +x "$repo"/harness/*.sh
printf '# Guide\n' > "$repo/docs/guide.md"
cat > "$repo/.architrave/learning/repo-profile.md" <<'MD'
# Repo Profile

Build uses make release on Windows.
UNVALIDATED: Old claim.
Evidence-backed claim. Evidence: [guide](docs/guide.md)
MD
cat > "$repo/.architrave/learning/repo-lessons.md" <<'MD'
# Repo Lessons

No durable semantic claims here.
MD

(cd "$repo" && harness/semantic-learning-review.sh --provider copilot >/tmp/semantic-review.txt)
grep -q 'semantic-learning-review prompt:' /tmp/semantic-review.txt
grep -q 'JSON Lines only' "$repo/.architrave/learning/semantic-stale-facts-prompt.md" && echo 'ok   semantic-review-prompt'

cat > "$repo/.architrave/learning/semantic-stale-facts.jsonl" <<'JSONL'
{"file":".architrave/learning/repo-profile.md","line":3,"currentText":"Build uses make release on Windows.","severity":"major","reason":"No current evidence supports this Windows release claim."}
{"file":".architrave/learning/repo-profile.md","line":4,"currentText":"Old claim.","severity":"minor","reason":"Already marked unvalidated."}
JSONL

(cd "$repo" && harness/apply-semantic-learning-findings.sh >/tmp/semantic-dry.txt)
grep -q 'would mark .architrave/learning/repo-profile.md:3' /tmp/semantic-dry.txt
! grep -q '^UNVALIDATED: Build uses make release' "$repo/.architrave/learning/repo-profile.md" && echo 'ok   semantic-dry-run'
(cd "$repo" && harness/apply-semantic-learning-findings.sh --apply >/tmp/semantic-apply.txt)
grep -q '^UNVALIDATED: Build uses make release on Windows\.$' "$repo/.architrave/learning/repo-profile.md" && echo 'ok   semantic-apply'
count="$(grep -c '^UNVALIDATED: Old claim\.$' "$repo/.architrave/learning/repo-profile.md")"
[ "$count" -eq 1 ] && echo 'ok   semantic-existing-unvalidated'

cat > "$repo/.architrave/learning/semantic-stale-facts.jsonl" <<'JSONL'
{"file":".architrave/learning/repo-profile.md","line":3,"currentText":"Different text.","severity":"major","reason":"stale finding"}
JSONL
if (cd "$repo" && harness/apply-semantic-learning-findings.sh --apply >/dev/null 2>&1); then echo 'FAIL stale finding expected failure' >&2; exit 1; else echo 'ok   semantic-stale-finding'; fi

cat > "$repo/.architrave/learning/semantic-stale-facts.jsonl" <<'JSONL'
{"file":"README.md","line":1,"currentText":"# README","severity":"major","reason":"invalid target"}
JSONL
if (cd "$repo" && harness/apply-semantic-learning-findings.sh --apply >/dev/null 2>&1); then echo 'FAIL invalid target expected failure' >&2; exit 1; else echo 'ok   semantic-invalid-target'; fi

printf 'PASS\n' > "$repo/.architrave/learning/semantic-stale-facts.jsonl"
(cd "$repo" && harness/apply-semantic-learning-findings.sh >/tmp/semantic-pass.txt)
grep -q 'no semantic stale findings' /tmp/semantic-pass.txt && echo 'ok   semantic-pass-output'