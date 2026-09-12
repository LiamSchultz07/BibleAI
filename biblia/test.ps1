<#
    Biblia — run the verification suite (118 tests).
#>

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

$venvPy = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) {
    Write-Host "No .venv found. Run .\setup.ps1 first." -ForegroundColor Red
    exit 1
}

Push-Location backend
try { & $venvPy -m pytest -q } finally { Pop-Location }
