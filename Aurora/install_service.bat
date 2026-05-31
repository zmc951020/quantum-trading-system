@echo off
chcp 65001 >nul
title Aurora 量化系统 — Windows服务安装

:: ═══════════════════════════════════════════════════════
:: Aurora 量化交易系统 — Windows开机自启服务安装脚本
:: 使用NSSM (Non-Sucking Service Manager) 注册为Windows服务
:: ═══════════════════════════════════════════════════════

set "AURORA_DIR=%~dp0"
set "SERVICE_NAME=AuroraQuantServer"
set "PYTHON_EXE=%AURORA_DIR%aurora_venv\Scripts\python.exe"
set "START_SCRIPT=%AURORA_DIR%production_start.py"
set "NSSM_EXE=%AURORA_DIR%nssm.exe"

echo ============================================================
echo   Aurora 量化交易系统 — Windows服务安装
echo ============================================================
echo.

:: ── 步骤1: 检查Python虚拟环境 ──
echo [1/5] 检查Python环境...
if not exist "%PYTHON_EXE%" (
    echo [!] 未找到虚拟环境Python: %PYTHON_EXE%
    echo [!] 请先创建虚拟环境: python -m venv aurora_venv
    pause
    exit /b 1
)
echo [OK] Python路径: %PYTHON_EXE%

:: ── 步骤2: 检查NSSM是否存在 ──
echo [2/5] 检查NSSM...
if not exist "%NSSM_EXE%" (
    echo [!] NSSM未找到，正在从winget安装...
    winget install nssm --accept-source-agreements
    if errorlevel 1 (
        echo [!] winget安装失败，请手动下载NSSM: https://nssm.cc/download
        echo [!] 将 nssm.exe 放到: %AURORA_DIR%
        pause
        exit /b 1
    )
    :: 复制nssm到项目目录
    for /f "tokens=*" %%i in ('where nssm 2^>nul') do (
        copy "%%i" "%NSSM_EXE%" >nul 2>&1
        echo [OK] NSSM已安装并复制到项目目录
        goto :nssm_found
    )
    echo [!] 无法定位nssm.exe，请手动放置到 %AURORA_DIR%
    pause
    exit /b 1
)
:nssm_found
echo [OK] NSSM路径: %NSSM_EXE%

:: ── 步骤3: 停止旧服务（如果存在） ──
echo [3/5] 检查已有服务...
"%NSSM_EXE%" status "%SERVICE_NAME%" 2>nul | findstr /i "SERVICE_" >nul
if %errorlevel% equ 0 (
    echo [INFO] 发现已有服务，正在停止...
    "%NSSM_EXE%" stop "%SERVICE_NAME%" 2>nul
    timeout /t 3 /nobreak >nul
    "%NSSM_EXE%" remove "%SERVICE_NAME%" confirm 2>nul
    echo [OK] 旧服务已移除
) else (
    echo [INFO] 未发现已有服务
)

:: ── 步骤4: 安装新服务 ──
echo [4/5] 安装Aurora服务...

:: 安装服务
"%NSSM_EXE%" install "%SERVICE_NAME%" "%PYTHON_EXE%" "%START_SCRIPT%"
if errorlevel 1 (
    echo [!] 服务安装失败!
    pause
    exit /b 1
)

:: 设置服务显示名称
"%NSSM_EXE%" set "%SERVICE_NAME%" DisplayName "Aurora 量化交易系统"

:: 设置服务描述
"%NSSM_EXE%" set "%SERVICE_NAME%" Description "Aurora AI-Driven Quantitative Trading Platform — DeepSeek v4.0 + Smart Model Router"

:: 设置启动类型为自动（延迟启动，避免开机风暴）
"%NSSM_EXE%" set "%SERVICE_NAME%" Start SERVICE_AUTO_START

:: 设置工作目录
"%NSSM_EXE%" set "%SERVICE_NAME%" AppDirectory "%AURORA_DIR%"

:: 设置失败恢复策略：失败后重启，最多3次，间隔30秒
"%NSSM_EXE%" set "%SERVICE_NAME%" AppRestartDelay 30000
"%NSSM_EXE%" set "%SERVICE_NAME%" AppThrottle 60000

:: 设置标准输出日志
"%NSSM_EXE%" set "%SERVICE_NAME%" AppStdout "%AURORA_DIR%logs\service_stdout.log"
"%NSSM_EXE%" set "%SERVICE_NAME%" AppStderr "%AURORA_DIR%logs\service_stderr.log"

:: 设置优雅关闭超时（给风控守护进程时间清理）
"%NSSM_EXE%" set "%SERVICE_NAME%" AppStopMethodSkip 0
"%NSSM_EXE%" set "%SERVICE_NAME%" AppStopMethodConsole 15000
"%NSSM_EXE%" set "%SERVICE_NAME%" AppStopMethodWindow 15000

:: 设置环境变量
"%NSSM_EXE%" set "%SERVICE_NAME%" AppEnvironmentExtra "AURORA_ENV=production"

:: 设置依赖关系（如果安装了数据库服务）
:: "%NSSM_EXE%" set "%SERVICE_NAME%" DependOnService "MSSQLSERVER"

echo [OK] 服务配置完成

:: ── 步骤5: 启动服务 ──
echo [5/5] 启动Aurora服务...
"%NSSM_EXE%" start "%SERVICE_NAME%"
if errorlevel 1 (
    echo [!] 服务启动失败，请检查日志
    echo [INFO] 日志路径: %AURORA_DIR%logs\
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   安装完成！
echo ============================================================
echo.
echo   服务名称: %SERVICE_NAME%
echo   显示名称: Aurora 量化交易系统
echo   启动类型: 自动（延迟启动）
echo   崩溃恢复: 自动重启（最多3次）
echo   标准日志: logs\service_stdout.log
echo   错误日志: logs\service_stderr.log
echo.
echo   管理命令:
echo     启动服务: nssm start %SERVICE_NAME%
echo     停止服务: nssm stop %SERVICE_NAME%
echo     重启服务: nssm restart %SERVICE_NAME%
echo     查看状态: nssm status %SERVICE_NAME%
echo     卸载服务: nssm remove %SERVICE_NAME% confirm
echo     查看日志: type logs\service_stdout.log
echo.
echo   测试服务可用性:
echo     curl http://localhost:5000/health
echo.
echo ============================================================
pause