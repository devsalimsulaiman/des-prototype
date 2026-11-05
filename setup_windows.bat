@echo off
setlocal
cd /d %~dp0

where python >nul 2>&1
if errorlevel 1 (
  echo Python was not found on PATH.
  echo Install Python 3.11 or 3.12 from python.org, tick "Add Python to PATH", then run this file again.
  pause
  exit /b 1
)

if not exist .venv\Scripts\python.exe (
  echo Creating local virtual environment...
  python -m venv .venv
)

call .venv\Scripts\activate
python -m pip install --upgrade pip
if errorlevel 1 goto :fail
python -m pip install -r requirements.txt
if errorlevel 1 goto :fail

echo.
echo Running detailed automated tests and controlled fault-detection checks...
python -u run_console_checks.py
if errorlevel 1 goto :fail

echo.
echo Recording installed package versions...
python -m pip freeze > environment_freeze.txt
echo.
echo Setup complete and tests passed.
echo Next: double-click launch_gui.bat
pause
exit /b 0

:fail
echo.
echo Setup did not complete successfully. Read the error above before continuing.
pause
exit /b 1
