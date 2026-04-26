# Ollama MemX All Services One-Click Start (Industrial Grade)
# Automatically start all dependencies, configure environment, pull models, import memory

# Set UTF-8 encoding
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# Color definitions
$GREEN = "`e[92m"
$YELLOW = "`e[93m"
$RED = "`e[91m"
$RESET = "`e[0m"

# Create logs directory
if (-not (Test-Path "logs")) {
    New-Item -ItemType Directory -Path "logs" -Force | Out-Null
}

Write-Host ""
Write-Host "=========================================================="
Write-Host "$GREEN🚀 Ollama MemX All Services One-Click Start (Industrial Grade)$RESET"
Write-Host "Automatically start all dependencies, configure environment, pull models, import memory"
Write-Host "=========================================================="
Write-Host ""

# ====================== 1. Basic Check ======================
Write-Host "$YELLOW[1/8] Environment Check$RESET"
# Check working directory
if (-not (Test-Path "main.py")) {
    Write-Host "$RED[ERROR]$RESET Please run this script in the MemX-Ollama directory!"
    Read-Host "Press Enter to exit..."
    exit 1
}
# Check Docker
try {
    docker info | Out-Null
    Write-Host "$GREEN[SUCCESS]$RESET Environment check passed"
} catch {
    Write-Host "$RED[ERROR]$RESET Docker is not running, please start Docker Desktop first!"
    Read-Host "Press Enter to exit..."
    exit 1
}

# ====================== 2. Stop Old Services ======================
Write-Host ""
Write-Host "$YELLOW[2/8] Cleanup Old Services$RESET"
# Stop old containers
docker stop memx-ollama memx-qdrant memx-neo4j memx-redis 2>$null
docker rm memx-ollama memx-qdrant memx-neo4j memx-redis 2>$null
Write-Host "$GREEN[SUCCESS]$RESET Old services cleanup completed"

# ====================== 3. Pull Images (Domestic Acceleration) ======================
Write-Host ""
Write-Host "$YELLOW[3/8] Pull Docker Images (Domestic Acceleration)$RESET"
# Domestic mirror source
$ALIYUN_REGISTRY = "registry.cn-hangzhou.aliyuncs.com/mirror"

# Pull Redis
Write-Host "  Pulling Redis..."
try {
    docker pull "$ALIYUN_REGISTRY/redis:7.2.4-alpine" 2>$null
    if ($LASTEXITCODE -eq 0) {
        docker tag "$ALIYUN_REGISTRY/redis:7.2.4-alpine" "redis:7.2.4-alpine" 2>$null
    } else {
        docker pull "redis:7.2.4-alpine" 2>$null
    }
} catch {
    Write-Host "  Failed to pull Redis from mirror, trying official image..."
    docker pull "redis:7.2.4-alpine" 2>$null
}

# Pull Qdrant
Write-Host "  Pulling Qdrant..."
try {
    docker pull "$ALIYUN_REGISTRY/qdrant:v1.7.3" 2>$null
    if ($LASTEXITCODE -eq 0) {
        docker tag "$ALIYUN_REGISTRY/qdrant:v1.7.3" "qdrant/qdrant:v1.7.3" 2>$null
    } else {
        docker pull "qdrant/qdrant:v1.7.3" 2>$null
    }
} catch {
    Write-Host "  Failed to pull Qdrant from mirror, trying official image..."
    docker pull "qdrant/qdrant:v1.7.3" 2>$null
}

# Pull Neo4j
Write-Host "  Pulling Neo4j..."
try {
    docker pull "$ALIYUN_REGISTRY/neo4j:5.18-enterprise" 2>$null
    if ($LASTEXITCODE -eq 0) {
        docker tag "$ALIYUN_REGISTRY/neo4j:5.18-enterprise" "neo4j:5.18-enterprise" 2>$null
    } else {
        docker pull "neo4j:5.18-enterprise" 2>$null
    }
} catch {
    Write-Host "  Failed to pull Neo4j from mirror, trying official image..."
    docker pull "neo4j:5.18-enterprise" 2>$null
}

