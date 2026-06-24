#!/usr/bin/env pwsh
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Root
$Tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("architrave-semantic-learning-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $Tmp | Out-Null
try {
  $Repo = Join-Path $Tmp 'repo'
  New-Item -ItemType Directory -Force -Path (Join-Path $Repo '.architrave/learning'),(Join-Path $Repo 'harness'),(Join-Path $Repo 'docs') | Out-Null
  Copy-Item harness/semantic-learning-review.ps1,harness/apply-semantic-learning-findings.ps1 -Destination (Join-Path $Repo 'harness')
  Set-Content -Path (Join-Path $Repo 'docs/guide.md') -Value '# Guide' -Encoding utf8
  Set-Content -Path (Join-Path $Repo '.architrave/learning/repo-profile.md') -Encoding utf8 -Value @'
# Repo Profile

Build uses make release on Windows.
UNVALIDATED: Old claim.
Evidence-backed claim. Evidence: [guide](docs/guide.md)
'@
  Set-Content -Path (Join-Path $Repo '.architrave/learning/repo-lessons.md') -Encoding utf8 -Value @'
# Repo Lessons

No durable semantic claims here.
'@

  Push-Location $Repo
  try {
    & ./harness/semantic-learning-review.ps1 -Provider copilot *> $null
    if ((Get-Content '.architrave/learning/semantic-stale-facts-prompt.md' -Raw) -notmatch 'JSON Lines only') { throw 'prompt missing JSONL instruction' }
    Write-Host 'ok   semantic-review-prompt'

    Set-Content -Path '.architrave/learning/semantic-stale-facts.jsonl' -Encoding utf8 -Value @'
{"file":".architrave/learning/repo-profile.md","line":3,"currentText":"Build uses make release on Windows.","severity":"major","reason":"No current evidence supports this Windows release claim."}
{"file":".architrave/learning/repo-profile.md","line":4,"currentText":"Old claim.","severity":"minor","reason":"Already marked unvalidated."}
'@
    & ./harness/apply-semantic-learning-findings.ps1 *> $null
    if ((Get-Content '.architrave/learning/repo-profile.md' -Raw) -match '^UNVALIDATED: Build uses make release') { throw 'dry run wrote file' }
    Write-Host 'ok   semantic-dry-run'
    & ./harness/apply-semantic-learning-findings.ps1 -Apply *> $null
    $ProfileText = Get-Content '.architrave/learning/repo-profile.md' -Raw
    if ($ProfileText -notmatch 'UNVALIDATED: Build uses make release on Windows\.') { throw 'apply did not mark semantic stale claim' }
    Write-Host 'ok   semantic-apply'
    if (([regex]::Matches($ProfileText, 'UNVALIDATED: Old claim\.')).Count -ne 1) { throw 'existing UNVALIDATED line duplicated' }
    Write-Host 'ok   semantic-existing-unvalidated'

    Set-Content -Path '.architrave/learning/semantic-stale-facts.jsonl' -Encoding utf8 -Value '{"file":".architrave/learning/repo-profile.md","line":3,"currentText":"Different text.","severity":"major","reason":"stale finding"}'
    & ./harness/apply-semantic-learning-findings.ps1 -Apply *> $null; if ($LASTEXITCODE -eq 0) { throw 'stale finding expected failure' }
    Write-Host 'ok   semantic-stale-finding'

    Set-Content -Path '.architrave/learning/semantic-stale-facts.jsonl' -Encoding utf8 -Value '{"file":"README.md","line":1,"currentText":"# README","severity":"major","reason":"invalid target"}'
    & ./harness/apply-semantic-learning-findings.ps1 -Apply *> $null; if ($LASTEXITCODE -eq 0) { throw 'invalid target expected failure' }
    Write-Host 'ok   semantic-invalid-target'

    Set-Content -Path '.architrave/learning/semantic-stale-facts.jsonl' -Encoding utf8 -Value 'PASS'
    & ./harness/apply-semantic-learning-findings.ps1 *> $null
    if ($LASTEXITCODE -ne 0) { throw 'PASS output expected success' }
    Write-Host 'ok   semantic-pass-output'
  } finally { Pop-Location }
}
finally { Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue }
exit 0