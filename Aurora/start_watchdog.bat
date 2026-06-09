@echo off
chcp 65001 >nul
echo ========================================
echo   Aurora+QS-Robot 守护进程启动 (Windows)
echo ========================================
echo.

cd /d "%~dp0"

echo [启动中] 正在启动守护进程...
start "AuroraWatchdog" /B python aurora_watchdog_v2.py

echo [提示] 守护进程已在后台启动
echo [提示] 30秒后服务将在 http://127.0.0.1:5002 可用
echo [提示] 查看日志: logs\aurora_watchdog.log
echo.
echo 按任意键关闭此窗口（守护进程仍在后台运行）...
pause >nul
