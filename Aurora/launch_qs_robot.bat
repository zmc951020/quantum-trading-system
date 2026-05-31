@echo off
title QS Robot V3.0

echo.
echo ==============================================================
echo    QS Robot Desktop V3.0
echo    Aurora Deep Integration Control Panel
echo ==============================================================
echo.

echo    [1/3] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo    [ERROR] Python not found
    pause
    exit /b 1
)
echo    [OK] Python ready

echo    [2/3] Checking dependencies...
pip install flask aiohttp -q >nul 2>&1
echo    [OK] Dependencies OK

echo    [3/3] Starting QS Robot Server...
echo.

cd /d "%~dp0"

start "QS-Robot-Server" python qs_robot_desktop.py --port 5001

echo    Waiting 5 seconds for server to start...
ping -n 6 127.0.0.1 >nul

echo    Opening browser: http://localhost:5001
start http://localhost:5001

echo.
echo    Done! The Control Panel is now open in your browser.
echo    Close the "QS-Robot-Server" window to stop.
echo.
pause