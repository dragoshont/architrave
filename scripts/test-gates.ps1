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
}
finally { Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue }
exit 0