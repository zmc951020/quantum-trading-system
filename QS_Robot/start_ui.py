
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
QS Robot UI 启动脚本
"""
import sys
import os

# 确保当前目录在路径中
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

print("=" * 60)
print("QS Robot 量化系统智能助手")
print("=" * 60)

try:
    from flask import Flask
    print("✓ Flask 导入成功")
except ImportError:
    print("⚠ Flask 未安装，请运行: pip install flask flask-cors requests")
    sys.exit(1)

try:
    from ui.server import app
    print("✓ UI 模块加载成功")
except Exception as e:
    print(f"⚠ UI 模块加载失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n启动服务器...")
print("访问地址: http://localhost:5001")
print("按 Ctrl+C 停止服务器")
print("=" * 60 + "\n")

app.run(host='0.0.0.0', port=5001, debug=True, use_reloader=False)