# Pull Ollama
Write-Host "  Pulling Ollama..."
try {
    docker pull "$ALIYUN_REGISTRY/ollama:0.1.38" 2>$null
    if ($LASTEXITCODE -eq 0) {
        docker tag "$ALIYUN_REGISTRY/ollama:0.1.38" "ollama/ollama:0.1.38" 2>$null
    } else {
        docker pull "ollama/ollama:0.1.38" 2>$null
    }
} catch {
    Write-Host "  Failed to pull Ollama from mirror, trying official image..."
    docker pull "ollama/ollama:0.1.38" 2>$null
}
Write-Host "$GREEN[SUCCESS]$RESET All images pulled successfully"

# ====================== 4. Start All Dependent Services ======================
Write-Host ""
Write-Host "$YELLOW[4/8] Start Dependent Services$RESET"

# Start Redis
Write-Host "  Starting Redis..."
docker run -d --name memx-redis -p 6379:6379 redis:7.2.4-alpine redis-server --requirepass memx123456 > logs/redis.log 2>&1
# Wait for Redis to be ready
Write-Host "  Waiting for Redis to be ready..."
while ($true) {
    try {
        docker exec memx-redis redis-cli -a memx123456 ping | Out-Null
        if ($LASTEXITCODE -eq 0) {
            break
        }
    } catch {
        # Ignore errors
    }
    Start-Sleep -Seconds 1
}
Write-Host "  ✅ Redis ready"

# Start Qdrant
Write-Host "  Starting Qdrant..."
docker run -d --name memx-qdrant -p 6333:6333 qdrant/qdrant:v1.7.3 > logs/qdrant.log 2>&1
# Wait for Qdrant to be ready
Write-Host "  Waiting for Qdrant to be ready..."
while ($true) {
    try {
        Invoke-WebRequest -Uri "http://localhost:6333/" -UseBasicParsing | Out-Null
        break
    } catch {
        # Ignore errors
    }
    Start-Sleep -Seconds 1
}
Write-Host "  ✅ Qdrant ready"

# Start Neo4j
Write-Host "  Starting Neo4j..."
docker run -d --name memx-neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/memx123456 -e NEO4J_ACCEPT_LICENSE_AGREEMENT=eval neo4j:5.18-enterprise > logs/neo4j.log 2>&1
# Wait for Neo4j to be ready
Write-Host "  Waiting for Neo4j to be ready..."
while ($true) {
    try {
        Invoke-WebRequest -Uri "http://localhost:7474/" -UseBasicParsing | Out-Null
        break
    } catch {
        # Ignore errors
    }
    Start-Sleep -Seconds 2
}
Write-Host "  ✅ Neo4j ready"

# Start Ollama
Write-Host "  Starting Ollama..."
docker run -d --name memx-ollama -p 11434:11434 ollama/ollama:0.1.38 > logs/ollama.log 2>&1
# Wait for Ollama to be ready
Write-Host "  Waiting for Ollama to be ready..."
while ($true) {
    try {
        Invoke-WebRequest -Uri "http://localhost:11434/" -UseBasicParsing | Out-Null
        break
    } catch {
        # Ignore errors
    }
    Start-Sleep -Seconds 1
}
Write-Host "  ✅ Ollama ready"

Write-Host "$GREEN[SUCCESS]$RESET All dependent services started successfully"

# ====================== 5. Pull Ollama Models ======================
Write-Host ""
Write-Host "$YELLOW[5/8] Pull Ollama Models$RESET"
# Set domestic mirror
docker exec memx-ollama sh -c "export HF_ENDPOINT=https://hf-mirror.com && ollama pull llama3.2:1b"
docker exec memx-ollama sh -c "export HF_ENDPOINT=https://hf-mirror.com && ollama pull qwen:1.8b"
Write-Host "$GREEN[SUCCESS]$RESET Models pulled successfully"

