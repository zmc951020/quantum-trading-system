
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
QS Robot UI 启动脚本
"""
import sys
import os

# Windows控制台UTF-8编码补丁
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 确保当前目录在路径中
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

print("=" * 60)
print("QS Robot 量化系统智能助手")
print("=" * 60)

try:
    from flask import Flask
    print("[OK] Flask 导入成功")
except ImportError:
    print("[WARN] Flask 未安装，请运行: pip install flask flask-cors requests")
    sys.exit(1)

try:
    from ui.server import app
    from config.config import config
    print("[OK] UI 模块加载成功")
except Exception as e:
    print(f"[ERROR] UI 模块加载失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 从配置读取端口
shell_port = config.get('port_allocation.qs_robot_shell', 5001)

print("\n启动服务器...")
print(f"访问地址: http://localhost:{shell_port}")
print("按 Ctrl+C 停止服务器")
print("=" * 60 + "\n")

app.run(host='0.0.0.0', port=shell_port, debug=True, use_reloader=False)

