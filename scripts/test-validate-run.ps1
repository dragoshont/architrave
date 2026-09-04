#!/usr/bin/env pwsh
# Smoke tests for harness/validate-run.ps1. Mirrors scripts/test-validate-run.sh.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Root
$Tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("architrave-validate-run-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $Tmp | Out-Null
try {
  function Make-Repo([string]$Repo) {
    $Run = Join-Path $Repo '.architrave/runs/test-run'
    New-Item -ItemType Directory -Force -Path $Run,(Join-Path $Repo '.architrave/learning') | Out-Null
    Copy-Item -Recurse -Path 'harness' -Destination (Join-Path $Repo 'harness')
    Set-Content -Path (Join-Path $Repo 'architrave.config.json') -Value '{}' -Encoding utf8
    Set-Content -Path (Join-Path $Repo '.architrave/learning/repo-profile.md') -Value '# Repo Profile' -Encoding utf8
    Set-Content -Path (Join-Path $Repo '.architrave/learning/repo-lessons.md') -Value '# Repo Lessons' -Encoding utf8
    Set-Content -Path (Join-Path $Run 'intake.md') -Encoding utf8 -Value @'
# Intake

## Understanding
ok

## Acceptance Criteria
ok

## Grounding Sources
ok
'@
    Set-Content -Path (Join-Path $Run 'tournament.md') -Encoding utf8 -Value @'
# Tournament of Options

## Decision Matrix
ok
'@
    Set-Content -Path (Join-Path $Run 'recommended-plan.md') -Encoding utf8 -Value @'
# Recommended Plan

## Implementation Sequence
ok

## Test Strategy
ok
'@
    Set-Content -Path (Join-Path $Run 'phase-ledger.md') -Encoding utf8 -Value @'
# Phase Ledger

| Phase | Name | Status | Scope | Gate | Result |
|---:|---|---|---|---|---|
| 1 | Grounding | completed | Read source truth. | Evidence collected. | pass |
| 2 | Implementation | in-progress | Validate the harness. | Validator tests. | pending |

## Phase Transition Log
'@
    Set-Content -Path (Join-Path $Run 'deterministic-gates.md') -Encoding utf8 -Value @'
# Deterministic Gates

## checks
ok
'@
    Set-Content -Path (Join-Path $Run 'summary.json') -Encoding utf8 -Value @'
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
'@
  }

  function Expect-Pass([string]$Name, [string]$Repo) {
    Push-Location $Repo
    try {
      & ./harness/validate-run.ps1 .architrave/runs/test-run *> $null
      $code = $LASTEXITCODE
    } finally { Pop-Location }
    if ($code -eq 0) { Write-Host "ok   $Name" } else { Write-Error "FAIL $Name expected pass (exit $code)"; exit 1 }
  }

  function Expect-Fail([string]$Name, [string]$Repo) {
    Push-Location $Repo
    try {
      & ./harness/validate-run.ps1 .architrave/runs/test-run *> $null
      $code = $LASTEXITCODE
    } finally { Pop-Location }
    if ($code -ne 0) { Write-Host "ok   $Name" } else { Write-Error "FAIL $Name expected failure"; exit 1 }
  }

  function Make-AdaptiveTerminal([string]$Repo) {
    $SummaryPath = Join-Path $Repo '.architrave/runs/test-run/summary.json'
    $Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
    $Summary.status = 'passed'
    $Summary.phases[1].status = 'completed'
    $Execution = [pscustomobject]@{
      profile = 'CRITICAL'
      intent = [pscustomobject]@{ modelClass = 'strong'; reasoning = 'high'; context = 'default'; verification = 'cross-family' }
      effectiveVerification = 'cross-family'
      selectionReason = 'Security-sensitive acceptance requires verified cross-family review.'
      requested = [pscustomobject]@{ hostProvider = 'vscode-copilot'; model = $null; reasoningEffort = $null; contextTier = $null }
      observed = [pscustomobject]@{ models = @(); modelReasoning = @() }
      events = @()
      judgePasses = @(
        [pscustomobject]@{ stage = 'post'; hostProvider = 'vscode-copilot'; declaredFamily = 'gpt'; requestedModel = $null; requestedEffort = $null; observedModels = @('gpt-model'); observedVendors = @('openai'); familyEvidence = 'observed-vendor'; independent = $true; verdict = 'PASS'; promptVersion = '1'; rubricSha256 = ('a' * 64) },
        [pscustomobject]@{ stage = 'post'; hostProvider = 'vscode-copilot'; declaredFamily = 'claude'; requestedModel = $null; requestedEffort = $null; observedModels = @('claude-model'); observedVendors = @('anthropic'); familyEvidence = 'observed-vendor'; independent = $true; verdict = 'PASS'; promptVersion = '1'; rubricSha256 = ('a' * 64) }
      )
    }
    Add-Member -InputObject $Summary -NotePropertyName execution -NotePropertyValue $Execution -Force
    $Summary | ConvertTo-Json -Depth 15 | Set-Content -Path $SummaryPath -Encoding utf8
    (Get-Content (Join-Path $Repo '.architrave/runs/test-run/phase-ledger.md') -Raw).Replace('| 2 | Implementation | in-progress |', '| 2 | Implementation | completed |') | Set-Content -Path (Join-Path $Repo '.architrave/runs/test-run/phase-ledger.md') -Encoding utf8
  }

  $Valid = Join-Path $Tmp 'valid'; Make-Repo $Valid; Expect-Pass 'valid-run' $Valid

  $BadStatus = Join-Path $Tmp 'bad-status'; Make-Repo $BadStatus
  (Get-Content (Join-Path $BadStatus '.architrave/runs/test-run/phase-ledger.md') -Raw).Replace('| 2 | Implementation | in-progress |', '| 2 | Implementation | doing |') | Set-Content -Path (Join-Path $BadStatus '.architrave/runs/test-run/phase-ledger.md') -Encoding utf8
  Expect-Fail 'invalid-status' $BadStatus

  $BadHeader = Join-Path $Tmp 'bad-header'; Make-Repo $BadHeader
  (Get-Content (Join-Path $BadHeader '.architrave/runs/test-run/phase-ledger.md') -Raw).Replace('| Phase | Name | Status | Scope | Gate | Result |', '| Phase | Name | Status | Scope | Result |') | Set-Content -Path (Join-Path $BadHeader '.architrave/runs/test-run/phase-ledger.md') -Encoding utf8
  Expect-Fail 'missing-column' $BadHeader

  $TwoActive = Join-Path $Tmp 'two-active'; Make-Repo $TwoActive
  (Get-Content (Join-Path $TwoActive '.architrave/runs/test-run/phase-ledger.md') -Raw).Replace('| 1 | Grounding | completed |', '| 1 | Grounding | in-progress |') | Set-Content -Path (Join-Path $TwoActive '.architrave/runs/test-run/phase-ledger.md') -Encoding utf8
  Expect-Fail 'multiple-active' $TwoActive

  $BadSummary = Join-Path $Tmp 'bad-summary'; Make-Repo $BadSummary
  $SummaryPath = Join-Path $BadSummary '.architrave/runs/test-run/summary.json'
  $Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
  $Summary.phases[1].status = 'doing'
  $Summary | ConvertTo-Json -Depth 10 | Set-Content -Path $SummaryPath -Encoding utf8
  Expect-Fail 'invalid-summary-phase' $BadSummary

  $TerminalActive = Join-Path $Tmp 'terminal-active'; Make-Repo $TerminalActive
  $TerminalSummary = Join-Path $TerminalActive '.architrave/runs/test-run/summary.json'
  $Summary = Get-Content $TerminalSummary -Raw | ConvertFrom-Json
  $Summary.status = 'passed'
  $Summary | ConvertTo-Json -Depth 10 | Set-Content -Path $TerminalSummary -Encoding utf8
  Expect-Fail 'terminal-summary-active-phase' $TerminalActive

  $ProgressNoActive = Join-Path $Tmp 'progress-no-active'; Make-Repo $ProgressNoActive
  $ProgressSummary = Join-Path $ProgressNoActive '.architrave/runs/test-run/summary.json'
  $Summary = Get-Content $ProgressSummary -Raw | ConvertFrom-Json
  $Summary.phases[1].status = 'completed'
  $Summary | ConvertTo-Json -Depth 10 | Set-Content -Path $ProgressSummary -Encoding utf8
  (Get-Content (Join-Path $ProgressNoActive '.architrave/runs/test-run/phase-ledger.md') -Raw).Replace('| 2 | Implementation | in-progress |', '| 2 | Implementation | completed |') | Set-Content -Path (Join-Path $ProgressNoActive '.architrave/runs/test-run/phase-ledger.md') -Encoding utf8
  Expect-Fail 'in-progress-summary-no-active-phase' $ProgressNoActive

  $Adaptive = Join-Path $Tmp 'adaptive'; Make-Repo $Adaptive; Make-AdaptiveTerminal $Adaptive; Expect-Pass 'adaptive-cross-family-run' $Adaptive

  $BadPreset = Join-Path $Tmp 'bad-preset'; Make-Repo $BadPreset; Make-AdaptiveTerminal $BadPreset
  $SummaryPath = Join-Path $BadPreset '.architrave/runs/test-run/summary.json'; $Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json; $Summary.execution.intent.reasoning = 'max'; $Summary | ConvertTo-Json -Depth 15 | Set-Content $SummaryPath -Encoding utf8
  Expect-Fail 'adaptive-preset-mismatch' $BadPreset

  $UnverifiedFamily = Join-Path $Tmp 'unverified-family'; Make-Repo $UnverifiedFamily; Make-AdaptiveTerminal $UnverifiedFamily
  $SummaryPath = Join-Path $UnverifiedFamily '.architrave/runs/test-run/summary.json'; $Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json; $Summary.execution.judgePasses[1].familyEvidence = 'unverified'; $Summary | ConvertTo-Json -Depth 15 | Set-Content $SummaryPath -Encoding utf8
  Expect-Fail 'adaptive-unverified-cross-family' $UnverifiedFamily

  $BadEvent = Join-Path $Tmp 'bad-event'; Make-Repo $BadEvent; Make-AdaptiveTerminal $BadEvent
  $SummaryPath = Join-Path $BadEvent '.architrave/runs/test-run/summary.json'; $Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json; $Summary.execution.events = @([pscustomobject]@{ type = 'escalation'; from = 'BALANCED'; to = 'DEEP'; evidence = '' }); $Summary | ConvertTo-Json -Depth 15 | Set-Content $SummaryPath -Encoding utf8
  Expect-Fail 'adaptive-event-needs-evidence' $BadEvent

  $NoReason = Join-Path $Tmp 'no-reason'; Make-Repo $NoReason; Make-AdaptiveTerminal $NoReason
  $SummaryPath = Join-Path $NoReason '.architrave/runs/test-run/summary.json'; $Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json; $Summary.execution.selectionReason = $null; $Summary | ConvertTo-Json -Depth 15 | Set-Content $SummaryPath -Encoding utf8
  Expect-Fail 'adaptive-terminal-needs-reason' $NoReason

  $WeakerVerification = Join-Path $Tmp 'weaker-verification'; Make-Repo $WeakerVerification; Make-AdaptiveTerminal $WeakerVerification
  $SummaryPath = Join-Path $WeakerVerification '.architrave/runs/test-run/summary.json'; $Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json; $Summary.execution.profile = $null; $Summary.execution.effectiveVerification = 'default'; $Summary | ConvertTo-Json -Depth 15 | Set-Content $SummaryPath -Encoding utf8
  Expect-Fail 'adaptive-verification-cannot-weaken' $WeakerVerification

  $ContradictoryFamily = Join-Path $Tmp 'contradictory-family'; Make-Repo $ContradictoryFamily; Make-AdaptiveTerminal $ContradictoryFamily
  $SummaryPath = Join-Path $ContradictoryFamily '.architrave/runs/test-run/summary.json'; $Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json; $Summary.execution.judgePasses[1].observedVendors = @('openai'); $Summary | ConvertTo-Json -Depth 15 | Set-Content $SummaryPath -Encoding utf8
  Expect-Fail 'adaptive-family-evidence-must-match' $ContradictoryFamily

  $ScalarCollections = Join-Path $Tmp 'scalar-collections'; Make-Repo $ScalarCollections; Make-AdaptiveTerminal $ScalarCollections
  $SummaryPath = Join-Path $ScalarCollections '.architrave/runs/test-run/summary.json'; $Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json; $Summary.execution.observed.models = 'gpt-model'; $Summary | ConvertTo-Json -Depth 15 | Set-Content $SummaryPath -Encoding utf8
  Expect-Fail 'adaptive-collections-must-be-arrays' $ScalarCollections

  $PreOnly = Join-Path $Tmp 'pre-only'; Make-Repo $PreOnly; Make-AdaptiveTerminal $PreOnly
  $SummaryPath = Join-Path $PreOnly '.architrave/runs/test-run/summary.json'; $Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json; $Summary.execution.judgePasses | ForEach-Object { $_.stage = 'pre' }; $Summary | ConvertTo-Json -Depth 15 | Set-Content $SummaryPath -Encoding utf8
  Expect-Fail 'adaptive-terminal-needs-post-judges' $PreOnly

  $ValidMetrics = Join-Path $Tmp 'valid-metrics'; Make-Repo $ValidMetrics; Make-AdaptiveTerminal $ValidMetrics
  $SummaryPath = Join-Path $ValidMetrics '.architrave/runs/test-run/summary.json'; $Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json; Add-Member -InputObject $Summary.execution -NotePropertyName metrics -NotePropertyValue ([pscustomobject]@{ durationMs = 10; outputTokens = 20; toolCalls = 3 }); $Summary | ConvertTo-Json -Depth 15 | Set-Content $SummaryPath -Encoding utf8
  Expect-Pass 'adaptive-valid-metrics' $ValidMetrics

  $BadMetrics = Join-Path $Tmp 'bad-metrics'; Make-Repo $BadMetrics; Make-AdaptiveTerminal $BadMetrics
  $SummaryPath = Join-Path $BadMetrics '.architrave/runs/test-run/summary.json'; $Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json; Add-Member -InputObject $Summary.execution -NotePropertyName metrics -NotePropertyValue ([pscustomobject]@{ durationMs = 'ten' }); $Summary | ConvertTo-Json -Depth 15 | Set-Content $SummaryPath -Encoding utf8
  Expect-Fail 'adaptive-invalid-metrics' $BadMetrics

  $FractionalMetrics = Join-Path $Tmp 'fractional-metrics'; Make-Repo $FractionalMetrics; Make-AdaptiveTerminal $FractionalMetrics
  $SummaryPath = Join-Path $FractionalMetrics '.architrave/runs/test-run/summary.json'; $Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json; Add-Member -InputObject $Summary.execution -NotePropertyName metrics -NotePropertyValue ([pscustomobject]@{ durationMs = 1.5 }); $Summary | ConvertTo-Json -Depth 15 | Set-Content $SummaryPath -Encoding utf8
  Expect-Fail 'adaptive-fractional-metrics' $FractionalMetrics

  $UnknownMetrics = Join-Path $Tmp 'unknown-metrics'; Make-Repo $UnknownMetrics; Make-AdaptiveTerminal $UnknownMetrics
  $SummaryPath = Join-Path $UnknownMetrics '.architrave/runs/test-run/summary.json'; $Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json; Add-Member -InputObject $Summary.execution -NotePropertyName metrics -NotePropertyValue ([pscustomobject]@{ latencyMs = 10 }); $Summary | ConvertTo-Json -Depth 15 | Set-Content $SummaryPath -Encoding utf8
  Expect-Fail 'adaptive-unknown-metrics' $UnknownMetrics
}
finally {
  Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue
}
exit 0