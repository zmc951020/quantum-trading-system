<#
.SYNOPSIS
    Aurora量化交易系统 - 数据库备份与归档定时任务脚本 (Windows)
.DESCRIPTION
    用于Windows任务计划程序定时执行数据库备份和归档
    支持 backup/archive/vacuum/full/status 五种模式
.PARAMETER Mode
    运行模式: backup, archive, vacuum, full, status
.EXAMPLE
    .\cron_backup.ps1 backup
    .\cron_backup.ps1 full
    .\cron_backup.ps1 status
.NOTES
    在Windows任务计划程序中设置:
    1. 打开"任务计划程序"
    2. 创建基本任务
    3. 触发器: 每天, 时间: 02:00
    4. 操作: 启动程序
       程序: powershell.exe
       参数: -ExecutionPolicy Bypass -File "D:\path\to\Aurora\cron_backup.ps1" full
#>

param(
    [Parameter(Position=0)]
    [ValidateSet('backup', 'archive', 'vacuum', 'full', 'status')]
    [string]$Mode = 'status'
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $ScriptDir "logs"
$LogFile = Join-Path $LogDir "cron_backup.log"

# 确保日志目录存在
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

# 日志函数
function Write-Log {
    param([string]$Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$Timestamp $Message" | Out-File -FilePath $LogFile -Append -Encoding utf8
    Write-Host "$Timestamp $Message"
}

# 执行Python脚本
function Invoke-PythonScript {
    param([string]$Code)
    $ScriptPath = Join-Path $env:TEMP "aurora_maintenance_$([System.Guid]::NewGuid().ToString('N')).py"
    try {
        $Code | Out-File -FilePath $ScriptPath -Encoding utf8
        $result = python $ScriptPath 2>&1
        if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne $null) {
            Write-Log "Python脚本执行失败 (ExitCode: $LASTEXITCODE)"
            return $false
        }
        return $result
    }
    catch {
        Write-Log "Python执行异常: $_"
        return $false
    }
    finally {
        if (Test-Path $ScriptPath) {
            Remove-Item $ScriptPath -Force -ErrorAction SilentlyContinue
        }
    }
}

# 执行备份
function Do-Backup {
    Write-Log "开始数据库备份..."
    $result = Invoke-PythonScript @"
import sys, os
sys.path.insert(0, r'$ScriptDir'.replace('\\', '/'))
from utils.db_maintenance import DatabaseMaintenanceScheduler
scheduler = DatabaseMaintenanceScheduler()
result = scheduler.perform_backup()
if result:
    print(f'备份成功: {result}')
else:
    print('备份失败')
    sys.exit(1)
"@
    if ($result) {
        Write-Log "备份完成: $result"
    } else {
        Write-Log "备份失败"
    }
}

# 执行归档
function Do-Archive {
    Write-Log "开始数据归档..."
    $result = Invoke-PythonScript @"
import sys, os
sys.path.insert(0, r'$ScriptDir'.replace('\\', '/'))
from utils.db_maintenance import DatabaseMaintenanceScheduler
scheduler = DatabaseMaintenanceScheduler()
result = scheduler.perform_archive()
total = sum(result.values())
print(f'归档完成，删除 {total} 条记录')
"@
    Write-Log "归档完成"
}

# 执行压缩
function Do-Vacuum {
    Write-Log "开始数据库压缩..."
    $result = Invoke-PythonScript @"
import sys, os
sys.path.insert(0, r'$ScriptDir'.replace('\\', '/'))
from utils.db_maintenance import DatabaseMaintenanceScheduler
scheduler = DatabaseMaintenanceScheduler()
result = scheduler.perform_vacuum()
print(f'压缩结果: {"成功" if result else "失败"}')
"@
    Write-Log "压缩完成"
}

# 执行完整维护
function Do-Full {
    Write-Log "开始完整数据库维护..."
    Do-Backup
    Do-Archive
    Do-Vacuum
    Write-Log "完整维护完成"
}

# 显示维护状态
function Do-Status {
    Invoke-PythonScript @"
import sys, os
sys.path.insert(0, r'$ScriptDir'.replace('\\', '/'))
from utils.db_maintenance import DatabaseMaintenanceScheduler
scheduler = DatabaseMaintenanceScheduler()
status = scheduler.get_maintenance_status()
print('=' * 50)
print('  数据库维护状态')
print('=' * 50)
print(f'  自动维护运行中: {"是" if status["is_running"] else "否"}')
print(f'  上次备份: {status["last_backup"] or "从未"}')
print(f'  下次备份: {status["next_backup"] or "未知"}')
print(f'  上次归档: {status["last_archive"] or "从未"}')
print(f'  下次归档: {status["next_archive"] or "未知"}')
print(f'  上次压缩: {status["last_vacuum"] or "从未"}')
print(f'  下次压缩: {status["next_vacuum"] or "未知"}')
print(f'  数据库大小: {status.get("database_size", {}).get("megabytes", 0)} MB')
print('=' * 50)
"@
}

# 主函数
Write-Log "===== 数据库维护任务开始 (Mode: $Mode) ====="

switch ($Mode) {
    'backup'  { Do-Backup }
    'archive' { Do-Archive }
    'vacuum'  { Do-Vacuum }
    'full'    { Do-Full }
    'status'  { Do-Status }
}

Write-Log "===== 数据库维护任务结束 ====="
