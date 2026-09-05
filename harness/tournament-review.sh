#!/usr/bin/env bash
set -euo pipefail

run_dir=""
execute=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --run) run_dir="${2:-}"; shift 2 ;;
    --execute) execute=1; shift ;;
    *) echo "usage: harness/tournament-review.sh --run .architrave/runs/<id> [--execute]" >&2; exit 2 ;;
  esac
done
[ -n "$run_dir" ] && [ -d "$run_dir" ] || { echo "tournament-review: run dir not found" >&2; exit 2; }
if [ -f agents/tournament-analyst.agent.md ]; then agent_file=agents/tournament-analyst.agent.md
elif [ -f .github/agents/tournament-analyst.agent.md ]; then agent_file=.github/agents/tournament-analyst.agent.md
else echo "tournament-review: canonical Tournament Analyst not found" >&2; exit 2; fi

prompt="$run_dir/tournament-review-prompt.md"
cat >"$prompt" <<EOF
Read the intake and governing repository sources for the Architrave run at $run_dir.
Compare viable options using the canonical Tournament Analyst instructions.
Do not edit files or authorize mutations. End with one line exactly TOURNAMENT: COMPLETE.
EOF
body="$(cat "$prompt")"
cmd=(claude --model claude-opus-4.8 --effort max --tools Read,Grep,Glob --allowedTools Read,Grep,Glob --append-system-prompt-file "$agent_file" -p "$body")
if [ "$execute" -eq 0 ]; then printf 'suggested command (review before running):\n  '; printf '%q ' "${cmd[@]}"; printf '\n'; exit 0; fi
nonce_file="$(mktemp)"; output="$(mktemp)"; trap 'rm -f "$nonce_file" "$output"' EXIT
if command -v uuidgen >/dev/null 2>&1; then uuidgen | tr '[:upper:]' '[:lower:]' >"$nonce_file"
else printf '%s' "$$-$(date +%s)-$RANDOM" | shasum -a 256 | awk '{print $1}' >"$nonce_file"; fi
cmd[${#cmd[@]}-1]="$body

Read $nonce_file and include EVIDENCE_NONCE: <value>; the value is absent from this prompt."
exit_code=0; "${cmd[@]}" >"$output" 2>&1 || exit_code=$?; cat "$output"
nonce="$(cat "$nonce_file")"
result="$(cat "$output")"
# Bash command substitution retains a terminal CR from CRLF output. Normalize
# line endings before matching: GNU grep ERE does not portably treat \r as CR.
result="${result//$'\r\n'/$'\n'}"
result="${result%$'\r'}"
nonce_count="$(printf '%s\n' "$result" | grep -Ec "^EVIDENCE_NONCE: $nonce$" || true)"
completion_count="$(printf '%s\n' "$result" | grep -Ec '^TOURNAMENT: COMPLETE$' || true)"
last_line="$(printf '%s\n' "$result" | awk 'NF { line=$0 } END { print line }')"
[ "$exit_code" -eq 0 ] && [ "$nonce_count" -eq 1 ] && [ "$completion_count" -eq 1 ] && [ "$last_line" = 'TOURNAMENT: COMPLETE' ] || { echo "tournament-review: unverified result" >&2; exit 1; }