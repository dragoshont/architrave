#!/usr/bin/env pwsh
# Smoke tests for PowerShell gate scripts against temporary adopted repos.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Root
$Pwsh = if ($IsWindows) { Join-Path $PSHOME 'pwsh.exe' } else { Join-Path $PSHOME 'pwsh' }
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

  function Invoke-CapturedPwsh([string]$ScriptPath, [string]$WorkingDirectory, [string[]]$Arguments) {
    $StartInfo = [Diagnostics.ProcessStartInfo]::new()
    $StartInfo.FileName = $Pwsh
    $StartInfo.WorkingDirectory = $WorkingDirectory
    $StartInfo.UseShellExecute = $false
    $StartInfo.RedirectStandardOutput = $true
    $StartInfo.RedirectStandardError = $true
    $StartInfo.ArgumentList.Add('-NoProfile')
    $StartInfo.ArgumentList.Add('-File')
    $StartInfo.ArgumentList.Add($ScriptPath)
    foreach ($Argument in $Arguments) { $StartInfo.ArgumentList.Add($Argument) }
    $Process = [Diagnostics.Process]::new()
    $Process.StartInfo = $StartInfo
    [void]$Process.Start()
    $Stdout = $Process.StandardOutput.ReadToEnd()
    $Stderr = $Process.StandardError.ReadToEnd()
    $Process.WaitForExit()
    return [pscustomobject]@{ ExitCode = $Process.ExitCode; Stdout = $Stdout; Stderr = $Stderr }
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
    $HookProcess = Invoke-CapturedPwsh (Join-Path $KnowledgeRepo 'gates/quality-gate.ps1') $KnowledgeRepo @('-HookJson')
    if ($HookProcess.ExitCode -ne 0) { throw 'knowledge hook JSON gate failed' }
    $HookBytes = [Text.Encoding]::UTF8.GetBytes($HookProcess.Stdout)
    $ExpectedHookBytes = [Text.Encoding]::UTF8.GetBytes('{"continue":true}')
    if (-not [Linq.Enumerable]::SequenceEqual([byte[]]$HookBytes, [byte[]]$ExpectedHookBytes)) { throw 'knowledge hook JSON bytes invalid' }
    $HookOutput = $HookProcess.Stdout
    if ($HookProcess.Stderr.Length -ne 0) { throw 'knowledge hook success wrote stderr' }
    $HookValue = $HookOutput | ConvertFrom-Json
    if ($HookValue.continue -ne $true -or @($HookValue.PSObject.Properties).Count -ne 1) { throw 'knowledge hook JSON contract invalid' }

    Set-Content -Path architrave.config.json -Encoding utf8 -Value '{'
    $HookFailProcess = Invoke-CapturedPwsh (Join-Path $KnowledgeRepo 'gates/quality-gate.ps1') $KnowledgeRepo @('-HookJson')
    if ($HookFailProcess.ExitCode -ne 2 -or $HookFailProcess.Stdout.Length -ne 0 -or $HookFailProcess.Stderr -notmatch 'quality-gate: BLOCKING') { throw 'knowledge hook blocking contract invalid' }
    Write-Host 'ok   knowledge-profile-gates'
  } finally { Pop-Location }
}
finally { Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue }
exit 0