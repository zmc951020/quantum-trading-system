"""L4 数据行情检查"""
import os
import re
import sys
from typing import Callable, List

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def build_l4_checks(hc) -> List[Callable]:
    def _l4_001():
        ok, d = hc._api_post("/api/technical/analyze",
                               {"symbol": "000001", "days": 30})
        indicators = d.get("data", {}).get("indicators", {})
        return (ok and len(indicators) > 0, 100 if ok and len(indicators) > 0 else 0,
                f"技术指标: {len(indicators)}个" if ok else "技术分析失败", "")
    yield ("L4_001", "技术指标计算", "L4_数据行情", "warning", "both", _l4_001)

    def _l4_002():
        ok, d = hc._api_get("/api/market-data")
        stocks = d.get("data", {}).get("stocks", [])
        has_data = len(stocks) > 0
        return (True, 100 if has_data else 70,
                f"市场数据: {len(stocks)}条" if has_data else "市场数据为空（需要数据源配置）",
                "" if has_data else "配置数据源或启动行情服务")
    yield ("L4_002", "市场数据源", "L4_数据行情", "warning", "both", _l4_002)

    # 深度扩展
    def _l4_004():
        ok, d = hc._api_get("/api/performance-data")
        return (ok, 100 if ok else 0, f"绩效数据: {'通过' if ok else '失败'}", "")
    yield ("L4_004", "绩效数据", "L4_数据行情", "info", "deep", _l4_004)

    def _l4_005():
        ok, d = hc._api_get("/api/technical-indicators")
        return (ok, 100 if ok else 0, f"技术指标列表: {'通过' if ok else '失败'}", "")
    yield ("L4_005", "技术指标列表", "L4_数据行情", "info", "deep", _l4_005)

    # 新模块：实时行情推送
    def _l4_006():
        try:
            from core.realtime_feed import RealtimeFeed, get_realtime_feed
            feed = get_realtime_feed()
            stats = feed.get_stats()
            ticks = stats.get("total_ticks", 0)
            source = stats.get("source", "未启动")
            return (True, 100 if ticks > 0 else 80,
                    f"实时行情: {source}源, {ticks}次推送" if ticks > 0 else "实时行情: 已就绪，待启动",
                    "启动: feed.start()" if ticks == 0 else "")
        except Exception as e:
            return (False, 0, f"实时行情: 不可用 - {e}", "检查 core/realtime_feed.py")
    yield ("L4_006", "实时行情推送", "L4_数据行情", "warning", "both", _l4_006)

    def _l4_007():
        """API不返回假数据：检查API路由中是否使用random假数据"""
        issues = []
        check_dirs = ["api", "routes"]
        for check_dir in check_dirs:
            dir_path = os.path.join(PROJECT_ROOT, check_dir)
            if not os.path.isdir(dir_path):
                continue
            for fname in os.listdir(dir_path):
                if not fname.endswith('.py'):
                    continue
                fpath = os.path.join(dir_path, fname)
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    if 'random.uniform' in content or 'random.randint' in content:
                        if 'test' not in fname.lower():
                            issues.append(f"{check_dir}/{fname}")
                except Exception:
                    pass
        ok = len(issues) == 0
        return (ok, 100 if ok else max(0, 100 - len(issues) * 20),
                "API数据真实性: 全部通过" if ok else f"发现 {len(issues)} 处random假数据: {issues}",
                "" if ok else "API路由不得使用random生成假数据")
    yield ("L4_007", "API不返回假数据", "L4_数据行情", "critical", "both", _l4_007)

    def _l4_008():
        """真实数据源连通性：检查akshare等数据源是否可用"""
        try:
            import importlib
            akshare = importlib.import_module('akshare')
            ok = hasattr(akshare, 'stock_zh_a_spot_em')
            return (ok, 100 if ok else 0,
                    f"akshare: {'可用' if ok else '不可用'}", "" if ok else "pip install akshare")
        except ImportError:
            return (False, 0, "akshare未安装，真实数据源不可用", "pip install akshare")
        except Exception as e:
            return (False, 0, f"数据源检查异常: {e}", "")
    yield ("L4_008", "真实数据源连通性", "L4_数据行情", "warning", "both", _l4_008)