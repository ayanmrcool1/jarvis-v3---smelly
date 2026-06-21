@echo off
cd /d C:\Jarvis

echo Starting J.A.R.V.I.S HUD...
start "J.A.R.V.I.S HUD" ".venv\Scripts\pythonw.exe" "app\jarvis_ui.py"

timeout /t 2 /nobreak >nul

echo Starting J.A.R.V.I.S Voice Core...
start /min "J.A.R.V.I.S Voice Core" ".venv\Scripts\python.exe" "app\phase1_audio_loop.py"

exit