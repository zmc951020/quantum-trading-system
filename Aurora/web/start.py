#!/usr/bin/env python3
"""
量化交易系统启动脚本
"""
import os
import sys
import subprocess

# 项目根目录
project_root = os.path.dirname(os.path.abspath(__file__))

def check_dependencies():
    """
    检查依赖是否已安装
    """
    print("=" * 50)
    print("检查依赖...")
    print("=" * 50)

    required_packages = [
        'flask',
        'flask_socketio',
        'redis',
        'pandas',
        'numpy',
        'scikit-learn',
        'requests',
        'echarts'
    ]

    missing = []
    for package in required_packages:
        try:
            if package == 'flask_socketio':
                __import__('flask_socketio')
            elif package == 'scikit-learn':
                __import__('sklearn')
            else:
                __import__(package)
            print(f"OK {package}")
        except ImportError:
            print(f"NO {package} (未安装)")
            missing.append(package)

    if missing:
        print("\n缺少以下依赖，正在安装...")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install'] + missing)
        print("依赖安装完成!")

    return True

def check_redis():
    """
    检查Redis服务
    """
    print("\n" + "=" * 50)
    print("检查Redis服务...")
    print("=" * 50)

    try:
        import redis
        client = redis.Redis(host='localhost', port=6379, db=2)
        client.ping()
        print("OK Redis服务已启动")
        return True
    except Exception as e:
        print(f"NO Redis服务未启动: {e}")
        print("提示: 请确保Redis服务正在运行")
        return False

def start_server():
    """
    启动Web服务器
    """
    print("\n" + "=" * 50)
    print("启动Web服务器...")
    print("=" * 50)

    # 在当前目录运行app.py
    try:
        import subprocess
        # 确保在web目录下运行
        web_dir = os.path.dirname(os.path.abspath(__file__))
        result = subprocess.run([sys.executable, 'app.py'], cwd=web_dir, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print("错误输出:")
            print(result.stderr)
        return result.returncode == 0
    except Exception as e:
        print(f"服务器启动失败: {e}")
        return False

if __name__ == '__main__':
    print("\n" + "=" * 50)
    print("  量化交易系统启动器")
    print("=" * 50)

    # 检查依赖
    if not check_dependencies():
        sys.exit(1)

    # 检查Redis
    redis_ok = check_redis()

    # 启动服务器
    start_server()
