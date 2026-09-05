#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir "$tmp/bin"
cat >"$tmp/bin/fake-agent" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
name="$(basename "$0")"
printf '%s\t' "$name" >>"$FAKE_AGENT_LOG"
printf '%q ' "$@" >>"$FAKE_AGENT_LOG"
printf '\n' >>"$FAKE_AGENT_LOG"
[ "${FAKE_AGENT_FAIL:-}" != "$name" ] || exit 7
prompt=""
model=""
output_format=""
args=("$@")
i=0
while [ "$i" -lt "${#args[@]}" ]; do
  case "${args[$i]}" in
    -p) prompt="${args[$((i + 1))]:-}" ;;
    --model) model="${args[$((i + 1))]:-}" ;;
    --output-format) output_format="${args[$((i + 1))]:-}" ;;
  esac
  i=$((i + 1))
done
nonce_file="${prompt##*Read }"
nonce_file="${nonce_file%% and include EVIDENCE_NONCE*}"
[ -f "$nonce_file" ] || { echo "nonce file missing" >&2; exit 8; }

# This single fake executable is symlinked as both `copilot` and `claude` and,
# without the JSON telemetry below, would be indistinguishable to a caller
# that only checks exit code/nonce/verdict. Real family evidence therefore
# only appears in the JSON branch (--output-format json), gated by
# FAKE_AGENT_FAMILY[_COPILOT|_CLAUDE] so tests can prove the gate rejects a
# twin executable that lacks separately verifiable per-family telemetry.
if [ "$output_format" != "json" ]; then
  case "${FAKE_TOURNAMENT_MODE:-}" in
    crlf) printf 'EVIDENCE_NONCE: %s\r\n' "$(tr -d '\r\n' <"$nonce_file")" ;;
    missing-nonce) ;;
    duplicate-nonce) printf 'EVIDENCE_NONCE: %s\nEVIDENCE_NONCE: %s\n' "$(tr -d '\r\n' <"$nonce_file")" "$(tr -d '\r\n' <"$nonce_file")" ;;
    *) printf 'EVIDENCE_NONCE: %s\n' "$(tr -d '\r\n' <"$nonce_file")" ;;
  esac
  if [ "${FAKE_AGENT_CONFLICT:-}" = "$name" ]; then
    printf 'VERDICT: PASS\nVERDICT: REVISE\n'
    exit 0
  fi
  if printf '%s' "$prompt" | grep -Fq 'TOURNAMENT: COMPLETE'; then
    case "${FAKE_TOURNAMENT_MODE:-}" in
      crlf) printf 'TOURNAMENT: COMPLETE\r\n' ;;
      missing) printf 'TOURNAMENT: INCOMPLETE\n' ;;
      duplicate) printf 'TOURNAMENT: COMPLETE\nTOURNAMENT: COMPLETE\n' ;;
      *) printf 'TOURNAMENT: COMPLETE\n' ;;
    esac
  else
    if [ "${FAKE_TOURNAMENT_MODE:-}" = "crlf" ]; then printf 'VERDICT: PASS\r\n'; else printf 'VERDICT: PASS\n'; fi
  fi
  exit 0
fi

case "${FAKE_TOURNAMENT_MODE:-}" in
  crlf) nonce_text="EVIDENCE_NONCE: $(tr -d '\r\n' <"$nonce_file")"$'\r' ;;
  missing-nonce) nonce_text="" ;;
  duplicate-nonce) nonce_text="EVIDENCE_NONCE: $(tr -d '\r\n' <"$nonce_file")
EVIDENCE_NONCE: $(tr -d '\r\n' <"$nonce_file")" ;;
  *) nonce_text="EVIDENCE_NONCE: $(tr -d '\r\n' <"$nonce_file")" ;;
esac
if [ "${FAKE_AGENT_CONFLICT:-}" = "$name" ]; then
  final_text=$'VERDICT: PASS\nVERDICT: REVISE'
else
  if [ "${FAKE_TOURNAMENT_MODE:-}" = "crlf" ]; then final_text="VERDICT: PASS"$'\r'; else final_text="VERDICT: PASS"; fi
fi
content="$nonce_text
$final_text"

