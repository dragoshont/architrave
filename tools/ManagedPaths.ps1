$script:ManagedRoot = $null
$script:ManagedLabel = 'architrave'

if (-not $IsWindows -and $null -eq $script:ManagedUnixLStat) {
  $AssemblyName = [Reflection.AssemblyName]::new('ArchitraveManagedPathsNative')
  $Assembly = [Reflection.Emit.AssemblyBuilder]::DefineDynamicAssembly($AssemblyName, [Reflection.Emit.AssemblyBuilderAccess]::Run)
  $Module = $Assembly.DefineDynamicModule('Native')
  $DelegateBuilder = $Module.DefineType('ArchitraveLStatDelegate', [Reflection.TypeAttributes]'Class,Public,Sealed', [MulticastDelegate])
  $Constructor = $DelegateBuilder.DefineConstructor([Reflection.MethodAttributes]'RTSpecialName,HideBySig,Public', [Reflection.CallingConventions]::Standard, @([object], [IntPtr]))
  $Constructor.SetImplementationFlags([Reflection.MethodImplAttributes]'Runtime,Managed')
  $Invoke = $DelegateBuilder.DefineMethod('Invoke', [Reflection.MethodAttributes]'Public,HideBySig,NewSlot,Virtual', [int], @([string], [IntPtr]))
  $Invoke.SetImplementationFlags([Reflection.MethodImplAttributes]'Runtime,Managed')
  $DelegateType = $DelegateBuilder.CreateType()

  $Architecture = [Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture
  if ($IsMacOS) {
    if ($Architecture -notin @([Runtime.InteropServices.Architecture]::X64, [Runtime.InteropServices.Architecture]::Arm64)) {
      throw "unsupported macOS process architecture: $Architecture"
    }
    $script:ManagedUnixLibrary = [Runtime.InteropServices.NativeLibrary]::Load('libSystem.B.dylib')
    $Symbol = if ($Architecture -eq [Runtime.InteropServices.Architecture]::X64) { 'lstat$INODE64' } else { 'lstat' }
    $script:ManagedUnixModeOffset = 4
    $script:ManagedUnixModeIs16Bit = $true
  } elseif ($IsLinux) {
    if ($Architecture -notin @([Runtime.InteropServices.Architecture]::X64, [Runtime.InteropServices.Architecture]::Arm64)) {
      throw "unsupported Linux process architecture: $Architecture"
    }
    $Candidates = if ($Architecture -eq [Runtime.InteropServices.Architecture]::Arm64) {
      @('libc.so.6', 'libc.musl-aarch64.so.1', 'libc.so')
    } else {
      @('libc.so.6', 'libc.musl-x86_64.so.1', 'libc.so')
    }
    $LoadErrors = @()
    foreach ($Candidate in $Candidates) {
      try { $script:ManagedUnixLibrary = [Runtime.InteropServices.NativeLibrary]::Load($Candidate); break }
      catch { $LoadErrors += "$Candidate`: $($_.Exception.Message)" }
    }
    if ($null -eq $script:ManagedUnixLibrary) { throw "unable to load the platform C library ($($LoadErrors -join '; '))" }
    $Symbol = 'lstat'
    $script:ManagedUnixModeOffset = if ($Architecture -eq [Runtime.InteropServices.Architecture]::Arm64) { 16 } else { 24 }
    $script:ManagedUnixModeIs16Bit = $false
  } else {
    throw 'managed-path Unix validation supports only macOS and Linux'
  }
  $Pointer = [Runtime.InteropServices.NativeLibrary]::GetExport($script:ManagedUnixLibrary, $Symbol)
  $script:ManagedUnixLStat = [Runtime.InteropServices.Marshal]::GetDelegateForFunctionPointer($Pointer, $DelegateType)
}

function Initialize-ManagedPaths([string]$Root, [string]$Label = 'architrave') {
  $RootItem = Get-Item -LiteralPath $Root -Force -ErrorAction Stop
  if (-not $RootItem.PSIsContainer) { throw "$Label`: target root must be a directory" }
  if (($RootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
    $Resolved = $RootItem.ResolveLinkTarget($true)
    if (-not $Resolved -or -not $Resolved.PSIsContainer) { throw "$Label`: target root link is invalid" }
    $RootItem = $Resolved
  }
  $script:ManagedRoot = [IO.Path]::TrimEndingDirectorySeparator([IO.Path]::GetFullPath($RootItem.FullName))
  $script:ManagedLabel = $Label
}

function Assert-ManagedRelativePath([string]$RelativePath) {
  if ([string]::IsNullOrWhiteSpace($RelativePath)) { throw "$script:ManagedLabel`: unsafe managed path: empty path" }
  if ([IO.Path]::IsPathRooted($RelativePath) -or $RelativePath.Contains('\')) {
    throw "$script:ManagedLabel`: unsafe managed path '$RelativePath': path must be relative and use '/' separators"
  }
  foreach ($Segment in $RelativePath.Split('/')) {
    if ([string]::IsNullOrEmpty($Segment) -or $Segment -in @('.', '..')) {
      throw "$script:ManagedLabel`: unsafe managed path '$RelativePath': invalid path segment"
    }
  }
}

function Get-ManagedPath([string]$RelativePath) {
  Assert-ManagedRelativePath $RelativePath
  $Candidate = [IO.Path]::GetFullPath((Join-Path $script:ManagedRoot ($RelativePath.Replace('/', [IO.Path]::DirectorySeparatorChar))))
  $Prefix = $script:ManagedRoot + [IO.Path]::DirectorySeparatorChar
  $Comparison = if ($IsWindows) { [StringComparison]::OrdinalIgnoreCase } else { [StringComparison]::Ordinal }
  if (-not $Candidate.StartsWith($Prefix, $Comparison)) {
    throw "$script:ManagedLabel`: unsafe managed path '$RelativePath': path escapes target root"
  }
  return $Candidate
}

function Get-ManagedParentRelative([string]$RelativePath) {
  $Index = $RelativePath.LastIndexOf('/')
  if ($Index -lt 0) { return '' }
  return $RelativePath.Substring(0, $Index)
}

function Test-ManagedReparsePoint([string]$LiteralPath) {
  if (-not (Test-Path -LiteralPath $LiteralPath)) { return $false }
  $Item = Get-Item -LiteralPath $LiteralPath -Force -ErrorAction Stop
  return (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)
}

function Test-ManagedRegularFile([string]$LiteralPath) {
  if (-not (Test-Path -LiteralPath $LiteralPath -PathType Leaf) -or (Test-ManagedReparsePoint $LiteralPath)) { return $false }
  $Item = Get-Item -LiteralPath $LiteralPath -Force -ErrorAction Stop
  if ($Item.PSIsContainer) { return $false }
  if ($IsWindows) { return $true }
  $Buffer = [Runtime.InteropServices.Marshal]::AllocHGlobal(256)
  try {
    $Result = $script:ManagedUnixLStat.Invoke($LiteralPath, $Buffer)
    if ($Result -ne 0) {
      $ErrorNumber = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
      throw "lstat failed for '$LiteralPath' (errno $ErrorNumber)"
    }
    $Mode = if ($script:ManagedUnixModeIs16Bit) {
      [uint32]([Runtime.InteropServices.Marshal]::ReadInt16($Buffer, $script:ManagedUnixModeOffset) -band 0xFFFF)
    } else {
      [uint32][Runtime.InteropServices.Marshal]::ReadInt32($Buffer, $script:ManagedUnixModeOffset)
    }
    return (($Mode -band 0xF000) -eq 0x8000)
  } finally {
    [Runtime.InteropServices.Marshal]::FreeHGlobal($Buffer)
  }
}

function Assert-ManagedDirectoryPreflight([string]$RelativePath) {
  Assert-ManagedRelativePath $RelativePath
  $Current = $script:ManagedRoot
  foreach ($Segment in $RelativePath.Split('/')) {
    $Current = Join-Path $Current $Segment
    if (Test-Path -LiteralPath $Current) {
      if (Test-ManagedReparsePoint $Current) { throw "$script:ManagedLabel`: unsafe managed path '$RelativePath': reparse component '$Segment'" }
      $Item = Get-Item -LiteralPath $Current -Force
      if (-not $Item.PSIsContainer) { throw "$script:ManagedLabel`: unsafe managed path '$RelativePath': component '$Segment' is not a directory" }
    } else {
      break
    }
  }
}

function Assert-ManagedDirectory([string]$RelativePath) {
  Assert-ManagedDirectoryPreflight $RelativePath
  $Path = Get-ManagedPath $RelativePath
  if (-not (Test-Path -LiteralPath $Path -PathType Container) -or (Test-ManagedReparsePoint $Path)) {
    throw "$script:ManagedLabel`: unsafe managed path '$RelativePath': directory is missing or unsafe"
  }
}

function New-ManagedDirectory([string]$RelativePath) {
  Assert-ManagedRelativePath $RelativePath
  $Current = $script:ManagedRoot
  $Built = @()
  foreach ($Segment in $RelativePath.Split('/')) {
    $Built += $Segment
    $Current = Join-Path $Current $Segment
    if (Test-Path -LiteralPath $Current) {
      if (Test-ManagedReparsePoint $Current) { throw "$script:ManagedLabel`: unsafe managed path '$RelativePath': reparse component '$Segment'" }
      if (-not (Get-Item -LiteralPath $Current -Force).PSIsContainer) { throw "$script:ManagedLabel`: unsafe managed path '$RelativePath': component '$Segment' is not a directory" }
    } else {
      if ($Built.Count -gt 1) { Assert-ManagedDirectory (($Built[0..($Built.Count - 2)]) -join '/') }
      New-Item -ItemType Directory -Path $Current -ErrorAction Stop | Out-Null
    }
    Assert-ManagedDirectory ($Built -join '/')
  }
}

function Assert-ManagedFilePreflight([string]$RelativePath) {
  Assert-ManagedRelativePath $RelativePath
  $Parent = Get-ManagedParentRelative $RelativePath
  if ($Parent) { Assert-ManagedDirectoryPreflight $Parent }
  $Path = Get-ManagedPath $RelativePath
  if (Test-Path -LiteralPath $Path) {
    if (Test-ManagedReparsePoint $Path) { throw "$script:ManagedLabel`: unsafe managed path '$RelativePath': destination is a reparse point" }
    if (-not (Test-ManagedRegularFile $Path)) { throw "$script:ManagedLabel`: unsafe managed path '$RelativePath': destination is not a regular file" }
  }
}

function Assert-ManagedFile([string]$RelativePath) {
  Assert-ManagedFilePreflight $RelativePath
  $Path = Get-ManagedPath $RelativePath
  if (-not (Test-ManagedRegularFile $Path)) {
    throw "$script:ManagedLabel`: unsafe managed path '$RelativePath': regular file is missing or unsafe"
  }
}

function Assert-ManagedTree([string]$RelativePath) {
  Assert-ManagedDirectoryPreflight $RelativePath
  $Path = Get-ManagedPath $RelativePath
  if (-not (Test-Path -LiteralPath $Path)) { return }
  Assert-ManagedDirectory $RelativePath
  foreach ($Entry in Get-ChildItem -LiteralPath $Path -Force -Recurse) {
    if (($Entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
      throw "$script:ManagedLabel`: unsafe managed tree '$RelativePath': reparse entry '$($Entry.FullName)'"
    }
    if (-not $Entry.PSIsContainer -and -not (Test-ManagedRegularFile $Entry.FullName)) {
      throw "$script:ManagedLabel`: unsafe managed tree '$RelativePath': unsupported entry '$($Entry.FullName)'"
    }
  }
}

function Assert-PackagedFile([string]$LiteralPath) {
  if (-not (Test-ManagedRegularFile $LiteralPath)) {
    throw "$script:ManagedLabel`: packaged source is not a regular non-link file: $LiteralPath"
  }
}

function Assert-PackagedTree([string]$LiteralPath) {
  if (-not (Test-Path -LiteralPath $LiteralPath -PathType Container) -or (Test-ManagedReparsePoint $LiteralPath)) {
    throw "$script:ManagedLabel`: packaged source is not a real directory: $LiteralPath"
  }
  foreach ($Entry in Get-ChildItem -LiteralPath $LiteralPath -Force -Recurse) {
    if (($Entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
      throw "$script:ManagedLabel`: packaged source tree contains a reparse entry: $($Entry.FullName)"
    }
  }
}

function Copy-ManagedFile([string]$Source, [string]$RelativePath, [switch]$CreateOnly) {
  Assert-PackagedFile $Source
  Assert-ManagedFilePreflight $RelativePath
  $Destination = Get-ManagedPath $RelativePath
  if ($CreateOnly -and (Test-Path -LiteralPath $Destination)) { throw "$script:ManagedLabel`: managed destination already exists: $RelativePath" }
  $ParentRelative = Get-ManagedParentRelative $RelativePath
  $Parent = if ($ParentRelative) { Assert-ManagedDirectory $ParentRelative; Get-ManagedPath $ParentRelative } else { $script:ManagedRoot }
  $Temp = Join-Path $Parent ('.architrave.tmp.' + [guid]::NewGuid().ToString('N'))
  try {
    [IO.File]::Copy($Source, $Temp, $false)
    if ($ParentRelative) { Assert-ManagedDirectory $ParentRelative }
    Assert-ManagedFilePreflight $RelativePath
    if ($CreateOnly -and (Test-Path -LiteralPath $Destination)) { throw "$script:ManagedLabel`: managed destination appeared before create: $RelativePath" }
    [IO.File]::Move($Temp, $Destination, (-not $CreateOnly))
    Assert-ManagedFile $RelativePath
  } finally {
    Remove-Item -LiteralPath $Temp -Force -ErrorAction SilentlyContinue
  }
}

function Set-ManagedContent([string]$RelativePath, [string]$Content, [switch]$CreateOnly) {
  $TempSource = [IO.Path]::GetTempFileName()
  try {
    [IO.File]::WriteAllText($TempSource, $Content, [Text.UTF8Encoding]::new($false))
    Copy-ManagedFile $TempSource $RelativePath -CreateOnly:$CreateOnly
  } finally {
    Remove-Item -LiteralPath $TempSource -Force -ErrorAction SilentlyContinue
  }
}

function Remove-ManagedFile([string]$RelativePath) {
  Assert-ManagedFilePreflight $RelativePath
  $Destination = Get-ManagedPath $RelativePath
  if (-not (Test-Path -LiteralPath $Destination)) { return }
  $Parent = Get-ManagedParentRelative $RelativePath
  if ($Parent) { Assert-ManagedDirectory $Parent }
  Assert-ManagedFile $RelativePath
  Remove-Item -LiteralPath $Destination -Force -ErrorAction Stop
  if (Test-Path -LiteralPath $Destination) { throw "$script:ManagedLabel`: managed file remains after removal: $RelativePath" }
}

function Copy-ManagedTree([string]$Source, [string]$RelativePath) {
  Assert-PackagedTree $Source
  Assert-ManagedTree $RelativePath
  New-ManagedDirectory $RelativePath
  Assert-ManagedTree $RelativePath
  foreach ($Directory in Get-ChildItem -LiteralPath $Source -Directory -Recurse | Where-Object { $_.FullName -notmatch '[/\\]__pycache__(?:[/\\]|$)' } | Sort-Object FullName) {
    $Suffix = [IO.Path]::GetRelativePath($Source, $Directory.FullName).Replace('\', '/')
    New-ManagedDirectory "$RelativePath/$Suffix"
  }
  foreach ($File in Get-ChildItem -LiteralPath $Source -File -Recurse | Where-Object { $_.Extension -ne '.pyc' -and $_.FullName -notmatch '[/\\]__pycache__[/\\]' } | Sort-Object FullName) {
    $Suffix = [IO.Path]::GetRelativePath($Source, $File.FullName).Replace('\', '/')
    Copy-ManagedFile $File.FullName "$RelativePath/$Suffix"
  }
  Assert-ManagedTree $RelativePath
}