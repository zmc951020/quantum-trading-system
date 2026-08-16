
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

# ── 断电保护：注册退出信号处理 ──
import signal
import atexit

def _save_system_state():
    """保存系统运行状态，用于断电后恢复"""
    state_file = os.path.join(current_dir, "data", "system_state.json")
    try:
        os.makedirs(os.path.dirname(state_file), exist_ok=True)
        import json
        from datetime import datetime
        state = {
            "last_shutdown": datetime.now().isoformat(),
            "status": "shutdown",
            "port": shell_port
        }
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False)
    except Exception:
        pass

def _check_previous_crash():
    """检查上次是否异常退出"""
    state_file = os.path.join(current_dir, "data", "system_state.json")
    try:
        if os.path.exists(state_file):
            import json
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            if state.get("status") != "shutdown":
                print(f"[WARN] 检测到上次异常退出: {state.get('last_shutdown', 'unknown')}")
                print("[WARN] 系统将尝试恢复，请检查持仓和策略状态")
    except Exception:
        pass

_check_previous_crash()
atexit.register(_save_system_state)
signal.signal(signal.SIGTERM, lambda *_: _save_system_state() or sys.exit(0))
signal.signal(signal.SIGINT, lambda *_: _save_system_state() or sys.exit(0))

app.run(host='127.0.0.1', port=shell_port, debug=True, use_reloader=False)

