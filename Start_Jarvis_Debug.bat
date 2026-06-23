@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo JARVIS has not been set up yet.
    echo Run Setup_Jarvis.bat first.
    echo.
    pause
    exit /b 1
)

echo Starting JARVIS in live debug mode...
echo.
".venv\Scripts\python.exe" "scripts\launch_jarvis.py" --hud web --debug
set "EXITCODE=%ERRORLEVEL%"

echo.
echo Debug session ended.
pause
exit /b %EXITCODE%
