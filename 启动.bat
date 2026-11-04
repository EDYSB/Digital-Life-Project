@echo off
setlocal
cd /d "%~dp0"
title EchoMind

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo [EchoMind] Python 3.10+ was not found in PATH.
    echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
    echo.
    pause
    exit /b 1
)

python app.py serve
if errorlevel 1 (
    echo.
    echo [EchoMind] Startup failed. See the message above.
    pause
    exit /b 1
)
exit /b 0