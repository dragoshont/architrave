#!/usr/bin/env pwsh
# Initialize one compact legacy Run v1 record. New work should use Run v2.
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
New-Item -ItemType Directory -Force -Path $runDir,'.architrave/learning' | Out-Null
$summary = Join-Path $runDir 'summary.json'
if (-not (Test-Path $summary)) {
  [ordered]@{
    schema = 'architrave.run.v1'
    runId = $RunId
    status = 'in-progress'
    startedAt = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    note = 'Legacy compact record; migrate to Run v2 for state transitions and evidence.'
  } | ConvertTo-Json -Compress | Set-Content -Path $summary -Encoding utf8
}
Write-Host $runDir