family_mode="${FAKE_AGENT_FAMILY:-auto}"
case "$name" in
  copilot) family_mode="${FAKE_AGENT_FAMILY_COPILOT:-$family_mode}" ;;
  claude) family_mode="${FAKE_AGENT_FAMILY_CLAUDE:-$family_mode}" ;;
esac
model_family=""
case "$model" in
  *[Cc]laude*|*[Aa]nthropic*) model_family="claude" ;;
  gpt-*|openai/*|o1*|o3*|o4*) model_family="gpt" ;;
esac
telemetry_model=""
vendor=""
case "$family_mode" in
  none) : ;;
  cross)
    if [ "$model_family" = "claude" ]; then telemetry_model="gpt-cross-model"; vendor="openai"
    else telemetry_model="claude-cross-model"; vendor="anthropic"; fi
    ;;
  *)
    telemetry_model="$model"
    case "$model_family" in
      claude) vendor="anthropic" ;;
      gpt) vendor="openai" ;;
    esac
    ;;
esac

if [ "$name" = "claude" ]; then
  if [ -n "$telemetry_model" ]; then
    jq -cn --arg content "$content" --arg model "$telemetry_model" '{"result": $content, "modelUsage": {($model): {}}}'
  else
    jq -cn --arg content "$content" '{"result": $content}'
  fi
else
  jq -cn --arg model "$telemetry_model" --arg content "$content" '{"type": "assistant.message", "data": {"model": $model, "content": $content}}'
  if [ -n "$vendor" ]; then
    jq -cn --arg model "$telemetry_model" --arg vendor "$vendor" '{"type": "session.usage_checkpoint", "data": {"promptCacheBreakState": [{"conversation": "main", "models": {($model): {"model": $model, "vendor": $vendor}}}]}}'
  fi
fi
EOF
chmod +x "$tmp/bin/fake-agent"
ln -s fake-agent "$tmp/bin/copilot"
ln -s fake-agent "$tmp/bin/claude"

run_dir=".architrave/runs/20260711T-codex-chatgpt-adapter-r3"
export PATH="$tmp/bin:$PATH"
export FAKE_AGENT_LOG="$tmp/args.log"

# Host-local model bindings the gate requires for a full (--execute) run. The
# fake agent auto-derives matching family telemetry from these names, so the
# happy-path tests below exercise real per-provider evidence, not a hard-coded
# canonical model.
export ARCHITRAVE_SEMANTIC_REVIEW_COPILOT_MODEL="gpt-test-sol"
export ARCHITRAVE_SEMANTIC_REVIEW_CLAUDE_MODEL="claude-test-opus"

harness/semantic-review.sh --provider both --run "$run_dir" --execute >/dev/null
grep -q -- '--available-tools view\\,grep\\,glob' "$FAKE_AGENT_LOG"
grep -q -- '--append-system-prompt-file agents/adversarial-judge.agent.md' "$FAKE_AGENT_LOG"
! grep -q -- '--allow-all-tools' "$FAKE_AGENT_LOG"
echo "ok    POSIX semantic launcher argv and nonce"

harness/tournament-review.sh --run "$run_dir" --execute >/dev/null
grep -q -- '--model claude-opus-4.8' "$FAKE_AGENT_LOG"
grep -q -- '--append-system-prompt-file agents/tournament-analyst.agent.md' "$FAKE_AGENT_LOG"
echo "ok    POSIX tournament launcher argv and nonce"

pwsh -NoProfile -File harness/semantic-review.ps1 -Provider both -RunDir "$run_dir" -Execute >/dev/null
pwsh -NoProfile -File harness/tournament-review.ps1 -RunDir "$run_dir" -Execute >/dev/null
grep -q -- '--available-tools view\\,grep\\,glob' "$FAKE_AGENT_LOG"
grep -q -- '--append-system-prompt-file agents/adversarial-judge.agent.md' "$FAKE_AGENT_LOG"
echo "ok    PowerShell semantic and tournament launchers"

export FAKE_TOURNAMENT_MODE=crlf
harness/semantic-review.sh --provider both --run "$run_dir" --execute >/dev/null
pwsh -NoProfile -File harness/semantic-review.ps1 -Provider both -RunDir "$run_dir" -Execute >/dev/null
harness/tournament-review.sh --run "$run_dir" --execute >/dev/null
pwsh -NoProfile -File harness/tournament-review.ps1 -RunDir "$run_dir" -Execute >/dev/null
unset FAKE_TOURNAMENT_MODE
echo "ok    POSIX and PowerShell semantic/tournament launchers accept exact CRLF evidence"

for mode in missing duplicate missing-nonce duplicate-nonce; do
  export FAKE_TOURNAMENT_MODE="$mode"
  if harness/tournament-review.sh --run "$run_dir" --execute >/dev/null 2>&1; then
    echo "FAIL POSIX tournament launcher accepted $mode completion" >&2
    exit 1
  fi
  if pwsh -NoProfile -File harness/tournament-review.ps1 -RunDir "$run_dir" -Execute >/dev/null 2>&1; then
    echo "FAIL PowerShell tournament launcher accepted $mode completion" >&2
    exit 1
  fi
done
unset FAKE_TOURNAMENT_MODE
echo "ok    tournament launchers reject missing and duplicate nonce/completion evidence"

no_uuid_bin="$tmp/no-uuid-bin"
mkdir "$no_uuid_bin"
for command_name in bash basename cat date grep mktemp rm shasum tr awk; do
  command_path="$(command -v "$command_name")"
  ln -s "$command_path" "$no_uuid_bin/$command_name"
done
ln -s "$tmp/bin/fake-agent" "$no_uuid_bin/claude"
PATH="$no_uuid_bin" /bin/bash harness/tournament-review.sh --run "$run_dir" --execute >/dev/null
echo "ok    POSIX tournament launcher generates a nonce without uuidgen"

export FAKE_AGENT_FAIL=claude
if harness/semantic-review.sh --provider both --run "$run_dir" --execute >/dev/null 2>&1; then
  echo "FAIL semantic launcher ignored provider failure" >&2
  exit 1
fi
if pwsh -NoProfile -File harness/semantic-review.ps1 -Provider claude -RunDir "$run_dir" -Execute >/dev/null 2>&1; then
  echo "FAIL PowerShell semantic launcher ignored provider failure" >&2
  exit 1
fi
unset FAKE_AGENT_FAIL
echo "ok    provider failure propagates in POSIX and PowerShell"

export FAKE_AGENT_CONFLICT=copilot
if harness/semantic-review.sh --provider copilot --run "$run_dir" --execute >/dev/null 2>&1; then
  echo "FAIL POSIX semantic launcher accepted conflicting verdicts" >&2
  exit 1
fi
if pwsh -NoProfile -File harness/semantic-review.ps1 -Provider copilot -RunDir "$run_dir" -Execute >/dev/null 2>&1; then
  echo "FAIL PowerShell semantic launcher accepted conflicting verdicts" >&2
  exit 1
fi
unset FAKE_AGENT_CONFLICT
echo "ok    conflicting prior PASS and terminal REVISE is rejected"

# Adversarial: a full gate must fail closed when a host-local model binding is
# unset, instead of silently falling back to a canonical hard-coded model.
saved_copilot_model="$ARCHITRAVE_SEMANTIC_REVIEW_COPILOT_MODEL"
saved_claude_model="$ARCHITRAVE_SEMANTIC_REVIEW_CLAUDE_MODEL"
unset ARCHITRAVE_SEMANTIC_REVIEW_COPILOT_MODEL
if err="$(harness/semantic-review.sh --provider copilot --run "$run_dir" --execute 2>&1 1>/dev/null)"; then
  echo "FAIL POSIX semantic launcher ran the copilot judge without a host-local model binding" >&2
  exit 1
fi
printf '%s' "$err" | grep -q 'ARCHITRAVE_SEMANTIC_REVIEW_COPILOT_MODEL'
if err="$(pwsh -NoProfile -File harness/semantic-review.ps1 -Provider copilot -RunDir "$run_dir" -Execute 2>&1 1>/dev/null)"; then
  echo "FAIL PowerShell semantic launcher ran the copilot judge without a host-local model binding" >&2
  exit 1
fi
printf '%s' "$err" | grep -q 'ARCHITRAVE_SEMANTIC_REVIEW_COPILOT_MODEL'
export ARCHITRAVE_SEMANTIC_REVIEW_COPILOT_MODEL="$saved_copilot_model"
unset ARCHITRAVE_SEMANTIC_REVIEW_CLAUDE_MODEL
if err="$(harness/semantic-review.sh --provider claude --run "$run_dir" --execute 2>&1 1>/dev/null)"; then
  echo "FAIL POSIX semantic launcher ran the claude judge without a host-local model binding" >&2
  exit 1
fi
printf '%s' "$err" | grep -q 'ARCHITRAVE_SEMANTIC_REVIEW_CLAUDE_MODEL'
if err="$(pwsh -NoProfile -File harness/semantic-review.ps1 -Provider claude -RunDir "$run_dir" -Execute 2>&1 1>/dev/null)"; then
  echo "FAIL PowerShell semantic launcher ran the claude judge without a host-local model binding" >&2
  exit 1
fi
printf '%s' "$err" | grep -q 'ARCHITRAVE_SEMANTIC_REVIEW_CLAUDE_MODEL'
export ARCHITRAVE_SEMANTIC_REVIEW_CLAUDE_MODEL="$saved_claude_model"
echo "ok    full gate fails closed without a host-local model binding (no canonical fallback)"

# Adversarial: the single fake executable is symlinked as both copilot and
# claude. Strip its family telemetry (FAKE_AGENT_FAMILY=none) and confirm an
# otherwise perfect nonce+VERDICT:PASS is rejected: exit code/nonce/verdict
# alone must not buy a GPT or Claude verdict.
export FAKE_AGENT_FAMILY=none
if err="$(harness/semantic-review.sh --provider both --run "$run_dir" --execute 2>&1 1>/dev/null)"; then
  echo "FAIL POSIX semantic launcher accepted a verdict with no family telemetry" >&2
  exit 1
fi
printf '%s' "$err" | grep -q 'family evidence'
if err="$(pwsh -NoProfile -File harness/semantic-review.ps1 -Provider both -RunDir "$run_dir" -Execute 2>&1 1>/dev/null)"; then
  echo "FAIL PowerShell semantic launcher accepted a verdict with no family telemetry" >&2
  exit 1
fi
printf '%s' "$err" | grep -q 'family evidence'
unset FAKE_AGENT_FAMILY
echo "ok    an indistinguishable copilot/claude twin without family telemetry is rejected"

# Adversarial: the same twin executable now emits telemetry for the *other*
# family (e.g. the copilot invocation reports an Anthropic vendor). A
# self-asserted cross-family PASS must not be accepted either.
export FAKE_AGENT_FAMILY=cross
if err="$(harness/semantic-review.sh --provider both --run "$run_dir" --execute 2>&1 1>/dev/null)"; then
  echo "FAIL POSIX semantic launcher accepted mismatched family telemetry" >&2
  exit 1
fi
printf '%s' "$err" | grep -q 'family evidence'
if err="$(pwsh -NoProfile -File harness/semantic-review.ps1 -Provider both -RunDir "$run_dir" -Execute 2>&1 1>/dev/null)"; then
  echo "FAIL PowerShell semantic launcher accepted mismatched family telemetry" >&2
  exit 1
fi
printf '%s' "$err" | grep -q 'family evidence'
unset FAKE_AGENT_FAMILY
echo "ok    telemetry claiming the wrong provider family is rejected"

# Adversarial: only one side of the twin cheats (claude reports no family
# evidence while copilot is honest); the gate must still fail overall.
export FAKE_AGENT_FAMILY_CLAUDE=none
if harness/semantic-review.sh --provider both --run "$run_dir" --execute >/dev/null 2>&1; then
  echo "FAIL POSIX semantic launcher passed while only the claude twin lacked family evidence" >&2
  exit 1
fi
if pwsh -NoProfile -File harness/semantic-review.ps1 -Provider both -RunDir "$run_dir" -Execute >/dev/null 2>&1; then
  echo "FAIL PowerShell semantic launcher passed while only the claude twin lacked family evidence" >&2
  exit 1
fi
unset FAKE_AGENT_FAMILY_CLAUDE
echo "ok    one side of the twin lacking family evidence still fails the gate"

# Regression guard: with distinct, correctly-labeled per-provider model
# bindings and no adversarial overrides, the full gate still passes.
harness/semantic-review.sh --provider both --run "$run_dir" --execute >/dev/null
pwsh -NoProfile -File harness/semantic-review.ps1 -Provider both -RunDir "$run_dir" -Execute >/dev/null
echo "ok    full gate passes with distinct, verifiable per-provider family evidence"

echo "REVIEW-LAUNCHERS: PASS"