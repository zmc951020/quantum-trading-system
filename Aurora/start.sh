#!/bin/bash
"""
启动Aurora量化交易系统
"""

# 设置环境变量
export PYTHONPATH=$(pwd):$PYTHONPATH

# 创建必要的目录
mkdir -p logs
mkdir -p reports

# 安装依赖
echo "安装依赖..."
pip install -r requirements.txt

# 运行系统测试
echo "运行系统测试..."
python tests/test_system.py

# 启动交易系统
echo "启动交易系统..."
python main.py start
