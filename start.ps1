param([ValidateRange(1024, 65535)][int]$Port = 8768)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$jobflowPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $jobflowPython)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}
& $jobflowPython start.py --port $Port
if ($LASTEXITCODE -ne 0) { throw 'Jobflow could not start. Check the error above.' }
