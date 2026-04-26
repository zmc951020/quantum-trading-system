#!/bin/bash
set -e

echo "=========================================="
echo "  MemX Ollama 停止脚本"
echo "  停止时间：$(date)"
echo "=========================================="

if command -v docker-compose &> /dev/null; then
    docker-compose down
else
    docker compose down
fi

echo ""
echo "服务已停止"
echo ""
echo "注意：数据卷已保留，如需完全清理请执行："
echo "  rm -rf ollama_data qdrant_data neo4j_data redis_data prometheus_data grafana_data"
echo ""