@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONUTF8=1

if not exist ".venv\Scripts\python.exe" (
  echo The local virtual environment has not been created yet.
  echo Run setup_windows.bat first so SimPy and pytest are installed.
  pause
  exit /b 1
)

call ".venv\Scripts\activate.bat"
python -u run_console_checks.py
set RESULT=%ERRORLEVEL%
echo.
if "%RESULT%"=="0" (
  echo All automated tests and controlled fault-detection checks passed.
) else (
  echo At least one check failed. Read the full per-test output and saved log above.
)
echo A timestamped log is saved under outputs\console_checks_...
echo A convenient copy is saved as outputs\RO3_console_test_log_latest.txt
pause
exit /b %RESULT%
