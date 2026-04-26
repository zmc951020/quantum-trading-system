#!/usr/bin/env python3
"""
测试app模块是否能正常导入
"""
import sys
import os

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    print("导入app模块...")
    import app
    print("OK app模块导入成功")
    
    print("检查socketio和app对象...")
    from app import socketio, app as flask_app
    print("OK socketio和app对象获取成功")
    
    print("测试配置...")
    print(f"Flask配置: {flask_app.config.get('SECRET_KEY')}")
    print("OK 配置检查成功")
    
    print("所有测试通过!")
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()