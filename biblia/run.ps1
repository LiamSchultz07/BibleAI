<#
    Biblia — start the app.  Run .\setup.ps1 first.
#>

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

$venvPy = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

if (-not (Test-Path $venvPy)) {
    Write-Host "No .venv found. Run .\setup.ps1 first." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path 'backend\data\bible.db')) {
    Write-Host "No corpus database found. Run .\setup.ps1 first." -ForegroundColor Red
    exit 1
}

if (-not $env:ANTHROPIC_API_KEY) {
    Write-Host @'
Note: ANTHROPIC_API_KEY is not set, so the chat pane will show the retrieval
layer's raw output instead of a written reply. Everything else works.
'@ -ForegroundColor Yellow
}

Write-Host "`nBiblia running at http://localhost:8000   (Ctrl+C to stop)`n" -ForegroundColor Cyan

Push-Location backend
try {
    & $venvPy -m uvicorn app.main:app --host 127.0.0.1 --port 8000
} finally { Pop-Location }
