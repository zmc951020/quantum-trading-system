<#
.SYNOPSIS
Ollama MemX 统一部署脚本（主控脚本）
.DESCRIPTION
这是MemX-Ollama的统一入口脚本，调用auto_deploy_final_fixed.ps1执行实际部署
.NOTES
建议使用此脚本作为唯一入口，其他deploy_*.ps1可以删除以避免混乱
#>

# 自动切换到脚本所在目录
$scriptPath = $MyInvocation.MyCommand.Definition
$scriptDir = Split-Path $scriptPath -Parent
Set-Location $scriptDir

Write-Host "=============================================================" -ForegroundColor Cyan
Write-Host "Ollama MemX 统一部署系统" -ForegroundColor Cyan
Write-Host "=============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "使用 auto_deploy_final_fixed.ps1 执行部署..." -ForegroundColor Yellow
Write-Host ""

# 调用最终修复版部署脚本
& "$scriptDir\auto_deploy_final_fixed.ps1"
