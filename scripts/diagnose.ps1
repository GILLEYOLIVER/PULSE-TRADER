$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$python = Join-Path $PWD '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { $python = 'python' }
& $python -m trading_assistant.v2.cli diagnose
& $python -m unittest discover -s tests -v
exit $LASTEXITCODE
