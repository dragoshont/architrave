#!/usr/bin/env pwsh
# Architrave audit harness - initialize durable artifacts for one agent run.
[CmdletBinding()]
param([string]$RunId)
$ErrorActionPreference = 'Stop'

function Find-Root {
  $dir = (Get-Location).Path
  while ($dir) {
    if (Test-Path (Join-Path $dir 'architrave.config.json')) { return $dir }
    $parent = Split-Path $dir -Parent
    if ($parent -eq $dir -or [string]::IsNullOrEmpty($parent)) { break }
    $dir = $parent
  }
  return $null
}

$root = Find-Root
if (-not $root) { [Console]::Error.WriteLine('init-run: architrave.config.json not found'); exit 2 }
Set-Location $root

if (-not $RunId) { $RunId = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') }
$runDir = Join-Path '.architrave/runs' $RunId
$learningDir = '.architrave/learning'
New-Item -ItemType Directory -Force -Path $runDir,$learningDir | Out-Null

function New-Artifact($Name, $Title, $Body) {
  $file = Join-Path $runDir $Name
  if (-not (Test-Path $file)) {
    Set-Content -Path $file -Encoding utf8 -Value "# $Title`n`n$Body`n"
  }
}

New-Artifact 'intake.md' 'Intake' "## Understanding`n`n## Acceptance Criteria`n`n## Grounding Sources`n`n## Assumptions`n`n## Blocking Questions"
New-Artifact 'tournament.md' 'Tournament of Options' "## Option A - Minimal Safe Fix`n`n## Option B - Proper Architectural Fix`n`n## Option C - Defer / Ask More`n`n## Decision Matrix`n`n## Winner"
New-Artifact 'recommended-plan.md' 'Recommended Plan' "## Summary`n`n## Implementation Sequence`n`n## Test Strategy`n`n## Rollback / Recovery`n`n## Human Approval Needed"
New-Artifact 'phase-ledger.md' 'Phase Ledger' "| Phase | Name | Status | Scope | Gate | Result |`n|---:|---|---|---|---|---|`n| 0 | Intake / Grounding | in-progress | Define the request, acceptance criteria, and sources of truth. | Intake + tournament recorded | pending |`n`n## Phase Transition Log"
New-Artifact 'deterministic-gates.md' 'Deterministic Gates' "## checks`n`n## backend-checks`n`n## reconcile`n`n## other"
New-Artifact 'judge-pre.md' 'Judge Gate 1' "## Verdict`n`n## Findings"
New-Artifact 'judge-post.md' 'Judge Gate 2' "## Verdict`n`n## Findings"
New-Artifact 'runtime-observer.md' 'Runtime Observer' "## Sources Used`n`n## Observed State`n`n## Mismatches`n`n## Human Approval Items"

$summary = Join-Path $runDir 'summary.json'
if (-not (Test-Path $summary)) {
  $obj = [ordered]@{
    schema = 'architrave.run.v1'
    runId = $RunId
    status = 'in-progress'
    startedAt = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    artifacts = [ordered]@{
      intake = "$runDir/intake.md"
      tournament = "$runDir/tournament.md"
      recommendedPlan = "$runDir/recommended-plan.md"
      phaseLedger = "$runDir/phase-ledger.md"
      deterministicGates = "$runDir/deterministic-gates.md"
      judgePre = "$runDir/judge-pre.md"
      judgePost = "$runDir/judge-post.md"
      runtimeObserver = "$runDir/runtime-observer.md"
    }
    learning = [ordered]@{
      repoProfile = "$learningDir/repo-profile.md"
      repoLessons = "$learningDir/repo-lessons.md"
      candidateLessons = 0
      promotionsProposed = 0
    }
    phases = @(
      [ordered]@{
        phase = 0
        name = 'Intake / Grounding'
        status = 'in-progress'
        scope = 'Define the request, acceptance criteria, and sources of truth.'
        gate = 'Intake + tournament recorded'
        result = 'pending'
      }
    )
  }
  $obj | ConvertTo-Json -Depth 10 | Set-Content -Path $summary -Encoding utf8
}

$lessons = Join-Path $learningDir 'repo-lessons.md'
if (-not (Test-Path $lessons)) {
  Set-Content -Path $lessons -Encoding utf8 -Value "# Architrave Repo Lessons`n`nCandidate lessons learned while implementing in this repo. Keep this file short.`nEach entry needs evidence and validation before promotion. Do not store secrets.`nPromote repeated, stable lessons into ``architrave.config.json``, ``AGENTS.md``, ``.github/instructions/``, or docs after review.`n`n## Candidate Lessons`n`n| Lesson | Evidence | Occurrences | Validated | Proposed Target | Status |`n|---|---|---:|---|---|---|`n"
}

$profile = Join-Path $learningDir 'repo-profile.md'
if (-not (Test-Path $profile)) {
  Set-Content -Path $profile -Encoding utf8 -Value "# Architrave Repo Profile`n`nConcise, validated repository description for future Architrave runs. Keep this high-signal and cite evidence; move detailed rules into docs or path-scoped instructions.`n`n## Purpose`n`n## Surfaces And Lanes`n`n## Source Of Truth`n`n## Build And Test`n`n## Architecture Map`n`n## Recurring Gotchas`n`n## Validated Facts`n`n| Fact | Evidence | Last Checked |`n|---|---|---|`n`n## Last Reviewed`n"
}

Write-Host $runDir