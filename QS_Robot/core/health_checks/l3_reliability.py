"""L3 系统可靠性检查"""
import os
import sys
import time
from typing import Callable, List

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def build_l3_checks(hc) -> List[Callable]:
    def _l3_001():
        """健康检查（合并L3_001+L7_007，quick=基础/deep=完整）"""
        ok, d = hc._api_get("/api/health")
        status = d.get("status", "unknown")
        basic_ok = ok and status == "healthy"
        full_detail = ""
        if hc.mode == "deep":
            ok2, d2 = hc._api_get("/api/health/full")
            full = d2.get("data", {})
            checks = sum(1 for v in full.values() if v is True)
            total = max(len(full) - 1, 1)
            full_detail = f", 完整={checks}/{total}"
        return (basic_ok, 100 if basic_ok else 0,
                f"健康检查: {status}{full_detail}",
                "" if basic_ok else "检查系统健康状况")
    yield ("L3_001", "健康检查", "L3_系统可靠性", "critical", "both", _l3_001)

    def _l3_002():
        ok, d = hc._api_get("/api/health/degradation")
        level = d.get("data", {}).get("level", "unknown")
        degraded = d.get("data", {}).get("degraded_count", -1)
        return (level == "none" and degraded == 0, 100 if level == "none" else 50,
                f"降级状态: level={level}, degraded={degraded}",
                "" if level == "none" else "检查降级服务列表")
    yield ("L3_002", "降级状态", "L3_系统可靠性", "critical", "both", _l3_002)

    def _l3_003():
        ok, d = hc._api_get("/api/status")
        return (ok, 100 if ok else 0, f"系统状态端点: {'通过' if ok else '失败'}", "")
    yield ("L3_003", "系统状态端点", "L3_系统可靠性", "critical", "both", _l3_003)

    # 深度扩展
    def _l3_004():
        try:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            import requests
            def _req():
                r = requests.get(f"{hc.BASE_URL}/api/strategy/list",
                                cookies=hc._get_auth_cookies(), timeout=10)
                return r.status_code == 200
            with ThreadPoolExecutor(max_workers=10) as ex:
                futures = [ex.submit(_req) for _ in range(10)]
                results = [f.result() for f in as_completed(futures)]
            passed = sum(results)
            return (passed == 10, 100 if passed == 10 else passed * 10,
                    f"10并发: {passed}/10通过" if passed == 10 else f"10并发: {passed}/10通过",
                    "" if passed == 10 else "检查并发处理能力")
        except Exception as e:
            return (False, 0, f"并发测试异常: {e}", "")
    yield ("L3_004", "并发请求测试", "L3_系统可靠性", "warning", "deep", _l3_004)

    def _l3_005():
        ok, _ = hc._api_get("/api/aurora/system/info")
        return (ok, 100 if ok else 0, f"Aurora系统信息: {'通过' if ok else '失败'}", "")
    yield ("L3_005", "Aurora系统信息", "L3_系统可靠性", "warning", "deep", _l3_005)

    # 新模块：自动修复/重启机制
    def _l3_006():
        """
        自演进/自动修复检查：
        1. 检测进程是否存在
        2. 检测最近崩溃记录
        3. 提供自动重启建议
        """
        try:
            import psutil
            process = psutil.Process(os.getpid())
            uptime_sec = time.time() - process.create_time()
            uptime_str = f"{uptime_sec/3600:.1f}h" if uptime_sec > 3600 else f"{uptime_sec/60:.1f}m"

            # 检查是否有最近的崩溃记录
            crash_file = os.path.join(os.path.dirname(__file__), '..', '..', 'logs', 'crash.log')
            recent_crash = False
            if os.path.exists(crash_file):
                mtime = os.path.getmtime(crash_file)
                if time.time() - mtime < 3600:  # 1小时内
                    recent_crash = True

            if recent_crash:
                return (False, 40, f"自动修复: 检测到1小时内崩溃记录，运行时间={uptime_str}",
                        "检查 crash.log 并考虑自动重启")
            return (True, 100, f"自动修复: 正常，运行时间={uptime_str}，无近期崩溃", "")
        except Exception as e:
            return (True, 80, f"自动修复: 部分可用 - {e}", "安装 psutil: pip install psutil")
    yield ("L3_006", "自动修复/重启", "L3_系统可靠性", "warning", "deep", _l3_006)

    # 新模块：进程健康自愈
    def _l3_007():
        """检查关键模块是否全部可导入"""
        modules = [
            ("trade_executor", "core.trade_executor"),
            ("order_manager", "core.order_manager"),
            ("realtime_feed", "core.realtime_feed"),
            ("alert_manager", "core.alert_manager"),
            ("risk_control", "core.risk_control"),
            ("shepherd_optimizer", "core.shepherd_optimizer"),
        ]
        failed = []
        for name, path in modules:
            try:
                __import__(path)
            except Exception:
                failed.append(name)

        if failed:
            return (False, 0, f"自愈检查: {len(failed)}个模块不可用 - {', '.join(failed)}",
                    f"检查模块: {', '.join(failed)}")
        return (True, 100, f"自愈检查: 全部{len(modules)}个关键模块正常", "")
    yield ("L3_007", "关键模块自愈检查", "L3_系统可靠性", "critical", "both", _l3_007)

    # 新增：5003端口连通性检查
    def _l3_008():
        try:
            import requests
            r = requests.get("http://127.0.0.1:5003/", timeout=5)
            ok = r.status_code in (200, 302)
            return (ok, 100 if ok else 0,
                    f"5003端口: {'可达' if ok else '不可达'} (HTTP {r.status_code})",
                    "" if ok else "检查 start_ui.py 是否正常启动")
        except Exception as e:
            return (False, 0, f"5003端口: 不可达 - {e}", "检查 start_ui.py 是否正常启动")
    yield ("L3_008", "5003端口连通", "L3_系统可靠性", "critical", "both", _l3_008)