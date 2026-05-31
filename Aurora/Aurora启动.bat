@echo off
chcp 65001 >nul
title Aurora 量化交易系统
color 0A
echo.
echo ======================================================
echo.
echo     Aurora 量化交易系统 v2.0
echo.
echo ======================================================
echo.
echo 正在启动 Aurora 系统服务...
echo.

cd /d "%~dp0"
python production_start.py

if errorlevel 1 (
    echo.
    echo 启动失败！
    echo.
    pause
)
