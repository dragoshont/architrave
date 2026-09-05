#!/usr/bin/env bash
# Optional semantic review helper. It prepares a judge prompt from run artifacts.
# It does not mutate files. By default it prints the prompt path and suggested
# Copilot/Claude commands; use --execute only after reviewing permissions.
#
# Concrete model/effort bindings are host-local, never canonical: this gate
# resolves them from the environment. A full gate (--execute) fails closed
# with a clear error if the model for a requested provider is unset.
#
#   ARCHITRAVE_SEMANTIC_REVIEW_COPILOT_MODEL  (required for --execute with copilot/both)
#   ARCHITRAVE_SEMANTIC_REVIEW_COPILOT_EFFORT (optional)
#   ARCHITRAVE_SEMANTIC_REVIEW_CLAUDE_MODEL   (required for --execute with claude/both)
#   ARCHITRAVE_SEMANTIC_REVIEW_CLAUDE_EFFORT  (optional)
#
# An exit code, nonce, and terminal VERDICT alone are not accepted as GPT or
# Claude evidence: each provider's judgment is only accepted once its own
# host-observed provider/model-family telemetry (JSON vendor/model fields,
# not self-reported prompt text) confirms the declared family.
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

command -v jq >/dev/null 2>&1 || { echo "semantic-review: 'jq' is required (macOS: brew install jq · Windows: winget install jqlang.jq)" >&2; exit 2; }

resolve_agent() {
  local name="$1"
  if [ -f "agents/$name" ]; then printf '%s' "agents/$name"
  elif [ -f ".github/agents/$name" ]; then printf '%s' ".github/agents/$name"
  else echo "semantic-review: canonical agent not found: $name" >&2; return 2
  fi
}

agent_file="$(resolve_agent adversarial-judge.agent.md)" || exit $?
body="$(cat "$prompt")"

copilot_model="${ARCHITRAVE_SEMANTIC_REVIEW_COPILOT_MODEL:-}"
copilot_effort="${ARCHITRAVE_SEMANTIC_REVIEW_COPILOT_EFFORT:-}"
claude_model="${ARCHITRAVE_SEMANTIC_REVIEW_CLAUDE_MODEL:-}"
claude_effort="${ARCHITRAVE_SEMANTIC_REVIEW_CLAUDE_EFFORT:-}"

require_model() {
  local label="$1" value="$2" var_name="$3"
  [ "$execute" -eq 1 ] || return 0
  [ -n "$value" ] || { echo "semantic-review: set $var_name (host-local) to run the $label judge as a full gate" >&2; exit 2; }
}
{ [ "$provider" = "copilot" ] || [ "$provider" = "both" ]; } && require_model copilot "$copilot_model" ARCHITRAVE_SEMANTIC_REVIEW_COPILOT_MODEL
{ [ "$provider" = "claude" ] || [ "$provider" = "both" ]; } && require_model claude "$claude_model" ARCHITRAVE_SEMANTIC_REVIEW_CLAUDE_MODEL

copilot_cmd=(copilot -C "$PWD" --agent architrave:adversarial-judge --model "${copilot_model:-<unset:ARCHITRAVE_SEMANTIC_REVIEW_COPILOT_MODEL>}")
[ -n "$copilot_effort" ] && copilot_cmd+=(--reasoning-effort "$copilot_effort")
copilot_cmd+=(--available-tools view,grep,glob --allow-tool view --allow-tool grep --allow-tool glob --no-ask-user --output-format json --stream off --silent --no-color -p "$body")

claude_cmd=(claude --model "${claude_model:-<unset:ARCHITRAVE_SEMANTIC_REVIEW_CLAUDE_MODEL>}")
[ -n "$claude_effort" ] && claude_cmd+=(--effort "$claude_effort")
claude_cmd+=(--tools Read,Grep,Glob --allowedTools Read,Grep,Glob --append-system-prompt-file "$agent_file" --output-format json -p "$body")

# Extract the judge's final response text from provider-specific JSON telemetry.
# Copilot emits JSONL events; Claude's --output-format json emits one object.
extract_content() {
  local label="$1" output="$2"
  case "$label" in
    copilot) jq -rs '[.[]? | select(.type=="assistant.message")] | last | (.data.content // "")' "$output" 2>/dev/null || true ;;
    claude) jq -r '.result // ""' "$output" 2>/dev/null || true ;;
  esac
}

