#!/usr/bin/env python3
"""
Aurora量化交易系统 - 生产环境启动脚本
使用waitress作为WSGI服务器（Windows兼容）
"""

import os
import sys
from waitress import serve

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 导入应用
from visualization import app

if __name__ == '__main__':
    print("启动Aurora量化交易系统 - 生产环境")
    print("使用waitress作为WSGI服务器")
    print("访问地址: http://0.0.0.0:8000")
    
    # 启动服务器
    serve(app, host='0.0.0.0', port=8000, threads=4)
