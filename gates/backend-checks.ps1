#!/usr/bin/env pwsh
# Architrave - backend + infra deterministic gate (PowerShell mirror of
# gates/backend-checks.sh). Reads the `backend` and `iac` blocks of
# uikit.config.json: backend build/test, IaC PLAN (never apply), policy lint,
# and a secret scan of the IaC path. Exit 0 = PASS, non-zero = FAIL.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'

# Repo root = nearest ancestor containing uikit.config.json.
$dir = (Get-Location).Path
while ($dir -and -not (Test-Path (Join-Path $dir 'uikit.config.json'))) {
  $parent = Split-Path $dir -Parent
  if ($parent -eq $dir) { break }
  $dir = $parent
}
if (-not (Test-Path (Join-Path $dir 'uikit.config.json'))) {
  [Console]::Error.WriteLine('backend-checks: uikit.config.json not found'); exit 2
}
Set-Location $dir
$cfg = Get-Content 'uikit.config.json' -Raw | ConvertFrom-Json

$fail = 0
Write-Host "== Architrave backend-checks (root: $dir) =="

if (-not $cfg.backend -and -not $cfg.iac) {
  Write-Host 'skip  no backend/iac block in uikit.config.json'; exit 0
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

# --- Backend lane ---
if ($cfg.backend) {
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
