#!/usr/bin/env pwsh
# Architrave — deterministic gate runner (PowerShell / Windows). Mirror of
# gates/checks.sh. Reads architrave.config.json with native ConvertFrom-Json (no jq
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
    if (Test-Path (Join-Path $d 'architrave.config.json')) { return $d }
    $p = Split-Path $d -Parent
    if ($p -eq $d -or [string]::IsNullOrEmpty($p)) { break }
    $d = $p
  }
  return $null
}

$root = Find-Root
if (-not $root) { [Console]::Error.WriteLine('checks: architrave.config.json not found (run inside a repo that adopted Architrave)'); exit 2 }
Set-Location $root
$cfg = Get-Content 'architrave.config.json' -Raw | ConvertFrom-Json

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

# F4 drift nudge: non-blocking warning when the repo's copied kit assets are older
# than the locally installed plugin. Silent when it can't tell.
function Show-KitDriftNudge {
  $stamp = if (Test-Path 'gates/.kit-version') { (Get-Content 'gates/.kit-version' -Raw).Trim() } else { '' }
  $plug = Get-ChildItem -Path "$HOME/.copilot/installed-plugins","$HOME/.claude/plugins" -Recurse -Filter 'plugin.json' -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match 'architrave(-ui)?' } | Select-Object -First 1
  if (-not $plug) { return }
  $ref = (Get-Content $plug.FullName -Raw | ConvertFrom-Json).version
  if (-not $ref -or $stamp -eq $ref) { return }
  $older = $true
  if ($stamp) {
    $sa = $stamp.Split('.'); $ra = $ref.Split('.')
    if ($sa.Count -ge 3 -and $ra.Count -ge 3) {
      $older = $false
      for ($i = 0; $i -lt 3; $i++) { $x = [int]$sa[$i]; $y = [int]$ra[$i]; if ($x -lt $y) { $older = $true; break }; if ($x -gt $y) { break } }
    }
  }
  if ($older) {
    $repoTxt = if ($stamp) { $stamp } else { 'unstamped' }
    [Console]::Error.WriteLine("WARN  Architrave kit assets are stale (repo: $repoTxt, plugin: v$ref) - gates/knowledge won't auto-update.")
    [Console]::Error.WriteLine("      Refresh: pwsh -File `"$(Split-Path $plug.FullName)/tools/update.ps1`" `"$root`"")
  }
}

Write-Host "== Architrave checks (root: $root) =="
Test-JsonFile 'architrave.config.json' 'config   '
Test-JsonFile (Get-Field 'designMap') 'designMap'
Test-JsonFile (Get-Field 'tokens') 'tokens   '

if ($Quick) {
  if ($script:fail -eq 0) { Write-Host 'CHECKS (quick): PASS' } else { Write-Host 'CHECKS (quick): FAIL' }
  exit $script:fail
}

Show-KitDriftNudge

function Invoke-Step($name, $field) {
  $cmd = Get-Field $field
  if ([string]::IsNullOrWhiteSpace($cmd)) { Write-Host "skip  $name (not configured)"; return }
  Write-Host "== $name`: $cmd =="
  $global:LASTEXITCODE = 0
  try { Invoke-Expression $cmd } catch { Write-Host "FAIL  $name ($($_.Exception.Message))"; Show-DependencyHint $cmd; $script:fail = 1; return }
  if ($LASTEXITCODE -ne 0) { Write-Host "FAIL  $name"; Show-DependencyHint $cmd; $script:fail = 1 } else { Write-Host "ok    $name" }
}
function Show-DependencyHint($cmd) {
  $match = [regex]::Match($cmd, 'npm\s+--prefix\s+([^\s]+)\s+run')
  if ($match.Success) {
    $prefix = $match.Groups[1].Value
    if ((Test-Path (Join-Path $prefix 'package.json')) -and -not (Test-Path (Join-Path $prefix 'node_modules'))) {
      [Console]::Error.WriteLine("hint  $prefix/node_modules is missing - run: npm --prefix $prefix ci   (or npm --prefix $prefix install)")
    }
  }
}
Invoke-Step 'generate' 'generate'
Invoke-Step 'build'    'build'
Invoke-Step 'test'     'test'

if ($script:fail -eq 0) { Write-Host 'CHECKS: PASS' } else { Write-Host 'CHECKS: FAIL' }
exit $script:fail
