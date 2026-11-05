@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONUTF8=1

if not exist ".venv\Scripts\python.exe" (
  echo The local virtual environment has not been created yet.
  echo Run setup_windows.bat first so SimPy is installed.
  pause
  exit /b 1
)

call ".venv\Scripts\activate.bat"
python -u run_fault_detection_demo.py
set RESULT=%ERRORLEVEL%
echo.
if "%RESULT%"=="0" (
  echo Positive control passed and all five injected defects were detected.
) else (
  echo Fault-detection demonstration failed. Review the check details above.
)
echo Detailed CSV evidence is saved under outputs\RO3_fault_detection_...
pause
exit /b %RESULT%
