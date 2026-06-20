#!/usr/bin/env pwsh
# Architrave UI — deterministic gate runner (PowerShell / Windows). Mirror of
# gates/checks.sh. Reads uikit.config.json with native ConvertFrom-Json (no jq
# needed on Windows) and runs the configured generate/build/test, validating the
# designMap + tokens JSON.
#
#   pwsh -NoProfile -File gates/checks.ps1           # full
#   pwsh -NoProfile -File gates/checks.ps1 -Quick    # JSON validity only (hooks / Stop gate)
#
# Exit 0 = PASS, non-zero = FAIL.
[CmdletBinding()]
param([switch]$Quick)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Find-Root {
  $d = (Get-Location).Path
  while ($d) {
    if (Test-Path (Join-Path $d 'uikit.config.json')) { return $d }
    $p = Split-Path $d -Parent
    if ($p -eq $d -or [string]::IsNullOrEmpty($p)) { break }
    $d = $p
  }
  return $null
}

$root = Find-Root
if (-not $root) { [Console]::Error.WriteLine('checks: uikit.config.json not found (run inside a repo that adopted Architrave UI)'); exit 2 }
Set-Location $root
$cfg = Get-Content 'uikit.config.json' -Raw | ConvertFrom-Json

$script:fail = 0
function Get-Field($name) {
  if ($cfg.PSObject.Properties.Name -contains $name) { return [string]$cfg.$name }
  return ''
}
function Test-JsonFile($f, $label) {
  if ([string]::IsNullOrWhiteSpace($f)) { return }
  if (Test-Path $f) {
    try { Get-Content $f -Raw | ConvertFrom-Json | Out-Null; Write-Host "ok    $label $f" }
    catch { Write-Host "FAIL  $label $f (invalid JSON)"; $script:fail = 1 }
  } else { Write-Host "warn  $label $f (missing)" }
}

Write-Host "== Architrave UI checks (root: $root) =="
Test-JsonFile 'uikit.config.json' 'config   '
Test-JsonFile (Get-Field 'designMap') 'designMap'
Test-JsonFile (Get-Field 'tokens') 'tokens   '

if ($Quick) {
  if ($script:fail -eq 0) { Write-Host 'CHECKS (quick): PASS' } else { Write-Host 'CHECKS (quick): FAIL' }
  exit $script:fail
}

function Invoke-Step($name, $field) {
  $cmd = Get-Field $field
  if ([string]::IsNullOrWhiteSpace($cmd)) { Write-Host "skip  $name (not configured)"; return }
  Write-Host "== $name`: $cmd =="
  $global:LASTEXITCODE = 0
  try { Invoke-Expression $cmd } catch { Write-Host "FAIL  $name ($($_.Exception.Message))"; $script:fail = 1; return }
  if ($LASTEXITCODE -ne 0) { Write-Host "FAIL  $name" ; $script:fail = 1 } else { Write-Host "ok    $name" }
}
Invoke-Step 'generate' 'generate'
Invoke-Step 'build'    'build'
Invoke-Step 'test'     'test'

if ($script:fail -eq 0) { Write-Host 'CHECKS: PASS' } else { Write-Host 'CHECKS: FAIL' }
exit $script:fail
