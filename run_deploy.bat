@echo off
chcp 65001 >nul
echo.
echo ==============================================================
echo 🚀 启动 Ollama MemX 一键部署
 echo ==============================================================
echo.
echo [INFO] 正在启动 PowerShell 执行部署脚本...
echo [INFO] 请耐心等待，部署过程可能需要 5-10 分钟
echo [INFO] 窗口会保持打开，您可以看到完整的执行过程
echo.
pause

:: 切换到MemX-Ollama目录
cd MemX-Ollama
echo [INFO] 当前目录: %cd%
echo [INFO] 检查目录内容...
dir

:: 使用完整路径执行PowerShell脚本
echo [INFO] 执行部署脚本...
powershell.exe -ExecutionPolicy Bypass -NoExit -File "%cd%\auto_deploy_final_fixed.ps1"

:: 如果脚本执行完成，等待用户按任意键退出
echo.
echo ==============================================================
echo 🎉 部署脚本执行完成
echo ==============================================================
echo.
echo [INFO] 按任意键退出...
pause >nul