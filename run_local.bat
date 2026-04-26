@echo off
chcp 65001 >nul
echo.
echo ==============================================================
echo 🚀 Ollama MemX 本地运行（不依赖Docker）
echo ==============================================================
echo.
echo [INFO] 检查工作目录...
cd MemX-Ollama
echo [INFO] 当前目录: %cd%
echo.
echo [INFO] 检查Python...
python --version
echo.
echo [INFO] 检查依赖...
pip list | findstr "fastapi uvicorn ollama qdrant-client redis neo4j"
echo.
echo [INFO] 启动MemX API服务...
echo [INFO] 请确保本地Ollama服务已启动（http://localhost:11434）
echo [INFO] 请确保本地Qdrant服务已启动（http://localhost:6333）
echo [INFO] 请确保本地Redis服务已启动（localhost:6379）
echo [INFO] 请确保本地Neo4j服务已启动（http://localhost:7474）
echo.
echo [INFO] 启动API服务...
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
echo.
echo [INFO] 服务已启动！
echo [INFO] 访问 http://localhost:8000/docs 查看API文档
echo [INFO] 运行以下命令测试记忆功能：
echo [INFO] curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" -d {"request_id":"test","user_id":"test_user","prompt":"我叫张三，今年28岁，喜欢打篮球"}
echo.
echo ==============================================================
echo 🎉 服务启动成功！
echo ==============================================================
echo.
pause