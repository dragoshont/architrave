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
  Write-Host 'ok    summary schema'
} catch {
  Write-Host 'FAIL  invalid summary.json'; $fail = 1
}

if ($fail -eq 0) { Write-Host 'ARCHITRAVE-RUN: PASS' } else { Write-Host 'ARCHITRAVE-RUN: FAIL' }
exit $fail