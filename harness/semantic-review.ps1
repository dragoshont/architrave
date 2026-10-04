[CmdletBinding()]
param(
  [ValidateSet('copilot','claude','both')][string]$Provider = 'both',
  [string]$RunDir,
  [switch]$Execute
)
$root = Split-Path $MyInvocation.MyCommand.Path -Parent
$Forwarded = @('--provider', $Provider)
if ($RunDir) { $Forwarded += @('--run', $RunDir) }
if ($Execute) { $Forwarded += '--execute' }
foreach ($candidate in @(
  [pscustomobject]@{ Name = 'py'; Prefix = @('-3') },
  [pscustomobject]@{ Name = 'python3'; Prefix = @() },
  [pscustomobject]@{ Name = 'python'; Prefix = @() }
)) {
  $command = Get-Command $candidate.Name -ErrorAction SilentlyContinue
  if (-not $command) { continue }
  $prefix = @($candidate.Prefix)
  & $command.Source @prefix -c 'import sys' *> $null
  if ($LASTEXITCODE -ne 0) { continue }
  & $command.Source @prefix (Join-Path $root 'architrave_cli.py') semantic-review @Forwarded
  exit $LASTEXITCODE
}
[Console]::Error.WriteLine('semantic-review: Python 3 is required. Install from https://www.python.org/downloads/windows/ and enable the Python launcher or add Python to PATH.')
exit 2
