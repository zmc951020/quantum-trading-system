# Ollama MemX 记忆导入脚本
Write-Host "`n=============================================================" -ForegroundColor Green
Write-Host "🚀 Ollama MemX 记忆导入脚本" -ForegroundColor Green
Write-Host "=============================================================`n" -ForegroundColor Green

Write-Host "[INFO] 开始导入核心文件到记忆系统..." -ForegroundColor Yellow

# 导入README.md
Write-Host "`n[INFO] 导入 README.md..." -ForegroundColor Yellow
try {
    $body1 = @{
        user_id = "zmc"
        prompt = "# Ollama MemX 工业级永久记忆系统 基于豆包专家方案实施的Ollama永久记忆系统，采用四级记忆架构，实现工业级0漏洞可运营部署。 系统架构：API Gateway -> Working Mem (短期记忆)、Vector Mem (中期记忆)、Graph Mem (长期记忆) -> Maintenance Engine (记忆维护引擎) 核心功能：短期记忆（动态上下文窗口，智能裁剪压缩）、中期记忆（向量数据库存储，语义检索）、长期记忆（知识图谱，实体关系管理）、永久记忆（核心知识库，版本管理） API接口：/chat 用于聊天和记忆存储，/memory/search 用于记忆搜索 配置说明：主要配置文件是 .env，关键配置项包括 MODEL_NAME、OLLAMA_HOST、QDRANT_HOST、NEO4J_URI、REDIS_HOST 数据备份：使用 backup.sh 备份，restore.sh 恢复 监控地址：Prometheus: http://localhost:9090, Grafana: http://localhost:3000 目录结构：MemX-Ollama/ -> memx/ (核心模块)、main.py (API入口)、docker-compose.yml (部署配置)、Dockerfile (镜像构建)、requirements.txt (Python依赖)、.env (环境配置)、start.sh (启动脚本)、stop.sh (停止脚本)、backup.sh (备份脚本)、restore.sh (恢复脚本)、test_prod.sh (测试脚本)、prometheus.yml (监控配置)"
    } | ConvertTo-Json
    $response1 = Invoke-RestMethod `
        -Uri "http://localhost:8000/chat" `
        -Method POST `
        -Body $body1 `
        -ContentType "application/json"
    Write-Host "[SUCCESS] README.md 导入完成" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] README.md 导入失败: $_" -ForegroundColor Red
}

# 导入ollama_bridge.py核心功能
Write-Host "`n[INFO] 导入 ollama_bridge.py 核心功能..." -ForegroundColor Yellow
try {
    $body2 = @{
        user_id = "zmc"
        prompt = "# Ollama MemX Bridge核心功能 系统架构：OllamaMemXBridge类包含working_mem（短期记忆）、session_mem（中期记忆）、vector_mem（向量记忆）、graph_mem（知识图谱）、abstractor（记忆抽象引擎） 核心方法：chat_with_memory（带记忆的对话）、_ollama_generate_with_retry（Ollama调用带重试）、_write_memory（记忆写入）、_build_prompt（构建带记忆的提示） 记忆处理流程：加载会话历史 -> 搜索长期记忆 -> 搜索知识图谱 -> 构建提示 -> 调用Ollama -> 写入记忆 -> 抽象实体和关系 技术特性：idempotent（幂等性）、circuit_breaker（熔断）、desensitize（脱敏）、clamp_priority（优先级管理） 错误处理：完整的异常捕获和日志记录，确保系统稳定性"
    } | ConvertTo-Json
    $response2 = Invoke-RestMethod `
        -Uri "http://localhost:8000/chat" `
        -Method POST `
        -Body $body2 `
        -ContentType "application/json"
    Write-Host "[SUCCESS] ollama_bridge.py 核心功能导入完成" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] ollama_bridge.py 核心功能导入失败: $_" -ForegroundColor Red
}

