#!/usr/bin/env pwsh
# Validate Architrave learning artifacts without trusting their contents.
[CmdletBinding()]
param([string]$Repo = (Get-Location).Path)
$ErrorActionPreference = 'Stop'

Set-Location $Repo
$RepoRoot = (Resolve-Path '.').Path
$Profile = '.architrave/learning/repo-profile.md'
$Lessons = '.architrave/learning/repo-lessons.md'
$Fail = 0

function Ok($Message) { Write-Host "ok    $Message" }
function Err($Message) { Write-Host "FAIL  $Message"; $script:Fail = 1 }

if ((Test-Path $Profile) -and ((Get-Item $Profile).Length -gt 0)) { Ok $Profile } else { Err "missing/empty $Profile" }
if ((Test-Path $Lessons) -and ((Get-Item $Lessons).Length -gt 0)) { Ok $Lessons } else { Err "missing/empty $Lessons" }

$SecretPattern = '(-----BEGIN [A-Z ]*PRIVATE KEY|gh[pousr]_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}|(api[_-]?key|token|password)\s*[:=]\s*\S{12,})'
$SecretHits = @()
if (Test-Path '.architrave/learning') {
  $SecretHits = Get-ChildItem '.architrave/learning' -Recurse -File | Select-String -Pattern $SecretPattern -CaseSensitive:$false
}
if ($SecretHits.Count -gt 0) {
  Err 'possible secret material in learning artifacts'
  $SecretHits | Select-Object -First 10 | ForEach-Object { Write-Host "      $($_.Path):$($_.LineNumber):$($_.Line)" }
} else { Ok 'no obvious secrets in learning artifacts' }

function Validate-Links($File) {
  if (-not (Test-Path $File)) { return }
  $Bad = 0
  $Text = Get-Content $File -Raw
  $Matches = [regex]::Matches($Text, '\[[^\]]+\]\(([^)]+)\)')
  foreach ($Match in $Matches) {
    $Target = $Match.Groups[1].Value
    if ($Target -match '^(https?://|mailto:|#)' -or -not $Target) { continue }
    $Path = ($Target -split '#', 2)[0].Replace('%20', ' ')
    if (-not $Path) { continue }
    if ([System.IO.Path]::IsPathRooted($Path)) { Err "$File link escapes repo: $Target"; $Bad = 1; continue }
    $FullPath = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $Path))
    $RepoPrefix = $RepoRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
    if (-not ($FullPath.StartsWith($RepoPrefix, [System.StringComparison]::OrdinalIgnoreCase) -or [string]::Equals($FullPath, $RepoRoot, [System.StringComparison]::OrdinalIgnoreCase))) {
      Err "$File link escapes repo: $Target"; $Bad = 1; continue
    }
    if (-not (Test-Path $FullPath)) { Err "$File missing link target: $Target"; $Bad = 1 }
  }
  if ($Bad -eq 0) { Ok "links resolve in $File" } else { $script:Fail = 1 }
}

Validate-Links $Profile
Validate-Links $Lessons

if ($Fail -eq 0) { Write-Host 'ARCHITRAVE-LEARNING: PASS' } else { Write-Host 'ARCHITRAVE-LEARNING: FAIL' }
exit $Fail