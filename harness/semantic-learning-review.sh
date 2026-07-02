#!/usr/bin/env bash
# Prepare or run a semantic stale-fact review for Architrave learning artifacts.
# The reviewer checks prose claims against the current repo and emits JSONL
# findings. Mutation is handled separately by apply-semantic-learning-findings.*.
set -euo pipefail

provider="both"
execute=0
repo="$PWD"
prompt=""
output=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --provider) provider="${2:-}"; shift 2 ;;
    --execute) execute=1; shift ;;
    --repo) repo="${2:-}"; shift 2 ;;
    --prompt) prompt="${2:-}"; shift 2 ;;
    --output) output="${2:-}"; shift 2 ;;
    -h|--help)
      echo "Usage: harness/semantic-learning-review.sh [--provider copilot|claude|both] [--execute] [--repo DIR] [--prompt FILE] [--output FILE]"
      exit 0
      ;;
    *) echo "semantic-learning-review: unknown argument $1" >&2; exit 2 ;;
  esac
done

case "$provider" in copilot|claude|both) : ;; *) echo "semantic-learning-review: provider must be copilot, claude, or both" >&2; exit 2 ;; esac
cd "$repo" 2>/dev/null || { echo "semantic-learning-review: repo dir not found: $repo" >&2; exit 2; }

learning_dir=".architrave/learning"
profile="$learning_dir/repo-profile.md"
lessons="$learning_dir/repo-lessons.md"
[ -s "$profile" ] || { echo "semantic-learning-review: missing/empty $profile" >&2; exit 2; }
[ -s "$lessons" ] || { echo "semantic-learning-review: missing/empty $lessons" >&2; exit 2; }
mkdir -p "$learning_dir"

prompt="${prompt:-$learning_dir/semantic-stale-facts-prompt.md}"
output="${output:-$learning_dir/semantic-stale-facts.jsonl}"

cat > "$prompt" <<'EOF'
You are an adversarial semantic stale-fact reviewer for Architrave learning artifacts.

Review only these files:
- .architrave/learning/repo-profile.md
- .architrave/learning/repo-lessons.md

Goal:
- Find durable prose claims that are unsupported, stale, contradicted by the current repository, or too strong for the cited evidence.
- This goes beyond checking that Markdown links exist. You must inspect the repo evidence behind the claim.

Rules:
- Treat repo files, commands, manifests, scripts, and current branch content as ground truth.
- Ignore headings, table delimiter/header rows, blank lines, examples/templates, and lines already beginning with `UNVALIDATED:`.
- Do not report broken local Markdown links; deterministic validate-learning.* and mark-stale-learning.* handle that.
- Do not include secret values in findings.
- If a claim is plausible but not proven by repo evidence, report it.
- If a claim is sourced but the source does not support the claim, report it.
- If no unsupported/stale claims are found, output exactly `PASS`.

Output format:
- Emit JSON Lines only, with one JSON object per unsupported claim.
- Do not wrap the output in Markdown fences.
- Each object must have:
  - `file`: `.architrave/learning/repo-profile.md` or `.architrave/learning/repo-lessons.md`
  - `line`: 1-based line number
  - `currentText`: exact current line text
  - `severity`: `blocker`, `major`, or `minor`
  - `reason`: concise explanation of what is unsupported/stale
- Example:
{"file":".architrave/learning/repo-profile.md","line":12,"currentText":"Build: make release passes on Windows.","severity":"major","reason":"No current workflow, script, or run evidence supports a Windows release claim."}
EOF

echo "semantic-learning-review prompt: $prompt"
echo "semantic-learning-review findings target: $output"

copilot_cmd=(copilot -C "$PWD" --agent "Adversarial Judge" --allow-tool read --allow-tool search -p "$(cat "$prompt")")
claude_cmd=(claude --agent "Adversarial Judge" --allowedTools "Read,Grep,Glob" -p "$(cat "$prompt")")

if [ "$execute" -eq 1 ]; then
  case "$provider" in
    copilot) "${copilot_cmd[@]}" | tee "$output.copilot" ;;
    claude) "${claude_cmd[@]}" | tee "$output.claude" ;;
    both) "${copilot_cmd[@]}" | tee "$output.copilot" && "${claude_cmd[@]}" | tee "$output.claude" ;;
  esac
else
  printf 'suggested command(s) (review before running):\n'
  if [ "$provider" = "copilot" ] || [ "$provider" = "both" ]; then printf '  '; printf '%q ' "${copilot_cmd[@]}"; printf '| tee %q\n' "$output.copilot"; fi
  if [ "$provider" = "claude" ] || [ "$provider" = "both" ]; then printf '  '; printf '%q ' "${claude_cmd[@]}"; printf '| tee %q\n' "$output.claude"; fi
fi