param([switch]$Full)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
python -m venv --without-pip .venv
if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ with venv is required' }
$python = Join-Path $PWD '.venv\Scripts\python.exe'
if ($Full) {
    $env:TMP = Join-Path $PWD '.pip-temp'
    $env:TEMP = $env:TMP
    New-Item -ItemType Directory -Force -Path $env:TMP | Out-Null
    & $python -m ensurepip --upgrade
    if ($LASTEXITCODE -ne 0) { throw 'Cannot bootstrap pip. Core/Tk mode requires no packages.' }
    & $python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Offline core still runs with Tkinter.' }
}
& $python -m trading_assistant.v2.cli diagnose
if ($LASTEXITCODE -ne 0) { throw 'Diagnostic failed' }
Write-Output 'Ready. Run scripts\start.ps1. No live orders are available.'
