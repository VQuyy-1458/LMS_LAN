@echo off
setlocal
chcp 65001 >nul
title LMS_LAN - Tao du lieu demo
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONNOUSERSITE=1
set PYTHONDONTWRITEBYTECODE=1
set "LMS_PYTHON="
for %%P in (".venv-windows\Scripts\python.exe" ".venv\Scripts\python.exe") do (
    if not defined LMS_PYTHON if exist "%%~P" (
        "%%~P" -c "import jinja2" >nul 2>&1
        if not errorlevel 1 set "LMS_PYTHON=%%~P"
    )
)
if not defined LMS_PYTHON (
    echo [ERROR] Run setup_windows.bat first.
    pause
    exit /b 1
)
echo Close the LMS web server before creating demo data.
"%LMS_PYTHON%" -u -m scripts.seed_full_demo_once
if errorlevel 1 (
    echo [ERROR] Demo data was not created. See the message above.
    pause
    exit /b 1
)
echo.
echo [OK] Demo data is ready. Student DEMO001 to DEMO010: password 01012005.
echo Create an admin with "%LMS_PYTHON%" -m app.setup_admin if needed.
pause
