#!/usr/bin/env pwsh
# Validate a compact Run v2 or a legacy compact Run v1 summary.
[CmdletBinding()]
param([string]$RunDir)
$ErrorActionPreference = 'Stop'

if (-not $RunDir) {
  $latest = Get-ChildItem '.architrave/runs' -Directory -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if ($latest) { $RunDir = $latest.FullName }
}
if (-not $RunDir -or -not (Test-Path $RunDir -PathType Container)) {
  [Console]::Error.WriteLine('validate-run: run dir not found')
  exit 2
}

if (Test-Path (Join-Path $RunDir 'run.json') -PathType Leaf) {
  $Python = Get-Command python -ErrorAction SilentlyContinue
  if (-not $Python) { $Python = Get-Command python3 -ErrorAction SilentlyContinue }
  if (-not $Python) { [Console]::Error.WriteLine('validate-run: Python 3 is required for Run v2'); exit 2 }
  & $Python.Source (Join-Path $PSScriptRoot 'validate_run_v2.py') $RunDir
  exit $LASTEXITCODE
}

try {
  $summary = Get-Content (Join-Path $RunDir 'summary.json') -Raw | ConvertFrom-Json
  if ($summary.schema -ne 'architrave.run.v1' -or
      [string]::IsNullOrWhiteSpace([string]$summary.runId) -or
      $summary.status -notin @('in-progress','blocked','passed','revised','failed')) {
    throw 'invalid legacy summary'
  }
  Write-Host 'ARCHITRAVE-RUN: PASS'
  exit 0
} catch {
  Write-Host 'ARCHITRAVE-RUN: FAIL'
  exit 1
}
