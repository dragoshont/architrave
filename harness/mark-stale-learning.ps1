#!/usr/bin/env pwsh
[CmdletBinding()]
param([string]$Repo = (Get-Location).Path, [switch]$Apply)
$ErrorActionPreference = 'Stop'
Set-Location $Repo
$Files = @('.architrave/learning/repo-profile.md', '.architrave/learning/repo-lessons.md')
$Changed = $false
foreach ($File in $Files) {
  if (-not (Test-Path $File)) { continue }
  $Out = New-Object System.Collections.Generic.List[string]
  foreach ($Line in Get-Content $File) {
    $Stale = $false
    foreach ($Match in [regex]::Matches($Line, '\[[^\]]+\]\(([^)]+)\)')) {
      $Target = $Match.Groups[1].Value
      if ($Target -match '^(https?://|mailto:|#)' -or -not $Target) { continue }
      $Path = ($Target -split '#', 2)[0].Replace('%20', ' ')
      if (-not $Path) { continue }
      if ([System.IO.Path]::IsPathRooted($Path) -or $Path -match '^[A-Za-z]:[\\/]' -or $Path.StartsWith('\')) { $Stale = $true; continue }
      $FullPath = [System.IO.Path]::GetFullPath((Join-Path (Resolve-Path '.').Path $Path))
      if (-not (Test-Path $FullPath)) { $Stale = $true }
    }
    if ($Stale -and $Line -notmatch 'UNVALIDATED:') {
      $Changed = $true
      if ($Apply) { $Out.Add("UNVALIDATED: $Line") } else { Write-Host "would mark $File: $Line"; $Out.Add($Line) }
    } else { $Out.Add($Line) }
  }
  if ($Apply) { Set-Content -Path $File -Encoding utf8 -Value $Out }
}
if (-not $Changed) { Write-Host 'mark-stale-learning: no stale local learning links found' }
exit 0