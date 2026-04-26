@echo off
chcp 65001 >nul
echo.
echo ==============================================================
echo 🚀 Ollama MemX 一键部署（简化版）
echo ==============================================================
echo.
echo [INFO] 检查工作目录...
cd MemX-Ollama
echo [INFO] 当前目录: %cd%
echo [INFO] 检查目录内容...
dir
echo.
echo [INFO] 检查Python...
python --version
echo.
echo [INFO] 检查Docker...
docker --version
echo.
echo [INFO] 安装Python依赖...
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
echo.
echo [INFO] 拉取Docker镜像...
docker pull ollama/ollama:0.1.38
docker pull qdrant/qdrant:v1.7.3
docker pull redis:7.2.4-alpine
docker pull neo4j:5.18-enterprise
docker pull prom/prometheus:v2.47.0
docker pull grafana/grafana:10.1.0
echo.
echo [INFO] 启动服务...
docker-compose down
docker-compose up -d
echo.
echo [INFO] 等待服务启动...
echo [INFO] 请等待约30秒，然后手动检查服务状态
 echo [INFO] 访问 http://localhost:8000/health 检查API服务
 echo [INFO] 访问 http://localhost:11434/api/health 检查Ollama服务
echo.
echo [INFO] 部署完成！
echo [INFO] 请手动测试记忆系统功能
 echo [INFO] 运行：curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" -d {"request_id":"test","user_id":"test_user","prompt":"我叫张三，今年28岁，喜欢打篮球"}
echo.
echo ==============================================================
echo 🎉 部署完成！
echo ==============================================================
echo.
pause