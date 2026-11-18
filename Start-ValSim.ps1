param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8765,
    [switch]$Setup
)

$ErrorActionPreference = 'Stop'
$valSimRoot = $PSScriptRoot
$valSimPython = Join-Path $valSimRoot '.venv\Scripts\python.exe'

Push-Location -LiteralPath $valSimRoot
try {
    if ($Setup -or -not (Test-Path -LiteralPath $valSimPython)) {
        if (-not (Test-Path -LiteralPath $valSimPython)) {
            python -m venv .venv
            if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
        }
        & $valSimPython -m pip install -r requirements.txt
        if ($LASTEXITCODE -ne 0) { throw 'Could not install the Python dependencies.' }
    }
    if ($Setup -or -not (Test-Path -LiteralPath (Join-Path $valSimRoot 'frontend\dist\index.html'))) {
        Push-Location -LiteralPath (Join-Path $valSimRoot 'frontend')
        try {
            npm.cmd ci --no-audit --no-fund
            if ($LASTEXITCODE -ne 0) { throw 'Could not install the frontend dependencies.' }
            npm.cmd run build
            if ($LASTEXITCODE -ne 0) { throw 'Could not build the frontend.' }
        } finally {
            Pop-Location
        }
    }
    Write-Host "ValSim is available at http://127.0.0.1:$Port once the server starts."
    & $valSimPython -m uvicorn backend.valsim.api:app --host 127.0.0.1 --port $Port
    if ($LASTEXITCODE -ne 0) { throw 'The ValSim server exited with an error.' }
} finally {
    Pop-Location
}
