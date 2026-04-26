@echo off

echo === 量化交易仪表盘启动脚本 ===
echo.
echo 1. 启动后端服务...
echo 后端服务地址: http://localhost:8000
echo.

REM 启动后端服务
start "Backend Server" python simple_backend.py

REM 等待后端服务启动
ping 127.0.0.1 -n 3 > nul

echo 2. 启动前端服务器...
echo 前端地址: http://localhost:3000
echo.

REM 启动前端服务器
cd ..\frontend
start "Frontend Server" python -m http.server 3000

echo === 服务已启动 ===
echo 后端服务: http://localhost:8000
echo 前端服务: http://localhost:3000
echo.
echo 服务已在后台运行
 echo 按任意键退出...
pause > nul
