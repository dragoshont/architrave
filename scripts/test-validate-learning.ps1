#!/usr/bin/env pwsh
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Root
$Tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("architrave-learning-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $Tmp | Out-Null
try {
  function Make-Repo([string]$Repo) {
    New-Item -ItemType Directory -Force -Path (Join-Path $Repo '.architrave/learning'),(Join-Path $Repo 'docs') | Out-Null
    Copy-Item -Recurse -Path 'harness' -Destination (Join-Path $Repo 'harness')
    Set-Content -Path (Join-Path $Repo 'docs/guide.md') -Value '# Guide' -Encoding utf8
    Set-Content -Path (Join-Path $Repo '.architrave/learning/repo-profile.md') -Value "# Repo Profile`n`nSee [guide](docs/guide.md)." -Encoding utf8
    Set-Content -Path (Join-Path $Repo '.architrave/learning/repo-lessons.md') -Value "# Repo Lessons`n`nNo secrets here." -Encoding utf8
  }
  function Expect-Pass([string]$Name, [string]$Repo) { Push-Location $Repo; try { & ./harness/validate-learning.ps1 *> $null; $Code = $LASTEXITCODE } finally { Pop-Location }; if ($Code -eq 0) { Write-Host "ok   $Name" } else { Write-Error "FAIL $Name expected pass"; exit 1 } }
  function Expect-Fail([string]$Name, [string]$Repo) { Push-Location $Repo; try { & ./harness/validate-learning.ps1 *> $null; $Code = $LASTEXITCODE } finally { Pop-Location }; if ($Code -ne 0) { Write-Host "ok   $Name" } else { Write-Error "FAIL $Name expected failure"; exit 1 } }

  $Valid = Join-Path $Tmp 'valid'; Make-Repo $Valid; Expect-Pass 'valid-learning' $Valid
  $Missing = Join-Path $Tmp 'missing'; Make-Repo $Missing; Remove-Item (Join-Path $Missing '.architrave/learning/repo-profile.md'); Expect-Fail 'missing-profile' $Missing
  $Broken = Join-Path $Tmp 'broken'; Make-Repo $Broken; Set-Content -Path (Join-Path $Broken '.architrave/learning/repo-profile.md') -Value "# Repo Profile`n`n[missing](docs/missing.md)" -Encoding utf8; Expect-Fail 'broken-link' $Broken
  $ParentEscape = Join-Path $Tmp 'parent-escape'; Make-Repo $ParentEscape; Set-Content -Path (Join-Path $ParentEscape '.architrave/learning/repo-profile.md') -Value "# Repo Profile`n`n[out](../outside.md)" -Encoding utf8; Expect-Fail 'parent-escape-link' $ParentEscape
  $WinParentEscape = Join-Path $Tmp 'win-parent-escape'; Make-Repo $WinParentEscape; Set-Content -Path (Join-Path $WinParentEscape '.architrave/learning/repo-profile.md') -Value "# Repo Profile`n`n[out](..\outside.md)" -Encoding utf8; Expect-Fail 'windows-parent-escape-link' $WinParentEscape
  $DriveEscape = Join-Path $Tmp 'drive-escape'; Make-Repo $DriveEscape; Set-Content -Path (Join-Path $DriveEscape '.architrave/learning/repo-profile.md') -Value "# Repo Profile`n`n[out](C:\outside.md)" -Encoding utf8; Expect-Fail 'drive-escape-link' $DriveEscape
  $RootEscape = Join-Path $Tmp 'root-escape'; Make-Repo $RootEscape; Set-Content -Path (Join-Path $RootEscape '.architrave/learning/repo-profile.md') -Value "# Repo Profile`n`n[out](\outside.md)" -Encoding utf8; Expect-Fail 'root-escape-link' $RootEscape
  $Secret = Join-Path $Tmp 'secret'; Make-Repo $Secret; Set-Content -Path (Join-Path $Secret '.architrave/learning/repo-lessons.md') -Value "# Repo Lessons`n`ntoken = ghp_123456789012345678901234567890123456" -Encoding utf8; Expect-Fail 'secret-material' $Secret
}
finally { Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue }