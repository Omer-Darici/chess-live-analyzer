# Build ChessLiveAnalyzer.exe with PyInstaller.
#   powershell -ExecutionPolicy Bypass -File build.ps1
#   powershell -ExecutionPolicy Bypass -File build.ps1 -OneDir   (faster startup)

param([switch]$OneDir)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$mode = if ($OneDir) { "--onedir" } else { "--onefile" }

python -m PyInstaller `
    --noconfirm `
    --clean `
    --noconsole `
    $mode `
    --name ChessLiveAnalyzer `
    --collect-all cv2 `
    --collect-all chess `
    --hidden-import pynput `
    --hidden-import pynput.keyboard `
    --hidden-import pynput.mouse `
    --hidden-import tkinter `
    --distpath dist `
    --workpath build `
    --specpath build `
    main.py

if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

if (Test-Path "dist\ChessLiveAnalyzer.exe") {
    $size = [math]::Round((Get-Item "dist\ChessLiveAnalyzer.exe").Length / 1MB, 1)
    Write-Host "OK -> dist\ChessLiveAnalyzer.exe  ($size MB)" -ForegroundColor Green
} else {
    throw "exe not produced"
}
