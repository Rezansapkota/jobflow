param([ValidateRange(1024, 65535)][int]$Port = 8768)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PORT = [string]$Port
$jobflowUrl = "http://127.0.0.1:$Port"
try {
    $jobflowResponse = Invoke-WebRequest -UseBasicParsing -Uri "$jobflowUrl/api/automation" -TimeoutSec 2
    if ($jobflowResponse.StatusCode -eq 200) {
        Write-Host "Jobflow is already running at $jobflowUrl"
        return
    }
} catch {
    # Continue to normal startup when no current server responds.
}
$jobflowPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $jobflowPython)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}
Write-Host 'Keep this terminal open while using Jobflow. Press Ctrl+C to stop it.'
& $jobflowPython app.py
if ($LASTEXITCODE -ne 0) { throw 'Jobflow could not start. Check the error above, or select another port with -Port.' }
