[CmdletBinding()]
param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Forwarded)
$root = Split-Path $MyInvocation.MyCommand.Path -Parent
$candidates = @(
  [pscustomobject]@{ Name = 'py'; Prefix = @('-3') },
  [pscustomobject]@{ Name = 'python3'; Prefix = @() },
  [pscustomobject]@{ Name = 'python'; Prefix = @() }
)
foreach ($candidate in $candidates) {
  $command = Get-Command $candidate.Name -ErrorAction SilentlyContinue
  if (-not $command) { continue }
  $prefix = @($candidate.Prefix)
  & $command.Source @prefix -c 'import sys; raise SystemExit(0 if sys.version_info[0] == 3 else 1)' *> $null
  if ($LASTEXITCODE -ne 0) { continue }
  & $command.Source @prefix (Join-Path $root 'test-improvement.py') PromotionTests.test_dry_run_apply_and_picker PromotionTests.test_executable_check_or_explicit_prose_justification_required PromotionTests.test_invalid_target_missing_and_stale_lesson @Forwarded
  exit $LASTEXITCODE
}
[Console]::Error.WriteLine('test-promote-lesson-picker: Python 3 is required. Install from https://www.python.org/downloads/windows/ and enable the Python launcher or add Python to PATH.')
exit 2
