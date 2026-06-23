@echo off
setlocal

cd /d "%~dp0"

echo.
echo JARVIS setup
echo ============
echo.

where py >nul 2>nul
if not errorlevel 1 (
    py -3.11 -c "import sys; v=sys.version_info[:2]; raise SystemExit(0 if (3,11) <= v < (3,13) else 1)" >nul 2>nul
    if not errorlevel 1 (
        py -3.11 "%~dp0scripts\setup_jarvis.py"
        goto done
    )

    py -3.12 -c "import sys; v=sys.version_info[:2]; raise SystemExit(0 if (3,11) <= v < (3,13) else 1)" >nul 2>nul
    if not errorlevel 1 (
        py -3.12 "%~dp0scripts\setup_jarvis.py"
        goto done
    )
)

python -c "import sys; v=sys.version_info[:2]; raise SystemExit(0 if (3,11) <= v < (3,13) else 1)" >nul 2>nul
if not errorlevel 1 (
    python "%~dp0scripts\setup_jarvis.py"
    goto done
)

python3 -c "import sys; v=sys.version_info[:2]; raise SystemExit(0 if (3,11) <= v < (3,13) else 1)" >nul 2>nul
if not errorlevel 1 (
    python3 "%~dp0scripts\setup_jarvis.py"
    goto done
)

echo No supported Python was found.
echo Install Python 3.11 from https://www.python.org/downloads/ and run this file again.
echo During install, enable "Add python.exe to PATH" if the installer offers it.
set "EXITCODE=1"
goto finish

:done
set "EXITCODE=%ERRORLEVEL%"

:finish
echo.
if not "%EXITCODE%"=="0" (
    echo Setup did not complete successfully.
    echo Check the logs folder if it was created.
    echo.
)
pause
exit /b %EXITCODE%
