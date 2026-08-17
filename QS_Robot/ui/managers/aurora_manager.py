# -*- coding: utf-8 -*-
"""Aurora 5002 子进程管理"""
import os
import sys
import subprocess
import time
import signal
import urllib.request
import urllib.error

_AURORA_PORT = 5002
_AURORA_HEALTH_URL = f"http://127.0.0.1:{_AURORA_PORT}/api/health"
_AURORA_STARTUP_TIMEOUT = 180
_aurora_process = None


def get_aurora_path():
    """获取 Aurora 系统根目录"""
    from config.config import config
    aurora_path = config.get('aurora_system.base_path', '')
    if aurora_path and os.path.isdir(aurora_path):
        return aurora_path
    aurora_path = os.environ.get('AURORA_HOME', '')
    if aurora_path and os.path.isdir(aurora_path):
        return aurora_path
    return None


def is_aurora_running():
    """检查 5002 是否健康运行"""
    try:
        req = urllib.request.Request(_AURORA_HEALTH_URL, method='GET')
        req.add_header('User-Agent', 'QS-Robot-Startup-Check')
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status in (200, 503)
    except urllib.error.HTTPError as e:
        return e.code == 503
    except Exception:
        return False


def _is_port_occupied(port: int) -> bool:
    """检查端口是否被占用"""
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        return result == 0
    except Exception:
        return False


def _kill_zombie_on_port(port: int) -> bool:
    """尝试清除占用指定端口的僵尸进程"""
    try:
        result = subprocess.run(
            ['netstat', '-ano'],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.split('\n'):
            if f':{port}' in line and 'LISTENING' in line:
                parts = line.strip().split()
                pid = parts[-1]
                if pid.isdigit() and int(pid) != os.getpid():
                    print(f"[Aurora] 端口 {port} 被僵尸进程 PID={pid} 占用，尝试清除...")
                    kill_result = subprocess.run(
                        ['taskkill', '/F', '/PID', pid],
                        capture_output=True, text=True, timeout=5
                    )
                    if kill_result.returncode == 0:
                        print(f"[Aurora] 僵尸进程 PID={pid} 已终止")
                        time.sleep(2)
                        return True
                    else:
                        print(f"[Aurora] 无法终止 PID={pid}（需要管理员权限）")
                        print(f"  请以管理员身份运行: 清除Aurora僵尸进程.bat")
                        print(f"  或手动执行: taskkill /F /PID {pid}")
                        return False
        return False
    except Exception as e:
        print(f"[Aurora] 僵尸检测失败: {e}")
        return False


def start_aurora_backend():
    """启动 Aurora 5002 后端服务"""
    global _aurora_process
    from config.config import config

    aurora_path = get_aurora_path()
    if not aurora_path:
        print("[Aurora] 未找到 Aurora 系统路径，跳过自动启动")
        print("  设置方法: config.aurora_system.base_path 或 AURORA_HOME 环境变量")
        return False

    if is_aurora_running():
        print(f"[Aurora] 5002 服务健康运行中，无需重复启动")
        return True

    if _is_port_occupied(_AURORA_PORT):
        print(f"[Aurora] 端口 {_AURORA_PORT} 被占用但健康检查失败 → 疑似僵尸进程")
        _kill_zombie_on_port(_AURORA_PORT)
        if _is_port_occupied(_AURORA_PORT):
            print(f"[Aurora] 端口 {_AURORA_PORT} 仍被占用，无法启动 5002")
            print(f"  请以管理员身份运行: 清除Aurora僵尸进程.bat")
            return False

    visualization_py = os.path.join(aurora_path, 'visualization.py')
    if not os.path.isfile(visualization_py):
        print(f"[Aurora] 未找到 visualization.py: {visualization_py}")
        return False

    print(f"[Aurora] 启动 5002 后端服务...")
    print(f"  路径: {aurora_path}")
    print(f"  脚本: visualization.py")

    try:
        aurora_log_path = os.path.join(aurora_path, 'logs', 'aurora_5002_stdout.log')
        os.makedirs(os.path.dirname(aurora_log_path), exist_ok=True)
        aurora_log_file = open(aurora_log_path, 'a', encoding='utf-8', buffering=1)
        _aurora_process = subprocess.Popen(
            [sys.executable, 'visualization.py'],
            cwd=aurora_path,
            stdout=aurora_log_file,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
        )

        print(f"[Aurora] 等待 5002 就绪（最多 {_AURORA_STARTUP_TIMEOUT}s）...")
        waited = 0
        while waited < _AURORA_STARTUP_TIMEOUT:
            if is_aurora_running():
                print(f"[Aurora] 5002 服务就绪 (耗时 {waited}s)")
                return True

            if _aurora_process.poll() is not None:
                exit_code = _aurora_process.returncode
                print(f"[Aurora] 5002 进程异常退出 (exit_code={exit_code})")
                try:
                    aurora_log_file.flush()
                    with open(aurora_log_path, 'r', encoding='utf-8', errors='replace') as f:
                        lines = f.readlines()
                    if lines:
                        for line in lines[-5:]:
                            print(f"  {line.rstrip()}")
                except Exception:
                    pass
                _aurora_process = None
                return False

            time.sleep(1)
            waited += 1
            if waited % 10 == 0:
                print(f"  已等待 {waited}s...")

        print(f"[Aurora] 5002 启动超时 ({_AURORA_STARTUP_TIMEOUT}s)，请检查日志")
        stop_aurora_backend()
        return False

    except Exception as e:
        print(f"[Aurora] 启动失败: {e}")
        import traceback as _tb
        _tb.print_exc()
        return False


def stop_aurora_backend():
    """停止 Aurora 5002 后端子进程"""
    global _aurora_process
    if _aurora_process is None:
        return

    print("[Aurora] 正在停止 5002 服务...")
    try:
        if sys.platform == 'win32':
            _aurora_process.terminate()
        else:
            _aurora_process.send_signal(signal.SIGTERM)

        try:
            _aurora_process.wait(timeout=10)
            print("[Aurora] 5002 服务已停止")
        except subprocess.TimeoutExpired:
            print("[Aurora] 5002 未响应，强制终止...")
            _aurora_process.kill()
            _aurora_process.wait(timeout=5)
            print("[Aurora] 5002 已强制终止")
    except Exception as e:
        print(f"[Aurora] 停止 5002 时出错: {e}")
    finally:
        _aurora_process = None
