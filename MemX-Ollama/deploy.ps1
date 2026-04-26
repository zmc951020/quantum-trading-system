# Ollama权限系统部署脚本 (Windows版本)
# 工业级部署工具

Write-Host "============================================"
Write-Host "Ollama权限系统部署脚本"
Write-Host "工业级部署工具 v1.0"
Write-Host "============================================"

# 检查PowerShell版本
if ($PSVersionTable.PSVersion.Major -lt 5) {
    Write-Host "错误: 需要PowerShell 5.0或更高版本" -ForegroundColor Red
    exit 1
}

# 检查Python环境
function Check-Python {
    try {
        $pythonVersion = python --version 2>&1
        Write-Host "Python 版本: $pythonVersion"
        return $true
    } catch {
        Write-Host "错误: Python 未安装" -ForegroundColor Red
        return $false
    }
}

# 检查pip
function Check-Pip {
    try {
        $pipVersion = pip --version 2>&1
        Write-Host "pip 版本: $pipVersion"
        return $true
    } catch {
        Write-Host "错误: pip 未安装" -ForegroundColor Red
        return $false
    }
}

# 安装依赖
function Install-Dependencies {
    Write-Host "安装Python依赖..."
    
    # 创建requirements.txt
    @"
fastapi
uvicorn
pydantic
cryptography
redis
prometheus-client
"@ | Out-File -FilePath requirements.txt -Encoding UTF8
    
    try {
        pip install -r requirements.txt
        Write-Host "✓ 依赖安装成功" -ForegroundColor Green
        return $true
    } catch {
        Write-Host "错误: 依赖安装失败" -ForegroundColor Red
        return $false
    }
}

# 配置验证
function Validate-Config {
    Write-Host "验证配置..."
    
    # 创建默认配置文件
    @"
# Redis配置
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=2

# 日志配置
LOG_LEVEL=INFO

# 安全配置
HMAC_SECRET=your_hmac_secret_here
"@ | Out-File -FilePath .env -Encoding UTF8
    
    Write-Host "✓ 配置文件创建成功" -ForegroundColor Green
    Write-Host "⚠ 请修改 .env 文件中的 HMAC_SECRET 为安全的随机密钥" -ForegroundColor Yellow
    return $true
}

# 启动服务
function Start-Service {
    Write-Host "启动服务..."
    
    # 创建启动脚本
    @"
@echo off
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"@ | Out-File -FilePath start.bat -Encoding UTF8
    
    Write-Host "启动脚本创建成功: .\start.bat" -ForegroundColor Green
    Write-Host "使用以下命令启动服务:" -ForegroundColor Cyan
    Write-Host "  .\start.bat" -ForegroundColor Cyan
    
    return $true
}

# 主流程
function Main {
    if (-not (Check-Python)) { return 1 }
    if (-not (Check-Pip)) { return 1 }
    if (-not (Install-Dependencies)) { return 1 }
    if (-not (Validate-Config)) { return 1 }
    if (-not (Start-Service)) { return 1 }
    
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "部署完成!" -ForegroundColor Green
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "下一步:" -ForegroundColor Cyan
    Write-Host "1. 修改 .env 文件中的配置" -ForegroundColor Cyan
    Write-Host "2. 运行 .\start.bat 启动服务" -ForegroundColor Cyan
    Write-Host "3. 访问 http://localhost:8000/docs 查看API文档" -ForegroundColor Cyan
    Write-Host "4. 访问 http://localhost:8001 查看监控指标" -ForegroundColor Cyan
    Write-Host "============================================" -ForegroundColor Green
    return 0
}

# 执行主流程
Main
