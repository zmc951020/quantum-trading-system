"""L7 运维部署检查"""
import os
import sys
import time
from typing import Callable, List

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def build_l7_checks(hc) -> List[Callable]:
    def _l7_001():
        pages = ["/", "/maintenance", "/login", "/chat", "/vibe_analysis", "/cline-agent"]
        failed = []
        for p in pages:
            try:
                import requests
                r = requests.get(f"{hc.BASE_URL}{p}", timeout=5)
                if r.status_code != 200:
                    failed.append(p)
            except Exception:
                failed.append(p)
        ok = len(failed) == 0
        return (ok, 100 if ok else max(0, 100 - len(failed) * 20),
                f"前端页面: {len(pages) - len(failed)}/{len(pages)}可达" if ok else f"失败: {failed}", "")
    yield ("L7_001", "前端页面可达", "L7_运维部署", "critical", "both", _l7_001)

    def _l7_002():
        scripts = ["启动服务.bat", "QS_Robot启动器.bat", "start_ui.py"]
        missing = [s for s in scripts if not hc._file_check(s)]
        ok = len(missing) == 0
        return (ok, 100 if ok else max(0, 100 - len(missing) * 25),
                f"启动脚本: {len(scripts) - len(missing)}/{len(scripts)}存在" if ok else f"缺失: {missing}", "")
    yield ("L7_002", "启动脚本", "L7_运维部署", "warning", "both", _l7_002)

    def _l7_003():
        config_path = os.path.join(PROJECT_ROOT, "config", "config.py")
        config_json = os.path.join(PROJECT_ROOT, "config.json")
        ok = os.path.exists(config_path) or os.path.exists(config_json)
        return (ok, 100 if ok else 0, "配置文件存在" if ok else "配置文件缺失", "")
    yield ("L7_003", "配置文件", "L7_运维部署", "warning", "both", _l7_003)

    # 深度扩展
    def _l7_005():
        try:
            import requests
            r = requests.get(f"{hc.BASE_URL}/nonexistent-page-xyz", timeout=5)
            ok = r.status_code == 404
            return (ok, 100 if ok else 0, f"404处理: status={r.status_code}", "")
        except Exception as e:
            return (False, 0, f"404测试异常: {e}", "")
    yield ("L7_004", "404错误处理", "L7_运维部署", "info", "deep", _l7_005)

    def _l7_004():
        """告警系统（合并L7_006+L7_006b，模块+API双重验证）"""
        try:
            from core.alert_manager import get_alert_manager
            am = get_alert_manager()
            channels = list(am._channels.keys())
            am.get_history(limit=5)
            module_ok = True
        except Exception:
            channels = []
            module_ok = False
        api_ok, _ = hc._api_get("/api/alerts")
        ok = module_ok and api_ok
        return (ok, 100 if ok else 50,
                f"告警系统: {len(channels)}通道({', '.join(channels) if module_ok else 'N/A'}), "
                f"API={'✓' if api_ok else '✗'}",
                "" if ok else "检查 core/alert_manager.py")
    yield ("L7_005", "告警系统", "L7_运维部署", "warning", "both", _l7_004)

    def _l7_005():
        """内存泄漏检测"""
        try:
            import psutil
            process = psutil.Process(os.getpid())
            mem_info = process.memory_info()
            mem_mb = mem_info.rss / 1024 / 1024
            sys_mem = psutil.virtual_memory()
            sys_used_pct = sys_mem.percent

            # 内存阈值：进程 > 2GB 或 系统 > 98%
            process_ok = mem_mb < 2048
            sys_critical = sys_used_pct >= 98
            sys_warning = sys_used_pct >= 90
            ok = process_ok and not sys_critical

            detail = (f"进程内存: {mem_mb:.1f}MB, "
                     f"系统内存: {sys_used_pct:.1f}% "
                     f"({'正常' if ok else '告警'})")
            suggestion = ""
            if not process_ok:
                suggestion = "进程内存超过2GB，可能存在内存泄漏，建议重启服务"
            if sys_critical:
                suggestion = "系统内存使用率超过98%，严重告警，建议释放资源"
            elif sys_warning:
                suggestion = "系统内存偏高，建议监控"

            return (ok, 100 if ok else 85, detail, suggestion)
        except ImportError:
            return (True, 70, "psutil未安装，跳过内存检测", "pip install psutil")
        except Exception as e:
            return (False, 0, f"内存检测异常: {e}", "")
    yield ("L7_006", "内存泄漏检测", "L7_运维部署", "warning", "deep", _l7_005)

    def _l7_009():
        """磁盘空间监控"""
        try:
            disk_usage = os.path.join(PROJECT_ROOT, '..')
            if os.name == 'nt':
                import ctypes
                free_bytes = ctypes.c_ulonglong(0)
                total_bytes = ctypes.c_ulonglong(0)
                ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                    ctypes.c_wchar_p(disk_usage),
                    None, ctypes.byref(total_bytes), ctypes.byref(free_bytes))
                total_gb = total_bytes.value / 1024**3
                free_gb = free_bytes.value / 1024**3
                used_pct = (1 - free_gb / total_gb) * 100 if total_gb > 0 else 0
            else:
                stat = os.statvfs(disk_usage)
                total_gb = (stat.f_frsize * stat.f_blocks) / 1024**3
                free_gb = (stat.f_frsize * stat.f_bavail) / 1024**3
                used_pct = (1 - free_gb / total_gb) * 100 if total_gb > 0 else 0

            ok = used_pct < 85 and free_gb > 5
            detail = (f"磁盘: {used_pct:.1f}%已用, "
                     f"剩余{free_gb:.1f}GB "
                     f"({'正常' if ok else '告警'})")
            suggestion = ""
            if not ok:
                suggestion = (f"磁盘空间不足(剩余{free_gb:.1f}GB)，"
                             f"建议清理日志文件或扩容")

            return (ok, 100 if ok else 30, detail, suggestion)
        except Exception as e:
            return (False, 0, f"磁盘检测异常: {e}", "")
    yield ("L7_007", "磁盘空间监控", "L7_运维部署", "warning", "deep", _l7_009)

    def _l7_010():
        """性能监控（响应时间）"""
        try:
            import requests
            t0 = time.time()
            r = requests.get(f"{hc.BASE_URL}/api/health", timeout=5)
            elapsed = (time.time() - t0) * 1000

            ok = r.status_code == 200 and elapsed < 3000
            detail = f"API响应: {elapsed:.0f}ms ({'正常' if ok else '告警'})"
            suggestion = ""
            if elapsed >= 3000:
                suggestion = "API响应时间超过3秒，建议检查系统负载"
            elif elapsed >= 1000:
                suggestion = "API响应时间超过1秒，建议关注"

            return (ok, 100 if elapsed < 500 else 80 if elapsed < 1000 else 50,
                   detail, suggestion)
        except Exception as e:
            return (False, 0, f"性能检测异常: {e}", "")
    yield ("L7_008", "API响应性能", "L7_运维部署", "warning", "deep", _l7_010)

    def _l7_009():
        """模拟/实盘环境隔离：检查环境变量配置是否区分模拟和实盘"""
        env_file = os.path.join(PROJECT_ROOT, ".env.example")
        env_exists = os.path.exists(env_file)
        env_key = os.environ.get("QS_ROBOT_ENV", os.environ.get("AURORA_ENV", ""))
        is_simulation = env_key.lower() in ("simulation", "paper", "dev", "")
        ok = env_exists and is_simulation
        return (ok, 100 if ok else 50,
                f"环境隔离: .env={'✓' if env_exists else '✗'}, "
                f"当前环境={'simulation' if is_simulation else env_key or '未设置'}",
                "" if ok else "确保默认环境为 simulation，实盘需显式设置")
    yield ("L7_009", "模拟/实盘隔离", "L7_运维部署", "critical", "both", _l7_009)
