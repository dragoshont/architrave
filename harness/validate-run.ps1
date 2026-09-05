#!/usr/bin/env pwsh
# Architrave audit harness - validate run artifacts exist and are parseable.
[CmdletBinding()]
param([string]$RunDir)
$ErrorActionPreference = 'Stop'

if (-not $RunDir) {
  $latest = Get-ChildItem '.architrave/runs' -Directory -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if ($latest) { $RunDir = $latest.FullName }
}
if (-not $RunDir -or -not (Test-Path $RunDir -PathType Container)) { [Console]::Error.WriteLine('validate-run: run dir not found'); exit 2 }

if (Test-Path (Join-Path $RunDir 'run.json') -PathType Leaf) {
  $Python = Get-Command python3 -ErrorAction SilentlyContinue
  if (-not $Python) { $Python = Get-Command python -ErrorAction SilentlyContinue }
  if (-not $Python) { [Console]::Error.WriteLine('validate-run: Python 3 is required for Run v2'); exit 2 }
  & $Python.Source (Join-Path $PSScriptRoot 'validate_run_v2.py') $RunDir
  exit $LASTEXITCODE
}

$fail = 0
function Require-File($Name, $Label) {
  $file = Join-Path $RunDir $Name
  if ((Test-Path $file) -and ((Get-Item $file).Length -gt 0)) { Write-Host "ok    $Label $file" } else { Write-Host "FAIL  missing/empty $Label $file"; $script:fail = 1 }
}
function Require-Heading($Name, $Heading) {
  $file = Join-Path $RunDir $Name
  if ((Test-Path $file) -and ((Get-Content $file -Raw) -match "(?m)^##\s+$([regex]::Escape($Heading))")) { Write-Host "ok    heading '$Heading' in $file" } else { Write-Host "FAIL  heading '$Heading' missing in $file"; $script:fail = 1 }
}

Require-File 'intake.md' 'intake'
Require-Heading 'intake.md' 'Understanding'
Require-Heading 'intake.md' 'Acceptance Criteria'
Require-Heading 'intake.md' 'Grounding Sources'
Require-File 'tournament.md' 'tournament'
Require-Heading 'tournament.md' 'Decision Matrix'
Require-File 'recommended-plan.md' 'recommended plan'
Require-Heading 'recommended-plan.md' 'Implementation Sequence'
Require-Heading 'recommended-plan.md' 'Test Strategy'
Require-File 'phase-ledger.md' 'phase ledger'
if ((Test-Path (Join-Path $RunDir 'phase-ledger.md')) -and ((Get-Content (Join-Path $RunDir 'phase-ledger.md') -Raw) -match '(?m)^\|\s*Phase\s*\|')) { Write-Host 'ok    phase ledger table' } else { Write-Host "FAIL  phase ledger table missing in $(Join-Path $RunDir 'phase-ledger.md')"; $fail = 1 }
function Validate-PhaseLedger {
  $file = Join-Path $RunDir 'phase-ledger.md'
  if (-not (Test-Path $file)) { return }
  $lines = Get-Content $file
  $headerSeen = $false
  $rows = 0
  $active = 0
  foreach ($line in $lines) {
    if ($line -notmatch '^\|') { continue }
    $cells = $line.Trim('|').Split('|') | ForEach-Object { $_.Trim() }
    if ($cells.Count -lt 6) { continue }
    if ($cells[0] -eq 'Phase') {
      $headerSeen = $true
      if ($cells[1] -ne 'Name' -or $cells[2] -ne 'Status' -or $cells[3] -ne 'Scope' -or $cells[4] -ne 'Gate' -or $cells[5] -ne 'Result') {
        Write-Host 'FAIL  phase ledger header must be Phase | Name | Status | Scope | Gate | Result'; $script:fail = 1
      }
      continue
    }
    if (($cells -join '') -match '^[-:]+$') { continue }
    $rows++
    if ($cells[0] -notmatch '^[0-9]+$') { Write-Host "FAIL  phase ledger invalid phase $($cells[0])"; $script:fail = 1 }
    if ($cells[2] -notin @('not-started','in-progress','blocked','completed','skipped')) { Write-Host "FAIL  phase ledger invalid status $($cells[2])"; $script:fail = 1 }
    if ($cells[2] -eq 'in-progress') { $active++ }
    if (-not $cells[1] -or -not $cells[3] -or -not $cells[4]) { Write-Host 'FAIL  phase ledger rows require name, scope, and gate'; $script:fail = 1 }
  }
  if (-not $headerSeen) { Write-Host 'FAIL  phase ledger header missing'; $script:fail = 1 }
  if ($rows -lt 1) { Write-Host 'FAIL  phase ledger has no phase rows'; $script:fail = 1 }
  if ($active -gt 1) { Write-Host 'FAIL  phase ledger has more than one in-progress phase'; $script:fail = 1 }
  if ($script:fail -eq 0) { Write-Host 'ok    phase ledger structure' }
}
Validate-PhaseLedger
Require-File 'deterministic-gates.md' 'deterministic gates'
Require-File 'summary.json' 'summary'

