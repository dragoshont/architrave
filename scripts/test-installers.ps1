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

function Invoke-Updater([string[]]$Arguments) {
  & pwsh -NoProfile -File (Join-Path $Root 'tools/update.ps1') @Arguments *> $null
  return $LASTEXITCODE
}

function Get-TreeSnapshot([string]$Path) {
  $Lines = foreach ($Entry in Get-ChildItem -LiteralPath $Path -Force -Recurse | Sort-Object FullName) {
    $Relative = [IO.Path]::GetRelativePath($Path, $Entry.FullName).Replace('\', '/')
    if (($Entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
      "link $Relative -> $($Entry.LinkTarget)"
    } elseif ($Entry.PSIsContainer) {
      "dir  $Relative"
    } else {
      "file $Relative $((Get-FileHash -LiteralPath $Entry.FullName -Algorithm SHA256).Hash)"
    }
  }
  return ($Lines -join "`n")
}

function Assert-UnchangedFailure([int]$Expected, [string]$Target, [string]$External, [scriptblock]$Action) {
  $TargetBefore = Get-TreeSnapshot $Target
  $ExternalBefore = Get-TreeSnapshot $External
  $Actual = & $Action
  if ($Actual -ne $Expected) { throw "expected exit $Expected, got $Actual" }
  if ((Get-TreeSnapshot $Target) -ne $TargetBefore) { throw 'failed command changed target tree' }
  if ((Get-TreeSnapshot $External) -ne $ExternalBefore) { throw 'failed command changed external sentinel tree' }
}

function New-TestDirectoryLink([string]$Path, [string]$Target) {
  $Type = if ($IsWindows) { 'Junction' } else { 'SymbolicLink' }
  New-Item -ItemType $Type -Path $Path -Target $Target | Out-Null
}

try {
  $Application = Join-Path $Tmp 'application'; $Knowledge = Join-Path $Tmp 'knowledge'; $LegacyKnowledge = Join-Path $Tmp 'legacy-knowledge'; $Preserved = Join-Path $Tmp 'preserved'
  New-Item -ItemType Directory -Force -Path $Application,$Knowledge,$LegacyKnowledge,$Preserved | Out-Null
  if ((Invoke-Installer @($Application)) -ne 0) { throw 'default installer failed' }
  if (Test-Path (Join-Path $Application 'harness/__pycache__')) { throw 'installer copied Python cache files' }
  $AppConfig = Get-Content (Join-Path $Application 'architrave.config.json') -Raw | ConvertFrom-Json
  if ($AppConfig.platform -ne 'web' -or $AppConfig.stack -ne 'react') { throw 'default application profile changed' }
  if (-not (Test-Path (Join-Path $Application '.github/agents/ui-visual.agent.md'))) { throw 'application profile missing UI agents' }
  if (-not (Test-Path (Join-Path $Application '.github/agents/tournament-analyst.agent.md'))) { throw 'application profile missing Tournament Analyst' }
  if (-not (Get-ChildItem (Join-Path $Application 'constitution-*.md') -ErrorAction SilentlyContinue)) { throw 'application profile missing constitutions' }
  if (Test-Path (Join-Path $Application '.codex')) { throw 'default installer created Codex assets' }
  Write-Host 'ok    installer default application profile (full crew + constitutions, no Codex)'

  Remove-Item (Join-Path $Application '.github/agents/ui-visual.agent.md'),(Join-Path $Application 'constitution-apple.md') -Force
  & pwsh -NoProfile -File (Join-Path $Root 'tools/update.ps1') $Application -Agents *> $null
  if ($LASTEXITCODE -ne 0) { throw 'application updater failed' }
  if (Test-Path (Join-Path $Application 'harness/__pycache__')) { throw 'updater copied Python cache files' }
  if (-not (Test-Path (Join-Path $Application '.github/agents/ui-visual.agent.md'))) { throw 'application update did not restore full crew' }
  if (-not (Test-Path (Join-Path $Application 'constitution-apple.md'))) { throw 'application update did not restore constitutions' }
  Write-Host 'ok    updater preserves legacy application full-profile behavior'

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

  foreach ($Agent in 'architrave','adversarial-judge','tournament-analyst','product-research','runtime-observer') {
    if (-not (Test-Path (Join-Path $Knowledge ".github/agents/$Agent.agent.md"))) { throw "knowledge missing $Agent agent" }
  }
  if (@(Get-ChildItem (Join-Path $Knowledge '.github/agents') -Filter '*.agent.md' -File).Count -ne 5) { throw 'knowledge agent count changed' }
  if (Test-Path (Join-Path $Knowledge '.github/agents/ui-visual.agent.md')) { throw 'knowledge should not install UI agents' }
  if (Test-Path (Join-Path $Knowledge '.github/agents/backend-planner.agent.md')) { throw 'knowledge should not install backend agents' }
  if (Get-ChildItem (Join-Path $Knowledge 'constitution-*.md') -ErrorAction SilentlyContinue) { throw 'knowledge should not install constitutions' }
  if (-not ((Get-Content (Join-Path $Knowledge '.gitignore')) -contains '.architrave/runs/')) { throw 'knowledge should ignore .architrave/runs/' }
  if (-not ((Get-Content (Join-Path $Knowledge '.gitignore')) -contains '.architrave/worktrees/')) { throw 'knowledge should ignore .architrave/worktrees/' }
  if (-not ((Get-Content (Join-Path $Knowledge '.gitignore')) -contains '.architrave/runtime.key')) { throw 'knowledge should ignore .architrave/runtime.key' }
  Write-Host 'ok    installer knowledge profile is lean (five-agent crew, no constitutions, runs/worktrees ignored)'

  $Before = (Get-FileHash (Join-Path $Knowledge 'architrave.config.json') -Algorithm SHA256).Hash
  if ((Invoke-Installer @($Knowledge, '-Profile', 'knowledge')) -ne 0) { throw 'knowledge reinstall failed' }
  $After = (Get-FileHash (Join-Path $Knowledge 'architrave.config.json') -Algorithm SHA256).Hash
  if ($Before -ne $After) { throw 'installer clobbered existing knowledge config' }
  if (@(Get-Content (Join-Path $Knowledge '.gitignore') | Where-Object { $_ -eq '.architrave/runs/' }).Count -ne 1) { throw 'installer duplicated .architrave/runs/ rule' }
  if (@(Get-Content (Join-Path $Knowledge '.gitignore') | Where-Object { $_ -eq '.architrave/worktrees/' }).Count -ne 1) { throw 'installer duplicated .architrave/worktrees/ rule' }
  if (@(Get-Content (Join-Path $Knowledge '.gitignore') | Where-Object { $_ -eq '.architrave/runtime.key' }).Count -ne 1) { throw 'installer duplicated .architrave/runtime.key rule' }
  Write-Host 'ok    installer knowledge profile idempotent'

  & pwsh -NoProfile -File (Join-Path $Root 'tools/update.ps1') $Knowledge -Agents *> $null
  if ($LASTEXITCODE -ne 0) { throw 'knowledge updater failed' }
  $UpdateDiff = (& git -C $Knowledge diff --check *>&1 | Out-String)
  if ($LASTEXITCODE -ne 0) { throw "knowledge updater produced whitespace errors:`n$UpdateDiff" }
  $ActiveHook = Get-Content (Join-Path $Knowledge '.github/hooks/design-guard.json') -Raw
  $WindowsHook = Get-Content (Join-Path $Root 'gates/hooks/design-guard.windows.json') -Raw
  if ($ActiveHook -ne $WindowsHook) { throw 'updater did not refresh active Windows hook' }
  if (Test-Path (Join-Path $Knowledge '.github/agents/ui-visual.agent.md')) { throw 'updater re-bloated knowledge repo' }
  Write-Host 'ok    updater refreshes active Windows hook and keeps knowledge repo lean'

  $Codex = Join-Path $Tmp 'codex'
  New-Item -ItemType Directory -Force -Path $Codex | Out-Null
  if ((Invoke-Installer @($Codex, '-Profile', 'knowledge', '-Codex')) -ne 0) { throw 'Codex installer failed' }
  $RoleFiles = @(Get-ChildItem (Join-Path $Codex '.codex/agents') -Filter '*.toml' -File)
  if ($RoleFiles.Count -ne 2) { throw 'Codex role count changed' }
  if (-not (Test-Path (Join-Path $Codex '.codex/config.toml'))) { throw 'Codex config missing' }
  if (Test-Path (Join-Path $Codex '.agents/skills')) { throw 'installer copied plugin skills into project' }
  $BeforeRoles = ($RoleFiles + @(Get-Item (Join-Path $Codex '.codex/config.toml')) | Sort-Object FullName | ForEach-Object { (Get-FileHash $_.FullName -Algorithm SHA256).Hash }) -join ':'
  & pwsh -NoProfile -File (Join-Path $Root 'tools/update.ps1') $Codex -Codex *> $null
  if ($LASTEXITCODE -ne 0) { throw 'Codex updater failed' }
  $AfterFiles = @(Get-ChildItem (Join-Path $Codex '.codex/agents') -Filter '*.toml' -File) + @(Get-Item (Join-Path $Codex '.codex/config.toml'))
  $AfterRoles = ($AfterFiles | Sort-Object FullName | ForEach-Object { (Get-FileHash $_.FullName -Algorithm SHA256).Hash }) -join ':'
  if ($BeforeRoles -ne $AfterRoles) { throw 'Codex update is not idempotent' }
  Write-Host 'ok    PowerShell Codex roles install/update without project skills'

  $Collision = Join-Path $Tmp 'codex-collision'
  New-Item -ItemType Directory -Force -Path (Join-Path $Collision '.codex') | Out-Null
  "[agents.architrave_judge]`ndescription = `"user-owned`"`n" | Set-Content (Join-Path $Collision '.codex/config.toml') -Encoding utf8 -NoNewline
  $CollisionBefore = (Get-FileHash (Join-Path $Collision '.codex/config.toml') -Algorithm SHA256).Hash
  if ((Invoke-Installer @($Collision, '-Profile', 'knowledge', '-Codex')) -ne 2) { throw 'Codex collision should exit 2' }
  $CollisionAfter = (Get-FileHash (Join-Path $Collision '.codex/config.toml') -Algorithm SHA256).Hash
  if ($CollisionBefore -ne $CollisionAfter) { throw 'Codex collision changed config' }
  if (Test-Path (Join-Path $Collision 'architrave.config.json')) { throw 'Codex collision wrote default assets before preflight' }
  Write-Host 'ok    PowerShell Codex collision fails before writes'

  if ((Invoke-Installer @($LegacyKnowledge, '-Codex')) -ne 0) { throw 'legacy application Codex installer failed' }
  $LegacyConfigPath = Join-Path $LegacyKnowledge 'architrave.config.json'
  $LegacyConfig = Get-Content $LegacyConfigPath -Raw | ConvertFrom-Json
  $LegacyConfig | Add-Member -NotePropertyName kind -NotePropertyValue knowledge
  $LegacyConfig | ConvertTo-Json -Depth 20 | Set-Content $LegacyConfigPath -Encoding utf8
  'custom agent' | Set-Content (Join-Path $LegacyKnowledge '.github/agents/custom.agent.md') -Encoding utf8
  '*.local' | Set-Content (Join-Path $LegacyKnowledge '.gitignore') -Encoding utf8
  & pwsh -NoProfile -File (Join-Path $Root 'tools/update.ps1') $LegacyKnowledge -Codex *> $null
  if ($LASTEXITCODE -ne 0) { throw 'legacy knowledge Codex update failed without agent refresh' }
  if (-not (Test-Path (Join-Path $LegacyKnowledge '.github/agents/ui-visual.agent.md'))) { throw 'updater pruned agents without -Agents' }
  if (-not (Test-Path (Join-Path $LegacyKnowledge '.github/agents/custom.agent.md'))) { throw 'updater removed custom agent' }
  if (Get-ChildItem (Join-Path $LegacyKnowledge 'constitution-*.md') -ErrorAction SilentlyContinue) { throw 'updater left legacy constitutions' }
  $LegacyIgnore = Get-Content (Join-Path $LegacyKnowledge '.gitignore')
  if ($LegacyIgnore -notcontains '*.local') { throw 'updater changed unrelated ignore content' }
  if (@($LegacyIgnore | Where-Object { $_ -eq '.architrave/runs/' }).Count -ne 1) { throw 'updater should add one runs ignore rule' }
  if (@($LegacyIgnore | Where-Object { $_ -eq '.architrave/worktrees/' }).Count -ne 1) { throw 'updater should add one worktrees ignore rule' }
  & pwsh -NoProfile -File (Join-Path $Root 'tools/update.ps1') $LegacyKnowledge -Agents -Codex *> $null
  if ($LASTEXITCODE -ne 0) { throw 'legacy knowledge Codex agent refresh failed' }
  foreach ($Agent in 'architrave','adversarial-judge','tournament-analyst','product-research','runtime-observer') {
    if (-not (Test-Path (Join-Path $LegacyKnowledge ".github/agents/$Agent.agent.md"))) { throw "migrated knowledge missing $Agent agent" }
  }
  if (@(Get-ChildItem (Join-Path $LegacyKnowledge '.github/agents') -Filter '*.agent.md' -File).Count -ne 6) { throw 'migrated knowledge should contain five managed agents plus custom agent' }
  if (Test-Path (Join-Path $LegacyKnowledge '.github/agents/ui-visual.agent.md')) { throw 'updater left legacy UI agent' }
  if (Test-Path (Join-Path $LegacyKnowledge '.github/agents/backend-planner.agent.md')) { throw 'updater left legacy backend agent' }
  if (-not (Test-Path (Join-Path $LegacyKnowledge '.github/agents/custom.agent.md'))) { throw 'updater removed custom agent during refresh' }
  if (@(Get-ChildItem (Join-Path $LegacyKnowledge '.codex/agents') -Filter '*.toml' -File).Count -ne 2) { throw 'migration changed Codex role count' }
  Write-Host 'ok    Codex update migrates legacy knowledge repo and preserves custom assets'

  $PathAgents = Join-Path $Tmp 'path-agents'; $ExternalAgents = Join-Path $Tmp 'external-agents'
  New-Item -ItemType Directory -Force -Path (Join-Path $PathAgents '.github'),$ExternalAgents | Out-Null
  '{"kind":"knowledge","build":"true","test":"true"}' | Set-Content (Join-Path $PathAgents 'architrave.config.json') -Encoding utf8
  'outside agent sentinel' | Set-Content (Join-Path $ExternalAgents 'ui-visual.agent.md') -Encoding utf8
  New-TestDirectoryLink (Join-Path $PathAgents '.github/agents') $ExternalAgents
  Assert-UnchangedFailure 1 $PathAgents $ExternalAgents { Invoke-Updater @($PathAgents, '-Agents') }

  $PathKnowledge = Join-Path $Tmp 'path-knowledge'; $ExternalKnowledge = Join-Path $Tmp 'external-knowledge'
  New-Item -ItemType Directory -Force -Path $PathKnowledge,$ExternalKnowledge | Out-Null
  'outside knowledge sentinel' | Set-Content (Join-Path $ExternalKnowledge 'sentinel.md') -Encoding utf8
  New-TestDirectoryLink (Join-Path $PathKnowledge 'knowledge') $ExternalKnowledge
  Assert-UnchangedFailure 1 $PathKnowledge $ExternalKnowledge { Invoke-Installer @($PathKnowledge, '-Profile', 'knowledge') }

  $PathHarness = Join-Path $Tmp 'path-harness'; $ExternalHarness = Join-Path $Tmp 'external-harness'
  New-Item -ItemType Directory -Force -Path (Join-Path $PathHarness 'harness'),$ExternalHarness | Out-Null
  '{"kind":"knowledge","build":"true","test":"true"}' | Set-Content (Join-Path $PathHarness 'architrave.config.json') -Encoding utf8
  'outside harness sentinel' | Set-Content (Join-Path $ExternalHarness 'sentinel.json') -Encoding utf8
  New-TestDirectoryLink (Join-Path $PathHarness 'harness/schemas') $ExternalHarness
  Assert-UnchangedFailure 1 $PathHarness $ExternalHarness { Invoke-Updater @($PathHarness) }

  $PathIgnore = Join-Path $Tmp 'path-ignore'; $ExternalIgnore = Join-Path $Tmp 'external-ignore'
  New-Item -ItemType Directory -Force -Path $PathIgnore,$ExternalIgnore | Out-Null
  'outside ignore sentinel' | Set-Content (Join-Path $ExternalIgnore 'gitignore') -Encoding utf8
  $FileLinkCreated = $true
  try { New-Item -ItemType SymbolicLink -Path (Join-Path $PathIgnore '.gitignore') -Target (Join-Path $ExternalIgnore 'gitignore') -ErrorAction Stop | Out-Null } catch { $FileLinkCreated = $false }
  if ($FileLinkCreated) {
    Assert-UnchangedFailure 1 $PathIgnore $ExternalIgnore { Invoke-Installer @($PathIgnore, '-Profile', 'knowledge') }
  }
  Write-Host 'ok    PowerShell managed paths reject external directory and supported file links without writes'

  . (Join-Path $Root 'tools/ManagedPaths.ps1')
  $PathSyntax = Join-Path $Tmp 'path-syntax'; New-Item -ItemType Directory -Path $PathSyntax | Out-Null
  Initialize-ManagedPaths $PathSyntax test
  foreach ($UnsafePath in '../escape','/absolute') {
    $Rejected = $false
    try { New-ManagedDirectory $UnsafePath } catch { $Rejected = $true }
    if (-not $Rejected) { throw "managed path helper accepted unsafe path: $UnsafePath" }
  }
  if (Test-Path (Join-Path $Tmp 'escape')) { throw 'managed path helper created an escaping directory' }
  Write-Host 'ok    PowerShell managed paths reject absolute and escaping relative paths'

  $PathUnicode = Join-Path $Tmp 'path-unicode'; New-Item -ItemType Directory -Path $PathUnicode | Out-Null
  $UnicodeSource = Join-Path $Tmp 'unicode-source'; 'unicode sentinel' | Set-Content $UnicodeSource -Encoding utf8
  Initialize-ManagedPaths $PathUnicode test
  New-ManagedDirectory 'unicodé'
  Copy-ManagedFile $UnicodeSource 'unicodé/naïve.md'
  if ((Get-Content (Join-Path $PathUnicode 'unicodé/naïve.md') -Raw).Trim() -ne 'unicode sentinel') { throw 'managed path helper did not preserve Unicode path content' }
  Write-Host 'ok    PowerShell managed paths support Unicode directory and file names'

  if (-not $IsWindows) {
    $PathFifo = Join-Path $Tmp 'path-fifo'; New-Item -ItemType Directory -Path $PathFifo | Out-Null
    & mkfifo (Join-Path $PathFifo '.gitignore')
    if ($LASTEXITCODE -ne 0) { throw 'failed to create FIFO fixture' }
    if ((Invoke-Installer @($PathFifo, '-Profile', 'knowledge')) -ne 1) { throw 'installer should reject FIFO managed file' }
    if (-not (Test-Path (Join-Path $PathFifo '.gitignore'))) { throw 'installer removed FIFO fixture' }
    if (Test-ManagedRegularFile '/dev/null') { throw 'managed path helper accepted Unix device node as a regular file' }
  }
  Write-Host 'ok    PowerShell managed files reject FIFO and device-node entry types'

  $HardlinkIgnore = Join-Path $Tmp 'hardlink-ignore'; $ExternalHardlink = Join-Path $Tmp 'external-hardlink'
  New-Item -ItemType Directory -Force -Path $HardlinkIgnore | Out-Null
  'outside hard-link sentinel' | Set-Content $ExternalHardlink -Encoding utf8
  New-Item -ItemType HardLink -Path (Join-Path $HardlinkIgnore '.gitignore') -Target $ExternalHardlink | Out-Null
  $ExternalBefore = (Get-FileHash -LiteralPath $ExternalHardlink -Algorithm SHA256).Hash
  if ((Invoke-Installer @($HardlinkIgnore, '-Profile', 'knowledge')) -ne 0) { throw 'hard-link-safe install failed' }
  $ExternalAfter = (Get-FileHash -LiteralPath $ExternalHardlink -Algorithm SHA256).Hash
  if ($ExternalBefore -ne $ExternalAfter) { throw 'installer modified external hard-linked file' }
  if (-not ((Get-Content (Join-Path $HardlinkIgnore '.gitignore')) -contains '.architrave/runs/')) { throw 'installer did not replace target hard link safely' }
  Write-Host 'ok    PowerShell managed file replacement does not mutate external hard links'

  $MalformedConfig = Join-Path $Tmp 'malformed-config'; $MalformedExternal = Join-Path $Tmp 'malformed-external'; $NonObjectConfig = Join-Path $Tmp 'nonobject-config'; $NonObjectExternal = Join-Path $Tmp 'nonobject-external'; $DuplicateKind = Join-Path $Tmp 'duplicate-kind'; $DuplicateExternal = Join-Path $Tmp 'duplicate-external'; $CaseKind = Join-Path $Tmp 'case-kind'; $CaseExternal = Join-Path $Tmp 'case-external'
  $UnsupportedKind = Join-Path $Tmp 'unsupported-kind'; $UnsupportedExternal = Join-Path $Tmp 'unsupported-external'
  New-Item -ItemType Directory -Force -Path $MalformedConfig,$MalformedExternal,$NonObjectConfig,$NonObjectExternal,$DuplicateKind,$DuplicateExternal,$CaseKind,$CaseExternal,$UnsupportedKind,$UnsupportedExternal | Out-Null
  '{"kind":' | Set-Content (Join-Path $MalformedConfig 'architrave.config.json') -Encoding utf8
  'malformed sentinel' | Set-Content (Join-Path $MalformedExternal 'sentinel') -Encoding utf8
  Assert-UnchangedFailure 2 $MalformedConfig $MalformedExternal { Invoke-Updater @($MalformedConfig) }
  '[]' | Set-Content (Join-Path $NonObjectConfig 'architrave.config.json') -Encoding utf8
  'nonobject sentinel' | Set-Content (Join-Path $NonObjectExternal 'sentinel') -Encoding utf8
  Assert-UnchangedFailure 2 $NonObjectConfig $NonObjectExternal { Invoke-Updater @($NonObjectConfig) }
  '{"kind":"application","kind":"knowledge","build":"true","test":"true"}' | Set-Content (Join-Path $DuplicateKind 'architrave.config.json') -Encoding utf8
  'duplicate sentinel' | Set-Content (Join-Path $DuplicateExternal 'sentinel') -Encoding utf8
  Assert-UnchangedFailure 2 $DuplicateKind $DuplicateExternal { Invoke-Updater @($DuplicateKind) }
  '{"Kind":"knowledge","build":"true","test":"true"}' | Set-Content (Join-Path $CaseKind 'architrave.config.json') -Encoding utf8
  'case sentinel' | Set-Content (Join-Path $CaseExternal 'sentinel') -Encoding utf8
  Assert-UnchangedFailure 2 $CaseKind $CaseExternal { Invoke-Updater @($CaseKind) }
  '{"kind":"application","build":"true","test":"true"}' | Set-Content (Join-Path $UnsupportedKind 'architrave.config.json') -Encoding utf8
  'unsupported sentinel' | Set-Content (Join-Path $UnsupportedExternal 'sentinel') -Encoding utf8
  Assert-UnchangedFailure 2 $UnsupportedKind $UnsupportedExternal { Invoke-Updater @($UnsupportedKind) }
  Write-Host 'ok    PowerShell updater rejects malformed/non-object JSON and ambiguous/unsupported kind before writes'

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