$dir = Split-Path $MyInvocation.MyCommand.Path -Parent
$args2 = @('checks') + @($args | ForEach-Object { if ($_ -eq '-Quick') { '--quick' } else { $_ } })
$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) { & $py.Source -3 (Join-Path $dir 'gate_runner.py') @args2; exit $LASTEXITCODE }
foreach ($name in 'python3','python') { $p=Get-Command $name -ErrorAction SilentlyContinue; if ($p) { & $p.Source (Join-Path $dir 'gate_runner.py') @args2; exit $LASTEXITCODE } }
[Console]::Error.WriteLine('checks: Python 3 is required. Install from https://www.python.org/downloads/windows/.'); exit 2
