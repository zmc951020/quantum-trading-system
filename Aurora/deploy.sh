#!/bin/bash
"""
Aurora量化交易系统部署脚本
用于生产环境的启动、停止和重启
"""

# 配置
APP_NAME="aurora_quant"
APP_DIR=$(dirname "$0")
LOG_DIR="$APP_DIR/logs"
PID_FILE="$APP_DIR/gunicorn.pid"

# 确保日志目录存在
mkdir -p "$LOG_DIR"

# 启动服务
start() {
    echo "正在启动 $APP_NAME..."
    
    # 检查是否已在运行
    if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        echo "$APP_NAME 已经在运行中"
        return 1
    fi
    
    # 启动Gunicorn
    cd "$APP_DIR"
    gunicorn -c gunicorn.conf.py visualization:app --pid "$PID_FILE"
    
    echo "$APP_NAME 启动成功"
    echo "访问地址: http://0.0.0.0:8000"
}

# 停止服务
stop() {
    echo "正在停止 $APP_NAME..."
    
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 $PID 2>/dev/null; then
            kill $PID
            rm "$PID_FILE"
            echo "$APP_NAME 已停止"
        else
            rm "$PID_FILE"
            echo "$APP_NAME 未运行，已清理PID文件"
        fi
    else
        echo "$APP_NAME 未运行"
    fi
}

# 重启服务
restart() {
    stop
    sleep 2
    start
}

# 查看状态
status() {
    if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        echo "$APP_NAME 正在运行"
        echo "PID: $(cat "$PID_FILE")"
    else
        echo "$APP_NAME 未运行"
    fi
}

# 查看日志
logs() {
    if [ -f "$LOG_DIR/gunicorn_error.log" ]; then
        tail -f "$LOG_DIR/gunicorn_error.log"
    else
        echo "日志文件不存在"
    fi
}

# ===== 数据库维护 =====

# 执行数据库备份
backup() {
    echo "正在执行数据库备份..."
    cd "$APP_DIR"
    python3 -c "
from utils.db_maintenance import DatabaseMaintenanceScheduler
scheduler = DatabaseMaintenanceScheduler()
result = scheduler.perform_backup()
if result:
    print(f'备份成功: {result}')
else:
    print('备份失败')
    exit(1)
"
}

# 执行数据归档
archive() {
    echo "正在执行数据归档..."
    cd "$APP_DIR"
    python3 -c "
from utils.db_maintenance import DatabaseMaintenanceScheduler
scheduler = DatabaseMaintenanceScheduler()
result = scheduler.perform_archive()
total = sum(result.values())
print(f'归档完成，删除 {total} 条记录')
"
}

# 执行数据库压缩
vacuum() {
    echo "正在执行数据库压缩..."
    cd "$APP_DIR"
    python3 -c "
from utils.db_maintenance import DatabaseMaintenanceScheduler
scheduler = DatabaseMaintenanceScheduler()
result = scheduler.perform_vacuum()
print(f'压缩结果: {\"成功\" if result else \"失败\"}')
"
}

# 执行完整维护
maintenance() {
    echo "正在执行完整数据库维护..."
    cd "$APP_DIR"
    python3 -c "
from utils.db_maintenance import DatabaseMaintenanceScheduler
scheduler = DatabaseMaintenanceScheduler()
results = scheduler.check_and_maintain()
print(f'备份: {\"成功\" if results.get(\"backup\") else \"跳过/失败\"}')
print(f'归档: {\"成功\" if results.get(\"archive\") else \"跳过/失败\"}')
print(f'压缩: {\"成功\" if results.get(\"vacuum\") else \"跳过/失败\"}')
"
}

# 查看维护状态
maintenance_status() {
    cd "$APP_DIR"
    python3 -c "
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
"
}

# 启动维护守护进程
maintenance_daemon() {
    echo "正在启动数据库维护守护进程..."
    cd "$APP_DIR"
    python3 -c "
from utils.db_maintenance import DatabaseMaintenanceScheduler
scheduler = DatabaseMaintenanceScheduler()
scheduler.start_auto_maintenance(interval_minutes=60)
print('维护守护进程已启动 (检查间隔: 60分钟)')
import time
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    scheduler.stop_auto_maintenance()
    print('维护守护进程已停止')
"
}

# 帮助信息
help() {
    echo "使用方法: $0 {start|stop|restart|status|logs|backup|archive|vacuum|maintenance|maint-status|maint-daemon}"
    echo ""
    echo "服务管理:"
    echo "  start          - 启动服务"
    echo "  stop           - 停止服务"
    echo "  restart        - 重启服务"
    echo "  status         - 查看服务状态"
    echo "  logs           - 查看错误日志"
    echo ""
    echo "数据库维护:"
    echo "  backup         - 执行数据库备份"
    echo "  archive        - 执行旧数据归档"
    echo "  vacuum         - 执行数据库压缩"
    echo "  maintenance    - 执行完整维护（备份+归档+压缩）"
    echo "  maint-status   - 查看维护状态"
    echo "  maint-daemon   - 启动维护守护进程"
    echo ""
    echo "其他:"
    echo "  help           - 显示此帮助信息"
}

# 主函数
case "$1" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    status)
        status
        ;;
    logs)
        logs
        ;;
    backup)
        backup
        ;;
    archive)
        archive
        ;;
    vacuum)
        vacuum
        ;;
    maintenance)
        maintenance
        ;;
    maint-status)
        maintenance_status
        ;;
    maint-daemon)
        maintenance_daemon
        ;;
    help|*)
        help
        ;;
esac
