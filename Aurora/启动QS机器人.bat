@echo off
chcp 65001 >nul
title QS Robot Desktop V3.0 - Aurora深度集成控制面板
echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║     🤖 QS Robot Desktop V3.0                       ║
echo ║     Aurora深度集成 — Web控制面板                   ║
echo ╚══════════════════════════════════════════════════════╝
echo.
echo   [1/3] 检查Python环境...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   [错误] 未找到Python，请先安装Python 3.9+
    pause
    exit /b 1
)
echo   [OK] Python已就绪

echo   [2/3] 安装依赖 (如需要)...
pip install flask aiohttp -q >nul 2>&1
echo   [OK] 依赖检查完成

echo   [3/3] 启动QS Robot Web控制台...
echo.
echo   🌐 控制面板地址: http://localhost:5001
echo   📌 按 Ctrl+C 或关闭此窗口停止
echo.
cd /d "%~dp0"
python qs_robot_desktop.py --port 5001

pause