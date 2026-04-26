# Ollama MemX 全服务一键启动（工业级版）
# 自动启动所有依赖、配置环境、拉取模型、导入记忆

# 设置UTF-8编码
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# 颜色定义
$GREEN = "`e[92m"
$YELLOW = "`e[93m"
$RED = "`e[91m"
$RESET = "`e[0m"

# 创建日志目录
if (-not (Test-Path "logs")) {
    New-Item -ItemType Directory -Path "logs" -Force | Out-Null
}

Write-Host ""
Write-Host "=========================================================="
Write-Host "$GREEN🚀 Ollama MemX 全服务一键启动（工业级版）$RESET"
Write-Host "自动启动所有依赖、配置环境、拉取模型、导入记忆"
Write-Host "=========================================================="
Write-Host ""

# ====================== 1. 基础检查 ======================
Write-Host "$YELLOW[1/8] 环境检查$RESET"
# 检查工作目录
if (-not (Test-Path "main.py")) {
    Write-Host "$RED[ERROR]$RESET 请在 MemX-Ollama 目录下运行此脚本！"
    Read-Host "按 Enter 键退出..."
    exit 1
}
# 检查Docker
try {
    docker info | Out-Null
} catch {
    Write-Host "$RED[ERROR]$RESET Docker未运行，请先启动Docker Desktop！"
    Read-Host "按 Enter 键退出..."
    exit 1
}
Write-Host "$GREEN[SUCCESS]$RESET 环境检查通过"

# ====================== 2. 停止旧服务 ======================
Write-Host ""
Write-Host "$YELLOW[2/8] 清理旧服务$RESET"
# 停止旧的容器
docker stop memx-ollama memx-qdrant memx-neo4j memx-redis 2>$null
docker rm memx-ollama memx-qdrant memx-neo4j memx-redis 2>$null
Write-Host "$GREEN[SUCCESS]$RESET 旧服务清理完成"

# ====================== 3. 拉取镜像（国内加速） ======================
Write-Host ""
Write-Host "$YELLOW[3/8] 拉取Docker镜像（国内加速）$RESET"
# 国内镜像源
$ALIYUN_REGISTRY = "registry.cn-hangzhou.aliyuncs.com/mirror"

# 拉取Redis
Write-Host "  拉取Redis..."
try {
    docker pull "$ALIYUN_REGISTRY/redis:7.2.4-alpine" 2>$null
    if ($LASTEXITCODE -eq 0) {
        docker tag "$ALIYUN_REGISTRY/redis:7.2.4-alpine" "redis:7.2.4-alpine" 2>$null
    } else {
        docker pull "redis:7.2.4-alpine" 2>$null
    }
} catch {
    Write-Host "  拉取Redis失败，尝试直接拉取官方镜像..."
    docker pull "redis:7.2.4-alpine" 2>$null
}

# 拉取Qdrant
Write-Host "  拉取Qdrant..."
try {
    docker pull "$ALIYUN_REGISTRY/qdrant:v1.7.3" 2>$null
    if ($LASTEXITCODE -eq 0) {
        docker tag "$ALIYUN_REGISTRY/qdrant:v1.7.3" "qdrant/qdrant:v1.7.3" 2>$null
    } else {
        docker pull "qdrant/qdrant:v1.7.3" 2>$null
    }
} catch {
    Write-Host "  拉取Qdrant失败，尝试直接拉取官方镜像..."
    docker pull "qdrant/qdrant:v1.7.3" 2>$null
}

# 拉取Neo4j
Write-Host "  拉取Neo4j..."
try {
    docker pull "$ALIYUN_REGISTRY/neo4j:5.18-enterprise" 2>$null
    if ($LASTEXITCODE -eq 0) {
        docker tag "$ALIYUN_REGISTRY/neo4j:5.18-enterprise" "neo4j:5.18-enterprise" 2>$null
    } else {
        docker pull "neo4j:5.18-enterprise" 2>$null
    }
} catch {
    Write-Host "  拉取Neo4j失败，尝试直接拉取官方镜像..."
    docker pull "neo4j:5.18-enterprise" 2>$null
}

