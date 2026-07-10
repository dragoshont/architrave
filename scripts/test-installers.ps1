#!/usr/bin/env pwsh
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Root
$Tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("architrave-installers-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $Tmp | Out-Null

function Invoke-Installer([string[]]$Arguments) {
  & pwsh -NoProfile -File (Join-Path $Root 'tools/install.ps1') @Arguments *> $null
  return $LASTEXITCODE
}

try {
  $Application = Join-Path $Tmp 'application'; $Knowledge = Join-Path $Tmp 'knowledge'; $Preserved = Join-Path $Tmp 'preserved'
  New-Item -ItemType Directory -Force -Path $Application,$Knowledge,$Preserved | Out-Null
  if ((Invoke-Installer @($Application)) -ne 0) { throw 'default installer failed' }
  $AppConfig = Get-Content (Join-Path $Application 'architrave.config.json') -Raw | ConvertFrom-Json
  if ($AppConfig.platform -ne 'web' -or $AppConfig.stack -ne 'react') { throw 'default application profile changed' }
  Write-Host 'ok    installer default application profile'

  git -C $Knowledge init -q
  if ((Invoke-Installer @($Knowledge, '-Profile', 'knowledge')) -ne 0) { throw 'knowledge installer failed' }
  $Actual = Get-Content (Join-Path $Knowledge 'architrave.config.json') -Raw
  $Expected = Get-Content (Join-Path $Root 'kit/examples/knowledge.architrave.json') -Raw
  if ($Actual -ne $Expected) { throw 'knowledge scaffold differs from canonical example' }
  & npx --yes ajv-cli@5 validate --spec=draft7 -s (Join-Path $Root 'kit/architrave.config.schema.json') -d (Join-Path $Knowledge 'architrave.config.json') *> $null
  if ($LASTEXITCODE -ne 0) { throw 'knowledge scaffold schema validation failed' }
  git -C $Knowledge add .
  Push-Location $Knowledge
  try { ./gates/checks.ps1 *> $null; if ($LASTEXITCODE -ne 0) { throw 'knowledge scaffold gates failed' } } finally { Pop-Location }
  Write-Host 'ok    installer knowledge scaffold validates and passes gates'

  $Before = (Get-FileHash (Join-Path $Knowledge 'architrave.config.json') -Algorithm SHA256).Hash
  if ((Invoke-Installer @($Knowledge, '-Profile', 'knowledge')) -ne 0) { throw 'knowledge reinstall failed' }
  $After = (Get-FileHash (Join-Path $Knowledge 'architrave.config.json') -Algorithm SHA256).Hash
  if ($Before -ne $After) { throw 'installer clobbered existing knowledge config' }
  Write-Host 'ok    installer knowledge profile idempotent'

  '{"sentinel":true}' | Set-Content (Join-Path $Preserved 'architrave.config.json') -Encoding utf8
  if ((Invoke-Installer @($Preserved, '-Profile', 'knowledge')) -ne 0) { throw 'preserve-existing install failed' }
  if (-not (Get-Content (Join-Path $Preserved 'architrave.config.json') -Raw | ConvertFrom-Json).sentinel) { throw 'existing config was clobbered' }
  Write-Host 'ok    installer preserves existing config'

  if ((Invoke-Installer @($Preserved, '-Profile', 'unknown')) -ne 2) { throw 'unknown profile should exit 2' }
  if ((Invoke-Installer @('-Help')) -ne 0) { throw 'installer help failed' }
  Write-Host 'ok    installer help and profile errors'
  Write-Host 'INSTALLERS: PASS'
}
finally { Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue }