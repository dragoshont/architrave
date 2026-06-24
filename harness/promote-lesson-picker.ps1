#!/usr/bin/env pwsh
[CmdletBinding()]
param(
  [int]$Index,
  [string]$Target,
  [string]$Repo = (Get-Location).Path,
  [switch]$Apply
)
$ErrorActionPreference = 'Stop'
Set-Location $Repo
if ($Index -lt 1) { [Console]::Error.WriteLine('promote-lesson-picker: -Index must be a positive integer'); exit 2 }
if (-not $Target) { [Console]::Error.WriteLine('promote-lesson-picker: -Target is required'); exit 2 }
$Lessons = '.architrave/learning/repo-lessons.md'
if (-not (Test-Path $Lessons) -or (Get-Item $Lessons).Length -eq 0) { [Console]::Error.WriteLine("promote-lesson-picker: missing $Lessons"); exit 2 }
$Rows = @()
foreach ($Line in Get-Content $Lessons) {
  if ($Line -notmatch '^\|') { continue }
  $Cells = $Line.Trim('|').Split('|') | ForEach-Object { $_.Trim() }
  if ($Cells.Count -lt 1 -or $Cells[0] -match '^(-+|Lesson)$') { continue }
  $Rows += $Cells[0]
}
if ($Index -gt $Rows.Count) { [Console]::Error.WriteLine("promote-lesson-picker: candidate index not found: $Index"); exit 2 }
$RepoRoot = (Get-Location).Path
if ($Apply) {
  & ./harness/promote-lesson.ps1 -Lesson $Rows[$Index - 1] -Target $Target -Repo $RepoRoot -Apply
} else {
  & ./harness/promote-lesson.ps1 -Lesson $Rows[$Index - 1] -Target $Target -Repo $RepoRoot
}
exit $LASTEXITCODE