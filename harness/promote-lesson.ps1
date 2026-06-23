#!/usr/bin/env pwsh
# Promote an approved lesson into a repo-local Markdown guidance file.
[CmdletBinding()]
param(
  [string]$Lesson,
  [string]$Target,
  [string]$Heading = 'Promoted Lessons',
  [string]$Repo = (Get-Location).Path,
  [switch]$Apply
)
$ErrorActionPreference = 'Stop'

Set-Location $Repo
if (-not $Lesson) { [Console]::Error.WriteLine('promote-lesson: -Lesson is required'); exit 2 }
if (-not $Target) { [Console]::Error.WriteLine('promote-lesson: -Target is required'); exit 2 }
if (-not ($Target.EndsWith('.md') -or $Target -eq 'AGENTS.md')) { [Console]::Error.WriteLine('promote-lesson: target must be a Markdown file'); exit 2 }
$RepoRoot = (Resolve-Path '.').Path
if ($Target -match '^[A-Za-z]:[\\/]' -or $Target.StartsWith('\')) { [Console]::Error.WriteLine('promote-lesson: target must be repo-relative and stay inside the repo'); exit 2 }
if ([System.IO.Path]::IsPathRooted($Target)) { [Console]::Error.WriteLine('promote-lesson: target must be repo-relative and stay inside the repo'); exit 2 }
$FullTarget = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $Target))
$RepoPrefix = $RepoRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
if (-not ($FullTarget.StartsWith($RepoPrefix, [System.StringComparison]::OrdinalIgnoreCase) -or [string]::Equals($FullTarget, $RepoRoot, [System.StringComparison]::OrdinalIgnoreCase))) {
  [Console]::Error.WriteLine('promote-lesson: target must be repo-relative and stay inside the repo')
  exit 2
}

if (-not (Test-Path 'harness/validate-learning.ps1')) { [Console]::Error.WriteLine('promote-lesson: harness/validate-learning.ps1 not found'); exit 2 }
& ./harness/validate-learning.ps1 *> $null
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$Entry = "- $Lesson"
if (-not $Apply) {
  Write-Host "DRY RUN: would append to $Target under heading '$Heading':"
  Write-Host $Entry
  exit 0
}

$Target = [System.IO.Path]::GetRelativePath($RepoRoot, $FullTarget)
$Parent = Split-Path $Target -Parent
if ($Parent) { New-Item -ItemType Directory -Force -Path $Parent | Out-Null }
if (-not (Test-Path $Target)) { New-Item -ItemType File -Force -Path $Target | Out-Null }
$Text = Get-Content $Target -Raw -ErrorAction SilentlyContinue
if ($Text -notmatch "(?m)^##\s+$([regex]::Escape($Heading))$") {
  if ($Text) { Add-Content -Path $Target -Value '' }
  Add-Content -Path $Target -Value "## $Heading"
  Add-Content -Path $Target -Value ''
}
Add-Content -Path $Target -Value $Entry
Write-Host "promoted lesson to $Target"