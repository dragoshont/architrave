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
Require-File 'deterministic-gates.md' 'deterministic gates'
Require-File 'summary.json' 'summary'

if ((Test-Path '.architrave/learning/repo-profile.md') -and ((Get-Item '.architrave/learning/repo-profile.md').Length -gt 0)) { Write-Host 'ok    repo profile .architrave/learning/repo-profile.md' } else { Write-Host 'FAIL  missing/empty repo profile .architrave/learning/repo-profile.md'; $fail = 1 }
if ((Test-Path '.architrave/learning/repo-lessons.md') -and ((Get-Item '.architrave/learning/repo-lessons.md').Length -gt 0)) { Write-Host 'ok    repo lessons .architrave/learning/repo-lessons.md' } else { Write-Host 'FAIL  missing/empty repo lessons .architrave/learning/repo-lessons.md'; $fail = 1 }

try {
  $summary = Get-Content (Join-Path $RunDir 'summary.json') -Raw | ConvertFrom-Json
  if ($summary.schema -eq 'architrave.run.v1' -and $summary.runId -and $summary.status -and ($summary.PSObject.Properties.Name -contains 'phases')) { Write-Host 'ok    summary schema' } else { throw 'invalid fields' }
} catch {
  Write-Host 'FAIL  invalid summary.json'; $fail = 1
}

if ($fail -eq 0) { Write-Host 'ARCHITRAVE-RUN: PASS' } else { Write-Host 'ARCHITRAVE-RUN: FAIL' }
exit $fail