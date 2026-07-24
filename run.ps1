#!/usr/bin/env pwsh
<#
.SYNOPSIS
  TeleDecision Orchestrator -- local setup and run script (Windows PowerShell).

.DESCRIPTION
  Native PowerShell equivalent of run.sh, for machines without WSL/Git Bash.
  Run this from the project root (the folder containing app/, tests/, requirements.txt).

.PARAMETER TestOnly
  Install deps and run the test suite only -- do not start the server.

.PARAMETER NoInstall
  Skip dependency install (use when .venv is already set up).

.PARAMETER Port
  Port for the API server. Defaults to 8000.

.EXAMPLE
  .\run.ps1
.EXAMPLE
  .\run.ps1 -TestOnly
.EXAMPLE
  .\run.ps1 -Port 9000
#>

param(
    [switch]$TestOnly,
    [switch]$NoInstall,
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path "requirements.txt") -or -not (Test-Path "app")) {
    Write-Error "Run this from the project root (the folder with app/, tests/, requirements.txt)."
    exit 1
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    $python = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $python) {
    Write-Error "Python not found on PATH. Install Python 3.10+ from python.org (check 'Add to PATH' during install) and try again."
    exit 1
}
$pythonCmd = $python.Source
Write-Host "Using python: $pythonCmd ($(& $pythonCmd --version))"

$venvPython = Join-Path ".venv" "Scripts\python.exe"

if (-not $NoInstall) {
    if (-not (Test-Path ".venv")) {
        Write-Host "Creating virtual environment in .venv\ ..."
        & $pythonCmd -m venv .venv
    }
    if (-not (Test-Path $venvPython)) {
        Write-Error "Virtual environment creation failed -- $venvPython not found."
        exit 1
    }
    Write-Host "Installing dependencies from requirements.txt ..."
    & $venvPython -m pip install --quiet --upgrade pip
    & $venvPython -m pip install --quiet -r requirements.txt
} else {
    if (-not (Test-Path $venvPython)) {
        Write-Host "No .venv found and -NoInstall was passed -- falling back to system python."
        $venvPython = $pythonCmd
    }
}

Write-Host ""
Write-Host "Running test suite ..."
& $venvPython -m pytest tests/ -v
if ($LASTEXITCODE -ne 0) {
    Write-Error "Test suite failed (exit code $LASTEXITCODE)."
    exit $LASTEXITCODE
}
Write-Host ""
Write-Host "Test suite passed."

if ($TestOnly) {
    exit 0
}

Write-Host ""
Write-Host "Starting the API on http://127.0.0.1:$Port"
Write-Host "  Interactive docs: http://127.0.0.1:$Port/docs"
Write-Host "  Health check:     http://127.0.0.1:$Port/health"
Write-Host "  Press Ctrl+C to stop."
Write-Host ""
& $venvPython -m uvicorn app.main:app --reload --port $Port
