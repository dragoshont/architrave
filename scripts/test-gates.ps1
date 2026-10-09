#!/usr/bin/env pwsh
# Smoke tests for PowerShell gate scripts against temporary adopted repos.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Root
$PowerShellHost = (Get-Process -Id $PID).Path
$Tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("architrave-gates-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $Tmp | Out-Null
try {
  function Make-Repo([string]$Repo) {
    New-Item -ItemType Directory -Force -Path (Join-Path $Repo 'gates'),(Join-Path $Repo 'harness'),(Join-Path $Repo 'knowledge') | Out-Null
    Copy-Item gates/*.ps1 -Destination (Join-Path $Repo 'gates')
    Copy-Item gates/gate_runner.py -Destination (Join-Path $Repo 'gates')
    Copy-Item gates/rubric.md -Destination (Join-Path $Repo 'gates')
    Copy-Item harness/*.ps1 -Destination (Join-Path $Repo 'harness')
    Copy-Item harness/platform_launch.py -Destination (Join-Path $Repo 'harness')
    [ordered]@{
      platform = 'web'
      stack = 'react'
      designSource = [ordered]@{ type = 'design-doc'; path = 'README.md' }
      applyTo = @('src/**')
      build = "& '$PowerShellHost' -NoProfile -Command `"Write-Output build-ok`""
      test = "& '$PowerShellHost' -NoProfile -Command `"Write-Output test-ok`""
    } | ConvertTo-Json -Depth 5 | Set-Content -Path (Join-Path $Repo 'architrave.config.json') -Encoding utf8
  }

  function Expect-Code([string]$Name, [string]$Repo, [scriptblock]$Command, [int]$Expected) {
    Push-Location $Repo
    try { & $Command *> $null; $Code = $LASTEXITCODE } finally { Pop-Location }
    if ($Code -eq $Expected) { Write-Host "ok   $Name" } else { Write-Error "FAIL $Name expected exit $Expected got $Code"; exit 1 }
  }

  function Invoke-CapturedPwsh([string]$ScriptPath, [string]$WorkingDirectory, [string[]]$Arguments) {
    function Quote-NativeArgument([string]$Value) {
      if ($Value -notmatch '[\s"]') { return $Value }
      $Escaped = [regex]::Replace($Value, '(\\*)"', '$1$1\"')
      $Escaped = [regex]::Replace($Escaped, '(\\+)$', '$1$1')
      return '"' + $Escaped + '"'
    }
    $StartInfo = New-Object Diagnostics.ProcessStartInfo
    $StartInfo.FileName = $PowerShellHost
    $StartInfo.WorkingDirectory = $WorkingDirectory
    $StartInfo.UseShellExecute = $false
    $StartInfo.RedirectStandardOutput = $true
    $StartInfo.RedirectStandardError = $true
    $NativeArguments = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $ScriptPath) + $Arguments
    $QuotedArguments = @($NativeArguments | ForEach-Object { Quote-NativeArgument -Value ([string]$_) })
    $StartInfo.Arguments = $QuotedArguments -join ' '
    $Process = New-Object Diagnostics.Process
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

  $InvalidDesign = Join-Path $Tmp 'invalid-design'; Make-Repo $InvalidDesign
  Set-Content -Path (Join-Path $InvalidDesign 'design.json') -Encoding utf8 -Value '{'
  $InvalidConfig = Get-Content (Join-Path $InvalidDesign 'architrave.config.json') -Raw | ConvertFrom-Json
  $InvalidConfig.designSource.path = 'design.json'
  $InvalidConfig | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $InvalidDesign 'architrave.config.json') -Encoding utf8
  Expect-Code 'checks-invalid-design-json' $InvalidDesign { ./gates/checks.ps1 -Quick } 1

  $CopyRepo = Join-Path $Tmp 'product-copy'; Make-Repo $CopyRepo
  New-Item -ItemType Directory -Force -Path (Join-Path $CopyRepo 'strings') | Out-Null
  Set-Content -Path (Join-Path $CopyRepo 'strings/en.json') -Encoding utf8 -Value '{"signIn": "Sign in with Microsoft"}'
  $CopyConfig = Get-Content (Join-Path $CopyRepo 'architrave.config.json') -Raw | ConvertFrom-Json
  $CopyConfig | Add-Member -NotePropertyName productCopy -NotePropertyValue ([ordered]@{ paths = @('strings/*.json') })
  $CopyConfig | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $CopyRepo 'architrave.config.json') -Encoding utf8
  Expect-Code 'product-copy-clean' $CopyRepo { ./gates/checks.ps1 -Quick } 0
  Set-Content -Path (Join-Path $CopyRepo 'strings/en.json') -Encoding utf8 -Value '{"status": "Registry only - not ownership evidence"}'
  Expect-Code 'product-copy-internal-language' $CopyRepo { ./gates/quality-gate.ps1 } 2

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
    Set-Content -Path architrave.config.json -Encoding utf8 -Value '{'
    $QualityFailProcess = Invoke-CapturedPwsh (Join-Path $KnowledgeRepo 'gates/quality-gate.ps1') $KnowledgeRepo @()
    if ($QualityFailProcess.ExitCode -ne 2 -or $QualityFailProcess.Stdout -notmatch 'quality-gate: BLOCKING') {
      throw "knowledge quality blocking contract invalid (exit=$($QualityFailProcess.ExitCode), stdout=$($QualityFailProcess.Stdout), stderr=$($QualityFailProcess.Stderr))"
    }
    Write-Host 'ok   knowledge-profile-gates'
  } finally { Pop-Location }
}
finally { Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue }
exit 0