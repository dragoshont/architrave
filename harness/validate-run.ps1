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
  & $command.Source @prefix -c 'import sys' *> $null
  if ($LASTEXITCODE -ne 0) { continue }
  & $command.Source @prefix (Join-Path $root 'architrave_cli.py') validate-run @Forwarded
  exit $LASTEXITCODE
}
[Console]::Error.WriteLine('validate-run: Python 3 is required. Install from https://www.python.org/downloads/windows/ and enable the Python launcher or add Python to PATH.')
exit 2
