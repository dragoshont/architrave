#!/usr/bin/env bash
# Optional semantic review helper. It prepares a judge prompt from run artifacts.
# It does not mutate files. By default it prints the prompt path and suggested
# Copilot/Claude commands; use --execute only after reviewing permissions.
set -euo pipefail

provider=""
execute=0
run_dir=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --provider) provider="${2:-}"; shift 2 ;;
    --run) run_dir="${2:-}"; shift 2 ;;
    --execute) execute=1; shift ;;
    *) echo "usage: harness/semantic-review.sh --provider copilot|claude --run .architrave/runs/<id> [--execute]" >&2; exit 2 ;;
  esac
done

[ -n "$provider" ] || { echo "semantic-review: --provider required" >&2; exit 2; }
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
case "$provider" in
  copilot)
    cmd=(copilot -C "$PWD" --agent "Adversarial Judge" --allow-tool read --allow-tool search -p "$(cat "$prompt")")
    ;;
  claude)
    cmd=(claude --agent "Adversarial Judge" --allowedTools "Read,Grep,Glob" -p "$(cat "$prompt")")
    ;;
  *) echo "semantic-review: provider must be copilot or claude" >&2; exit 2 ;;
esac

if [ "$execute" -eq 1 ]; then
  "${cmd[@]}"
else
  printf 'suggested command (review before running):\n  '
  printf '%q ' "${cmd[@]}"
  printf '\n'
fi