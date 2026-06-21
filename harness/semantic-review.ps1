#!/usr/bin/env pwsh
# Optional semantic review helper. It prepares a judge prompt from run artifacts.
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][ValidateSet('copilot','claude')][string]$Provider,
  [string]$RunDir,
  [switch]$Execute
)
$ErrorActionPreference = 'Stop'

if (-not $RunDir) {
  $latest = Get-ChildItem '.architrave/runs' -Directory -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if ($latest) { $RunDir = $latest.FullName }
}
if (-not $RunDir -or -not (Test-Path $RunDir -PathType Container)) { [Console]::Error.WriteLine('semantic-review: run dir not found'); exit 2 }

$prompt = Join-Path $RunDir 'semantic-review-prompt.md'
Set-Content -Path $prompt -Encoding utf8 -Value @"
You are an adversarial semantic reviewer for an Architrave run.

Review the run artifacts in $RunDir against gates/rubric.md. Focus on:
- visible intake quality;
- Tournament of Options quality;
- Recommended Plan quality;
- contract/architecture fit;
- deterministic gate evidence;
- safety, capability honesty, and missing tests.

Return PASS / REVISE / FAIL with findings ordered by severity.
"@

Write-Host "semantic-review prompt: $prompt"
if (-not $Execute) {
  if ($Provider -eq 'copilot') { Write-Host "suggested command: copilot -C `"$PWD`" --agent `"Adversarial Judge`" -p (Get-Content `"$prompt`" -Raw)" }
  else { Write-Host "suggested command: claude --agent `"Adversarial Judge`" -p (Get-Content `"$prompt`" -Raw)" }
  exit 0
}

$body = Get-Content $prompt -Raw
if ($Provider -eq 'copilot') { & copilot -C "$PWD" --agent 'Adversarial Judge' -p $body }
else { & claude --agent 'Adversarial Judge' -p $body }