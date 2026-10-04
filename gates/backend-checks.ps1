$dir = Split-Path $MyInvocation.MyCommand.Path -Parent
$args2 = @('backend-checks') + $args
$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) { & $py.Source -3 -c 'import sys' *> $null; if ($LASTEXITCODE -eq 0) { & $py.Source -3 (Join-Path $dir 'gate_runner.py') @args2; exit $LASTEXITCODE } }
foreach ($name in 'python3','python') { $p=Get-Command $name -ErrorAction SilentlyContinue; if ($p) { & $p.Source -c 'import sys; raise SystemExit(0 if sys.version_info[0] == 3 else 1)' *> $null; if ($LASTEXITCODE -eq 0) { & $p.Source (Join-Path $dir 'gate_runner.py') @args2; exit $LASTEXITCODE } } }
[Console]::Error.WriteLine('backend-checks: Python 3 is required. Install from https://www.python.org/downloads/windows/.'); exit 2
