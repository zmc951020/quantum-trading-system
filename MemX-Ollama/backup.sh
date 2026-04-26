#!/bin/bash
set -e

BACKUP_DATE=$(date +%Y%m%d%H%M%S)
BACKUP_DIR=/data/backup/memx
LOCAL_DIR=/app
REMOTE_DIR=s3://memx-backup/prod/

echo "开始备份MemX数据，时间：$BACKUP_DATE"

mkdir -p $BACKUP_DIR

tar -zcf $BACKUP_DIR/ollama_$BACKUP_DATE.tar.gz $LOCAL_DIR/ollama_data 2>/dev/null || echo "ollama数据备份跳过"
tar -zcf $BACKUP_DIR/qdrant_$BACKUP_DATE.tar.gz $LOCAL_DIR/qdrant_data 2>/dev/null || echo "qdrant数据备份跳过"
tar -zcf $BACKUP_DIR/neo4j_$BACKUP_DATE.tar.gz $LOCAL_DIR/neo4j_data 2>/dev/null || echo "neo4j数据备份跳过"
tar -zcf $BACKUP_DIR/redis_$BACKUP_DATE.tar.gz $LOCAL_DIR/redis_data 2>/dev/null || echo "redis数据备份跳过"

for file in $BACKUP_DIR/*$BACKUP_DATE.tar.gz; do
    if [ -f "$file" ]; then
        tar -tzf $file > /dev/null && echo "备份文件验证成功：$file" || echo "备份文件验证失败：$file"
    fi
done

if command -v aws &> /dev/null; then
    aws s3 cp $BACKUP_DIR/*$BACKUP_DATE.tar.gz $REMOTE_DIR/ 2>/dev/null && echo "备份上传成功" || echo "备份上传跳过（aws cli未配置）"
fi

find $BACKUP_DIR -name "*.tar.gz" -mtime +7 -delete 2>/dev/null || true
echo "旧备份清理完成"
echo "备份完成，备份日期：$BACKUP_DATE"