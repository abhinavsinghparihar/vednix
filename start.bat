@echo off
rem Vednix AI one-click launcher for Windows. Requires Python 3.11+ and Node 20+.
rem Creates the project venv, installs dependencies, then starts the API and web app.
title VEDNIX AI - Launcher
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 scripts\launch.py
    goto :end
)

where python >nul 2>nul
if %errorlevel%==0 (
    python scripts\launch.py
    goto :end
)

echo.
echo   Python 3.11+ was not found: https://www.python.org/downloads/
echo   During installation, enable "Add python.exe to PATH".
echo.
goto :pause

:end
if errorlevel 1 (
    echo.
    echo   Launcher stopped. Read the error above and retry.
    echo.
)

:pause
pause
