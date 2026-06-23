@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo JARVIS has not been set up yet, so there is no .venv Python to run the reset helper.
    echo You can still delete the data, recordings, screenshots, and logs folders manually if needed.
    echo.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" "scripts\reset_runtime_data.py"
set "EXITCODE=%ERRORLEVEL%"
echo.
pause
exit /b %EXITCODE%
