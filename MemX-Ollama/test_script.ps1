# 测试脚本
Write-Host "测试PowerShell脚本执行..."
Write-Host "当前目录: $(Get-Location)"

# 检查Docker是否运行
try {
    docker info | Out-Null
    Write-Host "Docker已运行"
} catch {
    Write-Host "Docker未运行，请先启动Docker Desktop"
}

# 检查文件是否存在
if (Test-Path "main.py") {
    Write-Host "main.py文件存在"
} else {
    Write-Host "main.py文件不存在"
}

Read-Host "按Enter键退出..."