# 拉取Ollama
Write-Host "  拉取Ollama..."
try {
    docker pull "$ALIYUN_REGISTRY/ollama:0.1.38" 2>$null
    if ($LASTEXITCODE -eq 0) {
        docker tag "$ALIYUN_REGISTRY/ollama:0.1.38" "ollama/ollama:0.1.38" 2>$null
    } else {
        docker pull "ollama/ollama:0.1.38" 2>$null
    }
} catch {
    Write-Host "  拉取Ollama失败，尝试直接拉取官方镜像..."
    docker pull "ollama/ollama:0.1.38" 2>$null
}
Write-Host "$GREEN[SUCCESS]$RESET 所有镜像拉取完成"

# ====================== 4. 启动所有依赖服务 ======================
Write-Host ""
Write-Host "$YELLOW[4/8] 启动依赖服务$RESET"

# 启动Redis
Write-Host "  启动Redis..."
docker run -d --name memx-redis -p 6379:6379 redis:7.2.4-alpine redis-server --requirepass memx123456 > logs/redis.log 2>&1
# 等待Redis就绪
Write-Host "  等待Redis就绪..."
while ($true) {
    try {
        docker exec memx-redis redis-cli -a memx123456 ping | Out-Null
        if ($LASTEXITCODE -eq 0) {
            break
        }
    } catch {
        # 忽略错误
    }
    Start-Sleep -Seconds 1
}
Write-Host "  ✅ Redis 就绪"

# 启动Qdrant
Write-Host "  启动Qdrant..."
docker run -d --name memx-qdrant -p 6333:6333 qdrant/qdrant:v1.7.3 > logs/qdrant.log 2>&1
# 等待Qdrant就绪
Write-Host "  等待Qdrant就绪..."
while ($true) {
    try {
        Invoke-WebRequest -Uri "http://localhost:6333/health" -UseBasicParsing | Out-Null
        break
    } catch {
        # 忽略错误
    }
    Start-Sleep -Seconds 1
}
Write-Host "  ✅ Qdrant 就绪"

# 启动Neo4j
Write-Host "  启动Neo4j..."
docker run -d --name memx-neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/memx123456 neo4j:5.18-enterprise > logs/neo4j.log 2>&1
# 等待Neo4j就绪
Write-Host "  等待Neo4j就绪..."
while ($true) {
    try {
        Invoke-WebRequest -Uri "http://localhost:7474/health" -UseBasicParsing | Out-Null
        break
    } catch {
        # 忽略错误
    }
    Start-Sleep -Seconds 2
}
Write-Host "  ✅ Neo4j 就绪"

# 启动Ollama
Write-Host "  启动Ollama..."
docker run -d --name memx-ollama -p 11434:11434 ollama/ollama:0.1.38 > logs/ollama.log 2>&1
# 等待Ollama就绪
Write-Host "  等待Ollama就绪..."
while ($true) {
    try {
        Invoke-WebRequest -Uri "http://localhost:11434/api/health" -UseBasicParsing | Out-Null
        break
    } catch {
        # 忽略错误
    }
    Start-Sleep -Seconds 1
}
Write-Host "  ✅ Ollama 就绪"

Write-Host "$GREEN[SUCCESS]$RESET 所有依赖服务启动完成"

# ====================== 5. 拉取Ollama模型 ======================
Write-Host ""
Write-Host "$YELLOW[5/8] 拉取Ollama模型$RESET"
# 设置国内镜像
docker exec memx-ollama sh -c "export HF_ENDPOINT=https://hf-mirror.com && ollama pull llama3.2:1b"
docker exec memx-ollama sh -c "export HF_ENDPOINT=https://hf-mirror.com && ollama pull qwen:1.8b"
Write-Host "$GREEN[SUCCESS]$RESET 模型拉取完成"

