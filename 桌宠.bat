@echo off
setlocal
cd /d "%~dp0"
title Digital Life Pet

where python >nul 2>nul
if errorlevel 1 (
    echo [Pet] Python 3.10+ was not found in PATH.
    pause
    exit /b 1
)

python -m suoling.pet
if errorlevel 1 (
    echo.
    echo [Pet] Failed to open the pet window.
    pause
)
exit /b 0