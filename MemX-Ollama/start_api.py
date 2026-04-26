#!/usr/bin/env python3
"""
启动MemX-Ollama服务的脚本
解决模块导入问题
"""

import os
import sys
import subprocess
import time

def main():
    # 获取当前脚本所在目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 确保在MemX-Ollama目录下运行
    if not os.path.exists(os.path.join(script_dir, 'memx')):
        print("错误：请在MemX-Ollama目录下运行此脚本")
        sys.exit(1)
    
    # 设置PYTHONPATH
    os.environ['PYTHONPATH'] = script_dir + ';' + os.environ.get('PYTHONPATH', '')
    print(f"设置PYTHONPATH: {os.environ['PYTHONPATH']}")
    
    # 检查依赖
    print("检查依赖...")
    try:
        subprocess.run([sys.executable, '-c', 'import fastapi; import uvicorn; import memx'], 
                      check=True, capture_output=True, text=True)
        print("依赖检查通过")
    except subprocess.CalledProcessError as e:
        print(f"依赖检查失败: {e.stderr}")
        print("尝试安装依赖...")
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'], 
                      check=True)
    
    # 启动服务
    print("启动MemX-Ollama API服务...")
    print("服务地址: http://localhost:8009")
    print("API文档: http://localhost:8009/docs")
    print("按 Ctrl+C 停止服务")
    
    # 启动uvicorn服务
    subprocess.run([
        sys.executable, '-m', 'uvicorn', 'main:app',
        '--host', '0.0.0.0',
        '--port', '8009',
        '--reload'
    ])

if __name__ == "__main__":
    main()