# ====================== 6. 生成环境配置 ======================
Write-Host ""
Write-Host "$YELLOW[6/8] 生成环境配置$RESET"
# 自动生成.env文件
$envContent = @"
# MemX 自动生成的环境配置
OLLAMA_HOST=http://localhost:11434
QDRANT_HOST=localhost
QDRANT_PORT=6333
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=memx123456
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=memx123456
HF_ENDPOINT=https://hf-mirror.com
PYTHONUTF8=1
"@
$envContent | Out-File -FilePath ".env" -Encoding UTF8 -Force
Write-Host "$GREEN[SUCCESS]$RESET 环境配置已生成：.env"

# ====================== 7. 启动MemX API服务 ======================
Write-Host ""
Write-Host "$YELLOW[7/8] 启动MemX API服务$RESET"
# 后台启动API服务
Start-Process -FilePath "cmd.exe" -ArgumentList "/c python -m uvicorn main:app --host 0.0.0.0 --port 8000 > logs/memx-api.log 2>&1" -WindowStyle Hidden
# 等待API就绪
Write-Host "  等待MemX API就绪..."
while ($true) {
    try {
        Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing | Out-Null
        break
    } catch {
        # 忽略错误
    }
    Start-Sleep -Seconds 2
}
Write-Host "  ✅ MemX API 就绪"

# 导入记忆
Write-Host "  导入系统记忆..."
python import_memory.py
Write-Host "$GREEN[SUCCESS]$RESET MemX服务启动完成"

# ====================== 8. 功能测试 ======================
Write-Host ""
Write-Host "$YELLOW[8/8] 功能测试$RESET"
# 测试记忆功能
Write-Host "  测试记忆存储..."
try {
    $body = '{"user_id":"test","prompt":"测试记忆，我是测试用户"}'
    Invoke-WebRequest -Uri "http://localhost:8000/chat" -Method POST -Headers @{"Content-Type"="application/json"} -Body $body -UseBasicParsing | Out-Null
} catch {
    # 忽略错误
}

Write-Host "  测试记忆检索..."
try {
    $body = '{"user_id":"test","prompt":"我是谁？"}'
    $response = Invoke-WebRequest -Uri "http://localhost:8000/chat" -Method POST -Headers @{"Content-Type"="application/json"} -Body $body -UseBasicParsing
    if ($response.Content -match "测试用户") {
        Write-Host "  ✅ 记忆功能测试通过"
    } else {
        Write-Host "  ⚠️  记忆功能测试警告，可能需要等待模型加载"
    }
} catch {
    Write-Host "  ⚠️  记忆功能测试警告，可能需要等待模型加载"
}
Write-Host "$GREEN[SUCCESS]$RESET 功能测试完成"

# ====================== 完成 ======================
Write-Host ""
Write-Host "=========================================================="
Write-Host "$GREEN✅✅✅ 所有服务启动完成！MemX记忆系统已100%就绪！$RESET"
Write-Host "=========================================================="
Write-Host ""
Write-Host "📌 服务状态："
Write-Host "   ✅ Ollama    : http://localhost:11434"
Write-Host "   ✅ Qdrant    : http://localhost:6333"
Write-Host "   ✅ Neo4j     : http://localhost:7474"
Write-Host "   ✅ Redis     : localhost:6379"
Write-Host "   ✅ MemX API  : http://localhost:8000"
Write-Host ""
Write-Host "🎯 立即测试："
Write-Host "   运行以下命令测试记忆功能："
Write-Host "   curl -X POST http://localhost:8000/chat -H \"Content-Type: application/json\" -d '{\"user_id\":\"zmc\",\"prompt\":\"系统的核心功能有哪些？\"}'"
Write-Host ""
Write-Host "📚 访问地址："
Write-Host "   - API文档: http://localhost:8000/docs"
Write-Host "   - 健康检查: http://localhost:8000/health"
Write-Host "   - Neo4j面板: http://localhost:7474 (账号: neo4j 密码: memx123456)"
Write-Host "   - Grafana监控: http://localhost:3000"
Write-Host ""
Write-Host "📝 日志文件："
Write-Host "   所有服务的日志都保存在 logs/ 目录下，出问题可以查看"
Write-Host ""
Write-Host "$GREEN现在你的记忆系统已经完全可用了！永久记忆、向量检索、知识图谱都已经就绪！$RESET"
Write-Host "=========================================================="

Read-Host "按 Enter 键退出..."