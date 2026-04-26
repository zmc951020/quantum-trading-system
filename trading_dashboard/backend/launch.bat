@echo off

echo === Trading Dashboard Launch Script ===
echo.
echo 1. Starting backend server...
echo Backend URL: http://localhost:8000
echo.

REM Start backend server
start "Backend Server" python simple_backend.py

REM Wait for backend to start
timeout /t 3 /nobreak > nul

echo 2. Starting frontend server...
echo Frontend URL: http://localhost:3000
echo.

REM Start frontend server
cd ..\frontend
start "Frontend Server" python -m http.server 3000

echo === Servers Started ===
echo Backend: http://localhost:8000
echo Frontend: http://localhost:3000
echo.
echo Servers are running in background
echo Press any key to exit...
pause > nul
