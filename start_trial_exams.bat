@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONNOUSERSITE=1
set PYTHONDONTWRITEBYTECODE=1
set "PY_RUN=.venv-windows\Scripts\python.exe"
if not exist "%PY_RUN%" set "PY_RUN=.venv\Scripts\python.exe"
if not exist "%PY_RUN%" (
  echo [ERROR] Run setup_windows.bat first.
  pause
  exit /b 1
)
echo [INFO] Start Docker Desktop and wait until it is ready before continuing.
echo [INFO] Checking the judge and opening the three saved practice exams...
"%PY_RUN%" -m app.programming_trial --apply
if errorlevel 1 (
  echo [ERROR] Practice exams were not opened. Stop any running server and check Docker Desktop.
  pause
  exit /b 1
)
echo [INFO] Open http://127.0.0.1:8080/login - account CHAMTHU01
"%PY_RUN%" -u run_server.py
pause
