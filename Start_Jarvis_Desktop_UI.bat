@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    echo JARVIS has not been set up yet.
    echo Run Setup_Jarvis.bat first.
    echo.
    pause
    exit /b 1
)

if not exist ".env" (
    echo JARVIS is missing its .env file.
    echo Run Setup_Jarvis.bat first.
    echo.
    pause
    exit /b 1
)

start "" ".venv\Scripts\pythonw.exe" "scripts\launch_jarvis.py" --hud desktop --detached
exit /b 0
