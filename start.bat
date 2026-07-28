@echo off
rem ============================================================
rem   VEDNIX AI - one-click launcher (Windows)
rem   Bas is file pe DOUBLE-CLICK karo. Na Ollama janna zaroori,
rem   na pip, na npm - neeche diye steps sab apne aap hote hain:
rem     1. Python check          5. Vednix Engine auto-install
rem     2. Backend venv + deps   6. Engine start + model download
rem     3. Node check            7. Backend + Frontend start
rem     4. Frontend install      8. Browser khud khul jayega
rem   Rokna ho to is window me Ctrl+C dabao.
rem ============================================================
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
echo   [X] Python nahi mila.
echo   [-] Ek baar install karo: https://www.python.org/downloads/
echo       (install karte waqt "Add python.exe to PATH" zaroor tick karo)
echo.
goto :pause

:end
if errorlevel 1 (
    echo.
    echo   Launcher ruk gaya - upar diya message padho, wahi fix karna hai.
    echo.
)

:pause
pause
