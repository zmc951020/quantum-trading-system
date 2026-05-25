#!/bin/bash
# ================================================================
# Aurora量化交易系统 - 数据库备份与归档定时任务脚本
# 用于Linux crontab定时执行数据库备份和归档
#
# 使用方法:
#   1. 编辑crontab: crontab -e
#   2. 添加以下行:
#      # 每天凌晨2点执行数据库备份
#      0 2 * * * /path/to/Aurora/cron_backup.sh backup
#
#      # 每周日凌晨3点执行归档
#      0 3 * * 0 /path/to/Aurora/cron_backup.sh archive
#
#      # 每月1日凌晨4点执行压缩
#      0 4 1 * * /path/to/Aurora/cron_backup.sh vacuum
#
#      # 每天凌晨2:30执行完整维护（备份+归档+压缩）
#      30 2 * * * /path/to/Aurora/cron_backup.sh full
#
#   3. 确保脚本有执行权限: chmod +x cron_backup.sh
# ================================================================

APP_DIR=$(dirname "$0")
LOG_DIR="$APP_DIR/logs"
PYTHON=$(which python3 2>/dev/null || which python 2>/dev/null)

# 确保日志目录存在
mkdir -p "$LOG_DIR"

# 日志函数
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_DIR/cron_backup.log"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# 检查Python是否可用
if [ -z "$PYTHON" ]; then
    log "错误: 未找到Python"
    exit 1
fi

# 执行备份
do_backup() {
    log "开始数据库备份..."
    cd "$APP_DIR"
    $PYTHON -c "
from utils.db_maintenance import DatabaseMaintenanceScheduler
scheduler = DatabaseMaintenanceScheduler()
result = scheduler.perform_backup()
if result:
    print(f'备份成功: {result}')
else:
    print('备份失败')
    exit(1)
" 2>&1 | tee -a "$LOG_DIR/cron_backup.log"
    log "备份完成"
}

# 执行归档
do_archive() {
    log "开始数据归档..."
    cd "$APP_DIR"
    $PYTHON -c "
from utils.db_maintenance import DatabaseMaintenanceScheduler
scheduler = DatabaseMaintenanceScheduler()
result = scheduler.perform_archive()
total = sum(result.values())
print(f'归档完成，删除 {total} 条记录')
" 2>&1 | tee -a "$LOG_DIR/cron_backup.log"
    log "归档完成"
}

# 执行压缩
do_vacuum() {
    log "开始数据库压缩..."
    cd "$APP_DIR"
    $PYTHON -c "
from utils.db_maintenance import DatabaseMaintenanceScheduler
scheduler = DatabaseMaintenanceScheduler()
result = scheduler.perform_vacuum()
print(f'压缩结果: {\"成功\" if result else \"失败\"}')
" 2>&1 | tee -a "$LOG_DIR/cron_backup.log"
    log "压缩完成"
}

# 执行完整维护
do_full() {
    log "开始完整数据库维护..."
    do_backup
    do_archive
    do_vacuum
    log "完整维护完成"
}

# 显示维护状态
do_status() {
    cd "$APP_DIR"
    $PYTHON -c "
from utils.db_maintenance import DatabaseMaintenanceScheduler
scheduler = DatabaseMaintenanceScheduler()
status = scheduler.get_maintenance_status()
print('=' * 50)
print('  数据库维护状态')
print('=' * 50)
print(f'  自动维护运行中: {\"是\" if status[\"is_running\"] else \"否\"}')
print(f'  上次备份: {status[\"last_backup\"] or \"从未\"}')
print(f'  下次备份: {status[\"next_backup\"] or \"未知\"}')
print(f'  上次归档: {status[\"last_archive\"] or \"从未\"}')
print(f'  下次归档: {status[\"next_archive\"] or \"未知\"}')
print(f'  上次压缩: {status[\"last_vacuum\"] or \"从未\"}')
print(f'  下次压缩: {status[\"next_vacuum\"] or \"未知\"}')
print(f'  数据库大小: {status.get(\"database_size\", {}).get(\"megabytes\", 0)} MB')
print('=' * 50)
" 2>&1 | tee -a "$LOG_DIR/cron_backup.log"
}

# 主函数
case "$1" in
    backup)
        do_backup
        ;;
    archive)
        do_archive
        ;;
    vacuum)
        do_vacuum
        ;;
    full)
        do_full
        ;;
    status)
        do_status
        ;;
    *)
        echo "使用方法: $0 {backup|archive|vacuum|full|status}"
        echo ""
        echo "命令说明:"
        echo "  backup  - 执行数据库备份"
        echo "  archive - 执行旧数据归档"
        echo "  vacuum  - 执行数据库压缩"
        echo "  full    - 执行完整维护（备份+归档+压缩）"
        echo "  status  - 查看维护状态"
        exit 1
        ;;
esac

exit 0
