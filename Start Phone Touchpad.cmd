@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-phone.ps1"
  exit /b
)
".venv\Scripts\python.exe" -c "import aiohttp,qrcode,PIL" >nul 2>&1
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install -r requirements-phone.txt
  if errorlevel 1 (
    pause
    exit /b 1
  )
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\install_shortcut.ps1"
start "" ".venv\Scripts\pythonw.exe" -m mycursor --mode phone
