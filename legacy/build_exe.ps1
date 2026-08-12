# MAIK Build Script — creates standalone .exe files
# Usage: .\build_exe.ps1

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host "=== MAIK .EXE Builder ===" -ForegroundColor Cyan

# Check for PyInstaller
$py = ".\venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    $py = ".\venv\Scripts\python.exe"
    if (-not (Test-Path $py)) {
        $py = "python"
    }
}

Write-Host "Using Python: $py" -ForegroundColor Yellow

# Install PyInstaller if needed
& $py -m pip install pyinstaller --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to install PyInstaller" -ForegroundColor Red
    exit 1
}

# Build CLI .exe
Write-Host "`nBuilding MAIK CLI (maik.exe)..." -ForegroundColor Cyan
& $py -m PyInstaller --onefile --name maik --icon NONE --hidden-import=litellm --hidden-import=fastapi --hidden-import=uvicorn --add-data "experts.toml;." maik_cli.py
if ($LASTEXITCODE -eq 0) {
    Write-Host "CLI .exe built: dist\maik.exe" -ForegroundColor Green
} else {
    Write-Host "CLI build failed" -ForegroundColor Red
    exit 1
}

# Build GUI .exe
Write-Host "`nBuilding MAIK GUI (maik-gui.exe)..." -ForegroundColor Cyan
& $py -m PyInstaller --onefile --name maik-gui --icon NONE --windowed --hidden-import=litellm --hidden-import=tkinter --hidden-import=fastapi --hidden-import=uvicorn --add-data "experts.toml;." maik_gui.py
if ($LASTEXITCODE -eq 0) {
    Write-Host "GUI .exe built: dist\maik-gui.exe" -ForegroundColor Green
} else {
    Write-Host "GUI build failed" -ForegroundColor Red
    exit 1
}

Write-Host "`n=== BUILD COMPLETE ===" -ForegroundColor Green
Write-Host "  dist\maik.exe       — CLI tool (add to PATH)" -ForegroundColor White
Write-Host "  dist\maik-gui.exe   — Desktop GUI" -ForegroundColor White
Write-Host "`nUsage: maik ask ""your question""" -ForegroundColor Cyan
