#!/usr/bin/env bash
# Optional independent semantic review helper. Model selection is inherited from
# the invoking host and is never configured by Architrave.
set -euo pipefail

provider="both"
execute=0
run_dir=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --provider) provider="${2:-}"; shift 2 ;;
    --run) run_dir="${2:-}"; shift 2 ;;
    --execute) execute=1; shift ;;
    *) echo "usage: harness/semantic-review.sh [--provider copilot|claude|both] --run .architrave/runs/<id> [--execute]" >&2; exit 2 ;;
  esac
done

case "$provider" in copilot|claude|both) : ;; *) echo "semantic-review: invalid provider" >&2; exit 2 ;; esac
[ -n "$run_dir" ] || run_dir="$(ls -1dt .architrave/runs/* 2>/dev/null | head -1 || true)"
[ -n "$run_dir" ] && [ -d "$run_dir" ] || { echo "semantic-review: run dir not found" >&2; exit 2; }
command -v jq >/dev/null 2>&1 || { echo "semantic-review: jq is required" >&2; exit 2; }

agent_file="agents/adversarial-judge.agent.md"
[ -f "$agent_file" ] || agent_file=".github/agents/adversarial-judge.agent.md"
[ -f "$agent_file" ] || { echo "semantic-review: adversarial judge agent not found" >&2; exit 2; }

body="Review canonical state and referenced evidence in $run_dir against gates/rubric.md.
Focus on Outcome/acceptance coverage, TaskGraph scope, repository contract fit,
deterministic and runtime evidence, safety, capability honesty, and missing tests.
Return concise findings ordered by severity, then VERDICT: PASS|REVISE|FAIL."

copilot_cmd=(copilot -C "$PWD" --agent architrave:adversarial-judge --available-tools view,grep,glob --allow-tool view --allow-tool grep --allow-tool glob --no-ask-user --output-format json --stream off --silent --no-color -p "$body")
claude_cmd=(claude --tools Read,Grep,Glob --allowedTools Read,Grep,Glob --append-system-prompt-file "$agent_file" --output-format json -p "$body")

if [ "$execute" -eq 0 ]; then
  printf 'suggested command(s) (host-selected model):\n'
  if [ "$provider" = copilot ] || [ "$provider" = both ]; then printf '  '; printf '%q ' "${copilot_cmd[@]}"; printf '\n'; fi
  if [ "$provider" = claude ] || [ "$provider" = both ]; then printf '  '; printf '%q ' "${claude_cmd[@]}"; printf '\n'; fi
  exit 0
fi

nonce_file="$(mktemp)"
trap 'rm -f "$nonce_file"' EXIT
printf '%s' "$$-$(date +%s)-$RANDOM" | shasum -a 256 | awk '{print $1}' >"$nonce_file"
nonce="$(cat "$nonce_file")"
nonce_prompt="Read $nonce_file and include EVIDENCE_NONCE: <value>. End with exactly VERDICT: PASS, VERDICT: REVISE, or VERDICT: FAIL."
copilot_cmd[${#copilot_cmd[@]}-1]="$body

$nonce_prompt"
claude_cmd[${#claude_cmd[@]}-1]="$body

$nonce_prompt"

run_judge() {
  local label="$1"; shift
  local output content
  output="$(mktemp)"
  "$@" >"$output"
  if [ "$label" = copilot ]; then
    content="$(jq -rs '[.[]? | select(.type=="assistant.message")] | last | (.data.content // "")' "$output")"
  else
    content="$(jq -r '.result // ""' "$output")"
  fi
  rm -f "$output"
  printf '%s\n' "$content"
  [ "$(printf '%s\n' "$content" | grep -Fc "EVIDENCE_NONCE: $nonce")" -eq 1 ] &&
    [ "$(printf '%s\n' "$content" | grep -Ec '^VERDICT: (PASS|REVISE|FAIL)$')" -eq 1 ] &&
    [ "$(printf '%s\n' "$content" | awk 'NF { line=$0 } END { print line }')" = "VERDICT: PASS" ]
}

failed=0
if [ "$provider" = copilot ] || [ "$provider" = both ]; then run_judge copilot "${copilot_cmd[@]}" || failed=1; fi
if [ "$provider" = claude ] || [ "$provider" = both ]; then run_judge claude "${claude_cmd[@]}" || failed=1; fi
exit "$failed"
