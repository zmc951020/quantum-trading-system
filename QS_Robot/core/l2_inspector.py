"""
L2 业务功能链路 - 自动巡检脚本
===============================
覆盖 19 项检查：策略→优化→回测→引擎→工作流→股票池→自适应→同花顺

运行方式：
  python -m core.l2_inspector          # 快速模式（~15s）
  python -m core.l2_inspector --deep   # 深度模式
  python -m core.l2_inspector --json   # JSON输出
  python -m core.l2_inspector --help   # 查看帮助
"""
import os
import sys
import json
import time
import argparse
import requests
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

BASE_URL = "http://127.0.0.1:5003"


@dataclass
class L2CheckResult:
    id: str
    name: str
    category: str
    passed: bool
    score: float
    detail: str
    elapsed_ms: float = 0
    suggestion: str = ""


@dataclass
class L2Report:
    timestamp: str
    mode: str
    total: int
    passed: int
    failed: int
    overall_score: float
    categories: Dict[str, Dict] = field(default_factory=dict)
    items: List[Dict] = field(default_factory=list)
    elapsed_seconds: float = 0


class L2Inspector:

    def __init__(self, mode: str = "quick"):
        self.mode = mode
        self._session = None
        self._results: List[L2CheckResult] = []

    def _auth(self) -> dict:
        if self._session:
            return {"session_id": self._session}
        try:
            r = requests.post(f"{BASE_URL}/api/auth/login",
                            json={"username": "admin", "password": "admin123"}, timeout=5)
            if r.status_code == 200:
                self._session = r.json().get("session_id", "")
                return {"session_id": self._session}
        except Exception:
            pass
        return {}

    def _api_get(self, path, timeout=10):
        try:
            r = requests.get(f"{BASE_URL}{path}", cookies=self._auth(), timeout=timeout)
            ct = r.headers.get("content-type", "")
            return r.status_code in (200, 302), r.json() if ct.startswith("application/json") else {}
        except Exception:
            return False, {}

    def _check(self, cid, name, category, fn):
        t0 = time.time()
        try:
            passed, score, detail, suggestion = fn()
        except Exception as e:
            passed, score, detail, suggestion = False, 0, f"异常: {e}", "检查系统日志"
        result = L2CheckResult(
            id=cid, name=name, category=category,
            passed=passed, score=score, detail=detail,
            elapsed_ms=round((time.time() - t0) * 1000, 1),
            suggestion=suggestion,
        )
        self._results.append(result)
        return result

    # ========== 策略体系 ==========

    def _check_strategy_registry(self):
        ok, d = self._api_get("/api/strategy/list")
        strategies = d.get("data", {}).get("strategies", [])
        api_count = len(strategies)
        discovery_ok = True
        try:
            from core.strategy_auto_discovery import get_auto_discovery
            disc = get_auto_discovery()
            discovery_ok = hasattr(disc, 'run_once') or hasattr(disc, 'scan')
        except Exception:
            discovery_ok = False
        passed = api_count > 0 and discovery_ok
        return (passed, 100 if passed else (60 if api_count > 0 else 0),
                f"API={api_count}个策略, 自动发现={'✓' if discovery_ok else '✗'}",
                "" if passed else "执行 strategy_auto_discovery.run_once()")

    def _check_optimizer_list(self):
        ok, d = self._api_get("/api/optimizer/list")
        optimizers = d.get("data", {}).get("optimizers", [])
        return (len(optimizers) > 0, 100 if len(optimizers) > 0 else 0,
                f"{len(optimizers)}个优化器", "")

    def _check_backtest(self):
        ok, _ = self._api_get("/api/backtest/history")
        return (ok, 100 if ok else 0, f"回测端点: {'可达' if ok else '不可达'}", "")

    def _check_strategy_status(self):
        ok, _ = self._api_get("/api/strategy-status")
        return (ok, 100 if ok else 0, f"策略状态: {'可达' if ok else '不可达'}", "")

    # ========== 优化引擎 ==========

    def _check_shepherd(self):
        try:
            from core.shepherd_optimizer import ShepherdOptimizer, ShepherdVersion
            ShepherdOptimizer(version=ShepherdVersion.V6)
            return (True, 100, "牧羊人V6: 可用", "")
        except Exception as e:
            return (False, 0, f"牧羊人V6: {e}", "检查 core/shepherd_optimizer.py")

    def _check_walk_forward(self):
        try:
            from core.walk_forward import WalkForwardAnalyzer
            WalkForwardAnalyzer()
            return (True, 100, "Walk-Forward: 可用", "")
        except Exception as e:
            return (False, 0, f"Walk-Forward: {e}", "检查 core/walk_forward.py")

    def _check_backtest_comparator(self):
        try:
            from core.backtest_comparator import BacktestComparator
            BacktestComparator()
            return (True, 100, "回测对比: 可用", "")
        except Exception as e:
            return (False, 0, f"回测对比: {e}", "检查 core/backtest_comparator.py")

    # ========== 韬策略引擎 & 熵韬收敛 & 工作流 ==========

    def _check_tau_cluster(self):
        try:
            from core.tau_cluster_engine import get_cluster_engine
            engine = get_cluster_engine()
            count = len(engine.get_registered_strategies())
            has_scheduler = engine.weight_scheduler is not None
            has_validator = engine.validator is not None
            has_regime = engine.regime_detector is not None
            return (True, 100,
                    f"韬引擎: {count}个策略, 调度={'✓' if has_scheduler else '✗'}, "
                    f"验证={'✓' if has_validator else '✗'}, 市场={'✓' if has_regime else '✗'}", "")
        except Exception as e:
            return (False, 0, f"韬引擎: {e}", "检查 core/tau_cluster_engine.py")

    def _check_tau_optimizer(self):
        try:
            from core.tau_optimizer_cluster import get_parameter_store
            store = get_parameter_store()
            info = store.get_all_strategies_info() if hasattr(store, 'get_all_strategies_info') else []
            return (True, 100 if len(info) > 0 else 50,
                    f"熵韬优化器: {len(info)}条参数记录", "")
        except Exception as e:
            return (False, 0, f"熵韬优化器: {e}", "检查 core/tau_optimizer_cluster.py")

    def _check_workflow_engine(self):
        try:
            from core.workflow_engine import get_workflow_engine
            engine = get_workflow_engine()
            has_full = hasattr(engine, '_run_full_workflow')
            return (True, 100 if has_full else 70,
                    f"工作流引擎: 完整链路={'✓' if has_full else '✗'}", "")
        except Exception as e:
            return (False, 0, f"工作流引擎: {e}", "检查 core/workflow_engine.py")

    def _check_workflow_api(self):
        ok1, _ = self._api_get("/api/workflow/status")
        ok2, _ = self._api_get("/api/workflow/history")
        ok = ok1 and ok2
        return (ok, 100 if ok else 50,
                f"工作流API: status={'✓' if ok1 else '✗'}, history={'✓' if ok2 else '✗'}", "")

    # ========== 股票池 ==========

    def _check_stock_pool(self):
        try:
            from core.stock_pool import get_stock_pool_manager
            mgr = get_stock_pool_manager()
            summary = mgr.get_pool_summary()
            if isinstance(summary, dict):
                local_total = sum(summary.values())
            else:
                local_total = len(summary) if summary else 0
            api_ok, _ = self._api_get("/api/stock-pool")
            passed = local_total > 0 and api_ok
            return (passed, 100 if passed else 70,
                    f"本地={local_total}只, API={'✓' if api_ok else '✗'}", "")
        except Exception as e:
            return (False, 0, f"股票池: {e}", "检查 core/stock_pool.py")

    # ========== 自适应层 ==========

    def _check_adaptive(self):
        try:
            from core.adaptive_market_regime import get_adaptation_engine
            engine = get_adaptation_engine()
            has_detector = hasattr(engine, 'detector') and engine.detector is not None
            has_profile = hasattr(engine, '_profile_store') and engine._profile_store is not None
            return (True, 100,
                    f"自适应层: 市场检测={'✓' if has_detector else '✗'}, 画像存储={'✓' if has_profile else '✗'}", "")
        except Exception as e:
            return (False, 0, f"自适应层: {e}", "检查 core/adaptive_market_regime.py")

    # ========== 独立保留 ==========

    def _check_strategy_profiles(self):
        try:
            from core.adaptive_market_regime import StrategyProfileStore
            store_path = os.path.join(PROJECT_ROOT, "data", "strategy_profiles.json")
            store_exists = os.path.exists(store_path)
            store = StrategyProfileStore(storage_path=store_path)
            has_store = store_exists and store is not None
            priorities = store.get_regime_priorities() if hasattr(store, 'get_regime_priorities') else {}
            return (True, 100,
                    f"策略画像: 存储={'✓' if store_exists else '✗'}, 优先级配置={len(priorities)}个", "")
        except Exception as e:
            return (False, 0, f"策略画像: {e}", "检查 core/adaptive_market_regime.py")

    def _check_stock_diversion(self):
        try:
            from core.stock_pool import StockPoolManager, StockSource
            mgr = StockPoolManager()
            summary = mgr.get_source_summary()
            has_all = all(k in summary for k in ["aurora_native", "vibe_trading", "ths_iwencai"])
            return (has_all, 100 if has_all else 60,
                    f"三类分流: {len(summary)}个来源", "")
        except Exception as e:
            return (False, 0, f"三类分流: {e}", "检查 core/stock_pool.py")

    # ========== 同花顺入口 (4子项) ==========

    def _check_ths_bridge(self):
        try:
            from api.ths_bridge import SignalCollector
            c = SignalCollector()
            s14, s18 = c.list_strategies()
            ok = len(s14) == 14 and len(s18) == 18
            return (ok, 100 if ok else 0,
                    f"桥接: 14策略={len(s14)}, 18战法={len(s18)}", "")
        except Exception as e:
            return (False, 0, f"THS-桥接: {e}", "检查 api/ths_bridge/")

    def _check_ths_intel(self):
        try:
            from api.ths_bridge.market_intel import get_market_intel_collector
            c = get_market_intel_collector()
            data = c.fetch_all()
            dims = sum(1 for k in ["hot_stocks","market_overview","capital_flow",
                                   "sector_rotation","market_emotion"] if k in data)
            ok = dims == 5
            return (ok, 100 if ok else 0, f"情报: {dims}/5维度", "")
        except Exception as e:
            return (False, 0, f"THS-情报: {e}", "检查 api/ths_bridge/market_intel.py")

    def _check_ths_iwencai(self):
        ok, _ = self._api_get("/ths_academy/api/strategies")
        return (ok, 100 if ok else 0, f"问财: {'可达' if ok else '不可达'}", "")

    def _check_ths_signals(self):
        try:
            from api.ths_bridge import SignalCollector
            c = SignalCollector()
            s14, s18 = c.list_strategies()
            total = len(s14) + len(s18)
            return (total >= 32, 100 if total >= 32 else 0, f"信号: {total}个", "")
        except Exception as e:
            return (False, 0, f"THS-信号: {e}", "检查 api/ths_bridge/")

    # ========== 执行 ==========

    def run(self) -> L2Report:
        t0 = time.time()
        checks = [
            # 策略体系
            (self._check_strategy_registry, "L2_001", "策略注册与发现", "策略体系"),
            (self._check_optimizer_list, "L2_002", "优化器列表", "策略体系"),
            (self._check_backtest, "L2_003", "回测端点", "策略体系"),
            (self._check_strategy_status, "L2_004", "策略启停端点", "策略体系"),
            # 优化引擎
            (self._check_shepherd, "L2_005", "牧羊人优化器V6", "优化引擎"),
            (self._check_walk_forward, "L2_006", "Walk-Forward分析", "优化引擎"),
            (self._check_backtest_comparator, "L2_007", "回测多策略对比", "优化引擎"),
            # 韬策略 & 工作流
            (self._check_tau_cluster, "L2_008", "韬策略引擎", "策略引擎"),
            (self._check_tau_optimizer, "L2_009", "熵韬收敛优化器", "策略引擎"),
            (self._check_workflow_engine, "L2_010", "工作流引擎", "工作流"),
            (self._check_workflow_api, "L2_011", "工作流API", "工作流"),
            # 股票池 & 自适应
            (self._check_stock_pool, "L2_012", "股票池", "数据链路"),
            (self._check_adaptive, "L2_013", "策略自适应层", "自适应层"),
            # 独立保留
            (self._check_strategy_profiles, "L2_014", "策略性能画像", "自适应层"),
            (self._check_stock_diversion, "L2_015", "三类选股分流", "股票池"),
            # 同花顺入口 (4子项独立检查)
            (self._check_ths_bridge, "L2_016a", "THS-桥接模块", "同花顺入口"),
            (self._check_ths_intel, "L2_016b", "THS-市场情报", "同花顺入口"),
            (self._check_ths_iwencai, "L2_016c", "THS-问财选股", "同花顺入口"),
            (self._check_ths_signals, "L2_016d", "THS-信号收集", "同花顺入口"),
        ]

        for fn, cid, cname, ccat in checks:
            self._check(cid, cname, ccat, fn)

        elapsed = round(time.time() - t0, 1)
        total = len(self._results)
        passed = sum(1 for r in self._results if r.passed)
        failed = total - passed
        score = round(sum(r.score for r in self._results) / total, 1) if total > 0 else 0

        cats = {}
        for r in self._results:
            c = cats.setdefault(r.category, {"total": 0, "passed": 0, "score": 0})
            c["total"] += 1
            if r.passed:
                c["passed"] += 1
            c["score"] += r.score
        for c in cats.values():
            c["score"] = round(c["score"] / c["total"], 1) if c["total"] > 0 else 0

        return L2Report(
            timestamp=datetime.now().isoformat(),
            mode=self.mode,
            total=total, passed=passed, failed=failed,
            overall_score=score,
            categories=cats,
            items=[asdict(r) for r in self._results],
            elapsed_seconds=elapsed,
        )

    def print_report(self, report: L2Report):
        print(f"\n{'='*60}")
        print(f"  L2 业务功能链路巡检 - {report.mode}模式")
        print(f"  时间: {report.timestamp[:19]}")
        print(f"{'='*60}")
        print(f"  总项: {report.total} | 通过: {report.passed} | 失败: {report.failed}")
        print(f"  总评分: {report.overall_score}/100 | 耗时: {report.elapsed_seconds}s")
        print()
        for cat, info in report.categories.items():
            icon = "✅" if info["passed"] == info["total"] else "⚠️"
            print(f"  {icon} {cat}: {info['passed']}/{info['total']} ({info['score']}/100)")
        print()
        for r in self._results:
            icon = "✅" if r.passed else "❌"
            line = f"  {icon} {r.id} {r.name}: {r.detail}"
            if r.elapsed_ms:
                line += f" ({r.elapsed_ms}ms)"
            print(line)
            if r.suggestion:
                print(f"     → {r.suggestion}")
        print(f"\n{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="L2 业务功能链路自动巡检")
    parser.add_argument("--deep", action="store_true", help="深度模式")
    parser.add_argument("--json", action="store_true", help="JSON输出")
    args = parser.parse_args()

    mode = "deep" if args.deep else "quick"
    inspector = L2Inspector(mode=mode)
    report = inspector.run()

    if args.json:
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    else:
        inspector.print_report(report)

    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())