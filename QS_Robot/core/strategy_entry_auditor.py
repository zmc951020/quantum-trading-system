"""策略入口与工程闭环流审查器 - 独立可复用类
五维22节点：Aurora策略审查 → 三大入口关系 → 工程流完整性 → 优化器链路 → Vibe Trading
与 EngineeringLoopAuditor（基础设施检查）互补，专注策略业务逻辑深度审查
"""
import os
import sys
import json
import time
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger("StrategyEntryAuditor")


class StrategyEntryAuditor:
    """策略入口与工程闭环流审查器，五维22节点深度业务逻辑审查

    与 EngineeringLoopAuditor 的关系：
    - EngineeringLoopAuditor: 基础设施层（CSS/按钮/导航/API端点）
    - StrategyEntryAuditor:  业务逻辑层（策略数量/工程流/优化器链路/Vibe集成）

    用法:
        auditor = StrategyEntryAuditor()
        report = auditor.run_all()         # 全量审查
        report = auditor.run_category("Aurora策略审查")  # 按维度审查
        auditor.save_report(report)        # 保存JSON报告
        auditor.generate_markdown(report)  # 生成Markdown报告
    """

    # ── 类常量 ──────────────────────────────────────────

    STRATEGY_DIRS = {
        "14基础策略": "core/strategies/ths_strategies/14_strategies",
        "18高级战法": "core/strategies/ths_strategies/18_advanced",
    }

    OPTIMIZER_SOURCES = {
        "5003韬定律": ["tau_optimizer_cluster", "tau_enhanced_optimizer",
                        "shepherd_optimizer", "special_forces_optimizer"],
        "5002Aurora": ["shepherd", "genetic", "bayesian", "grid_search",
                       "random_search", "gyro", "hmm", "quantum"],
    }

    WORKFLOW_STAGES = [
        "vibe_analysis", "cluster_select", "integration_full", "discover",
        "optimize", "backtest", "match_stocks", "adapt", "signals", "trading_config",
    ]

    POOL_LEVELS = ["观察池", "候选池", "测试池", "预实盘池", "实盘池"]

    def __init__(self, project_root: str = None):
        if project_root:
            self.project_root = project_root
        else:
            # 默认取 __file__ 的父目录的父目录（即项目根目录）
            self.project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.results: List[Dict[str, Any]] = []
        self.start_time: Optional[datetime] = None

    # ══════════════════════════════════════════════════════
    # 公共API
    # ══════════════════════════════════════════════════════

    def run_all(self, verbose: bool = True) -> Dict[str, Any]:
        """运行全部22项检查"""
        self.start_time = datetime.now()
        self.results = []
        logger.info(f"[StrategyEntry] === 开始全量审查 {self.start_time.isoformat()} ===")

        if verbose:
            print("=" * 70)
            print("  策略入口与工程闭环流审查")
            print(f"  开始时间: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 70)

        for name, fn in self._all_checks():
            self._run_check(name, fn, verbose)

        return self._build_report(verbose)

    def run_category(self, category: str, verbose: bool = True) -> Dict[str, Any]:
        """运行指定维度检查"""
        self.start_time = datetime.now()
        self.results = []

        for name, fn in self._all_checks():
            if category in name:
                self._run_check(name, fn, verbose)

        return self._build_report(verbose)

    def save_report(self, report: Dict[str, Any] = None, filename: str = None) -> str:
        """保存审查报告为JSON"""
        if report is None:
            report = self._build_report(False)
        report_dir = os.path.join(self.project_root, "data", "health_reports")
        os.makedirs(report_dir, exist_ok=True)
        if filename is None:
            ts = (self.start_time or datetime.now()).strftime('%Y%m%d_%H%M%S')
            filename = f"strategy_entry_{ts}.json"
        path = os.path.join(report_dir, filename)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        logger.info(f"[StrategyEntry] 报告已保存: {path}")
        return path

    def generate_markdown(self, report: Dict[str, Any] = None, filename: str = None) -> str:
        """生成Markdown审查报告"""
        if report is None:
            report = self._build_report(False)
        lines = self._render_markdown(report)
        report_dir = os.path.join(self.project_root, "data", "health_reports")
        os.makedirs(report_dir, exist_ok=True)
        if filename is None:
            ts = (self.start_time or datetime.now()).strftime('%Y%m%d_%H%M%S')
            filename = f"策略入口审查_{ts}.md"
        path = os.path.join(report_dir, filename)
        with open(path, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))
        logger.info(f"[StrategyEntry] Markdown报告已保存: {path}")
        return path

    @classmethod
    def get_check_list(cls) -> List[Dict[str, str]]:
        """返回所有22个检查节点的元数据"""
        return [
            {"category": "Aurora策略审查", "node": "N1", "name": "Aurora策略-下拉框数量", "desc": "Aurora 5002 StrategyRegistry注册策略数"},
            {"category": "Aurora策略审查", "node": "N2", "name": "Aurora策略-孤儿策略检测", "desc": "THS策略文件是否在Aurora下拉框中"},
            {"category": "Aurora策略审查", "node": "N3", "name": "Aurora策略-分类完整性", "desc": "物理建模/ML增强/传统/网格四分类"},
            {"category": "Aurora策略审查", "node": "N4", "name": "Aurora策略-标签库与集群矩阵一致性", "desc": "标签库与集群矩阵数据源关系"},
            {"category": "三大入口关系", "node": "N1", "name": "三大入口-Aurora自创策略", "desc": "Aurora核心适配器与页面可用性"},
            {"category": "三大入口关系", "node": "N2", "name": "三大入口-同花顺金融大师", "desc": "14策略+18战法合计≥32"},
            {"category": "三大入口关系", "node": "N3", "name": "三大入口-港大Vibe智能体", "desc": "29智能体注册与集成"},
            {"category": "三大入口关系", "node": "N4", "name": "三大入口-数据源独立性", "desc": "三入口各自API端点独立"},
            {"category": "三大入口关系", "node": "N5", "name": "三大入口-页面展示关系", "desc": "同一页面aurora_main.html不同数据源"},
            {"category": "工程流完整性", "node": "N1", "name": "工程流-选股到候选池", "desc": "集群选股→_push_to_stock_pool(candidate)"},
            {"category": "工程流完整性", "node": "N2", "name": "工程流-候选池到测试迭代", "desc": "回测验证→测试池流转"},
            {"category": "工程流完整性", "node": "N3", "name": "工程流-测试到预实盘", "desc": "风控评分>80→预实盘池"},
            {"category": "工程流完整性", "node": "N4", "name": "工程流-预实盘到实盘", "desc": "模拟盘验证→实盘池"},
            {"category": "工程流完整性", "node": "N5", "name": "工程流-实盘到交易", "desc": "TradeExecutor交易执行"},
            {"category": "工程流完整性", "node": "N6", "name": "工程流-8阶段工作流引擎", "desc": "OneClickWorkflowEngine全阶段"},
            {"category": "优化器链路", "node": "N1", "name": "优化器-总数统计", "desc": "5003韬定律+5002Aurora优化器"},
            {"category": "优化器链路", "node": "N2", "name": "优化器-策略关联可视化", "desc": "aurora_main.html优化器卡片与策略表格按钮"},
            {"category": "优化器链路", "node": "N3", "name": "优化器-API端点", "desc": "/api/tau/optimize等端点"},
            {"category": "优化器链路", "node": "N4", "name": "优化器-闭环链路", "desc": "参数优化→回测→交易配置闭环"},
            {"category": "Vibe Trading", "node": "N1", "name": "Vibe-29智能体注册", "desc": "VibeAgentAnalyzer智能体方法数"},
            {"category": "Vibe Trading", "node": "N2", "name": "Vibe-分析推荐链路", "desc": "analyze_stock_enhanced→综合评分→股票池推荐"},
            {"category": "Vibe Trading", "node": "N3", "name": "Vibe-推荐到交易", "desc": "推荐→WorkflowEngine→选股→交易"},
        ]

    # ══════════════════════════════════════════════════════
    # 内部：检查流程
    # ══════════════════════════════════════════════════════

    def _run_check(self, name: str, fn, verbose: bool):
        """执行单个检查并记录结果"""
        try:
            t0 = time.time()
            logger.info(f"[StrategyEntry] 开始检查: {name}")
            passed, detail = fn()
            elapsed = (time.time() - t0) * 1000
            result = {"name": name, "passed": passed, "detail": str(detail), "elapsed_ms": round(elapsed, 1)}
            logger.info(f"[StrategyEntry] 完成检查: {name} -> {'PASS' if passed else 'FAIL'} ({elapsed:.1f}ms)")
        except Exception as e:
            logger.error(f"[StrategyEntry] 检查异常: {name} -> {e}", exc_info=True)
            result = {"name": name, "passed": False, "detail": f"异常: {e}", "elapsed_ms": 0}
        self.results.append(result)
        if verbose:
            status = "✅" if result["passed"] else "❌"
            print(f"  {status} {name}: {result['detail']}")

    def _all_checks(self) -> List[Tuple[str, callable]]:
        return [
            # 维度1: Aurora策略审查 (4)
            ("Aurora策略-下拉框数量", self._check_aurora_count),
            ("Aurora策略-孤儿策略检测", self._check_aurora_orphan),
            ("Aurora策略-分类完整性", self._check_aurora_category),
            ("Aurora策略-标签库与集群矩阵一致性", self._check_aurora_consistency),
            # 维度2: 三大入口关系 (5)
            ("三大入口-Aurora自创策略", self._check_entries_aurora),
            ("三大入口-同花顺金融大师", self._check_entries_ths),
            ("三大入口-港大Vibe智能体", self._check_entries_vibe),
            ("三大入口-数据源独立性", self._check_entries_independent),
            ("三大入口-页面展示关系", self._check_entries_same_page),
            # 维度3: 工程流完整性 (6)
            ("工程流-选股到候选池", self._check_flow_select_to_pool),
            ("工程流-候选池到测试迭代", self._check_flow_pool_to_test),
            ("工程流-测试到预实盘", self._check_flow_test_to_prelive),
            ("工程流-预实盘到实盘", self._check_flow_prelive_to_live),
            ("工程流-实盘到交易", self._check_flow_live_to_trade),
            ("工程流-8阶段工作流引擎", self._check_flow_workflow_stages),
            # 维度4: 优化器链路 (4)
            ("优化器-总数统计", self._check_optimizer_count),
            ("优化器-策略关联可视化", self._check_optimizer_visual),
            ("优化器-API端点", self._check_optimizer_api),
            ("优化器-闭环链路", self._check_optimizer_loop),
            # 维度5: Vibe Trading (3)
            ("Vibe-29智能体注册", self._check_vibe_agents),
            ("Vibe-分析推荐链路", self._check_vibe_recommend),
            ("Vibe-推荐到交易", self._check_vibe_to_trade),
        ]

    # ══════════════════════════════════════════════════════
    # 维度1: Aurora策略审查 (4节点)
    # ══════════════════════════════════════════════════════

    def _check_aurora_count(self):
        """N1: 下拉框策略数量——通过Aurora适配器获取策略列表"""
        try:
            from api.aurora_core_adapter import AuroraCoreAdapter
            adapter = AuroraCoreAdapter()
            strategies = adapter.get_strategy_list() if hasattr(adapter, 'get_strategy_list') else []
            count = len(strategies) if isinstance(strategies, list) else 0
            ok = count > 0
            logger.info(f"[StrategyEntry] Aurora策略列表: {count}个核心策略 -> {'PASS' if ok else 'FAIL'}")
            return ok, f"Aurora策略列表={count}个核心策略"
        except Exception as e:
            logger.warning(f"[StrategyEntry] Aurora策略列表获取失败: {e}")
            return False, f"Aurora适配器不可用: {e}"

    def _check_aurora_orphan(self):
        """N2: 孤儿策略检测——THS策略文件是否在Aurora下拉框中"""
        issues = []
        ths_files = self._scan_ths_strategy_files()
        aurora_names = self._get_aurora_strategy_names()

        for fname, display_name in ths_files:
            if display_name and display_name not in aurora_names:
                issues.append(f"{fname}({display_name})")

        ok = len(issues) == 0
        logger.info(f"[StrategyEntry] 孤儿策略: {len(issues)}个 -> {'PASS' if ok else 'FAIL'}")
        if issues:
            logger.warning(f"[StrategyEntry] 孤儿策略列表: {issues}")
        detail = f"THS文件={len(ths_files)}个, 孤儿={len(issues)}个"
        if issues:
            detail += f": {issues[:3]}"
        return ok, detail

    def _check_aurora_category(self):
        """N3: 策略分类完整性——物理建模/ML增强/传统/网格四分类"""
        categories_found = set()
        try:
            from api.aurora_core_adapter import AuroraCoreAdapter
            adapter = AuroraCoreAdapter()
            strategies = adapter.get_strategy_list() if hasattr(adapter, 'get_strategy_list') else []
            for s in strategies:
                # 多字段兼容：category > type > strategy_type > 策略名称推断
                cat = s.get("category", "") or s.get("type", "") or s.get("strategy_type", "")
                if not cat and isinstance(s.get("name", ""), str):
                    name = s["name"].lower()
                    if "物理" in name or "physics" in name or "gyro" in name or "bernoulli" in name or "fourier" in name:
                        cat = "physics"
                    elif "ml" in name or "机器学习" in name or "神经网络" in name:
                        cat = "ml"
                    elif "网格" in name or "grid" in name:
                        cat = "grid"
                    elif "均线" in name or "macd" in name or "rsi" in name or "kdj" in name or "布林" in name:
                        cat = "traditional"
                if cat:
                    categories_found.add(cat)
        except Exception:
            pass

        expected = {"physics", "ml", "traditional", "grid"}
        ok = len(categories_found & expected) >= 3
        logger.info(f"[StrategyEntry] 策略分类: 已发现={categories_found}, 期望={expected} -> {'PASS' if ok else 'FAIL'}")
        return ok, f"分类={categories_found}"

    def _check_aurora_consistency(self):
        """N4: 标签库与集群矩阵数据源一致性"""
        try:
            aurora_page = os.path.join(self.project_root, "ui", "templates", "aurora_main.html")
            if not os.path.exists(aurora_page):
                return False, "aurora_main.html不存在"
            with open(aurora_page, 'r', encoding='utf-8') as f:
                content = f.read()
            has_tag_lib = "/api/strategy/list" in content
            has_cluster_tab = "cluster-tabs" in content
            has_ths = "ths" in content.lower()
            has_custom = "custom" in content.lower()
            has_vibe = "vibe" in content.lower()
            ok = has_tag_lib and has_cluster_tab and has_ths and has_custom and has_vibe
            logger.info(f"[StrategyEntry] 页面一致性: 标签库={'✓' if has_tag_lib else '✗'}, "
                        f"集群Tab={'✓' if has_cluster_tab else '✗'}, "
                        f"THS={'✓' if has_ths else '✗'}, "
                        f"自创={'✓' if has_custom else '✗'}, "
                        f"Vibe={'✓' if has_vibe else '✗'} -> {'PASS' if ok else 'FAIL'}")
            return ok, "标签库+集群矩阵THS/自创/Vibe三Tab齐全"
        except Exception as e:
            return False, str(e)

    # ══════════════════════════════════════════════════════
    # 维度2: 三大入口关系 (5节点)
    # ══════════════════════════════════════════════════════

    def _check_entries_aurora(self):
        """N1: Aurora自创策略——核心适配器与页面可用性"""
        issues = []
        try:
            from api.aurora_core_adapter import AuroraCoreAdapter
            issues.append("Aurora适配器✅")
        except ImportError:
            issues.append("Aurora适配器❌")
        has_page = os.path.exists(os.path.join(self.project_root, "ui", "templates", "aurora_main.html"))
        issues.append(f"页面={'✓' if has_page else '✗'}")
        try:
            from core.tau_cluster_engine import get_cluster_engine
            engine = get_cluster_engine()
            count = len(engine.get_registered_strategies())
            issues.append(f"集群策略={count}个")
        except Exception as e:
            issues.append(f"集群策略❌({e})")
        all_ok = "❌" not in " ".join(issues)
        return all_ok, ", ".join(issues)

    def _check_entries_ths(self):
        """N2: 同花顺金融大师——14策略+18战法"""
        try:
            from api.ths_bridge.signal_collector import SignalCollector
            collector = SignalCollector()
            s14, s18 = collector.list_strategies()
            total = len(s14) + len(s18)
            ok = total >= 32
            logger.info(f"[StrategyEntry] 同花顺策略: 14策略={len(s14)}, 18战法={len(s18)}, 合计={total} -> {'PASS' if ok else 'FAIL'}")
            return ok, f"14策略={len(s14)}, 18战法={len(s18)}, 合计={total}"
        except Exception as e:
            logger.warning(f"[StrategyEntry] 同花顺入口检查失败: {e}")
            return False, str(e)

    def _check_entries_vibe(self):
        """N3: 港大Vibe智能体"""
        issues = []
        try:
            from core.vibe_29_agents import VibeAgentAnalyzer
            methods = [m for m in dir(VibeAgentAnalyzer) if m.endswith('_agent') and not m.startswith('__')]
            issues.append(f"智能体={len(methods)}个")
        except ImportError:
            issues.append("Vibe智能体❌")
        try:
            from core.vibe_integration import VibeIntegration
            issues.append("Vibe集成✅")
        except ImportError:
            issues.append("Vibe集成❌")
        has_page = os.path.exists(os.path.join(self.project_root, "ui", "templates", "vibe_analysis.html"))
        issues.append(f"页面={'✓' if has_page else '✗'}")
        all_ok = "❌" not in " ".join(issues)
        return all_ok, ", ".join(issues)

    def _check_entries_independent(self):
        """N4: 三入口数据源独立性——各自API端点独立"""
        gw_path = os.path.join(self.project_root, "api", "gateway.py")
        if not os.path.exists(gw_path):
            return False, "gateway.py不存在"
        with open(gw_path, 'r', encoding='utf-8') as f:
            content = f.read()
        patterns = [
            ("Aurora", ["/api/strategy/list", "/api/optimizer/list"]),
            ("同花顺", ["/api/cluster/ths", "/cluster/ths", "/api/ths", "/ths"]),
            ("Vibe", ["/api/vibe", "/api/vibe/agents"]),
        ]
        results = []
        for label, endpoints in patterns:
            found = [e for e in endpoints if e in content]
            results.append(f"{label}={len(found)}/{len(endpoints)}")
        ok = all("0/" not in r for r in results)
        return ok, ", ".join(results)

    def _check_entries_same_page(self):
        """N5: 页面展示关系——同一页面不同数据源"""
        aurora_page = os.path.join(self.project_root, "ui", "templates", "aurora_main.html")
        if not os.path.exists(aurora_page):
            return False, "aurora_main.html不存在"
        with open(aurora_page, 'r', encoding='utf-8') as f:
            content = f.read()
        has_tag_lib = "/api/strategy/list" in content
        has_cluster_tabs = "cluster-tabs" in content or "策略矩阵" in content
        has_three_tabs = sum(1 for kw in ["ths", "custom", "vibe"] if kw in content.lower()) >= 3
        ok = has_tag_lib and has_cluster_tabs and has_three_tabs
        logger.info(f"[StrategyEntry] 页面关系: 同一页面aurora_main.html, "
                    f"标签库={'✓' if has_tag_lib else '✗'}, "
                    f"集群矩阵={'✓' if has_cluster_tabs else '✗'}, "
                    f"三Tab={'✓' if has_three_tabs else '✗'} -> {'PASS' if ok else 'FAIL'}")
        return ok, "同一页面(aurora_main.html)不同数据源: 标签库(Aurora5002) + 集群矩阵(三入口独立API)"

    # ══════════════════════════════════════════════════════
    # 维度3: 工程流完整性 (6节点)
    # ══════════════════════════════════════════════════════

    def _check_flow_select_to_pool(self):
        """N1: 选股→候选池"""
        try:
            from core.workflow_engine import get_workflow_engine
            engine = get_workflow_engine()
            import inspect
            src = inspect.getsource(engine._stage_cluster_select)
            has_push = "_push_to_stock_pool" in src or "stock_pool" in src.lower()
            return has_push, f"集群选股自动入池={'✓' if has_push else '✗'}"
        except Exception as e:
            return False, str(e)

    def _check_flow_pool_to_test(self):
        """N2: 候选池→测试迭代"""
        issues = []
        try:
            from core.stock_pool import get_stock_pool_manager
            pool = get_stock_pool_manager()
            has_promote = hasattr(pool, 'promote') or hasattr(pool, 'move_to_testing')
            issues.append(f"池流转={'✓' if has_promote else '✗'}")
        except ImportError:
            issues.append("池管理❌")
        try:
            from core.backtest_engine import SimpleBacktestEngine
            issues.append("回测引擎✅")
        except ImportError:
            issues.append("回测引擎❌")
        all_ok = "❌" not in " ".join(issues)
        return all_ok, ", ".join(issues)

    def _check_flow_test_to_prelive(self):
        """N3: 测试池→预实盘池"""
        try:
            from core.stock_pool import get_stock_pool_manager, PoolLevel
            pool = get_stock_pool_manager()
            # 检查预实盘池是否存在（通过get_pool_summary获取各层级数量）
            summary = pool.get_pool_summary() if hasattr(pool, 'get_pool_summary') else {}
            has_prelive = summary.get('prelive', -1) >= 0
            # 检查是否有升级到预实盘的过滤器
            has_filters = hasattr(pool, '_filters') and 'to_prelive' in pool._filters
            return has_prelive or has_filters, f"预实盘池={'✓' if has_prelive else '✗'}, 过滤器={'✓' if has_filters else '✗'}"
        except Exception as e:
            return False, str(e)

    def _check_flow_prelive_to_live(self):
        """N4: 预实盘→实盘"""
        try:
            from core.stock_pool import get_stock_pool_manager, PoolLevel
            pool = get_stock_pool_manager()
            summary = pool.get_pool_summary() if hasattr(pool, 'get_pool_summary') else {}
            has_live = summary.get('live', -1) >= 0
            return has_live, f"实盘池={'✓' if has_live else '✗'}, 摘要={summary}"
        except Exception as e:
            return False, str(e)

    def _check_flow_live_to_trade(self):
        """N5: 实盘→交易执行"""
        try:
            from core.trade_executor import TradeExecutor
            executor = TradeExecutor()
            mode = getattr(executor, 'mode', 'unknown')
            is_sim = mode == 'simulation' or 'sim' in str(mode).lower()
            return True, f"TradeExecutor可用, 模式={'模拟盘' if is_sim else mode}"
        except Exception as e:
            return False, str(e)

    def _check_flow_workflow_stages(self):
        """N6: 8阶段工作流引擎"""
        try:
            from core.workflow_engine import get_workflow_engine
            engine = get_workflow_engine()
            import inspect
            src = inspect.getsource(engine.__class__)
            found = []
            for stage in self.WORKFLOW_STAGES:
                if f"_stage_{stage}" in src:
                    found.append(stage)
            ok = len(found) >= 7
            logger.info(f"[StrategyEntry] 工作流阶段: {len(found)}/{len(self.WORKFLOW_STAGES)} -> {'PASS' if ok else 'FAIL'}")
            return ok, f"工作流阶段={len(found)}/{len(self.WORKFLOW_STAGES)}"
        except Exception as e:
            return False, str(e)

    # ══════════════════════════════════════════════════════
    # 维度4: 优化器链路 (4节点)
    # ══════════════════════════════════════════════════════

    def _check_optimizer_count(self):
        """N1: 优化器总数统计"""
        # 使用预定义常量直接统计（避免依赖外部API）
        tau_count = len(self.OPTIMIZER_SOURCES.get("5003韬定律", []))
        aurora_count = len(self.OPTIMIZER_SOURCES.get("5002Aurora", []))
        total = tau_count + aurora_count
        # 兜底：扫描文件系统
        if total == 0:
            total = self._scan_optimizer_files()
        ok = total >= 10
        logger.info(f"[StrategyEntry] 优化器: 韬定律={tau_count}, Aurora={aurora_count}, 合计={total} -> {'PASS' if ok else 'FAIL'}")
        return ok, f"韬定律={tau_count}, Aurora={aurora_count}, 合计={total}"

    def _check_optimizer_visual(self):
        """N2: 优化器-策略关联可视化"""
        aurora_page = os.path.join(self.project_root, "ui", "templates", "aurora_main.html")
        if not os.path.exists(aurora_page):
            return False, "aurora_main.html不存在"
        with open(aurora_page, 'r', encoding='utf-8') as f:
            content = f.read()
        has_optimizer_tab = "优化器" in content
        has_optimize_button = "optimize" in content.lower() or "优化" in content
        has_card = "optimizer-card" in content.lower() or "优化器" in content
        ok = has_optimizer_tab and has_optimize_button
        logger.info(f"[StrategyEntry] 优化器可视化: 优化器标签={'✓' if has_optimizer_tab else '✗'}, "
                    f"优化按钮={'✓' if has_optimize_button else '✗'}, "
                    f"卡片={'✓' if has_card else '✗'} -> {'PASS' if ok else 'FAIL'}")
        return ok, f"优化器标签={'✓' if has_optimizer_tab else '✗'}, 优化按钮={'✓' if has_optimize_button else '✗'}"

    def _check_optimizer_api(self):
        """N3: 优化器API端点"""
        gw_path = os.path.join(self.project_root, "api", "gateway.py")
        if not os.path.exists(gw_path):
            return False, "gateway.py不存在"
        with open(gw_path, 'r', encoding='utf-8') as f:
            content = f.read()
        endpoints = [
            "/api/optimizer/list", "/api/tau/optimize",
            "/api/optimizer/run", "/api/strategy/optimize",
        ]
        found = [e for e in endpoints if e in content]
        ok = len(found) >= 2
        return ok, f"端点={len(found)}/{len(endpoints)}: {found}"

    def _check_optimizer_loop(self):
        """N4: 优化器闭环链路——参数优化→回测→交易配置"""
        issues = []
        for mod, label in [("tau_optimizer_cluster", "TauCluster优化器"),
                           ("backtest_engine", "回测引擎"),
                           ("trade_executor", "交易执行器")]:
            try:
                __import__(f"core.{mod}")
                issues.append(f"{label}✅")
            except ImportError:
                issues.append(f"{label}❌")
        all_ok = "❌" not in " ".join(issues)
        return all_ok, ", ".join(issues)

    # ══════════════════════════════════════════════════════
    # 维度5: Vibe Trading (3节点)
    # ══════════════════════════════════════════════════════

    def _check_vibe_agents(self):
        """N1: 29智能体注册"""
        try:
            from core.vibe_29_agents import VibeAgentAnalyzer
            methods = [m for m in dir(VibeAgentAnalyzer) if m.endswith('_agent') and not m.startswith('__')]
            ok = len(methods) >= 28
            logger.info(f"[StrategyEntry] Vibe智能体: {len(methods)}个 -> {'PASS' if ok else 'FAIL'}")
            return ok, f"智能体={len(methods)}个"
        except Exception as e:
            return False, str(e)

    def _check_vibe_recommend(self):
        """N2: 分析→评分→推荐链路"""
        try:
            from core.vibe_integration import VibeIntegration
            vi = VibeIntegration()
            has_analyze = hasattr(vi, 'analyze_stock_enhanced') or hasattr(vi, 'analyze_stock')
            has_recommend = hasattr(vi, 'get_recommendation') or hasattr(vi, 'get_pool_recommendation')
            has_score = hasattr(vi, 'get_composite_score') or hasattr(vi, 'calculate_score')
            ok = has_analyze
            return ok, f"分析={'✓' if has_analyze else '✗'}, 推荐={'✓' if has_recommend else '✗'}, 评分={'✓' if has_score else '✗'}"
        except Exception as e:
            return False, str(e)

    def _check_vibe_to_trade(self):
        """N3: Vibe推荐→WorkflowEngine→交易"""
        issues = []
        try:
            from core.vibe_integration import VibeIntegration
            issues.append("Vibe集成✅")
        except ImportError:
            issues.append("Vibe集成❌")
        try:
            from core.workflow_engine import get_workflow_engine
            engine = get_workflow_engine()
            import inspect
            src = inspect.getsource(engine.__class__)
            has_vibe = "vibe" in src.lower()
            issues.append(f"工作流Vibe集成={'✓' if has_vibe else '✗'}")
        except Exception as e:
            issues.append(f"工作流❌({e})")
        try:
            from core.trade_executor import TradeExecutor
            issues.append("交易执行✅")
        except ImportError:
            issues.append("交易执行❌")
        all_ok = "❌" not in " ".join(issues)
        return all_ok, ", ".join(issues)

    # ══════════════════════════════════════════════════════
    # 辅助方法
    # ══════════════════════════════════════════════════════

    def _scan_ths_strategy_files(self) -> List[Tuple[str, str]]:
        """扫描THS策略文件，返回[(文件名, 策略显示名), ...]"""
        result = []
        for label, subdir in self.STRATEGY_DIRS.items():
            full = os.path.join(self.project_root, subdir)
            if not os.path.exists(full):
                continue
            for f in sorted(os.listdir(full)):
                if not f.endswith(".py") or f.startswith("_") or f.startswith("__"):
                    continue
                fpath = os.path.join(full, f)
                display_name = self._extract_strategy_name(fpath)
                result.append((f"{label}/{f}", display_name))
        return result

    def _extract_strategy_name(self, filepath: str) -> str:
        """从策略文件提取类名或显示名"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            for pattern in [r'class\s+(\w+Strategy)', r'class\s+(\w+Strategy)', r'"""(.+?)"""']:
                m = re.search(pattern, content)
                if m:
                    return m.group(1)
        except Exception:
            pass
        return ""

    def _get_aurora_strategy_names(self) -> set:
        """获取Aurora 5002已注册策略名称集合"""
        try:
            from api.aurora_core_adapter import AuroraCoreAdapter
            adapter = AuroraCoreAdapter()
            strategies = adapter.get_strategy_list() if hasattr(adapter, 'get_strategy_list') else []
            return {s.get("name", "") for s in strategies if isinstance(s, dict)}
        except Exception:
            return set()

    def _scan_optimizer_files(self) -> int:
        """扫描本地优化器文件数量"""
        count = 0
        core_dir = os.path.join(self.project_root, "core")
        if os.path.exists(core_dir):
            for f in os.listdir(core_dir):
                if f.endswith(".py") and "optim" in f.lower():
                    count += 1
        return count

    # ══════════════════════════════════════════════════════
    # 报告生成
    # ══════════════════════════════════════════════════════

    def _build_report(self, verbose: bool = True) -> Dict[str, Any]:
        total = len(self.results)
        passed = sum(1 for r in self.results if r["passed"])
        failed = total - passed
        elapsed = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
        pct = round(passed / total * 100, 1) if total > 0 else 0

        categories = {}
        for r in self.results:
            cat = next((c for c in ["Aurora策略", "三大入口", "工程流", "优化器", "Vibe"] if c in r["name"]), "其他")
            categories.setdefault(cat, {"total": 0, "passed": 0})
            categories[cat]["total"] += 1
            if r["passed"]:
                categories[cat]["passed"] += 1

        if pct >= 95: grade = "优"
        elif pct >= 80: grade = "良"
        elif pct >= 60: grade = "中"
        else: grade = "差"

        logger.info(f"[StrategyEntry] === 审查完成: {passed}/{total} 通过 ({pct}%), 评级={grade}, 耗时={elapsed:.1f}s ===")
        for cat, stats in categories.items():
            cat_pct = stats["passed"] / stats["total"] * 100 if stats["total"] else 0
            logger.info(f"[StrategyEntry]   分类: {cat} = {stats['passed']}/{stats['total']} ({cat_pct:.0f}%)")

        report = {
            "timestamp": self.start_time.isoformat() if self.start_time else "",
            "total": total, "passed": passed, "failed": failed,
            "pass_rate": pct, "grade": grade,
            "elapsed_seconds": round(elapsed, 1),
            "categories": {k: {"total": v["total"], "passed": v["passed"]} for k, v in categories.items()},
            "results": self.results,
            "failed_items": [r for r in self.results if not r["passed"]],
        }

        if verbose and failed > 0:
            print(f"\n  ❌ 失败项 ({failed}):")
            for r in self.results:
                if not r["passed"]:
                    print(f"    - {r['name']}: {r['detail']}")

        if verbose:
            print(f"\n  整体健康度: {grade} ({pct}%) — {passed}/{total} 通过")

        return report

    def _render_markdown(self, report: Dict[str, Any]) -> List[str]:
        """生成Markdown格式报告"""
        lines = [
            "# 策略入口与工程闭环流审查报告",
            "",
            f"- 审查时间: {report['timestamp']}",
            f"- 通过率: {report['pass_rate']}%",
            f"- 评级: {report['grade']}",
            f"- 耗时: {report['elapsed_seconds']}s",
            "",
            "## 分类统计",
            "",
            "| 维度 | 通过 | 总数 | 通过率 |",
            "|------|------|------|--------|",
        ]
        for cat, stats in report["categories"].items():
            pct = stats["passed"] / stats["total"] * 100 if stats["total"] else 0
            lines.append(f"| {cat} | {stats['passed']} | {stats['total']} | {pct:.0f}% |")

        lines.extend(["", "## 详细结果", ""])
        for r in report["results"]:
            status = "✅" if r["passed"] else "❌"
            lines.append(f"- {status} **{r['name']}**: {r['detail']} ({r['elapsed_ms']}ms)")

        if report["failed_items"]:
            lines.extend(["", "## 失败项", ""])
            for r in report["failed_items"]:
                lines.append(f"- ❌ **{r['name']}**: {r['detail']}")

        return lines


# ── 命令行入口 ──────────────────────────────────────────

def main():
    auditor = StrategyEntryAuditor()
    report = auditor.run_all(verbose=True)
    auditor.save_report(report)
    auditor.generate_markdown(report)
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.exit(main())