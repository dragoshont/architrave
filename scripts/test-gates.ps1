#!/usr/bin/env pwsh
# Smoke tests for PowerShell gate scripts against temporary adopted repos.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Root
$Tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("architrave-gates-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $Tmp | Out-Null
try {
  function Make-Repo([string]$Repo) {
    New-Item -ItemType Directory -Force -Path (Join-Path $Repo 'gates'),(Join-Path $Repo 'harness'),(Join-Path $Repo 'knowledge') | Out-Null
    Copy-Item gates/*.ps1 -Destination (Join-Path $Repo 'gates')
    Copy-Item gates/rubric.md -Destination (Join-Path $Repo 'gates')
    Copy-Item harness/*.ps1 -Destination (Join-Path $Repo 'harness')
    Set-Content -Path (Join-Path $Repo 'architrave.config.json') -Encoding utf8 -Value @'
{
  "platform": "web",
  "stack": "react",
  "designSource": { "type": "design-doc", "path": "README.md" },
  "applyTo": ["src/**"],
  "build": "pwsh -NoProfile -Command \"Write-Output build-ok\"",
  "test": "pwsh -NoProfile -Command \"Write-Output test-ok\""
}
'@
  }

  function Expect-Code([string]$Name, [string]$Repo, [scriptblock]$Command, [int]$Expected) {
    Push-Location $Repo
    try { & $Command *> $null; $Code = $LASTEXITCODE } finally { Pop-Location }
    if ($Code -eq $Expected) { Write-Host "ok   $Name" } else { Write-Error "FAIL $Name expected exit $Expected got $Code"; exit 1 }
  }

  $Repo = Join-Path $Tmp 'repo'; Make-Repo $Repo
  Expect-Code 'checks-quick' $Repo { ./gates/checks.ps1 -Quick } 0
  Expect-Code 'checks-full' $Repo { ./gates/checks.ps1 } 0
  Expect-Code 'quality-gate' $Repo { ./gates/quality-gate.ps1 } 0
  Expect-Code 'reconcile-skip' $Repo { ./gates/reconcile.ps1 } 0
  Expect-Code 'backend-checks-skip' $Repo { ./gates/backend-checks.ps1 } 0

  $KnowledgeRepo = Join-Path $Tmp 'knowledge'; Make-Repo $KnowledgeRepo
  Set-Content -Path (Join-Path $KnowledgeRepo 'architrave.config.json') -Encoding utf8 -Value @'
{
  "kind": "knowledge",
  "build": "Set-Content -Path build.ran -Value build",
  "test": "Set-Content -Path test.ran -Value test"
}
'@
  Push-Location $KnowledgeRepo
  try {
    $QuickOutput = (& ./gates/checks.ps1 -Quick *>&1 | Out-String)
    if ($LASTEXITCODE -ne 0 -or $QuickOutput -notmatch 'profile knowledge: UI design JSON validation not applicable') { throw 'knowledge quick gate failed' }
    & ./gates/checks.ps1 *> $null
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path build.ran) -or -not (Test-Path test.ran)) { throw 'knowledge full gate did not execute build/test' }
    $ReconcileOutput = (& ./gates/reconcile.ps1 *>&1 | Out-String)
    if ($LASTEXITCODE -ne 0 -or $ReconcileOutput -notmatch 'UI design reconciliation not applicable for knowledge profile') { throw 'knowledge reconcile message failed' }
    $QualityOutput = (& ./gates/quality-gate.ps1 *>&1 | Out-String)
    if ($LASTEXITCODE -ne 0 -or $QualityOutput -notmatch 'knowledge profile config valid') { throw 'knowledge quality gate failed' }
    Write-Host 'ok   knowledge-profile-gates'
  } finally { Pop-Location }
}
finally { Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue }
exit 0