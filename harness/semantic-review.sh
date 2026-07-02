#!/usr/bin/env bash
# Optional semantic review helper. It prepares a judge prompt from run artifacts.
# It does not mutate files. By default it prints the prompt path and suggested
# Copilot/Claude commands; use --execute only after reviewing permissions.
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

[ -n "$run_dir" ] || run_dir="$(ls -1dt .architrave/runs/* 2>/dev/null | head -1 || true)"
[ -n "$run_dir" ] && [ -d "$run_dir" ] || { echo "semantic-review: run dir not found" >&2; exit 2; }

prompt="$run_dir/semantic-review-prompt.md"
cat > "$prompt" <<EOF
You are an adversarial semantic reviewer for an Architrave run.

Review the run artifacts in $run_dir against gates/rubric.md. Focus on:
- visible intake quality;
- Tournament of Options quality;
- Recommended Plan quality;
- contract/architecture fit;
- deterministic gate evidence;
- safety, capability honesty, and missing tests.

Return PASS / REVISE / FAIL with findings ordered by severity.
EOF

echo "semantic-review prompt: $prompt"
case "$provider" in copilot|claude|both) : ;; *) echo "semantic-review: provider must be copilot, claude, or both" >&2; exit 2 ;; esac

copilot_cmd=(copilot -C "$PWD" --agent "Adversarial Judge" --allow-tool read --allow-tool search -p "$(cat "$prompt")")
claude_cmd=(claude --agent "Adversarial Judge" --allowedTools "Read,Grep,Glob" -p "$(cat "$prompt")")

if [ "$execute" -eq 1 ]; then
  case "$provider" in
    copilot) "${copilot_cmd[@]}" ;;
    claude) "${claude_cmd[@]}" ;;
    both) "${copilot_cmd[@]}" && "${claude_cmd[@]}" ;;
  esac
else
  printf 'suggested command(s) (review before running):\n'
  if [ "$provider" = "copilot" ] || [ "$provider" = "both" ]; then printf '  '; printf '%q ' "${copilot_cmd[@]}"; printf '\n'; fi
  if [ "$provider" = "claude" ] || [ "$provider" = "both" ]; then printf '  '; printf '%q ' "${claude_cmd[@]}"; printf '\n'; fi
fi