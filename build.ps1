# Build MolPlayer with PyInstaller (Windows)
# Usage: right-click -> Run with PowerShell, or .\build.ps1

$ErrorActionPreference = "Stop"

Write-Host "=== MolPlayer PyInstaller build ===" -ForegroundColor Cyan

# Ensure deps
python -m pip install -r requirements.txt --quiet

$dist = "dist"
if (Test-Path $dist) { Remove-Item -Recurse -Force $dist }

# --onedir is recommended for speed and fewer AV false positives
# --windowed hides console
# --icon uses our generated one

$icon = "assets/icon.ico"
if (-not (Test-Path $icon)) {
    Write-Host "Warning: no icon.ico, building without custom icon" -ForegroundColor Yellow
    $iconArg = ""
} else {
    $iconArg = "--icon=`"$icon`""
}

Write-Host "Running PyInstaller (onedir + windowed + noupx)..." -ForegroundColor Green

# --noupx is important: UPX-compressed executables are heavily flagged by antiviruses
$cmd = "pyinstaller --clean --noconfirm --name MolPlayer --onedir --windowed --noupx --version-file=version_info.txt $iconArg main.py"
Write-Host $cmd
Invoke-Expression $cmd

if (Test-Path "dist/MolPlayer/MolPlayer.exe") {
    Write-Host "`n=== BUILD SUCCESS ===" -ForegroundColor Green
    Write-Host "Portable folder: dist/MolPlayer/" -ForegroundColor Green

    # Add useful files into the portable folder before zipping
    Copy-Item "README.md" "dist/MolPlayer/README.txt" -Force -ErrorAction SilentlyContinue

    @"
MolPlayer - Portable version

1. Просто запусти MolPlayer.exe (или MolPlayer.bat)
2. Ничего устанавливать не нужно.

Если Windows Defender / антивирус ругается:
- Нажми "Подробнее" → "Выполнить в любом случае"
- Или добавь эту папку в исключения Windows Defender

Подробности — в README.txt
"@ | Out-File -Encoding UTF8 "dist/MolPlayer/HOW_TO_RUN.txt"

    # Convenient launcher (double-click friendly)
    @"
@echo off
cd /d "%~dp0"
start "" MolPlayer.exe
"@ | Out-File -Encoding ASCII "dist/MolPlayer/MolPlayer.bat"

    # Create a clean zip for easy transfer between computers
    $version = "0.5"   # bump manually when releasing (match APP_VERSION in constants)
    $zipName = "MolPlayer-v$version-portable.zip"
    $zipPath = "releases\$zipName"

    if (-not (Test-Path "releases")) { New-Item -ItemType Directory -Path "releases" | Out-Null }

    # Remove old zip if exists
    if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

    # Zip the entire MolPlayer folder (this is what you send to others)
    Compress-Archive -Path "dist/MolPlayer" -DestinationPath $zipPath -Force

    # Also create a stable name for auto-updater
    $stableZip = "releases\MolPlayer-portable.zip"
    Copy-Item $zipPath $stableZip -Force

    # === Try to build Windows installer (Inno Setup) if available ===
    $isccPaths = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 5\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 5\ISCC.exe"
    )

    $iscc = $isccPaths | Where-Object { Test-Path $_ } | Select-Object -First 1

    if ($iscc) {
        Write-Host "Inno Setup found at $iscc - building installer..." -ForegroundColor Green
        $issFile = "installer\MolPlayer.iss"
        if (Test-Path $issFile) {
            & $iscc $issFile "/DMyAppVersion=$version" | Out-Null
            $setupExe = "releases\MolPlayer-v$version-setup.exe"
            if (Test-Path $setupExe) {
                Write-Host "Installer created: $setupExe" -ForegroundColor Green
            }
        }
    } else {
        Write-Host "Inno Setup not found. To build the .exe installer, install Inno Setup and run build again." -ForegroundColor Yellow
        Write-Host "Download: https://jrsoftware.org/isinfo.php" -ForegroundColor Yellow
    }

    Write-Host "`n=== PACKAGE CREATED ===" -ForegroundColor Cyan
    Write-Host "Ready to distribute: $zipPath" -ForegroundColor Green
    Write-Host "Just send this zip to another PC, extract anywhere, run MolPlayer.exe" -ForegroundColor Yellow
} else {
    Write-Host "Build may have failed. Check above output." -ForegroundColor Red
}
