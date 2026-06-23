@echo off
setlocal

cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" "scripts\stop_jarvis.py"
) else (
    python "scripts\stop_jarvis.py"
)

set "EXITCODE=%ERRORLEVEL%"
echo.
pause
exit /b %EXITCODE%
