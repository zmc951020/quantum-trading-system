#!/bin/bash

# 启动脚本 - 同时启动后端和前端服务器

echo "=== 量化交易仪表盘启动脚本 ==="
echo ""
echo "1. 启动后端服务..."
echo "后端服务地址: http://localhost:8000"
echo ""

# 启动后端服务
python simple_backend.py &
BACKEND_PID=$!

# 等待后端服务启动
sleep 2

echo "2. 启动前端服务器..."
echo "前端地址: http://localhost:3000"
echo ""

# 启动前端服务器
cd ../frontend
python -m http.server 3000 &
FRONTEND_PID=$!

echo "=== 服务已启动 ==="
echo "后端服务: http://localhost:8000"
echo "前端服务: http://localhost:3000"
echo ""
echo "按 Ctrl+C 停止服务"
echo ""

# 等待用户中断
wait $BACKEND_PID $FRONTEND_PID
