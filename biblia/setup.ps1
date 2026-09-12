<#
    Biblia — Windows setup.

    The Unix side of this project uses a Makefile; `make` is not present on
    Windows by default, so this script is the equivalent. Run it once:

        .\setup.ps1

    then start the app with:

        .\run.ps1

    Everything installs into a project-local .venv, so nothing touches your
    system Python.
#>

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

function Write-Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "  $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  $msg" -ForegroundColor Yellow }

# ---------------------------------------------------------------------------
# locate a usable Python
# ---------------------------------------------------------------------------
# Windows makes this genuinely annoying: `python` is often a Microsoft Store
# stub that opens the Store instead of running anything, and `py` (the official
# launcher) is the only reliable entry point when several versions are
# installed. Each candidate is therefore *executed* and its version parsed,
# rather than trusted because the name resolves.

function Find-Python {
    $candidates = @(
        @{ Cmd = 'py';      Args = @('-3') },
        @{ Cmd = 'python';  Args = @() },
        @{ Cmd = 'python3'; Args = @() }
    )
    foreach ($c in $candidates) {
        if (-not (Get-Command $c.Cmd -ErrorAction SilentlyContinue)) { continue }
        try {
            # Splatting requires a *variable* (@name). Writing @($c.Args + '--version')
            # is array-subexpression syntax instead, which passes one joined string
            # as a single argument and breaks `py -3 --version`.
            $probeArgs = @($c.Args) + '--version'
            $out = & $c.Cmd @probeArgs 2>&1 | Out-String
        } catch { continue }
        if ($out -match 'Python (\d+)\.(\d+)') {
            $major = [int]$Matches[1]; $minor = [int]$Matches[2]
            if ($major -eq 3 -and $minor -ge 10) {
                return @{ Cmd = $c.Cmd; Args = $c.Args; Version = "$major.$minor" }
            }
        }
    }
    return $null
}

Write-Step 'Checking prerequisites'

$py = Find-Python
if (-not $py) {
    Write-Host @'
  Python 3.10 or newer was not found.

  Install it with:
      winget install Python.Python.3.12

  Then CLOSE this terminal and open a new one so PATH updates, and re-run
  .\setup.ps1
'@ -ForegroundColor Red
    exit 1
}
Write-Ok "Python $($py.Version)"

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host @'
  Node.js was not found.

  Install it with:
      winget install OpenJS.NodeJS.LTS

  Then CLOSE this terminal, open a new one, and re-run .\setup.ps1
'@ -ForegroundColor Red
    exit 1
}
Write-Ok "Node $(node --version)"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host @'
  Git was not found.

  Install it with:
      winget install Git.Git

  Then CLOSE this terminal, open a new one, and re-run .\setup.ps1
'@ -ForegroundColor Red
    exit 1
}
Write-Ok "Git $((git --version) -replace 'git version ','')"

# ---------------------------------------------------------------------------
# virtualenv + Python dependencies
# ---------------------------------------------------------------------------

$venvPy = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

Write-Step 'Creating virtual environment'
if (-not (Test-Path $venvPy)) {
    $venvArgs = @($py.Args) + @('-m', 'venv', '.venv')
    & $py.Cmd @venvArgs
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create the virtual environment.' }
    Write-Ok 'Created .venv'
} else {
    Write-Ok '.venv already exists'
}

Write-Step 'Installing Python packages'
& $venvPy -m pip install --upgrade pip --quiet
& $venvPy -m pip install -r backend\requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'pip install failed.' }

# ---------------------------------------------------------------------------
# frontend dependencies
# ---------------------------------------------------------------------------

Write-Step 'Installing frontend packages'
Push-Location frontend
try {
    npm install
    if ($LASTEXITCODE -ne 0) { throw 'npm install failed.' }
} finally { Pop-Location }

# ---------------------------------------------------------------------------
# Bible texts
# ---------------------------------------------------------------------------

Write-Step 'Downloading the Bible texts (about 360 MB, one time)'
if (Test-Path 'sources\.git') {
    Write-Ok 'sources/ already present, pulling any updates'
    git -C sources pull --ff-only
} else {
    git clone --depth 1 https://github.com/seven1m/open-bibles.git sources
    if ($LASTEXITCODE -ne 0) { throw 'Failed to clone the Bible texts.' }
}

# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------

Write-Step 'Building the corpus database (about 30 seconds)'
Push-Location backend
try {
    & $venvPy -m app.ingest.run --source-dir ..\sources
    if ($LASTEXITCODE -ne 0) { throw 'Corpus build failed.' }
} finally { Pop-Location }

Write-Step 'Building the frontend'
Push-Location frontend
try {
    npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
} finally { Pop-Location }

Write-Host @'

===============================================
  Setup complete.

  Start the app:      .\run.ps1
  Then open:          http://localhost:8000

  To enable conversation, set your API key first:
      $env:ANTHROPIC_API_KEY = "sk-ant-..."
      .\run.ps1
===============================================
'@ -ForegroundColor Green
