#!/usr/bin/env pwsh
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Root
$Tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("architrave-promote-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $Tmp | Out-Null
try {
  $Repo = Join-Path $Tmp 'repo'
  New-Item -ItemType Directory -Force -Path (Join-Path $Repo '.architrave/learning'),(Join-Path $Repo 'harness') | Out-Null
  Copy-Item harness/validate-learning.ps1,harness/promote-lesson.ps1 -Destination (Join-Path $Repo 'harness')
  Set-Content -Path (Join-Path $Repo '.architrave/learning/repo-profile.md') -Value '# Repo Profile' -Encoding utf8
  Set-Content -Path (Join-Path $Repo '.architrave/learning/repo-lessons.md') -Value '# Repo Lessons' -Encoding utf8
  Push-Location $Repo
  try {
    & ./harness/promote-lesson.ps1 -Lesson 'Use the quick gate before release.' -Target 'docs/guide.md' *> $null
    if (Test-Path 'docs/guide.md') { throw 'dry run wrote target' }
    Write-Host 'ok   dry-run'
    & ./harness/promote-lesson.ps1 -Lesson 'Use the quick gate before release.' -Target 'docs/guide.md' -Apply *> $null
    if ((Get-Content 'docs/guide.md' -Raw) -notmatch 'Use the quick gate') { throw 'apply missing lesson' }
    Write-Host 'ok   apply'
    & ./harness/promote-lesson.ps1 -Target 'docs/guide.md' *> $null; if ($LASTEXITCODE -eq 0) { throw 'missing lesson passed' }
    Write-Host 'ok   missing-lesson'
    & ./harness/promote-lesson.ps1 -Lesson nope -Target '../escape.md' *> $null; if ($LASTEXITCODE -eq 0) { throw 'parent escape target passed' }
    & ./harness/promote-lesson.ps1 -Lesson nope -Target '..\escape.md' *> $null; if ($LASTEXITCODE -eq 0) { throw 'windows parent escape target passed' }
    & ./harness/promote-lesson.ps1 -Lesson nope -Target 'C:\escape.md' *> $null; if ($LASTEXITCODE -eq 0) { throw 'drive absolute target passed' }
    & ./harness/promote-lesson.ps1 -Lesson nope -Target '\escape.md' *> $null; if ($LASTEXITCODE -eq 0) { throw 'root absolute target passed' }
    Write-Host 'ok   invalid-targets'
  } finally { Pop-Location }
}
finally { Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue }