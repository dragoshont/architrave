#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

make_repo() {
  local repo="$1"
  mkdir -p "$repo/.architrave/learning" "$repo/docs"
  cp -R harness "$repo/harness"
  chmod +x "$repo"/harness/*.sh 2>/dev/null || true
  printf '# Guide\n' > "$repo/docs/guide.md"
  cat > "$repo/.architrave/learning/repo-profile.md" <<'MD'
# Repo Profile

See [guide](docs/guide.md).
MD
  cat > "$repo/.architrave/learning/repo-lessons.md" <<'MD'
# Repo Lessons

No secrets here.
MD
}

expect_pass() { local name="$1" repo="$2"; if (cd "$repo" && harness/validate-learning.sh >/dev/null); then echo "ok   $name"; else echo "FAIL $name expected pass" >&2; exit 1; fi; }
expect_fail() { local name="$1" repo="$2"; if (cd "$repo" && harness/validate-learning.sh >/dev/null 2>&1); then echo "FAIL $name expected failure" >&2; exit 1; else echo "ok   $name"; fi; }

valid="$tmp/valid"; make_repo "$valid"; expect_pass valid-learning "$valid"
missing="$tmp/missing"; make_repo "$missing"; rm "$missing/.architrave/learning/repo-profile.md"; expect_fail missing-profile "$missing"
broken="$tmp/broken"; make_repo "$broken"; printf '# Repo Profile\n\n[missing](docs/missing.md)\n' > "$broken/.architrave/learning/repo-profile.md"; expect_fail broken-link "$broken"
secret="$tmp/secret"; make_repo "$secret"; printf '# Repo Lessons\n\ntoken = ghp_123456789012345678901234567890123456\n' > "$secret/.architrave/learning/repo-lessons.md"; expect_fail secret-material "$secret"