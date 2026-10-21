"""L2 业务功能链路检查"""
import os
import sys
from typing import Callable, List

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def build_l2_checks(hc) -> List[Callable]:
    # ====== 策略体系 (3项) ======

    def _l2_001():
        """策略注册与发现（合并L2_001+L2_005+L2_015）"""
        ok, d = hc._api_get("/api/strategy/list")
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
                f"策略注册: API={api_count}个, 自动发现={'✓' if discovery_ok else '✗'}",
                "" if passed else "执行 strategy_auto_discovery.run_once() 填充注册表")
    yield ("L2_001", "策略注册与发现", "L2_业务链路", "critical", "both", _l2_001)

    def _l2_002():
        ok, d = hc._api_get("/api/optimizer/list")
        optimizers = d.get("data", {}).get("optimizers", [])
        return (len(optimizers) > 0, 100 if len(optimizers) > 0 else 0,
                f"优化器列表: {len(optimizers)}个" if len(optimizers) > 0 else "优化器列表为空",
                "" if len(optimizers) > 0 else "检查优化器注册表")
    yield ("L2_002", "优化器列表", "L2_业务链路", "critical", "both", _l2_002)

    def _l2_003():
        ok, _ = hc._api_get("/api/backtest/history")
        return (ok, 100 if ok else 0, "回测端点可达" if ok else "回测端点不可达", "")
    yield ("L2_003", "回测端点", "L2_业务链路", "warning", "both", _l2_003)

    def _l2_004():
        ok, _ = hc._api_get("/api/strategy-status")
        return (ok, 100 if ok else 0, "策略状态端点可达" if ok else "策略状态端点不可达", "")
    yield ("L2_004", "策略启停端点", "L2_业务链路", "critical", "both", _l2_004)

    # ====== 优化引擎 (3项) ======

    def _l2_005():
        try:
            from core.shepherd_optimizer import ShepherdOptimizer, ShepherdVersion
            s = ShepherdOptimizer(version=ShepherdVersion.V6)
            return (True, 100, "牧羊人V6优化器: 本地可用", "")
        except Exception as e:
            return (False, 0, f"牧羊人优化器: 不可用 - {e}", "检查 core/shepherd_optimizer.py")
    yield ("L2_005", "牧羊人优化器V6", "L2_业务链路", "critical", "both", _l2_005)

    def _l2_006():
        try:
            from core.walk_forward import WalkForwardAnalyzer
            wf = WalkForwardAnalyzer()
            return (True, 100, "Walk-Forward分析器: 可用", "")
        except Exception as e:
            return (False, 0, f"Walk-Forward: 不可用 - {e}", "检查 core/walk_forward.py")
    yield ("L2_006", "Walk-Forward分析", "L2_业务链路", "warning", "both", _l2_006)

    def _l2_007():
        try:
            from core.backtest_comparator import BacktestComparator
            bc = BacktestComparator()
            return (True, 100, "回测对比器: 可用", "")
        except Exception as e:
            return (False, 0, f"回测对比器: 不可用 - {e}", "检查 core/backtest_comparator.py")
    yield ("L2_007", "回测多策略对比", "L2_业务链路", "warning", "both", _l2_007)

    # ====== 韬策略引擎 & 熵韬收敛 & 工作流 (5项) ======

    def _l2_008():
        try:
            from core.tau_cluster_engine import TauClusterEngine, get_cluster_engine
            engine = get_cluster_engine()
            strategy_count = len(engine.get_registered_strategies())
            has_scheduler = engine.weight_scheduler is not None
            has_validator = engine.validator is not None
            has_regime = engine.regime_detector is not None
            return (True, 100 if strategy_count > 0 else 70,
                    f"韬策略引擎: {strategy_count}个策略, "
                    f"权重调度={'✓' if has_scheduler else '✗'}, "
                    f"共振验证={'✓' if has_validator else '✗'}, "
                    f"市场检测={'✓' if has_regime else '✗'}",
                    "注册策略以激活引擎" if strategy_count == 0 else "")
        except Exception as e:
            return (False, 0, f"韬策略引擎: 不可用 - {e}", "检查 core/tau_cluster_engine.py")
    yield ("L2_008", "韬策略引擎可用性", "L2_业务链路", "critical", "both", _l2_008)

    def _l2_009():
        try:
            from core.tau_optimizer_cluster import (
                TauOptimizerCluster,
                get_parameter_store,
            )
            has_cluster_class = TauOptimizerCluster is not None
            store = get_parameter_store()
            has_folding = hasattr(store, 'get_param_groups')
            has_cache = hasattr(store, 'get_stats')
            all_info = store.get_all_strategies_info() if hasattr(store, 'get_all_strategies_info') else []
            return (True, 100,
                    f"熵韬收敛优化器: 集群={'✓' if has_cluster_class else '✗'}, "
                    f"参数分组={'✓' if has_folding else '✗'}, "
                    f"缓存统计={'✓' if has_cache else '✗'}, "
                    f"历史参数={len(all_info)}条",
                    "检查 core/tau_optimizer_cluster.py" if not all([has_cluster_class, has_folding, has_cache]) else "")
        except Exception as e:
            return (False, 0, f"熵韬收敛优化器: 不可用 - {e}", "检查 core/tau_optimizer_cluster.py")
    yield ("L2_009", "熵韬收敛优化器核心", "L2_业务链路", "critical", "both", _l2_009)

    def _l2_010():
        try:
            from core.workflow_engine import OneClickWorkflowEngine, get_workflow_engine
            engine = get_workflow_engine()
            has_full = hasattr(engine, '_run_full_workflow')
            has_manual = hasattr(engine, '_run_manual_workflow')
            has_step = hasattr(engine, 'run_step')
            has_batch = 'batch_mode' in engine.run_oneclick.__code__.co_varnames
            return (True, 100,
                    f"工作流引擎: 完整链路={'✓' if has_full else '✗'}, "
                    f"降级手动={'✓' if has_manual else '✗'}, "
                    f"单步执行={'✓' if has_step else '✗'}, "
                    f"批量模式={'✓' if has_batch else '✗'}",
                    "检查 core/workflow_engine.py" if not all([has_full, has_manual, has_step, has_batch]) else "")
        except Exception as e:
            return (False, 0, f"工作流引擎: 不可用 - {e}", "检查 core/workflow_engine.py")
    yield ("L2_010", "工作流引擎可用性", "L2_业务链路", "critical", "both", _l2_010)

    def _l2_011():
        ok, d = hc._api_get("/api/workflow/status")
        status_ok = ok
        ok2, d2 = hc._api_get("/api/workflow/history")
        hist_ok = ok2
        all_ok = status_ok and hist_ok
        return (all_ok, 100 if all_ok else 50,
                f"工作流API: status={'✓' if status_ok else '✗'}, "
                f"history={'✓' if hist_ok else '✗'}",
                "" if all_ok else "检查 gateway.py 中 /api/workflow/* 端点")
    yield ("L2_011", "工作流API端点", "L2_业务链路", "warning", "both", _l2_011)

    # ====== 股票池 (1项，合并L2_014+L4_003) ======

    def _l2_012():
        try:
            from core.stock_pool import StockPoolManager, get_stock_pool_manager
            pool_mgr = get_stock_pool_manager()
            summary = pool_mgr.get_pool_summary()
            if isinstance(summary, dict):
                total = sum(summary.values())
                detail_parts = []
                for level_name in ['观察', '候选', '测试', '预实盘', '实盘']:
                    cnt = summary.get(level_name, 0)
                    detail_parts.append(f"{level_name}{cnt}")
                detail_str = '→'.join(detail_parts)
            else:
                total = len(summary) if summary else 0
                detail_str = f"共{total}只"
            api_ok, _ = hc._api_get("/api/stock-pool")
            return (True, 100 if total > 0 and api_ok else 70,
                    f"股票池: {detail_str}, API={'✓' if api_ok else '✗'}",
                    "执行选股流程以填充股票池" if total == 0 else "")
        except Exception as e:
            return (False, 0, f"股票池: 不可用 - {e}", "检查 core/stock_pool.py")
    yield ("L2_012", "股票池", "L2_业务链路", "warning", "both", _l2_012)

    # ====== 自适应层 (1项) ======

    def _l2_013():
        try:
            from core.adaptive_market_regime import (
                MultiDimensionalRegimeDetector,
                StrategyPerformanceProfile,
                StrategyProfileStore,
                get_adaptation_engine,
            )
            engine = get_adaptation_engine()
            has_detector = (hasattr(engine, 'detector') and engine.detector is not None)
            has_profile_store = (hasattr(engine, 'profile_store') and
                                engine.profile_store is not None)
            return (has_detector and has_profile_store, 100 if has_detector and has_profile_store else 70,
                    f"自适应层: 市场检测={'✓' if has_detector else '✗'}, "
                    f"画像存储={'✓' if has_profile_store else '✗'}",
                    "检查 core/adaptive_market_regime.py" if not (has_detector and has_profile_store) else "")
        except Exception as e:
            return (False, 0, f"自适应层: 不可用 - {e}", "检查 core/adaptive_market_regime.py")
    yield ("L2_013", "策略自适应层", "L2_业务链路", "warning", "both", _l2_013)

    # ====== 独立保留项 (2项) ======

    def _l2_014():
        try:
            from core.adaptive_market_regime import StrategyProfileStore
            store_path = os.path.join(PROJECT_ROOT, "data", "strategy_profiles.json")
            store = StrategyProfileStore(storage_path=store_path)
            profiles = store.get_all_profiles() if hasattr(store, 'get_all_profiles') else []
            profile_count = len(profiles) if profiles else 0
            return (True, 100 if profile_count > 0 else 80,
                    f"策略画像存储: {profile_count}个画像, "
                    f"路径={'✓' if os.path.exists(store_path) else '✗'}",
                    "执行一次优化以生成策略画像" if profile_count == 0 else "")
        except Exception as e:
            return (False, 0, f"策略画像存储: 不可用 - {e}", "检查 core/adaptive_market_regime.py")
    yield ("L2_014", "策略性能画像存储", "L2_业务链路", "warning", "both", _l2_014)

    def _l2_015():
        try:
            from core.stock_pool import StockPoolManager, StockSource
            mgr = StockPoolManager()
            summary = mgr.get_source_summary()
            has_all_sources = all(k in summary for k in
                                   ["aurora_native", "vibe_trading", "ths_iwencai"])
            matrix = mgr.get_source_level_matrix()
            has_matrix = "aurora_native" in matrix and "ths_iwencai" in matrix
            return (has_all_sources and has_matrix,
                    100 if has_all_sources and has_matrix else 60,
                    f"三类分流: 来源={len(summary)}, 矩阵={'✓' if has_matrix else '✗'}",
                    "检查 core/stock_pool.py StockSource 枚举" if not has_all_sources else "")
        except Exception as e:
            return (False, 0, f"三类选股分流: 不可用 - {e}", "检查 core/stock_pool.py")
    yield ("L2_015", "三类选股分流", "L2_业务链路", "warning", "both", _l2_015)

    # ====== 同花顺入口 (4子项，各占25分) ======

    def _l2_016a():
        try:
            from api.ths_bridge import HttpAdapter, IwencaiAdapter, SignalCollector
            collector = SignalCollector()
            s14, s18 = collector.list_strategies()
            ok = len(s14) == 14 and len(s18) == 18
            return (ok, 25 if ok else 0,
                    f"THS-桥接: 14策略={'✓' if len(s14)==14 else '✗'}({len(s14)}), "
                    f"18战法={'✓' if len(s18)==18 else '✗'}({len(s18)})",
                    "检查 core/strategies/ths_strategies/ 目录" if not ok else "")
        except Exception as e:
            return (False, 0, f"THS-桥接: 不可用 - {e}", "检查 api/ths_bridge/ 模块")
    yield ("L2_016a", "THS-桥接模块", "L2_业务链路", "critical", "both", _l2_016a)

    def _l2_016b():
        try:
            from api.ths_bridge.market_intel import get_market_intel_collector
            from core.stock_pool import StockSource
            collector = get_market_intel_collector()
            data = collector.fetch_all()
            dims = sum(1 for k in ["hot_stocks","market_overview","capital_flow",
                                    "sector_rotation","market_emotion"] if k in data)
            seed_ok = (StockSource.THS_MASTER_POOL.value in
                       [s.value for s in StockSource.seed_sources()])
            ok = dims == 5 and seed_ok
            return (ok, 25 if ok else 0,
                    f"THS-情报: {dims}/5维度, 种子池={'✓' if seed_ok else '✗'}",
                    "检查 api/ths_bridge/market_intel.py" if not ok else "")
        except Exception as e:
            return (False, 0, f"THS-情报: 不可用 - {e}", "检查 api/ths_bridge/market_intel.py")
    yield ("L2_016b", "THS-市场情报", "L2_业务链路", "warning", "both", _l2_016b)

    def _l2_016c():
        """同花顺问财选股API（新增）"""
        ok, _ = hc._api_get("/ths_academy/api/strategies")
        return (ok, 25 if ok else 0, f"THS-问财选股: {'可达' if ok else '不可达'}", "")
    yield ("L2_016c", "THS-问财选股", "L2_业务链路", "warning", "both", _l2_016c)

    def _l2_016d():
        """同花顺信号收集（新增）"""
        try:
            from api.ths_bridge import SignalCollector
            c = SignalCollector()
            s14, s18 = c.list_strategies()
            total = len(s14) + len(s18)
            return (total >= 32, 25 if total >= 32 else 0,
                    f"THS-信号收集: {total}个(14策略+18战法)", "")
        except Exception as e:
            return (False, 0, f"THS-信号收集: 不可用 - {e}", "检查 api/ths_bridge/")
    yield ("L2_016d", "THS-信号收集", "L2_业务链路", "warning", "both", _l2_016d)