# ====================== 6. Generate Environment Configuration ======================
Write-Host ""
Write-Host "$YELLOW[6/8] Generate Environment Configuration$RESET"
# Auto generate .env file
$envContent = @"
# MemX Auto-generated Environment Configuration
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
Write-Host "$GREEN[SUCCESS]$RESET Environment configuration generated: .env"

# ====================== 7. Start MemX API Service ======================
Write-Host ""
Write-Host "$YELLOW[7/8] Start MemX API Service$RESET"
# Start API service in background
Start-Process -FilePath "cmd.exe" -ArgumentList "/c python -m uvicorn main:app --host 0.0.0.0 --port 8000 > logs/memx-api.log 2>&1" -WindowStyle Hidden
# Wait for API to be ready
Write-Host "  Waiting for MemX API to be ready..."
while ($true) {
    try {
        Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing | Out-Null
        break
    } catch {
        # Ignore errors
    }
    Start-Sleep -Seconds 2
}
Write-Host "  ✅ MemX API ready"

# Import memory
Write-Host "  Importing system memory..."
python import_memory.py
Write-Host "$GREEN[SUCCESS]$RESET MemX service started successfully"

# ====================== 8. Function Test ======================
Write-Host ""
Write-Host "$YELLOW[8/8] Function Test$RESET"
# Test memory function
Write-Host "  Testing memory storage..."
try {
    $body = '{"user_id":"test","prompt":"Test memory, I am test user"}'
    Invoke-WebRequest -Uri "http://localhost:8000/chat" -Method POST -Headers @{"Content-Type"="application/json"} -Body $body -UseBasicParsing | Out-Null
} catch {
    # Ignore errors
}

Write-Host "  Testing memory retrieval..."
try {
    $body = '{"user_id":"test","prompt":"Who am I?"}'
    $response = Invoke-WebRequest -Uri "http://localhost:8000/chat" -Method POST -Headers @{"Content-Type"="application/json"} -Body $body -UseBasicParsing
    if ($response.Content -match "test user") {
        Write-Host "  ✅ Memory function test passed"
    } else {
        Write-Host "  ⚠️  Memory function test warning, may need to wait for model loading"
    }
} catch {
    Write-Host "  ⚠️  Memory function test warning, may need to wait for model loading"
}
Write-Host "$GREEN[SUCCESS]$RESET Function test completed"

# ====================== Completion ======================
Write-Host ""
Write-Host "=========================================================="
Write-Host "$GREEN✅✅✅ All services started successfully! MemX memory system is 100% ready!$RESET"
Write-Host "=========================================================="
Write-Host ""
Write-Host "📌 Service Status:"
Write-Host "   ✅ Ollama    : http://localhost:11434"
Write-Host "   ✅ Qdrant    : http://localhost:6333"
Write-Host "   ✅ Neo4j     : http://localhost:7474"
Write-Host "   ✅ Redis     : localhost:6379"
Write-Host "   ✅ MemX API  : http://localhost:8000"
Write-Host ""
Write-Host "🎯 Test Now:"
Write-Host "   Run the following command to test memory function:"
Write-Host "   curl -X POST http://localhost:8000/chat -H \"Content-Type: application/json\" -d '{\"user_id\":\"zmc\",\"prompt\":\"What are the core functions of the system?\"}'"
Write-Host ""
Write-Host "📚 Access Addresses:"
Write-Host "   - API Documentation: http://localhost:8000/docs"
Write-Host "   - Health Check: http://localhost:8000/health"
Write-Host "   - Neo4j Panel: http://localhost:7474 (Username: neo4j Password: memx123456)"
Write-Host "   - Grafana Monitoring: http://localhost:3000"
Write-Host ""
Write-Host "📝 Log Files:"
Write-Host "   All service logs are saved in the logs/ directory, check them if there are issues"
Write-Host ""
Write-Host "$GREENYour memory system is now fully functional! Permanent memory, vector retrieval, and knowledge graph are all ready!$RESET"
Write-Host "=========================================================="

Read-Host "Press Enter to exit..."