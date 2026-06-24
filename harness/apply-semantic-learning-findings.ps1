#!/usr/bin/env pwsh
# Apply reviewed semantic stale-fact findings to learning artifacts.
[CmdletBinding()]
param(
  [string]$Repo = (Get-Location).Path,
  [string]$Findings = '.architrave/learning/semantic-stale-facts.jsonl',
  [switch]$Apply
)
$ErrorActionPreference = 'Stop'

Set-Location $Repo
if (-not (Test-Path $Findings -PathType Leaf)) { [Console]::Error.WriteLine("apply-semantic-learning-findings: findings file not found: $Findings"); exit 2 }

$Allowed = @('.architrave/learning/repo-profile.md', '.architrave/learning/repo-lessons.md')
$Rows = Get-Content $Findings | Where-Object { $_.Trim() -and $_.Trim() -ne 'PASS' }
if ($Rows.Count -eq 0) { Write-Host 'apply-semantic-learning-findings: no semantic stale findings'; exit 0 }

$Fail = 0
$Changed = $false
foreach ($Row in $Rows) {
  try { $Finding = $Row | ConvertFrom-Json }
  catch { Write-Host "FAIL  invalid finding JSON: $Row"; $Fail = 1; continue }

  $File = [string]$Finding.file
  $Line = [int]$Finding.line
  $Current = [string]$Finding.currentText
  $Reason = if ($Finding.reason) { [string]$Finding.reason } else { 'semantic finding' }
  $Severity = if ($Finding.severity) { [string]$Finding.severity } else { 'major' }

  if ($Allowed -notcontains $File) { Write-Host "FAIL  finding file outside learning artifacts: $File"; $Fail = 1; continue }
  if ($Line -le 0) { Write-Host "FAIL  invalid line for ${File}: $Line"; $Fail = 1; continue }
  if (-not (Test-Path $File -PathType Leaf)) { Write-Host "FAIL  missing learning file: $File"; $Fail = 1; continue }

  $Lines = [System.Collections.Generic.List[string]]::new()
  foreach ($ExistingLine in Get-Content $File) { $Lines.Add($ExistingLine) }
  if ($Line -gt $Lines.Count) { Write-Host "FAIL  finding line outside file ${File}:$Line"; $Fail = 1; continue }
  $Actual = $Lines[$Line - 1]
  if ($Actual -eq "UNVALIDATED: $Current") { continue }
  if ($Actual -ne $Current) {
    Write-Host "FAIL  finding no longer matches ${File}:$Line"
    Write-Host "      expected: $Current"
    Write-Host "      actual:   $Actual"
    $Fail = 1
    continue
  }

  $Changed = $true
  if ($Apply) {
    $Lines[$Line - 1] = "UNVALIDATED: $Actual"
    Set-Content -Path $File -Encoding utf8 -Value $Lines
    Write-Host "marked ${File}:$Line [$Severity] $Reason"
  } else {
    Write-Host "would mark ${File}:$Line [$Severity] $Reason"
  }
}

if ($Fail -ne 0) { exit 1 }
if (-not $Changed) { Write-Host 'apply-semantic-learning-findings: no matching unvalidated lines to mark' }
exit 0