# 导入系统架构和功能说明
Write-Host "`n[INFO] 导入系统架构和功能说明..." -ForegroundColor Yellow
try {
    $body3 = @{
        user_id = "zmc"
        prompt = "# Ollama MemX 系统架构和功能 四级记忆架构： 1. 短期记忆（Working Memory）：动态上下文窗口，智能裁剪压缩，最大8192 tokens 2. 中期记忆（Session Memory）：Redis存储，会话管理，过期时间30天 3. 长期记忆（Vector Memory）：Qdrant向量数据库，语义检索，支持相似度搜索 4. 永久记忆（Graph Memory）：Neo4j知识图谱，实体关系管理，支持复杂查询 核心引擎： 1. 记忆抽象引擎：自动抽取实体和关系 2. 记忆检索引擎：基于语义相似度的记忆检索 3. 记忆维护引擎：自动管理记忆优先级和过期 工业级特性： 1. 熔断降级：依赖服务故障时自动降级 2. 幂等性：重复请求自动识别，避免重复写入 3. 输入脱敏：敏感信息自动过滤 4. 优先级管理：记忆优先级0~1.0自动计算 5. 超时控制：所有外部调用10s超时 6. 健康检查：所有服务配置健康检查探针 7. 资源限制：容器CPU/内存硬限制 8. 多租户隔离：数据按租户隔离，支持数据删除 部署架构： 1. 微服务架构：独立服务，松耦合 2. 容器化部署：Docker容器，一键启动 3. 监控体系：Prometheus + Grafana 4. 安全策略：网络隔离，数据加密 5. 灾备方案：自动备份，快速恢复 运行环境： 1. Python 3.11+ 2. Docker 20.10+ 3. 8GB+ 内存 4. 50GB+ 磁盘空间 核心API： 1. /health：健康检查 2. /chat：带记忆的对话 3. /memory/search：记忆搜索 4. /memory/delete：删除用户记忆 5. /memory/sessions/{tenant_id}：会话列表 预期效果： 1. 记忆检索速度提升5-10倍 2. 记忆存储容量支持TB级 3. 系统可靠性达到99.99% 4. 支持跨会话信息检索 5. 支持多源知识库集成 6. 提供更准确、更快速的响应 7. 支持更复杂的业务场景 商业价值： 1. 降低运营成本 2. 提升用户体验 3. 拓展应用场景 4. 为量化交易等专业领域提供智能支持"
    } | ConvertTo-Json
    $response3 = Invoke-RestMethod `
        -Uri "http://localhost:8000/chat" `
        -Method POST `
        -Body $body3 `
        -ContentType "application/json"
    Write-Host "[SUCCESS] 系统架构和功能说明导入完成" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] 系统架构和功能说明导入失败: $_" -ForegroundColor Red
}

Write-Host "`n=============================================================" -ForegroundColor Green
Write-Host "🎉 记忆导入完成！" -ForegroundColor Green
Write-Host "=============================================================" -ForegroundColor Green
Write-Host "[INFO] 所有核心文件已成功导入到Ollama MemX记忆系统" -ForegroundColor Yellow
Write-Host "[INFO] 您现在可以通过以下方式测试记忆系统：" -ForegroundColor Yellow
Write-Host "[INFO] 1. 访问 http://localhost:8000/docs 查看API文档" -ForegroundColor Yellow
Write-Host "[INFO] 2. 使用 PowerShell 命令测试记忆功能" -ForegroundColor Yellow
Write-Host "[INFO] 3. 与Ollama对话，测试记忆能力" -ForegroundColor Yellow
Write-Host "`n[INFO] 例如：" -ForegroundColor Yellow
Write-Host "[INFO] $body = @{user_id='zmc'; prompt='系统的核心功能有哪些？'} | ConvertTo-Json" -ForegroundColor Yellow
Write-Host "[INFO] Invoke-RestMethod -Uri 'http://localhost:8000/chat' -Method POST -Body $body -ContentType 'application/json'" -ForegroundColor Yellow
Write-Host "`n" -ForegroundColor Yellow
Read-Host "按 Enter 键退出..."