#!/usr/bin/env bash
# Apply reviewed semantic stale-fact findings to learning artifacts.
# Dry-run by default; --apply prefixes exact matching lines with UNVALIDATED:.
set -uo pipefail

apply=0
repo="$PWD"
findings=".architrave/learning/semantic-stale-facts.jsonl"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --apply) apply=1; shift ;;
    --repo) repo="${2:-}"; shift 2 ;;
    --findings) findings="${2:-}"; shift 2 ;;
    -h|--help)
      echo "Usage: harness/apply-semantic-learning-findings.sh [--apply] [--repo DIR] [--findings FILE]"
      exit 0
      ;;
    *) echo "apply-semantic-learning-findings: unknown argument $1" >&2; exit 2 ;;
  esac
done

command -v jq >/dev/null 2>&1 || { echo "apply-semantic-learning-findings: jq required" >&2; exit 2; }
cd "$repo" 2>/dev/null || { echo "apply-semantic-learning-findings: repo dir not found: $repo" >&2; exit 2; }
[ -f "$findings" ] || { echo "apply-semantic-learning-findings: findings file not found: $findings" >&2; exit 2; }

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
clean="$tmpdir/findings.jsonl"
grep -vE '^[[:space:]]*$|^[[:space:]]*PASS[[:space:]]*$' "$findings" > "$clean" || true

if [ ! -s "$clean" ]; then
  echo "apply-semantic-learning-findings: no semantic stale findings"
  exit 0
fi

fail=0
changed=0
allowed_file() {
  case "$1" in
    .architrave/learning/repo-profile.md|.architrave/learning/repo-lessons.md) return 0 ;;
    *) return 1 ;;
  esac
}

while IFS= read -r row || [ -n "$row" ]; do
  file="$(printf '%s' "$row" | jq -er '.file' 2>/dev/null)" || { echo "FAIL  invalid finding JSON: $row"; fail=1; continue; }
  line="$(printf '%s' "$row" | jq -er '.line' 2>/dev/null)" || { echo "FAIL  missing finding line: $row"; fail=1; continue; }
  current="$(printf '%s' "$row" | jq -er '.currentText' 2>/dev/null)" || { echo "FAIL  missing finding currentText: $row"; fail=1; continue; }
  reason="$(printf '%s' "$row" | jq -r '.reason // "semantic finding"' 2>/dev/null)"
  severity="$(printf '%s' "$row" | jq -r '.severity // "major"' 2>/dev/null)"

  allowed_file "$file" || { echo "FAIL  finding file outside learning artifacts: $file"; fail=1; continue; }
  case "$line" in ''|*[!0-9]*) echo "FAIL  invalid line for $file: $line"; fail=1; continue ;; esac
  [ "$line" -gt 0 ] || { echo "FAIL  invalid line for $file: $line"; fail=1; continue; }
  [ -f "$file" ] || { echo "FAIL  missing learning file: $file"; fail=1; continue; }

  actual="$(sed -n "${line}p" "$file")"
  if [ "$actual" = "UNVALIDATED: $current" ]; then
    continue
  fi
  if [ "$actual" != "$current" ]; then
    echo "FAIL  finding no longer matches $file:$line"
    echo "      expected: $current"
    echo "      actual:   $actual"
    fail=1
    continue
  fi

  changed=1
  if [ "$apply" -eq 1 ]; then
    awk -v n="$line" '{ if (NR == n) print "UNVALIDATED: " $0; else print }' "$file" > "$tmpdir/next" && mv "$tmpdir/next" "$file"
    echo "marked $file:$line [$severity] $reason"
  else
    echo "would mark $file:$line [$severity] $reason"
  fi
done < "$clean"

[ "$fail" -eq 0 ] || exit 1
if [ "$changed" -eq 0 ]; then echo "apply-semantic-learning-findings: no matching unvalidated lines to mark"; fi
exit 0