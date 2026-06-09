@echo off
chcp 65001 >nul
echo ========================================
echo  Aurora+QS-Robot 系统启动 (5002端口)
echo ========================================
cd /d %~dp0
echo 工作目录: %cd%
echo.
echo 正在启动 Aurora 服务...
python production_start.py
echo.
echo 服务已退出 (退出码: %ERRORLEVEL%)
pause