# Determine trusted, host-observed provider/model-family evidence: vendor or
# model-id telemetry reported by the CLI's own JSON output, never the judge's
# self-reported prompt text. Returns observed-vendor, observed-model, or
# unverified (no usable telemetry, or telemetry contradicting the declared
# family).
observed_family() {
  local label="$1" output="$2" declared="$3"
  case "$label" in
    copilot)
      jq -rs --arg declared "$declared" '
        def fam($v): if ($v // "" | test("anthropic|claude"; "i")) then "claude" elif ($v // "" | test("openai"; "i")) then "gpt" else empty end;
        def famModel($m): if ($m // "" | test("claude|anthropic"; "i")) then "claude" elif ($m // "" | test("^(gpt-|openai/|o1|o3|o4)"; "i")) then "gpt" else empty end;
        . as $events
        | ([$events[]? | select(.type=="session.usage_checkpoint") | (.data.promptCacheBreakState // [])[]? | select(.conversation=="main") | (.models // {}) | to_entries[]?.value.vendor? | select(. != null and . != "")]) as $vendors
        | ([$vendors[] | fam(.)] | unique) as $vendorFamilies
        | if ($vendorFamilies | index($declared)) then "observed-vendor"
          elif ($vendors | length) > 0 then "unverified"
          else
            ([$events[]? | select(.type=="assistant.message") | .data.model? | select(. != null and . != "")]) as $models
            | ([$models[] | famModel(.)] | unique) as $modelFamilies
            | if ($modelFamilies | index($declared)) then "observed-model" else "unverified" end
          end
      ' "$output" 2>/dev/null || echo unverified
      ;;
    claude)
      jq -r --arg declared "$declared" '
        def famModel($m): if ($m // "" | test("claude|anthropic"; "i")) then "claude" elif ($m // "" | test("^(gpt-|openai/|o1|o3|o4)"; "i")) then "gpt" else empty end;
        ([(.modelUsage // {}) | keys[]? | select(. != null and . != "")]) as $models
        | ([$models[] | famModel(.)] | unique) as $modelFamilies
        | if ($modelFamilies | index($declared)) then "observed-model" else "unverified" end
      ' "$output" 2>/dev/null || echo unverified
      ;;
  esac
}

run_judge() {
  local label="$1" nonce_file="$2" declared_family="$3" output stderr_output exit_code=0 nonce nonce_count verdict_count last_line content family_evidence
  shift 3
  output="$(mktemp)"
  stderr_output="$(mktemp)"
  "$@" >"$output" 2>"$stderr_output" || exit_code=$?
  [ -s "$stderr_output" ] && cat "$stderr_output" >&2
  nonce="$(cat "$nonce_file")"
  content="$(extract_content "$label" "$output")"
  printf '%s\n' "$content"
  nonce_count="$(printf '%s\n' "$content" | grep -Ec "^EVIDENCE_NONCE: $nonce\r?$" || true)"
  verdict_count="$(printf '%s\n' "$content" | grep -Ec '^VERDICT: (PASS|REVISE|FAIL)\r?$' || true)"
  last_line="$(printf '%s\n' "$content" | awk 'NF { line=$0 } END { sub(/\r$/, "", line); print line }')"
  if [ "$exit_code" -ne 0 ] || [ "$nonce_count" -ne 1 ] || [ "$verdict_count" -ne 1 ] || [ "$last_line" != 'VERDICT: PASS' ]; then
    echo "semantic-review: $label judge did not return a verified PASS" >&2
    rm -f "$output" "$stderr_output"
    return 1
  fi
  family_evidence="$(observed_family "$label" "$output" "$declared_family")"
  if [ "$family_evidence" = "unverified" ]; then
    echo "semantic-review: $label judge did not return verified $declared_family-family evidence" >&2
    rm -f "$output" "$stderr_output"
    return 1
  fi
  rm -f "$output" "$stderr_output"
}

if [ "$execute" -eq 1 ]; then
  nonce_file="$(mktemp)"
  trap 'rm -f "$nonce_file"' EXIT
  if command -v uuidgen >/dev/null 2>&1; then uuidgen | tr '[:upper:]' '[:lower:]' >"$nonce_file"
  else printf '%s' "$$-$(date +%s)-$RANDOM" | shasum -a 256 | awk '{print $1}' >"$nonce_file"; fi
  nonce_prompt="Read $nonce_file and include EVIDENCE_NONCE: <value> in your response; the value is absent from this prompt. End with one line exactly VERDICT: PASS, VERDICT: REVISE, or VERDICT: FAIL."
  copilot_cmd[${#copilot_cmd[@]}-1]="$body

$nonce_prompt"
  claude_cmd[${#claude_cmd[@]}-1]="$body

$nonce_prompt"
  failed=0
  case "$provider" in
    copilot) run_judge copilot "$nonce_file" gpt "${copilot_cmd[@]}" || failed=1 ;;
    claude) run_judge claude "$nonce_file" claude "${claude_cmd[@]}" || failed=1 ;;
    both)
      run_judge copilot "$nonce_file" gpt "${copilot_cmd[@]}" || failed=1
      run_judge claude "$nonce_file" claude "${claude_cmd[@]}" || failed=1
      ;;
  esac
  exit "$failed"
else
  printf 'suggested command(s) (review before running):\n'
  if [ "$provider" = "copilot" ] || [ "$provider" = "both" ]; then printf '  '; printf '%q ' "${copilot_cmd[@]}"; printf '\n'; fi
  if [ "$provider" = "claude" ] || [ "$provider" = "both" ]; then printf '  '; printf '%q ' "${claude_cmd[@]}"; printf '\n'; fi
fi
