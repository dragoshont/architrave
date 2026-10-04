$ErrorActionPreference = 'Stop'
$cli = Join-Path $PSScriptRoot 'install_update.py'

$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) {
  & $py.Source -3 -c 'import sys' *> $null
  if ($LASTEXITCODE -ne 0) { $py = $null }
}
if ($py) {
  & $py.Source -3 $cli update --entrypoint windows @args
  exit $LASTEXITCODE
}
foreach ($name in 'python3','python') {
  $python = Get-Command $name -ErrorAction SilentlyContinue
  if ($python) {
    & $python.Source -c 'import sys' *> $null
    if ($LASTEXITCODE -ne 0) { continue }
    & $python.Source $cli update --entrypoint windows @args
    exit $LASTEXITCODE
  }
}
[Console]::Error.WriteLine('Architrave requires Python 3. Download it from https://www.python.org/downloads/ and retry.')
exit 2
