#!/usr/bin/env pwsh
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Root
$Tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("architrave-stale-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $Tmp | Out-Null
try {
  $Repo = Join-Path $Tmp 'repo'
  New-Item -ItemType Directory -Force -Path (Join-Path $Repo '.architrave/learning'),(Join-Path $Repo 'harness'),(Join-Path $Repo 'docs') | Out-Null
  Copy-Item harness/mark-stale-learning.ps1 -Destination (Join-Path $Repo 'harness')
  Set-Content -Path (Join-Path $Repo 'docs/present.md') -Value '# Present' -Encoding utf8
  Set-Content -Path (Join-Path $Repo '.architrave/learning/repo-profile.md') -Encoding utf8 -Value "# Profile`nValid [present](docs/present.md)`nBroken [missing](docs/missing.md)"
  Set-Content -Path (Join-Path $Repo '.architrave/learning/repo-lessons.md') -Value '# Lessons' -Encoding utf8
  Push-Location $Repo
  try {
    & ./harness/mark-stale-learning.ps1 *> $null; if ((Get-Content '.architrave/learning/repo-profile.md' -Raw) -match 'UNVALIDATED') { throw 'dry run wrote file' }
    Write-Host 'ok   stale-dry-run'
    & ./harness/mark-stale-learning.ps1 -Apply *> $null
    if ((Get-Content '.architrave/learning/repo-profile.md' -Raw) -notmatch 'UNVALIDATED: Broken') { throw 'apply did not mark stale line' }
    Write-Host 'ok   stale-apply'
  } finally { Pop-Location }
}
finally { Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue }
exit 0