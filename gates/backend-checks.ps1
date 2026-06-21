#!/usr/bin/env pwsh
# Architrave - backend + infra deterministic gate (PowerShell mirror of
# gates/backend-checks.sh). Reads the `backend` and `iac` blocks of
# architrave.config.json: backend build/test, IaC PLAN (never apply), policy lint,
# and a secret scan of the IaC path. Exit 0 = PASS, non-zero = FAIL.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'

# Repo root = nearest ancestor containing architrave.config.json.
$dir = (Get-Location).Path
while ($dir -and -not (Test-Path (Join-Path $dir 'architrave.config.json'))) {
  $parent = Split-Path $dir -Parent
  if ($parent -eq $dir) { break }
  $dir = $parent
}
if (-not (Test-Path (Join-Path $dir 'architrave.config.json'))) {
  [Console]::Error.WriteLine('backend-checks: architrave.config.json not found'); exit 2
}
Set-Location $dir
$root = (Resolve-Path '.').Path
$cfg = Get-Content 'architrave.config.json' -Raw | ConvertFrom-Json

$fail = 0
Write-Host "== Architrave backend-checks (root: $dir) =="

if (-not $cfg.backend -and -not $cfg.iac) {
  Write-Host 'skip  no backend/iac block in architrave.config.json'; exit 0
}

function Run-Step($name, $cmd) {
  if ([string]::IsNullOrWhiteSpace($cmd)) { Write-Host "skip  $name (not configured)"; return }
  Write-Host "== $name`: $cmd =="
  & $env:SHELL -c $cmd 2>&1 | Write-Host
  if ($LASTEXITCODE -ne 0) {
    # Fallback for Windows shells where $env:SHELL is unset.
    if (-not $env:SHELL) { cmd /c $cmd 2>&1 | Write-Host }
  }
  if ($LASTEXITCODE -eq 0) { Write-Host "ok    $name" } else { Write-Host "FAIL  $name"; $script:fail = 1 }
}

function Get-SolutionProjectPaths($solution) {
  if ($solution -like '*.slnx') {
    [xml]$doc = Get-Content $solution -Raw
    return @($doc.SelectNodes('//Project') | ForEach-Object { $_.Path } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
  }
  if ($solution -like '*.sln') {
    $paths = New-Object System.Collections.Generic.List[string]
    foreach ($line in Get-Content $solution) {
      if ($line -match '^\s*Project\([^)]*\)\s*=\s*"[^"]+",\s*"([^"]+)"' -and $Matches[1] -match '\.(csproj|fsproj|vbproj|vcxproj)$') {
        [void]$paths.Add($Matches[1])
      }
    }
    return @($paths)
  }
  return @()
}

function Test-BackendSolutionPaths($solution) {
  if ([string]::IsNullOrWhiteSpace($solution)) { return }
  if (-not ($solution.EndsWith('.sln') -or $solution.EndsWith('.slnx'))) { return }
  Write-Host "== backend solution path check: $solution =="
  if (-not (Test-Path $solution)) {
    Write-Host "FAIL  backend solution not found: $solution"
    $script:fail = 1
    return
  }
  $solutionPath = (Resolve-Path $solution).Path
  $solutionDir = Split-Path $solutionPath -Parent
  $rootPrefix = $root.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
  $bad = $false
  foreach ($path in Get-SolutionProjectPaths $solutionPath) {
    if ([IO.Path]::IsPathRooted($path)) { $candidate = $path } else { $candidate = Join-Path $solutionDir $path }
    $full = [IO.Path]::GetFullPath($candidate)
    if (-not $full.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
      Write-Host "FAIL  solution project escapes repo: $path -> $full"
      $bad = $true
      continue
    }
    if (-not (Test-Path $full)) {
      Write-Host "FAIL  solution project missing: $path -> $full"
      $bad = $true
    }
  }
  if ($bad) { $script:fail = 1 } else { Write-Host 'ok    backend solution project paths stay inside repo' }
}

# --- Backend lane ---
if ($cfg.backend) {
  Test-BackendSolutionPaths $cfg.backend.solution
  Run-Step 'backend build' $cfg.backend.build
  Run-Step 'backend test'  $cfg.backend.test
}

# --- Infra lane (PLAN-ONLY) ---
if ($cfg.iac) {
  $plan = [string]$cfg.iac.plan
  $applyShaped = 'kubectl\s+(apply|create|delete|replace|patch)|terraform\s+(apply|destroy)|az\s+deployment\s+[a-z]+\s+create|pulumi\s+(up|destroy)|helm\s+(install|upgrade|uninstall)|apply\s+-f'
  if ($plan -and ($plan -imatch $applyShaped)) {
    Write-Host "FAIL  iac.plan looks like an APPLY ('$plan') - infra is plan-only; use diff / what-if / plan"
    $fail = 1
  } else {
    Run-Step 'iac plan'   $cfg.iac.plan
    Run-Step 'iac policy' $cfg.iac.policy
  }
}

# --- Secret scan (IaC path; *.example.* / *.sample excluded) ---
if ($cfg.iac -and $cfg.iac.path -and (Get-Command git -ErrorAction SilentlyContinue)) {
  Write-Host "== secret scan: $($cfg.iac.path) =="
  $pattern = '(-----BEGIN [A-Z ]*PRIVATE KEY|AKIA[0-9A-Z]{16}|(client_secret|api_key|apikey|password)\s*[:=]\s*\S{12,})'
  $hits = git grep -nIE $pattern -- $cfg.iac.path 2>$null | Where-Object { $_ -notmatch '\.example\.|\.sample|example\.ya?ml' }
  if ($hits) {
    Write-Host 'FAIL  possible committed secret(s):'; $hits | Select-Object -First 10 | ForEach-Object { Write-Host "      $_" }; $fail = 1
  } else {
    Write-Host "ok    no obvious secrets under $($cfg.iac.path)"
  }
}

if ($fail -eq 0) { Write-Host 'BACKEND-CHECKS: PASS' } else { Write-Host 'BACKEND-CHECKS: FAIL' }
exit $fail
