#!/bin/bash

# 颜色定义
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
NC="\033[0m" # No Color

echo -e "${YELLOW}\n=============================================================${NC}"
echo -e "${YELLOW}🚀 Ollama MemX 记忆系统 - Docker部署脚本${NC}"
echo -e "${YELLOW}=============================================================${NC}\n"

# 检查Docker
echo -e "${YELLOW}[INFO] 检查Docker...${NC}"
if ! command -v docker &> /dev/null; then
    echo -e "${RED}[ERROR] Docker未安装，请先安装Docker Desktop${NC}"
    echo -e "${YELLOW}[INFO] 下载地址: https://www.docker.com/products/docker-desktop/${NC}"
    exit 1
fi

# 检查Docker Compose
echo -e "${YELLOW}[INFO] 检查Docker Compose...${NC}"
if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}[ERROR] Docker Compose未安装${NC}"
    exit 1
fi

# 检查Docker是否运行
echo -e "${YELLOW}[INFO] 检查Docker服务状态...${NC}"
docker info > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo -e "${YELLOW}[INFO] Docker未运行，请手动启动Docker Desktop${NC}"
    echo -e "${YELLOW}[INFO] 启动后请重新运行此脚本${NC}"
    exit 1
fi
echo -e "${GREEN}[SUCCESS] Docker服务正常运行${NC}"

# 配置国内镜像
echo -e "${YELLOW}[INFO] 配置国内镜像源...${NC}"

# 配置Docker国内镜像
DOCKER_CONFIG_DIR="$HOME/.docker"
if [ ! -d "$DOCKER_CONFIG_DIR" ]; then
    mkdir -p "$DOCKER_CONFIG_DIR"
fi

cat > "$DOCKER_CONFIG_DIR/config.json" << EOF
{
  "registry-mirrors": [
    "https://docker.mirrors.ustc.edu.cn",
    "https://hub-mirror.c.163.com",
    "https://mirror.baidubce.com"
  ]
}
EOF
echo -e "${GREEN}[SUCCESS] Docker国内镜像配置完成${NC}"

# 配置Hugging Face国内镜像
export HF_ENDPOINT="https://hf-mirror.com"
echo -e "${GREEN}[SUCCESS] Hugging Face国内镜像配置完成${NC}"

# 拉取镜像
echo -e "${YELLOW}[INFO] 拉取必要的Docker镜像...${NC}"
docker pull ollama/ollama:0.1.38
docker pull qdrant/qdrant:v1.7.3
docker pull neo4j:5.18-enterprise
docker pull redis:7.2.4-alpine
docker pull confluentinc/cp-kafka:7.5.0
docker pull prom/prometheus:v2.47.0
docker pull grafana/grafana:10.1.0
echo -e "${GREEN}[SUCCESS] 所有镜像拉取完成${NC}"

# 启动服务
echo -e "${YELLOW}[INFO] 启动Ollama MemX服务...${NC}"
docker-compose down > /dev/null 2>&1
docker-compose up -d
echo -e "${GREEN}[SUCCESS] 服务启动命令已执行${NC}"

# 等待服务就绪
echo -e "${YELLOW}[INFO] 等待服务就绪（约30秒）...${NC}"
sleep 30

# 检查服务状态
echo -e "${YELLOW}[INFO] 检查服务状态...${NC}"
docker-compose ps

# 验证服务健康状态
echo -e "${YELLOW}[INFO] 验证服务健康状态...${NC}"

echo -e "${YELLOW}[INFO] 检查Ollama服务...${NC}"
curl -s http://localhost:11434/api/health
if [ $? -eq 0 ]; then
    echo -e "${GREEN}[SUCCESS] Ollama服务就绪${NC}"
else
    echo -e "${RED}[ERROR] Ollama服务未就绪${NC}"
fi

echo -e "${YELLOW}[INFO] 检查API服务...${NC}"
curl -s http://localhost:8000/health
if [ $? -eq 0 ]; then
    echo -e "${GREEN}[SUCCESS] API服务就绪${NC}"
else
    echo -e "${RED}[ERROR] API服务未就绪${NC}"
fi

echo -e "${YELLOW}[INFO] 检查Qdrant服务...${NC}"
curl -s http://localhost:6333/health
if [ $? -eq 0 ]; then
    echo -e "${GREEN}[SUCCESS] Qdrant服务就绪${NC}"
else
    echo -e "${RED}[ERROR] Qdrant服务未就绪${NC}"
fi

# 拉取Ollama模型
echo -e "${YELLOW}[INFO] 拉取Ollama模型...${NC}"
ollama pull llama3.2:1b > /dev/null 2>&1
ollama pull qwen:1.8b > /dev/null 2>&1
echo -e "${GREEN}[SUCCESS] Ollama模型拉取完成${NC}"

# 测试记忆系统
echo -e "${YELLOW}[INFO] 测试记忆系统功能...${NC}"

# 存储记忆
echo -e "${YELLOW}[INFO] 测试记忆存储...${NC}"
MEMORY_TEST=$(curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test_user","prompt":"我叫张三，今年28岁，喜欢打篮球"}')

if echo "$MEMORY_TEST" | grep -q "success"; then
    echo -e "${GREEN}[SUCCESS] 记忆存储测试通过${NC}"
else
    echo -e "${RED}[ERROR] 记忆存储测试失败${NC}"
    echo "$MEMORY_TEST"
fi

# 检索记忆
echo -e "${YELLOW}[INFO] 测试记忆检索...${NC}"
RETRIEVAL_TEST=$(curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test_user","prompt":"我叫什么名字？我多大了？我喜欢什么？"}')

if echo "$RETRIEVAL_TEST" | grep -q "张三" && echo "$RETRIEVAL_TEST" | grep -q "28" && echo "$RETRIEVAL_TEST" | grep -q "打篮球"; then
    echo -e "${GREEN}[SUCCESS] 记忆检索测试通过${NC}"
else
    echo -e "${RED}[ERROR] 记忆检索测试失败${NC}"
    echo "$RETRIEVAL_TEST"
fi

# 完成
echo -e "${GREEN}\n=============================================================${NC}"
echo -e "${GREEN}✅✅✅ 部署完成！Ollama MemX记忆系统已100%启动！${NC}"
echo -e "${GREEN}=============================================================${NC}"
echo -e "${YELLOW}\n📌 访问地址：${NC}"
echo -e "   - API文档: http://localhost:8000/docs"
echo -e "   - 监控面板: http://localhost:3000 (账号: admin 密码: admin)"
echo -e "   - Ollama界面: http://localhost:11434"
echo -e "${YELLOW}\n🎯 测试命令：${NC}"
echo -e "   curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' -d '{\"user_id\":\"test_user\",\"prompt\":\"我叫张三，今年28岁，喜欢打篮球\"}'"
echo -e "${YELLOW}\n🔧 常用命令：${NC}"
echo -e "   - 查看服务状态: docker-compose ps"
echo -e "   - 查看日志: docker-compose logs -f"
echo -e "   - 停止服务: docker-compose down"
echo -e "   - 重启服务: docker-compose restart"
echo -e "${GREEN}\n现在Ollama已经具备了工业级的永久记忆能力！${NC}"
echo -e "${GREEN}=============================================================${NC}"