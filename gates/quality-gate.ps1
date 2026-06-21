#!/usr/bin/env pwsh
# Architrave — lightweight quick gate (PowerShell / Windows).
# Mirror of gates/quality-gate.sh. Exit 0 = ok to stop, 2 = BLOCKING (invalid JSON).
$ErrorActionPreference = 'Stop'
$dir = Split-Path $MyInvocation.MyCommand.Path -Parent
$checks = Join-Path $dir 'checks.ps1'
$exe = if ($IsWindows) { Join-Path $PSHOME 'pwsh.exe' } else { Join-Path $PSHOME 'pwsh' }
& $exe -NoProfile -File $checks -Quick
if ($LASTEXITCODE -eq 0) {
  Write-Host 'quality-gate: design JSON valid. Before declaring done, confirm: gates/checks.ps1 (generate+build+test) green, gates/reconcile.ps1 reconciled, and an Adversarial Judge PASS.'
  exit 0
} else {
  [Console]::Error.WriteLine('quality-gate: BLOCKING — design map/tokens JSON is invalid. Fix before stopping.')
  exit 2
}
