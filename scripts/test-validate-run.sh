#!/usr/bin/env bash
# Smoke tests for harness/validate-run.sh. These create temporary Architrave-like
# repos so the validator is tested against both valid and malformed run artifacts.
set -euo pipefail
cd "$(dirname "$0")/.."

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

make_repo() {
  local repo="$1"
  local run="$repo/.architrave/runs/test-run"
  mkdir -p "$run" "$repo/.architrave/learning"
  cp -R harness "$repo/harness"
  chmod +x "$repo"/harness/*.sh 2>/dev/null || true
  printf '{}\n' > "$repo/architrave.config.json"
  cat > "$repo/.architrave/learning/repo-profile.md" <<'MD'
# Repo Profile
MD
  cat > "$repo/.architrave/learning/repo-lessons.md" <<'MD'
# Repo Lessons
MD
  cat > "$run/intake.md" <<'MD'
# Intake

## Understanding
ok

## Acceptance Criteria
ok

## Grounding Sources
ok
MD
  cat > "$run/tournament.md" <<'MD'
# Tournament of Options

## Decision Matrix
ok
MD
  cat > "$run/recommended-plan.md" <<'MD'
# Recommended Plan

## Implementation Sequence
ok

## Test Strategy
ok
MD
  cat > "$run/phase-ledger.md" <<'MD'
# Phase Ledger

| Phase | Name | Status | Scope | Gate | Result |
|---:|---|---|---|---|---|
| 1 | Grounding | completed | Read source truth. | Evidence collected. | pass |
| 2 | Implementation | in-progress | Validate the harness. | Validator tests. | pending |

## Phase Transition Log
MD
  cat > "$run/deterministic-gates.md" <<'MD'
# Deterministic Gates

## checks
ok
MD
  cat > "$run/summary.json" <<'JSON'
{
  "schema": "architrave.run.v1",
  "runId": "test-run",
  "status": "in-progress",
  "artifacts": {
    "intake": ".architrave/runs/test-run/intake.md",
    "tournament": ".architrave/runs/test-run/tournament.md",
    "recommendedPlan": ".architrave/runs/test-run/recommended-plan.md",
    "phaseLedger": ".architrave/runs/test-run/phase-ledger.md",
    "deterministicGates": ".architrave/runs/test-run/deterministic-gates.md"
  },
  "phases": [
    { "phase": 1, "name": "Grounding", "status": "completed", "scope": "Read source truth.", "gate": "Evidence collected.", "result": "pass" },
    { "phase": 2, "name": "Implementation", "status": "in-progress", "scope": "Validate the harness.", "gate": "Validator tests.", "result": "pending" }
  ]
}
JSON
}

expect_pass() {
  local name="$1" repo="$2"
  if (cd "$repo" && harness/validate-run.sh .architrave/runs/test-run >/dev/null); then
    echo "ok   $name"
  else
    echo "FAIL $name expected pass" >&2
    exit 1
  fi
}

expect_fail() {
  local name="$1" repo="$2"
  if (cd "$repo" && harness/validate-run.sh .architrave/runs/test-run >/dev/null 2>&1); then
    echo "FAIL $name expected failure" >&2
    exit 1
  else
    echo "ok   $name"
  fi
}

make_adaptive_terminal() {
  local repo="$1" summary="$1/.architrave/runs/test-run/summary.json"
  jq '
    .status = "passed" |
    .phases[1].status = "completed" |
    .execution = {
      profile: "CRITICAL",
      intent: {modelClass:"strong", reasoning:"high", context:"default", verification:"cross-family"},
      effectiveVerification: "cross-family",
      selectionReason: "Security-sensitive acceptance requires verified cross-family review.",
      requested: {hostProvider:"copilot", model:null, reasoningEffort:null, contextTier:null},
      observed: {models:[], modelReasoning:[]},
      events: [],
      judgePasses: [
        {stage:"post", hostProvider:"copilot", declaredFamily:"gpt", requestedModel:null, requestedEffort:null, observedModels:["gpt-model"], observedVendors:["openai"], familyEvidence:"observed-vendor", independent:true, verdict:"PASS", promptVersion:"1", rubricSha256:("a" * 64)},
        {stage:"post", hostProvider:"copilot", declaredFamily:"claude", requestedModel:null, requestedEffort:null, observedModels:["claude-model"], observedVendors:["anthropic"], familyEvidence:"observed-vendor", independent:true, verdict:"PASS", promptVersion:"1", rubricSha256:("a" * 64)}
      ]
    }
  ' "$summary" > "$summary.tmp" && mv "$summary.tmp" "$summary"
  perl -0pi -e 's/\| 2 \| Implementation \| in-progress \|/| 2 | Implementation | completed |/' "$repo/.architrave/runs/test-run/phase-ledger.md"
}

valid="$tmp/valid"
make_repo "$valid"
expect_pass valid-run "$valid"

bad_status="$tmp/bad-status"
make_repo "$bad_status"
perl -0pi -e 's/\| 2 \| Implementation \| in-progress \|/| 2 | Implementation | doing |/' "$bad_status/.architrave/runs/test-run/phase-ledger.md"
expect_fail invalid-status "$bad_status"

bad_header="$tmp/bad-header"
make_repo "$bad_header"
perl -0pi -e 's/\| Phase \| Name \| Status \| Scope \| Gate \| Result \|/| Phase | Name | Status | Scope | Result |/' "$bad_header/.architrave/runs/test-run/phase-ledger.md"
expect_fail missing-column "$bad_header"

two_active="$tmp/two-active"
make_repo "$two_active"
perl -0pi -e 's/\| 1 \| Grounding \| completed \|/| 1 | Grounding | in-progress |/' "$two_active/.architrave/runs/test-run/phase-ledger.md"
expect_fail multiple-active "$two_active"

bad_summary="$tmp/bad-summary"
make_repo "$bad_summary"
jq '.phases[1].status = "doing"' "$bad_summary/.architrave/runs/test-run/summary.json" > "$bad_summary/.architrave/runs/test-run/summary.tmp" && mv "$bad_summary/.architrave/runs/test-run/summary.tmp" "$bad_summary/.architrave/runs/test-run/summary.json"
expect_fail invalid-summary-phase "$bad_summary"

terminal_active="$tmp/terminal-active"
make_repo "$terminal_active"
jq '.status = "passed"' "$terminal_active/.architrave/runs/test-run/summary.json" > "$terminal_active/.architrave/runs/test-run/summary.tmp" && mv "$terminal_active/.architrave/runs/test-run/summary.tmp" "$terminal_active/.architrave/runs/test-run/summary.json"
expect_fail terminal-summary-active-phase "$terminal_active"

progress_no_active="$tmp/progress-no-active"
make_repo "$progress_no_active"
jq '.phases[1].status = "completed"' "$progress_no_active/.architrave/runs/test-run/summary.json" > "$progress_no_active/.architrave/runs/test-run/summary.tmp" && mv "$progress_no_active/.architrave/runs/test-run/summary.tmp" "$progress_no_active/.architrave/runs/test-run/summary.json"
perl -0pi -e 's/\| 2 \| Implementation \| in-progress \|/| 2 | Implementation | completed |/' "$progress_no_active/.architrave/runs/test-run/phase-ledger.md"
expect_fail in-progress-summary-no-active-phase "$progress_no_active"

adaptive="$tmp/adaptive"
make_repo "$adaptive"
make_adaptive_terminal "$adaptive"
expect_pass adaptive-cross-family-run "$adaptive"

bad_preset="$tmp/bad-preset"
make_repo "$bad_preset"
make_adaptive_terminal "$bad_preset"
jq '.execution.intent.reasoning = "max"' "$bad_preset/.architrave/runs/test-run/summary.json" > "$bad_preset/.architrave/runs/test-run/summary.tmp" && mv "$bad_preset/.architrave/runs/test-run/summary.tmp" "$bad_preset/.architrave/runs/test-run/summary.json"
expect_fail adaptive-preset-mismatch "$bad_preset"

unverified_family="$tmp/unverified-family"
make_repo "$unverified_family"
make_adaptive_terminal "$unverified_family"
jq '.execution.judgePasses[1].familyEvidence = "unverified"' "$unverified_family/.architrave/runs/test-run/summary.json" > "$unverified_family/.architrave/runs/test-run/summary.tmp" && mv "$unverified_family/.architrave/runs/test-run/summary.tmp" "$unverified_family/.architrave/runs/test-run/summary.json"
expect_fail adaptive-unverified-cross-family "$unverified_family"

bad_event="$tmp/bad-event"
make_repo "$bad_event"
make_adaptive_terminal "$bad_event"
jq '.execution.events = [{type:"escalation", from:"BALANCED", to:"DEEP", evidence:""}]' "$bad_event/.architrave/runs/test-run/summary.json" > "$bad_event/.architrave/runs/test-run/summary.tmp" && mv "$bad_event/.architrave/runs/test-run/summary.tmp" "$bad_event/.architrave/runs/test-run/summary.json"
expect_fail adaptive-event-needs-evidence "$bad_event"

no_reason="$tmp/no-reason"
make_repo "$no_reason"
make_adaptive_terminal "$no_reason"
jq '.execution.selectionReason = null' "$no_reason/.architrave/runs/test-run/summary.json" > "$no_reason/.architrave/runs/test-run/summary.tmp" && mv "$no_reason/.architrave/runs/test-run/summary.tmp" "$no_reason/.architrave/runs/test-run/summary.json"
expect_fail adaptive-terminal-needs-reason "$no_reason"

weaker_verification="$tmp/weaker-verification"
make_repo "$weaker_verification"
make_adaptive_terminal "$weaker_verification"
jq '.execution.profile = null | .execution.effectiveVerification = "default"' "$weaker_verification/.architrave/runs/test-run/summary.json" > "$weaker_verification/.architrave/runs/test-run/summary.tmp" && mv "$weaker_verification/.architrave/runs/test-run/summary.tmp" "$weaker_verification/.architrave/runs/test-run/summary.json"
expect_fail adaptive-verification-cannot-weaken "$weaker_verification"

contradictory_family="$tmp/contradictory-family"
make_repo "$contradictory_family"
make_adaptive_terminal "$contradictory_family"
jq '.execution.judgePasses[1].observedVendors = ["openai"]' "$contradictory_family/.architrave/runs/test-run/summary.json" > "$contradictory_family/.architrave/runs/test-run/summary.tmp" && mv "$contradictory_family/.architrave/runs/test-run/summary.tmp" "$contradictory_family/.architrave/runs/test-run/summary.json"
expect_fail adaptive-family-evidence-must-match "$contradictory_family"

scalar_collections="$tmp/scalar-collections"
make_repo "$scalar_collections"
make_adaptive_terminal "$scalar_collections"
jq '.execution.observed.models = "gpt-model"' "$scalar_collections/.architrave/runs/test-run/summary.json" > "$scalar_collections/.architrave/runs/test-run/summary.tmp" && mv "$scalar_collections/.architrave/runs/test-run/summary.tmp" "$scalar_collections/.architrave/runs/test-run/summary.json"
expect_fail adaptive-collections-must-be-arrays "$scalar_collections"

pre_only="$tmp/pre-only"
make_repo "$pre_only"
make_adaptive_terminal "$pre_only"
jq '.execution.judgePasses |= map(.stage = "pre")' "$pre_only/.architrave/runs/test-run/summary.json" > "$pre_only/.architrave/runs/test-run/summary.tmp" && mv "$pre_only/.architrave/runs/test-run/summary.tmp" "$pre_only/.architrave/runs/test-run/summary.json"
expect_fail adaptive-terminal-needs-post-judges "$pre_only"

valid_metrics="$tmp/valid-metrics"
make_repo "$valid_metrics"
make_adaptive_terminal "$valid_metrics"
jq '.execution.metrics = {durationMs:10, outputTokens:20, toolCalls:3}' "$valid_metrics/.architrave/runs/test-run/summary.json" > "$valid_metrics/.architrave/runs/test-run/summary.tmp" && mv "$valid_metrics/.architrave/runs/test-run/summary.tmp" "$valid_metrics/.architrave/runs/test-run/summary.json"
expect_pass adaptive-valid-metrics "$valid_metrics"

bad_metrics="$tmp/bad-metrics"
make_repo "$bad_metrics"
make_adaptive_terminal "$bad_metrics"
jq '.execution.metrics = {durationMs:"ten"}' "$bad_metrics/.architrave/runs/test-run/summary.json" > "$bad_metrics/.architrave/runs/test-run/summary.tmp" && mv "$bad_metrics/.architrave/runs/test-run/summary.tmp" "$bad_metrics/.architrave/runs/test-run/summary.json"
expect_fail adaptive-invalid-metrics "$bad_metrics"

fractional_metrics="$tmp/fractional-metrics"
make_repo "$fractional_metrics"
make_adaptive_terminal "$fractional_metrics"
jq '.execution.metrics = {durationMs:1.5}' "$fractional_metrics/.architrave/runs/test-run/summary.json" > "$fractional_metrics/.architrave/runs/test-run/summary.tmp" && mv "$fractional_metrics/.architrave/runs/test-run/summary.tmp" "$fractional_metrics/.architrave/runs/test-run/summary.json"
expect_fail adaptive-fractional-metrics "$fractional_metrics"

unknown_metrics="$tmp/unknown-metrics"
make_repo "$unknown_metrics"
make_adaptive_terminal "$unknown_metrics"
jq '.execution.metrics = {latencyMs:10}' "$unknown_metrics/.architrave/runs/test-run/summary.json" > "$unknown_metrics/.architrave/runs/test-run/summary.tmp" && mv "$unknown_metrics/.architrave/runs/test-run/summary.tmp" "$unknown_metrics/.architrave/runs/test-run/summary.json"
expect_fail adaptive-unknown-metrics "$unknown_metrics"