@echo off

REM 量化交易系统启动脚本
REM 启动API服务和相关组件

echo ======================================
echo 📊 量化交易策略系统启动脚本
echo ======================================

REM 设置环境变量
set PYTHONPATH=%PYTHONPATH%;.

REM 检查Python是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 错误: 未找到Python
    pause
    exit /b 1
)

echo ✅ Python检查通过

REM 安装依赖
if not exist "requirements.txt" (
    echo ⚠️  未找到requirements.txt，跳过依赖安装
) else (
    echo 📦 安装依赖...
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo ⚠️  依赖安装失败，继续启动
    ) else (
        echo ✅ 依赖安装成功
    )
)

REM 启动API服务
echo 🚀 启动API服务...
python main.py

pause
