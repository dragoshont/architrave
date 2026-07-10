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
  $InstalledHook = Get-Content (Join-Path $Knowledge '.github/hooks/design-guard.json') -Raw
  $ExpectedInstalledHook = Get-Content (Join-Path $Root 'gates/hooks/design-guard.windows.json') -Raw
  if ($InstalledHook -ne $ExpectedInstalledHook) { throw 'installer did not create active Windows hook' }
  & npx --yes ajv-cli@5 validate --spec=draft7 -s (Join-Path $Root 'kit/architrave.config.schema.json') -d (Join-Path $Knowledge 'architrave.config.json') *> $null
  if ($LASTEXITCODE -ne 0) { throw 'knowledge scaffold schema validation failed' }
  git -C $Knowledge add .
  $DiffOutput = (& git -C $Knowledge diff --check --cached *>&1 | Out-String)
  if ($LASTEXITCODE -ne 0) { throw "knowledge scaffold staged diff failed:`n$DiffOutput" }
  Push-Location $Knowledge
  try {
    $GateOutput = (& ./gates/checks.ps1 *>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) { throw "knowledge scaffold gates failed:`n$GateOutput" }
  } finally { Pop-Location }
  Write-Host 'ok    installer knowledge scaffold validates and passes gates'

  $Before = (Get-FileHash (Join-Path $Knowledge 'architrave.config.json') -Algorithm SHA256).Hash
  if ((Invoke-Installer @($Knowledge, '-Profile', 'knowledge')) -ne 0) { throw 'knowledge reinstall failed' }
  $After = (Get-FileHash (Join-Path $Knowledge 'architrave.config.json') -Algorithm SHA256).Hash
  if ($Before -ne $After) { throw 'installer clobbered existing knowledge config' }
  Write-Host 'ok    installer knowledge profile idempotent'

  & pwsh -NoProfile -File (Join-Path $Root 'tools/update.ps1') $Knowledge -Agents *> $null
  if ($LASTEXITCODE -ne 0) { throw 'knowledge updater failed' }
  $UpdateDiff = (& git -C $Knowledge diff --check *>&1 | Out-String)
  if ($LASTEXITCODE -ne 0) { throw "knowledge updater produced whitespace errors:`n$UpdateDiff" }
  $ActiveHook = Get-Content (Join-Path $Knowledge '.github/hooks/design-guard.json') -Raw
  $WindowsHook = Get-Content (Join-Path $Root 'gates/hooks/design-guard.windows.json') -Raw
  if ($ActiveHook -ne $WindowsHook) { throw 'updater did not refresh active Windows hook' }
  Write-Host 'ok    updater refreshes active Windows hook and remains whitespace-clean'

  $UpdateFailure = Join-Path $Tmp 'update-failure'
  New-Item -ItemType Directory -Force -Path (Join-Path $UpdateFailure '.github') | Out-Null
  '{"kind":"knowledge","build":"true","test":"true"}' | Set-Content (Join-Path $UpdateFailure 'architrave.config.json') -Encoding utf8
  'not-a-directory' | Set-Content (Join-Path $UpdateFailure '.github/hooks') -Encoding utf8
  & pwsh -NoProfile -File (Join-Path $Root 'tools/update.ps1') $UpdateFailure *> $null
  if ($LASTEXITCODE -eq 0) { throw 'updater hook delivery should fail closed' }
  Write-Host 'ok    updater hook delivery fails closed'

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