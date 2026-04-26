#!/bin/bash
set -e

BACKUP_DATE=$1
if [ -z "$BACKUP_DATE" ]; then
    echo "用法：./restore.sh 备份日期（如20240410120000）"
    exit 1
fi

echo "开始恢复数据，备份日期：$BACKUP_DATE"

LOCAL_DIR=/app
REMOTE_DIR=s3://memx-backup/prod/

if command -v aws &> /dev/null; then
    echo "从异地存储下载备份..."
    aws s3 cp $REMOTE_DIR/*$BACKUP_DATE.tar.gz /tmp/ 2>/dev/null || echo "从S3下载失败，尝试本地恢复"
fi

for component in ollama qdrant neo4j redis; do
    backup_file=""
    if [ -f "/tmp/${component}_${BACKUP_DATE}.tar.gz" ]; then
        backup_file="/tmp/${component}_${BACKUP_DATE}.tar.gz"
    elif [ -f "/data/backup/memx/${component}_${BACKUP_DATE}.tar.gz" ]; then
        backup_file="/data/backup/memx/${component}_${BACKUP_DATE}.tar.gz"
    fi

    if [ -n "$backup_file" ]; then
        echo "恢复${component}数据..."
        tar -zxf $backup_file -C $LOCAL_DIR/ 2>/dev/null && echo "${component}恢复成功" || echo "${component}恢复失败"
    else
        echo "${component}备份文件不存在，跳过"
    fi
done

if command -v docker-compose &> /dev/null; then
    echo "重启服务..."
    docker-compose restart 2>/dev/null || docker compose restart 2>/dev/null || echo "服务重启失败，请手动重启"
fi

echo "数据恢复完成，备份日期：$BACKUP_DATE"