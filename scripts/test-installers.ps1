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
  $Application = Join-Path $Tmp 'application'; $Knowledge = Join-Path $Tmp 'knowledge'; $LegacyKnowledge = Join-Path $Tmp 'legacy-knowledge'; $Preserved = Join-Path $Tmp 'preserved'
  New-Item -ItemType Directory -Force -Path $Application,$Knowledge,$LegacyKnowledge,$Preserved | Out-Null
  if ((Invoke-Installer @($Application)) -ne 0) { throw 'default installer failed' }
  $AppConfig = Get-Content (Join-Path $Application 'architrave.config.json') -Raw | ConvertFrom-Json
  if ($AppConfig.platform -ne 'web' -or $AppConfig.stack -ne 'react') { throw 'default application profile changed' }
  if (-not (Test-Path (Join-Path $Application '.github/agents/ui-visual.agent.md'))) { throw 'application profile missing UI agents' }
  if (-not (Test-Path (Join-Path $Application '.github/agents/backend-planner.agent.md'))) { throw 'application profile missing backend agents' }
  if (-not (Get-ChildItem (Join-Path $Application 'constitution-*.md') -ErrorAction SilentlyContinue)) { throw 'application profile missing constitutions' }
  Write-Host 'ok    installer default application profile (full crew + constitutions)'

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

  if (-not (Test-Path (Join-Path $Knowledge '.github/agents/architrave.agent.md'))) { throw 'knowledge missing orchestrator agent' }
  if (-not (Test-Path (Join-Path $Knowledge '.github/agents/adversarial-judge.agent.md'))) { throw 'knowledge missing judge agent' }
  if (Test-Path (Join-Path $Knowledge '.github/agents/ui-visual.agent.md')) { throw 'knowledge should not install UI agents' }
  if (Test-Path (Join-Path $Knowledge '.github/agents/backend-planner.agent.md')) { throw 'knowledge should not install backend agents' }
  if (Get-ChildItem (Join-Path $Knowledge 'constitution-*.md') -ErrorAction SilentlyContinue) { throw 'knowledge should not install constitutions' }
  if (-not ((Get-Content (Join-Path $Knowledge '.gitignore')) -contains '.architrave/runs/')) { throw 'knowledge should gitignore .architrave/runs/' }
  Write-Host 'ok    installer knowledge profile is lean (crew trimmed, no constitutions, runs ignored)'

  $Before = (Get-FileHash (Join-Path $Knowledge 'architrave.config.json') -Algorithm SHA256).Hash
  if ((Invoke-Installer @($Knowledge, '-Profile', 'knowledge')) -ne 0) { throw 'knowledge reinstall failed' }
  $After = (Get-FileHash (Join-Path $Knowledge 'architrave.config.json') -Algorithm SHA256).Hash
  if ($Before -ne $After) { throw 'installer clobbered existing knowledge config' }
  if (@(Get-Content (Join-Path $Knowledge '.gitignore') | Where-Object { $_ -eq '.architrave/runs/' }).Count -ne 1) { throw 'installer should keep one .architrave/runs/ ignore rule' }
  Write-Host 'ok    installer knowledge profile idempotent'

  & pwsh -NoProfile -File (Join-Path $Root 'tools/update.ps1') $Knowledge -Agents *> $null
  if ($LASTEXITCODE -ne 0) { throw 'knowledge updater failed' }
  $UpdateDiff = (& git -C $Knowledge diff --check *>&1 | Out-String)
  if ($LASTEXITCODE -ne 0) { throw "knowledge updater produced whitespace errors:`n$UpdateDiff" }
  $ActiveHook = Get-Content (Join-Path $Knowledge '.github/hooks/design-guard.json') -Raw
  $WindowsHook = Get-Content (Join-Path $Root 'gates/hooks/design-guard.windows.json') -Raw
  if ($ActiveHook -ne $WindowsHook) { throw 'updater did not refresh active Windows hook' }
  if (Test-Path (Join-Path $Knowledge '.github/agents/ui-visual.agent.md')) { throw 'updater -Agents re-bloated knowledge repo with UI agents' }
  Write-Host 'ok    updater refreshes active Windows hook, keeps repo lean and whitespace-clean'

  if ((Invoke-Installer @($LegacyKnowledge)) -ne 0) { throw 'legacy application installer failed' }
  $LegacyConfigPath = Join-Path $LegacyKnowledge 'architrave.config.json'
  $LegacyConfig = Get-Content $LegacyConfigPath -Raw | ConvertFrom-Json
  $LegacyConfig | Add-Member -NotePropertyName kind -NotePropertyValue knowledge
  $LegacyConfig | ConvertTo-Json -Depth 20 | Set-Content $LegacyConfigPath -Encoding utf8
  'custom agent' | Set-Content (Join-Path $LegacyKnowledge '.github/agents/custom.agent.md') -Encoding utf8
  '*.local' | Set-Content (Join-Path $LegacyKnowledge '.gitignore') -Encoding utf8
  & pwsh -NoProfile -File (Join-Path $Root 'tools/update.ps1') $LegacyKnowledge *> $null
  if ($LASTEXITCODE -ne 0) { throw 'legacy knowledge updater failed without agent refresh' }
  if (-not (Test-Path (Join-Path $LegacyKnowledge '.github/agents/ui-visual.agent.md'))) { throw 'updater pruned agents without -Agents' }
  if (-not (Test-Path (Join-Path $LegacyKnowledge '.github/agents/custom.agent.md'))) { throw 'updater removed custom agent' }
  if (Get-ChildItem (Join-Path $LegacyKnowledge 'constitution-*.md') -ErrorAction SilentlyContinue) { throw 'updater left legacy constitutions in knowledge repo' }
  $LegacyIgnore = Get-Content (Join-Path $LegacyKnowledge '.gitignore')
  if (@($LegacyIgnore | Where-Object { $_ -eq '.architrave/runs/' }).Count -ne 1) { throw 'updater should keep one .architrave/runs/ ignore rule' }
  if ($LegacyIgnore -notcontains '*.local') { throw 'updater changed unrelated .gitignore content' }
  & pwsh -NoProfile -File (Join-Path $Root 'tools/update.ps1') $LegacyKnowledge -Agents *> $null
  if ($LASTEXITCODE -ne 0) { throw 'legacy knowledge agent refresh failed' }
  if (Test-Path (Join-Path $LegacyKnowledge '.github/agents/ui-visual.agent.md')) { throw 'updater left legacy UI agent in knowledge repo' }
  if (Test-Path (Join-Path $LegacyKnowledge '.github/agents/backend-planner.agent.md')) { throw 'updater left legacy backend agent in knowledge repo' }
  if (-not (Test-Path (Join-Path $LegacyKnowledge '.github/agents/custom.agent.md'))) { throw 'updater removed custom agent' }
  $LegacyIgnore = Get-Content (Join-Path $LegacyKnowledge '.gitignore')
  if (@($LegacyIgnore | Where-Object { $_ -eq '.architrave/runs/' }).Count -ne 1) { throw 'updater should keep one .architrave/runs/ ignore rule' }
  Write-Host 'ok    updater migrates legacy knowledge repo and preserves custom files'

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