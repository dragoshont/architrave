#!/usr/bin/env bash
# Validate Architrave learning artifacts without trusting their contents.
# Checks: required files, local markdown links resolve, and obvious secrets absent.
set -uo pipefail

root="${1:-$PWD}"
cd "$root" 2>/dev/null || { echo "validate-learning: repo dir not found: $root" >&2; exit 2; }

profile=".architrave/learning/repo-profile.md"
lessons=".architrave/learning/repo-lessons.md"
fail=0

ok() { echo "ok    $*"; }
err() { echo "FAIL  $*"; fail=1; }

[ -s "$profile" ] && ok "$profile" || err "missing/empty $profile"
[ -s "$lessons" ] && ok "$lessons" || err "missing/empty $lessons"

secret_hits="$(grep -RInE '(-----BEGIN [A-Z ]*PRIVATE KEY|gh[pousr]_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}|(api[_-]?key|token|password)[[:space:]]*[:=][[:space:]]*[^[:space:]]{12,})' .architrave/learning 2>/dev/null || true)"
if [ -n "$secret_hits" ]; then
  err "possible secret material in learning artifacts"
  printf '%s\n' "$secret_hits" | sed 's/^/      /' | head -10
else
  ok "no obvious secrets in learning artifacts"
fi

validate_links() {
  local file="$1" target path anchor bad=0
  [ -f "$file" ] || return 0
  while IFS= read -r target; do
    case "$target" in
      http://*|https://*|mailto:*|""|'#'*) continue ;;
    esac
    path="${target%%#*}"
    anchor="${target#*#}"
    [ "$path" = "$target" ] && anchor=""
    path="${path//%20/ }"
    case "$path" in
      /*|../*|*/../*) echo "FAIL  $file link escapes repo: $target"; bad=1; continue ;;
    esac
    if [ -n "$path" ] && [ ! -e "$path" ]; then
      echo "FAIL  $file missing link target: $target"; bad=1; continue
    fi
    if [ -n "$anchor" ] && [ -n "$path" ] && [ -f "$path" ]; then
      if ! grep -qE "^#+[[:space:]].*" "$path"; then
        echo "FAIL  $file anchor references file without headings: $target"; bad=1
      fi
    fi
  done < <(grep -hoE '\[[^]]+\]\(([^)]+)\)' "$file" | sed -E 's/.*\(([^)]+)\).*/\1/')
  return "$bad"
}

for f in "$profile" "$lessons"; do
  if validate_links "$f"; then ok "links resolve in $f"; else fail=1; fi
done

if [ "$fail" -eq 0 ]; then echo "ARCHITRAVE-LEARNING: PASS"; else echo "ARCHITRAVE-LEARNING: FAIL"; fi
exit "$fail"