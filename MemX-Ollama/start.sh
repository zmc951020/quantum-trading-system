#!/bin/bash
set -e

echo "=========================================="
echo "  MemX Ollama 启动脚本"
echo "  启动时间：$(date)"
echo "=========================================="

if ! command -v docker &> /dev/null; then
    echo "错误：Docker未安装，请先安装Docker"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! command -v docker compose &> /dev/null; then
    echo "错误：Docker Compose未安装，请先安装Docker Compose"
    exit 1
fi

echo ""
echo ">>> 步骤1：创建必要的数据目录"
echo "-------------------------------------------"
mkdir -p ollama_data qdrant_data neo4j_data redis_data prometheus_data grafana_data
echo "数据目录创建完成"

echo ""
echo ">>> 步骤2：拉取最新的Docker镜像"
echo "-------------------------------------------"
docker pull ollama/ollama:0.1.38 || echo "Ollama镜像拉取失败，继续启动"
docker pull qdrant/qdrant:v1.7.3 || echo "Qdrant镜像拉取失败，继续启动"
docker pull neo4j:5.18-enterprise || echo "Neo4j镜像拉取失败，继续启动"
docker pull redis:7.2.4-alpine || echo "Redis镜像拉取失败，继续启动"
docker pull confluentinc/cp-kafka:7.5.0 || echo "Kafka镜像拉取失败，继续启动"
docker pull prom/prometheus:v2.47.0 || echo "Prometheus镜像拉取失败，继续启动"
docker pull grafana/grafana:10.1.0 || echo "Grafana镜像拉取失败，继续启动"
echo "镜像拉取完成"

echo ""
echo ">>> 步骤3：启动所有服务"
echo "-------------------------------------------"
if command -v docker-compose &> /dev/null; then
    docker-compose up -d
else
    docker compose up -d
fi
echo "服务启动完成"

echo ""
echo ">>> 步骤4：等待服务健康检查"
echo "-------------------------------------------"
echo -n "等待Ollama服务就绪"
for i in {1..30}; do
    if curl -sf http://localhost:11434/api/health > /dev/null 2>&1; then
        echo ""
        echo "Ollama服务就绪"
        break
    fi
    echo -n "."
    sleep 2
done

echo -n "等待API服务就绪"
for i in {1..30}; do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo ""
        echo "API服务就绪"
        break
    fi
    echo -n "."
    sleep 2
done

echo ""
echo "=========================================="
echo "  启动完成！"
echo "=========================================="
echo ""
echo "服务访问地址："
echo "  - API服务:     http://localhost:8000"
echo "  - API文档:     http://localhost:8000/docs"
echo "  - Ollama:      http://localhost:11434"
echo "  - Qdrant:      http://localhost:6333"
echo "  - Neo4j:       http://localhost:7474"
echo "  - Prometheus:  http://localhost:9090"
echo "  - Grafana:     http://localhost:3000"
echo ""
echo "常用命令："
echo "  - 查看服务状态: docker-compose ps"
echo "  - 查看日志:     docker-compose logs -f"
echo "  - 停止服务:     docker-compose down"
echo "  - 重启服务:     docker-compose restart"
echo ""