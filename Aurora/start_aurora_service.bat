@echo off
chcp 65001 >nul
title Aurora+QS-Robot 守护进程 (5002端口)

echo ========================================
echo   Aurora+QS-Robot 系统启动
echo   端口: 5002
echo   功能: 开机自启 + 崩溃自动重启
echo ========================================
echo.

cd /d %~dp0
echo 工作目录: %cd%
echo.
echo 正在启动守护进程...
echo 该进程将监控主进程，如遇崩溃会自动重启
echo.

python aurora_watchdog.py

echo.
echo 守护进程已退出 (退出码: %ERRORLEVEL%)
pause
