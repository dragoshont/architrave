#!/usr/bin/env pwsh
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $Root 'tools/ManagedPaths.ps1')

$Tmp = Join-Path ([IO.Path]::GetTempPath()) ("architrave-managed-paths-" + [guid]::NewGuid().ToString('N'))
$Target = Join-Path $Tmp 'target'
$External = Join-Path $Tmp 'external'
New-Item -ItemType Directory -Path $Target,$External | Out-Null

try {
  Initialize-ManagedPaths $Target test

  foreach ($UnsafePath in '../escape','/absolute') {
    $Rejected = $false
    try { New-ManagedDirectory $UnsafePath } catch { $Rejected = $true }
    if (-not $Rejected) { throw "accepted unsafe path: $UnsafePath" }
  }
  if (Test-Path (Join-Path $Tmp 'escape')) { throw 'created an escaping directory' }

  $UnicodeSource = Join-Path $Tmp 'unicode-source'
  [IO.File]::WriteAllText($UnicodeSource, 'unicode sentinel', [Text.UTF8Encoding]::new($false))
  New-ManagedDirectory 'unicodé'
  Copy-ManagedFile $UnicodeSource 'unicodé/naïve.md'
  if ([IO.File]::ReadAllText((Join-Path $Target 'unicodé/naïve.md')) -cne 'unicode sentinel') { throw 'Unicode managed copy changed content' }
  if (-not (Test-ManagedRegularFile (Join-Path $Target 'unicodé/naïve.md'))) { throw 'Unicode regular file was rejected' }

  $LinkedTarget = Join-Path $External 'linked-target'
  New-Item -ItemType Directory -Path $LinkedTarget | Out-Null
  [IO.File]::WriteAllText((Join-Path $LinkedTarget 'sentinel'), 'outside', [Text.UTF8Encoding]::new($false))
  $LinkType = if ($IsWindows) { 'Junction' } else { 'SymbolicLink' }
  New-Item -ItemType $LinkType -Path (Join-Path $Target 'linked') -Target $LinkedTarget | Out-Null
  $Rejected = $false
  try { Assert-ManagedTree 'linked' } catch { $Rejected = $true }
  if (-not $Rejected) { throw 'accepted linked managed directory' }
  if ([IO.File]::ReadAllText((Join-Path $LinkedTarget 'sentinel')) -cne 'outside') { throw 'changed external linked directory' }

  $ExternalHardlink = Join-Path $External 'hardlink'
  [IO.File]::WriteAllText($ExternalHardlink, 'external hardlink', [Text.UTF8Encoding]::new($false))
  New-Item -ItemType HardLink -Path (Join-Path $Target '.gitignore') -Target $ExternalHardlink | Out-Null
  $ExternalHash = (Get-FileHash -LiteralPath $ExternalHardlink -Algorithm SHA256).Hash
  Set-ManagedContent '.gitignore' "managed replacement`n"
  if ((Get-FileHash -LiteralPath $ExternalHardlink -Algorithm SHA256).Hash -ne $ExternalHash) { throw 'changed external hard-linked content' }
  if ([IO.File]::ReadAllText((Join-Path $Target '.gitignore')) -cne "managed replacement`n") { throw 'managed hard-link replacement failed' }

  if (-not $IsWindows) {
    $Fifo = Join-Path $Tmp 'fifo'
    & mkfifo $Fifo
    if ($LASTEXITCODE -ne 0) { throw 'failed to create FIFO fixture' }
    New-Item -ItemType SymbolicLink -Path (Join-Path $Tmp 'file-link') -Target $UnicodeSource | Out-Null
    if (Test-ManagedRegularFile $Fifo) { throw 'accepted FIFO as regular file' }
    if (Test-ManagedRegularFile (Join-Path $Tmp 'file-link')) { throw 'accepted symbolic link as regular file' }
    if (Test-ManagedRegularFile '/dev/null') { throw 'accepted device node as regular file' }
  }

  Write-Host 'MANAGED-PATHS: PASS'
} finally {
  Remove-Item -LiteralPath $Tmp -Recurse -Force -ErrorAction SilentlyContinue
}