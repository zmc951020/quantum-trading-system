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

# 帮助信息
help() {
    echo "使用方法: $0 {start|stop|restart|status|logs}"
    echo ""
    echo "命令说明:"
    echo "  start    - 启动服务"
    echo "  stop     - 停止服务"
    echo "  restart  - 重启服务"
    echo "  status   - 查看服务状态"
    echo "  logs     - 查看错误日志"
    echo "  help     - 显示此帮助信息"
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
    help|*)
        help
        ;;
esac