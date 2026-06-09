#!/usr/bin/env python3
"""
Aurora+QS-Robot 启动项管理工具
- 启用/禁用开机自启
- 检查当前状态
- 启动/停止守护进程

用法:
  python startup_manager.py enable   # 启用开机自启
  python startup_manager.py disable  # 禁用开机自启
  python startup_manager.py status   # 查看状态
  python startup_manager.py start    # 启动守护进程
  python startup_manager.py stop     # 停止守护进程
"""

import os
import sys
import subprocess
from pathlib import Path

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
STARTUP_DIR = os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
STARTUP_LNK = os.path.join(STARTUP_DIR, "AuroraService_5002.lnk")
STARTUP_BAT = os.path.join(WORK_DIR, "start_aurora_service.bat")
WATCHDOG_PY = os.path.join(WORK_DIR, "aurora_watchdog_v2.py")
PID_FILE = os.path.join(WORK_DIR, "logs", "aurora_watchdog.pid")


def create_shortcut(target, shortcut_path):
    """创建快捷方式（使用WSH）"""
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(shortcut_path)
        shortcut.Targetpath = target
        shortcut.WorkingDirectory = WORK_DIR
        shortcut.WindowStyle = 7  # 最小化
        shortcut.Description = "Aurora+QS-Robot 守护进程"
        shortcut.Save()
        return True
    except ImportError:
        # 如果没有pywin32，使用VBS脚本
        vbs_content = f'''Set WshShell = CreateObject("WScript.Shell")
Set objLink = WshShell.CreateShortcut("{shortcut_path}")
objLink.TargetPath = "{target}"
objLink.WorkingDirectory = "{WORK_DIR}"
objLink.WindowStyle = 7
objLink.Description = "Aurora+QS-Robot 守护进程"
objLink.Save
'''
        vbs_file = os.path.join(WORK_DIR, "_create_shortcut.vbs")
        with open(vbs_file, "w", encoding="utf-8") as f:
            f.write(vbs_content)
        subprocess.run(["cscript", "//Nologo", vbs_file], capture_output=True)
        if os.path.exists(vbs_file):
            os.remove(vbs_file)
        return os.path.exists(shortcut_path)
    except Exception as e:
        print(f"创建快捷方式失败: {e}")
        return False


def cmd_enable():
    """启用开机自启"""
    os.makedirs(STARTUP_DIR, exist_ok=True)
    if create_shortcut(STARTUP_BAT, STARTUP_LNK):
        print(f"✅ 开机自启已启用")
        print(f"   位置: {STARTUP_LNK}")
    else:
        print("❌ 启用失败，请检查权限")


def cmd_disable():
    """禁用开机自启"""
    if os.path.exists(STARTUP_LNK):
        os.remove(STARTUP_LNK)
        print(f"✅ 开机自启已禁用")
    else:
        print(f"ℹ️  开机自启本来就未启用")


def cmd_status():
    """显示状态"""
    print("=" * 50)
    print("Aurora+QS-Robot 状态")
    print("=" * 50)
    print()

    # 开机自启状态
    print(f"开机自启: {'✅ 已启用' if os.path.exists(STARTUP_LNK) else '❌ 未启用'}")
    print(f"  启动项: {STARTUP_LNK}")
    print()

    # 守护进程状态
    if os.path.exists(PID_FILE):
        with open(PID_FILE) as f:
            pid = f.read().strip()
        try:
            subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True)
            alive = True
        except Exception:
            alive = False
        print(f"守护进程 PID: {pid} ({'运行中' if alive else '已停止'})")
    else:
        print(f"守护进程: 未运行")

    # 端口状态
    print()
    result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
    for line in result.stdout.splitlines():
        if ":5002" in line and "LISTENING" in line:
            print(f"5002端口: ✅ 正在监听")
            print(f"  {line.strip()}")
            break
    else:
        print(f"5002端口: ❌ 未监听")
    print()


def cmd_start():
    """启动守护进程"""
    if os.path.exists(PID_FILE):
        with open(PID_FILE) as f:
            pid = f.read().strip()
        print(f"守护进程可能已运行 (PID: {pid})，请先停止")
        return

    print("正在启动守护进程...")
    # 用 start /B 后台启动
    subprocess.Popen(
        ["python", WATCHDOG_PY],
        cwd=WORK_DIR,
        stdout=open(os.path.join(WORK_DIR, "logs", "aurora_watchdog_launch.log"), "w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    )
    import time
    time.sleep(3)
    if os.path.exists(PID_FILE):
        with open(PID_FILE) as f:
            pid = f.read().strip()
        print(f"✅ 守护进程启动成功 (PID: {pid})")
    else:
        print("⚠️  启动中，请稍后查看状态")


def cmd_stop():
    """停止守护进程"""
    if not os.path.exists(PID_FILE):
        print("守护进程未运行")
        return

    with open(PID_FILE) as f:
        pid = f.read().strip()

    print(f"停止守护进程 (PID: {pid})...")
    try:
        subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
    except Exception:
        pass

    # 同时也停掉主进程
    try:
        result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if ":5002" in line and "LISTENING" in line:
                parts = line.strip().split()
                main_pid = parts[-1]
                if main_pid != pid:
                    subprocess.run(["taskkill", "/F", "/PID", main_pid], capture_output=True)
                break
    except Exception:
        pass

    try:
        os.remove(PID_FILE)
    except Exception:
        pass

    print("✅ 停止完成")


if __name__ == "__main__":
    commands = {
        "enable": cmd_enable,
        "disable": cmd_disable,
        "status": cmd_status,
        "start": cmd_start,
        "stop": cmd_stop,
    }

    if len(sys.argv) < 2:
        print("用法: python startup_manager.py <命令>")
        print("命令:")
        print("  status  - 查看当前状态")
        print("  start   - 启动守护进程")
        print("  stop    - 停止守护进程")
        print("  enable  - 启用开机自启")
        print("  disable - 禁用开机自启")
        sys.exit(0)

    cmd = sys.argv[1].lower()
    if cmd in commands:
        commands[cmd]()
    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)