if ((Test-Path '.architrave/learning/repo-profile.md') -and ((Get-Item '.architrave/learning/repo-profile.md').Length -gt 0)) { Write-Host 'ok    repo profile .architrave/learning/repo-profile.md' } else { Write-Host 'FAIL  missing/empty repo profile .architrave/learning/repo-profile.md'; $fail = 1 }
if ((Test-Path '.architrave/learning/repo-lessons.md') -and ((Get-Item '.architrave/learning/repo-lessons.md').Length -gt 0)) { Write-Host 'ok    repo lessons .architrave/learning/repo-lessons.md' } else { Write-Host 'FAIL  missing/empty repo lessons .architrave/learning/repo-lessons.md'; $fail = 1 }

try {
  $summary = Get-Content (Join-Path $RunDir 'summary.json') -Raw | ConvertFrom-Json
  if ($summary.schema -ne 'architrave.run.v1' -or -not $summary.runId -or -not $summary.status -or -not ($summary.PSObject.Properties.Name -contains 'phases') -or $summary.phases.Count -lt 1) { throw 'invalid fields' }
  $activeSummary = 0
  foreach ($phase in $summary.phases) {
    if ($phase.phase -isnot [int] -and $phase.phase -isnot [long]) { throw 'invalid phase number' }
    if (-not $phase.name -or -not $phase.scope -or -not $phase.gate) { throw 'missing phase fields' }
    if ($phase.status -notin @('not-started','in-progress','blocked','completed','skipped')) { throw 'invalid phase status' }
    if ($phase.status -eq 'in-progress') { $activeSummary++ }
  }
  if ($activeSummary -gt 1) { throw 'too many active phases' }
  if ($summary.status -eq 'in-progress' -and $activeSummary -ne 1) { throw 'in-progress summary requires exactly one active phase' }
  if ($summary.status -ne 'in-progress' -and $activeSummary -ne 0) { throw 'terminal summary cannot have active phases' }
  if ($summary.PSObject.Properties.Name -contains 'execution') {
    $execution = $summary.execution
    $required = @('profile','intent','effectiveVerification','selectionReason','requested','observed','events','judgePasses')
    foreach ($name in $required) { if ($execution.PSObject.Properties.Name -notcontains $name) { throw "missing execution.$name" } }
    if ($execution.intent.modelClass -notin @('inherit','fast','default','strong')) { throw 'invalid execution modelClass' }
    if ($execution.intent.reasoning -notin @('low','default','high','max')) { throw 'invalid execution reasoning' }
    if ($execution.intent.context -notin @('narrow','default','long')) { throw 'invalid execution context' }
    if ($execution.intent.verification -notin @('default','independent','cross-family')) { throw 'invalid execution verification' }
    if ($execution.effectiveVerification -notin @('default','independent','cross-family')) { throw 'invalid effective verification' }
    $verificationRank = @{ default = 0; independent = 1; 'cross-family' = 2 }
    if ($verificationRank[$execution.effectiveVerification] -lt $verificationRank[$execution.intent.verification]) { throw 'effective verification cannot weaken selected intent' }
    $presets = @{
      FAST = @('fast','low','narrow','default')
      BALANCED = @('default','default','default','default')
      DEEP = @('strong','high','default','independent')
      CRITICAL = @('strong','high','default','cross-family')
    }
    if ($null -ne $execution.profile) {
      if (-not $presets.ContainsKey([string]$execution.profile)) { throw 'invalid execution profile' }
      $actual = @($execution.intent.modelClass,$execution.intent.reasoning,$execution.intent.context,$execution.intent.verification)
      if ((Compare-Object $actual $presets[[string]$execution.profile] -SyncWindow 0).Count -ne 0) { throw 'execution profile does not match intent' }
    }
    foreach ($name in @('hostProvider','model','reasoningEffort','contextTier')) { if ($execution.requested.PSObject.Properties.Name -notcontains $name) { throw "missing execution.requested.$name" } }
    foreach ($name in @('models','modelReasoning')) { if ($execution.observed.PSObject.Properties.Name -notcontains $name) { throw "missing execution.observed.$name" } }
    if ($execution.observed.models -isnot [System.Array] -or $execution.observed.modelReasoning -isnot [System.Array] -or $execution.events -isnot [System.Array] -or $execution.judgePasses -isnot [System.Array]) { throw 'execution collections must be arrays' }
    foreach ($item in @($execution.observed.modelReasoning)) {
      if (-not $item.model -or $item.PSObject.Properties.Name -notcontains 'vendor' -or $item.PSObject.Properties.Name -notcontains 'reasoningEffort') { throw 'invalid observed model reasoning' }
    }
    foreach ($event in @($execution.events)) {
      if ($event.type -notin @('fallback','escalation') -or -not $event.from -or -not $event.to -or -not $event.evidence) { throw 'invalid execution event' }
    }
    $postVerifiedFamilies = @()
    foreach ($judge in @($execution.judgePasses)) {
      $judgeRequired = @('stage','hostProvider','declaredFamily','requestedModel','requestedEffort','observedModels','observedVendors','familyEvidence','independent','verdict','promptVersion','rubricSha256')
      foreach ($name in $judgeRequired) { if ($judge.PSObject.Properties.Name -notcontains $name) { throw "missing judge pass field $name" } }
      if ($judge.stage -notin @('pre','post') -or -not $judge.hostProvider -or $judge.declaredFamily -notin @('gpt','claude') -or $judge.familyEvidence -notin @('observed-vendor','observed-model','unverified') -or $judge.verdict -notin @('PASS','REVISE','FAIL') -or -not $judge.promptVersion -or $judge.rubricSha256 -notmatch '^[0-9a-f]{64}$') { throw 'invalid judge pass' }
      if ($judge.observedModels -isnot [System.Array] -or $judge.observedVendors -isnot [System.Array]) { throw 'judge observations must be arrays' }
      $vendorFamilies = @($judge.observedVendors | ForEach-Object { if ($_ -match '(?i)anthropic|claude') { 'claude' } elseif ($_ -match '(?i)openai') { 'gpt' } } | Sort-Object -Unique)
      $modelFamilies = @($judge.observedModels | ForEach-Object { if ($_ -match '(?i)claude|anthropic') { 'claude' } elseif ($_ -match '(?i)^(gpt-|openai/|o1|o3|o4)') { 'gpt' } } | Sort-Object -Unique)
      if ($judge.familyEvidence -eq 'observed-vendor' -and $vendorFamilies -notcontains $judge.declaredFamily) { throw 'judge vendor contradicts declared family' }
      if ($judge.familyEvidence -eq 'observed-model' -and $modelFamilies -notcontains $judge.declaredFamily) { throw 'judge model contradicts declared family' }
      if ($judge.stage -eq 'post' -and $judge.independent -eq $true -and $judge.verdict -eq 'PASS' -and $judge.familyEvidence -ne 'unverified') { $postVerifiedFamilies += $judge.declaredFamily }
    }
    if ($execution.PSObject.Properties.Name -contains 'metrics') {
      $metricNames = @($execution.metrics.PSObject.Properties.Name)
      if (@($metricNames | Where-Object { $_ -notin @('durationMs','outputTokens','toolCalls') }).Count -gt 0) { throw 'unknown execution metric' }
      foreach ($name in @('durationMs','outputTokens','toolCalls')) {
        if ($execution.metrics.PSObject.Properties.Name -contains $name) {
          $value = $execution.metrics.$name
          if ($value -is [bool] -or ($value -isnot [int] -and $value -isnot [long]) -or $value -lt 0) { throw 'invalid execution metric' }
        }
      }
    }
    if ($summary.status -ne 'in-progress') {
      if ([string]::IsNullOrWhiteSpace([string]$execution.selectionReason)) { throw 'terminal execution summary requires selection reason' }
      if ($summary.status -eq 'passed' -and $execution.effectiveVerification -eq 'independent' -and $postVerifiedFamilies.Count -lt 1) { throw 'post-implementation independent verification is unproven' }
      if ($summary.status -eq 'passed' -and $execution.effectiveVerification -eq 'cross-family' -and (@($postVerifiedFamilies | Sort-Object -Unique) -notcontains 'gpt' -or @($postVerifiedFamilies | Sort-Object -Unique) -notcontains 'claude')) { throw 'post-implementation cross-family verification is unproven' }
    }
  }
  Write-Host 'ok    summary schema'
} catch {
  Write-Host 'FAIL  invalid summary.json'; $fail = 1
}

if ($fail -eq 0) { Write-Host 'ARCHITRAVE-RUN: PASS' } else { Write-Host 'ARCHITRAVE-RUN: FAIL' }
exit $fail