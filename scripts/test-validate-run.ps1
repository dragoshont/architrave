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
}
finally {
  Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue
}