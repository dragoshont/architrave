#!/usr/bin/env pwsh
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Root
$Tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("architrave-picker-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $Tmp | Out-Null
try {
  $Repo = Join-Path $Tmp 'repo'
  New-Item -ItemType Directory -Force -Path (Join-Path $Repo '.architrave/learning'),(Join-Path $Repo 'harness') | Out-Null
  Copy-Item harness/validate-learning.ps1,harness/promote-lesson.ps1,harness/promote-lesson-picker.ps1 -Destination (Join-Path $Repo 'harness')
  Set-Content -Path (Join-Path $Repo '.architrave/learning/repo-profile.md') -Value '# Repo Profile' -Encoding utf8
  Set-Content -Path (Join-Path $Repo '.architrave/learning/repo-lessons.md') -Encoding utf8 -Value @'
# Lessons

| Lesson | Evidence | Occurrences | Validated | Proposed Target | Status |
|---|---|---:|---|---|---|
| Run quick gates before release | test | 2 | yes | docs | candidate |
| Keep secrets out of artifacts | test | 2 | yes | docs | candidate |
'@
  Push-Location $Repo
  try {
    & ./harness/promote-lesson-picker.ps1 -Index 2 -Target docs/guide.md *> $null; if ($LASTEXITCODE -ne 0) { throw 'dry run failed' }
    Write-Host 'ok   picker-dry-run'
    & ./harness/promote-lesson-picker.ps1 -Index 1 -Target docs/guide.md -Apply *> $null; if ($LASTEXITCODE -ne 0) { throw 'apply failed' }
    if ((Get-Content docs/guide.md -Raw) -notmatch 'Run quick gates') { throw 'lesson missing' }
    Write-Host 'ok   picker-apply'
    & ./harness/promote-lesson-picker.ps1 -Index 99 -Target docs/guide.md *> $null; if ($LASTEXITCODE -eq 0) { throw 'missing index passed' }
    Write-Host 'ok   picker-missing-index'
  } finally { Pop-Location }
}
finally { Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue }
exit 0