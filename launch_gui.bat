@echo off
setlocal
cd /d %~dp0
if not exist .venv\Scripts\python.exe (
  echo The local environment has not been created yet.
  echo Run setup_windows.bat first.
  pause
  exit /b 1
)
call .venv\Scripts\activate
python -m streamlit run app.py
