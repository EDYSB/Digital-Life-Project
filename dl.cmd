@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [dl] Python 3.10+ was not found in PATH.
    exit /b 1
)

if "%~1"=="" (
    python -m suoling.cli help
    exit /b 0
)

python -m suoling.cli %*
exit /b %ERRORLEVEL%