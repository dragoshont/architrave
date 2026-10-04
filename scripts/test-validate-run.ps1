#!/usr/bin/env pwsh
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("architrave-validate-" + [guid]::NewGuid())
try {
  $legacy = Join-Path $tmp 'legacy'
  $run = Join-Path $legacy '.architrave\runs\test-run'
  New-Item -ItemType Directory -Force -Path $run | Out-Null
  Copy-Item (Join-Path $root 'harness') $legacy -Recurse
  '{"schema":"architrave.run.v1","runId":"test-run","status":"in-progress"}' |
    Set-Content (Join-Path $run 'summary.json') -Encoding utf8
  & (Join-Path $legacy 'harness\validate-run.ps1') $run | Out-Null
  if ($LASTEXITCODE -ne 0) { throw 'compact legacy run failed' }
  Write-Host 'ok   compact legacy run'

  '{"schema":"architrave.run.v1","runId":"","status":"in-progress"}' |
    Set-Content (Join-Path $run 'summary.json') -Encoding utf8
  & (Join-Path $legacy 'harness\validate-run.ps1') $run | Out-Null
  if ($LASTEXITCODE -eq 0) { throw 'invalid compact legacy run passed' }
  Write-Host 'ok   invalid compact legacy run'

  $v2 = Join-Path $tmp 'v2'
  New-Item -ItemType Directory -Force -Path $v2 | Out-Null
  Copy-Item (Join-Path $root 'harness') $v2 -Recurse
  '{}' | Set-Content (Join-Path $v2 'architrave.config.json') -Encoding utf8
  git -C $v2 init -q
  git -C $v2 config user.email architrave@example.invalid
  git -C $v2 config user.name 'Architrave Test'
  git -C $v2 add .
  git -C $v2 commit -qm fixture
  $python = (Get-Command python).Source
  Push-Location $v2
  try {
    & $python (Join-Path $v2 'harness\architrave_runtime.py') run --run-id test-run `
      --goal 'Validate compact Run v2.' --outcome 'Run files remain valid.' | Out-Null
  } finally {
    Pop-Location
  }
  & (Join-Path $v2 'harness\validate-run.ps1') (Join-Path $v2 '.architrave\runs\test-run') | Out-Null
  if ($LASTEXITCODE -ne 0) { throw 'compact v2 run failed' }
  if (-not (Test-Path (Join-Path $v2 '.architrave\runs\test-run\recovery.json'))) { throw 'missing recovery.json' }
  if (Test-Path (Join-Path $v2 '.architrave\runs\test-run\phase-ledger.md')) { throw 'eager phase ledger remains' }
  if (Test-Path (Join-Path $v2 '.architrave\runs\test-run\summary.json')) { throw 'eager summary remains' }
  if (Test-Path (Join-Path $v2 '.architrave\runs\test-run\snapshots')) { throw 'snapshot directory remains' }
  Write-Host 'ok   compact v2 run'
} finally {
  if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
}
