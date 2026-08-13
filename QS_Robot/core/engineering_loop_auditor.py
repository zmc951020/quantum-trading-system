"""自动化工程闭环流审查器 - 独立可复用类
五维审查：自适应工程工作流 → 策略三大入口 → 可视化模块 → 链路通达性 → 色调风格统一
"""
import os
import re
import json
import time
import sys
import logging
from datetime import datetime
from typing import Dict, List, Any, Callable, Optional

logger = logging.getLogger("EngineeringLoopAuditor")


class EngineeringLoopAuditor:
    """自动化工程闭环流审查器，五维22节点全覆盖"""

    DARK_THEME_VARS = {
        "--bg-deep": "#0a0e1a",
        "--bg-card": "#111827",
        "--bg-panel": "#1a2744",
        "--accent-blue": "#4facfe",
        "--accent-cyan": "#00d4ff",
        "--accent-gold": "#f0c27b",
        "--text-primary": "#e0e6ed",
        "--text-secondary": "#8899aa",
        "--border-subtle": "rgba(107, 165, 247, 0.2)",
        "--success": "#00c853",
        "--danger": "#ff5252",
        "--warning": "#ffab40",
    }

    EXPECTED_PAGES = [
        "dashboard.html", "aurora_main.html", "main_system.html",
        "stock_pool.html", "cluster_selector.html", "vibe_analysis.html",
        "maintenance.html", "technical_analysis.html", "login.html",
        "model_switch.html", "cline_agent.html", "index.html",
    ]

    def __init__(self, project_root: str = None):
        self.project_root = project_root or os.path.dirname(os.path.abspath(__file__))
        self.template_dir = os.path.join(self.project_root, "ui", "templates")
        self.results: List[Dict[str, Any]] = []
        self.start_time: Optional[datetime] = None

    # ── 公共API ──────────────────────────────────────────

    def run_all(self, verbose: bool = True) -> Dict[str, Any]:
        """运行全部22项检查，返回结构化报告"""
        self.start_time = datetime.now()
        self.results = []
        logger.info(f"[EngineeringLoop] === 开始全量审查 {self.start_time.isoformat()} ===")
        logger.info(f"[EngineeringLoop] 项目路径: {self.project_root}")

        if verbose:
            print("=" * 70)
            print("  自动化工程闭环流审查")
            print(f"  开始时间: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  项目路径: {self.project_root}")
            print("=" * 70)

        for name, fn in self._all_checks():
            try:
                t0 = time.time()
                logger.info(f"[EngineeringLoop] 开始检查: {name}")
                passed, detail = fn()
                elapsed = (time.time() - t0) * 1000
                result = {"name": name, "passed": passed, "detail": str(detail), "elapsed_ms": round(elapsed, 1)}
                logger.info(f"[EngineeringLoop] 完成检查: {name} -> {'PASS' if passed else 'FAIL'} ({elapsed:.1f}ms) {detail}")
            except Exception as e:
                logger.error(f"[EngineeringLoop] 检查异常: {name} -> {e}", exc_info=True)
                result = {"name": name, "passed": False, "detail": f"异常: {e}", "elapsed_ms": 0}
            self.results.append(result)
            if verbose:
                status = "✅" if result["passed"] else "❌"
                print(f"  {status} {name}: {result['detail']}")

        return self._build_report()

    def run_category(self, category: str, verbose: bool = True) -> Dict[str, Any]:
        """运行指定维度的检查"""
        self.start_time = datetime.now()
        self.results = []

        checks = self._all_checks()
        for name, fn in checks:
            if category not in name:
                continue
            try:
                t0 = time.time()
                passed, detail = fn()
                elapsed = (time.time() - t0) * 1000
                result = {"name": name, "passed": passed, "detail": str(detail), "elapsed_ms": round(elapsed, 1)}
            except Exception as e:
                result = {"name": name, "passed": False, "detail": f"异常: {e}", "elapsed_ms": 0}
            self.results.append(result)
            if verbose:
                status = "✅" if result["passed"] else "❌"
                print(f"  {status} {name}: {result['detail']}")

        return self._build_report()

    @classmethod
    def get_check_list(cls) -> List[Dict[str, str]]:
        """返回所有检查项列表（不含结果）"""
        return [
            {"name": "自适应工程流-规划", "category": "自适应工程流", "node": "N1", "desc": "工作流引擎oneclick/step/status可用性"},
            {"name": "自适应工程流-工具", "category": "自适应工程流", "node": "N2", "desc": "智能体调度解析与注册"},
            {"name": "自适应工程流-审查", "category": "自适应工程流", "node": "N3", "desc": "风控/策略管理/灰度/告警模块可用"},
            {"name": "自适应工程流-验证", "category": "自适应工程流", "node": "N4", "desc": "测试文件+回测引擎+验收脚本"},
            {"name": "策略入口-Aurora", "category": "策略三大入口", "node": "N1", "desc": "Aurora适配器+页面+集群策略"},
            {"name": "策略入口-Aurora优化器", "category": "策略三大入口", "node": "N2", "desc": "TauCluster+Shepherd优化器"},
            {"name": "策略入口-Vibe", "category": "策略三大入口", "node": "N3", "desc": "Vibe智能体+集成+页面"},
            {"name": "策略入口-同花顺", "category": "策略三大入口", "node": "N4", "desc": "14策略+18战法合计≥32"},
            {"name": "策略入口-全流程", "category": "策略三大入口", "node": "N5", "desc": "选股→入池→回测→交易链路"},
            {"name": "策略入口-集群覆盖", "category": "策略三大入口", "node": "N6", "desc": "32+1集群策略覆盖"},
            {"name": "可视化-页面完整性", "category": "可视化模块", "node": "N1", "desc": "12个主页面+子页面完整性"},
            {"name": "可视化-按钮操作", "category": "可视化模块", "node": "N2", "desc": "关键页面按钮/链接可操作性"},
            {"name": "可视化-优化器入口", "category": "可视化模块", "node": "N3", "desc": "Aurora页面优化器+API端点"},
            {"name": "可视化-导航通达", "category": "可视化模块", "node": "N4", "desc": "页面间导航链接完整性"},
            {"name": "链路-Api端点", "category": "链路通达性", "node": "N1", "desc": "10个关键API端点定义"},
            {"name": "链路-选股入池", "category": "链路通达性", "node": "N2", "desc": "集群选股→自动入池流转"},
            {"name": "链路-回测交易", "category": "链路通达性", "node": "N3", "desc": "回测→优化→交易闭环"},
            {"name": "链路-风控闭环", "category": "链路通达性", "node": "N4", "desc": "风控→告警→止损→冷却"},
            {"name": "色调-暗色主题", "category": "色调风格", "node": "N1", "desc": "12个核心页面暗色主题一致性"},
            {"name": "色调-CSS变量", "category": "色调风格", "node": "N2", "desc": "CSS变量使用覆盖率"},
            {"name": "色调-accent色系", "category": "色调风格", "node": "N3", "desc": "accent-blue色系统一性"},
            {"name": "色调-子页风格", "category": "色调风格", "node": "N4", "desc": "市场情报/同花顺学院暗色对齐"},
        ]

    # ── 内部：检查方法注册 ──────────────────────────────

    def _all_checks(self) -> List[tuple]:
        """返回所有 (名称, 方法) 对"""
        return [
            ("自适应工程流-规划", self._check_workflow_plan),
            ("自适应工程流-工具", self._check_workflow_tool),
            ("自适应工程流-审查", self._check_workflow_review),
            ("自适应工程流-验证", self._check_workflow_validate),
            ("策略入口-Aurora", self._check_entries_aurora),
            ("策略入口-Aurora优化器", self._check_entries_optimizer),
            ("策略入口-Vibe", self._check_entries_vibe),
            ("策略入口-同花顺", self._check_entries_ths),
            ("策略入口-全流程", self._check_entries_pipeline),
            ("策略入口-集群覆盖", self._check_entries_cluster),
            ("可视化-页面完整性", self._check_visual_pages),
            ("可视化-按钮操作", self._check_visual_buttons),
            ("可视化-优化器入口", self._check_visual_optimizer),
            ("可视化-导航通达", self._check_visual_navigation),
            ("链路-Api端点", self._check_link_api),
            ("链路-选股入池", self._check_link_select),
            ("链路-回测交易", self._check_link_backtest),
            ("链路-风控闭环", self._check_link_risk),
            ("色调-暗色主题", self._check_style_dark),
            ("色调-CSS变量", self._check_style_vars),
            ("色调-accent色系", self._check_style_accent),
            ("色调-子页风格", self._check_style_subpages),
        ]

    # ── 一、自适应工程工作流（4项）──────────────────────

    def _check_workflow_plan(self):
        try:
            from core.workflow_engine import get_workflow_engine
            engine = get_workflow_engine()
            attrs = {'run_oneclick': hasattr(engine, 'run_oneclick'),
                     'run_step': hasattr(engine, 'run_step'),
                     'get_status': hasattr(engine, 'get_status')}
            ok = all(attrs.values())
            logger.info(f"[EngineeringLoop] 工作流引擎属性检查: {attrs} -> {'PASS' if ok else 'FAIL'}")
            return ok, "工作流引擎: oneclick+step+status 齐全"
        except Exception as e:
            logger.warning(f"[EngineeringLoop] 工作流引擎导入失败: {e}")
            return False, str(e)

    def _check_workflow_tool(self):
        try:
            from core.agent_dispatcher import parse_dispatch
            from core.agent_registry import get_all_agents
            intent = parse_dispatch("分析600519")
            agents = get_all_agents()
            ok = intent.symbol == "600519" and len(agents) > 0
            return ok, f"调度解析={intent.symbol}, 智能体={len(agents)}个"
        except Exception as e:
            return False, str(e)

    def _check_workflow_review(self):
        issues = []
        for mod_name, label in [("core.risk_control", "风控审查"), ("core.enhanced_strategy_manager", "策略管理"),
                                ("core.gray_switch", "灰度开关"), ("core.alert_manager", "告警管理")]:
            try:
                __import__(mod_name)
                issues.append(f"{label}✅")
                logger.info(f"[EngineeringLoop] 审查模块导入成功: {mod_name}")
            except Exception as e:
                issues.append(f"{label}❌")
                logger.warning(f"[EngineeringLoop] 审查模块导入失败: {mod_name} -> {e}")
        all_ok = "❌" not in " ".join(issues)
        logger.info(f"[EngineeringLoop] 审查模块检查结果: {'PASS' if all_ok else 'FAIL'} {issues}")
        return all_ok, ", ".join(issues)

    def _check_workflow_validate(self):
        tests_dir = os.path.join(self.project_root, "tests")
        test_count = 0
        if os.path.exists(tests_dir):
            for root, _, files in os.walk(tests_dir):
                test_count += sum(1 for f in files if f.startswith("test_") and f.endswith(".py"))
        try:
            from core.backtest_engine import SimpleBacktestEngine
            has_backtest = True
        except:
            has_backtest = False
        has_verify = os.path.exists(os.path.join(self.project_root, "_verify_three_entries.py"))
        ok = test_count > 0 and has_backtest and has_verify
        return ok, f"测试={test_count}个, 回测={'✓' if has_backtest else '✗'}, 验收={'✓' if has_verify else '✗'}"

    # ── 二、策略三大入口（6项）──────────────────────────

    def _check_entries_aurora(self):
        issues = []
        try:
            from api.aurora_core_adapter import AuroraCoreAdapter
            issues.append("Aurora适配器✅")
        except:
            issues.append("Aurora适配器❌")
        has_page = os.path.exists(os.path.join(self.template_dir, "aurora_main.html"))
        issues.append(f"Aurora页面={'✓' if has_page else '✗'}")
        try:
            from core.tau_cluster_engine import get_cluster_engine
            engine = get_cluster_engine()
            issues.append(f"集群策略={len(engine.get_registered_strategies())}个")
        except:
            issues.append("集群策略❌")
        all_ok = "❌" not in " ".join(issues)
        return all_ok, ", ".join(issues)

    def _check_entries_optimizer(self):
        try:
            from core.tau_optimizer_cluster import get_parameter_store
            store = get_parameter_store()
            info = store.get_all_strategies_info() if hasattr(store, 'get_all_strategies_info') else []
            from core.shepherd_optimizer import ShepherdOptimizer
            return True, f"优化器: TauCluster+Shepherd, 参数历史={len(info)}条"
        except Exception as e:
            return False, str(e)

    def _check_entries_vibe(self):
        issues = []
        try:
            from core.vibe_29_agents import VibeAgentAnalyzer
            methods = [m for m in dir(VibeAgentAnalyzer) if m.endswith('_agent') and not m.startswith('__')]
            issues.append(f"Vibe智能体={len(methods)}个")
        except:
            issues.append("Vibe智能体❌")
        try:
            from core.vibe_integration import VibeIntegration
            issues.append("Vibe集成✅")
        except:
            issues.append("Vibe集成❌")
        has_page = os.path.exists(os.path.join(self.template_dir, "vibe_analysis.html"))
        issues.append(f"Vibe页面={'✓' if has_page else '✗'}")
        all_ok = "❌" not in " ".join(issues)
        return all_ok, ", ".join(issues)

    def _check_entries_ths(self):
        try:
            from api.ths_bridge.signal_collector import SignalCollector
            collector = SignalCollector()
            s14, s18 = collector.list_strategies()
            total = len(s14) + len(s18)
            ok = total >= 32
            logger.info(f"[EngineeringLoop] 同花顺策略: 14策略={len(s14)}, 18战法={len(s18)}, 合计={total}, 阈值=32 -> {'PASS' if ok else 'FAIL'}")
            return ok, f"14策略={len(s14)}, 18战法={len(s18)}, 合计={total}"
        except Exception as e:
            logger.warning(f"[EngineeringLoop] 同花顺入口检查失败: {e}")
            return False, str(e)

    def _check_entries_pipeline(self):
        issues = []
        for mod, label in [("core.cluster_stock_selector", "集群选股"), ("core.stock_pool", "股票池"),
                           ("core.backtest_engine", "回测引擎"), ("core.trade_executor", "交易执行")]:
            try:
                __import__(mod)
                issues.append(f"{label}✅")
            except:
                issues.append(f"{label}❌")
        all_ok = "❌" not in " ".join(issues)
        return all_ok, ", ".join(issues)

    def _check_entries_cluster(self):
        try:
            from api.ths_bridge.signal_collector import SignalCollector
            collector = SignalCollector()
            s14, s18 = collector.list_strategies()
            ths_count = len(s14) + len(s18)
            from core.tau_cluster_engine import get_cluster_engine
            engine = get_cluster_engine()
            cluster_count = len(engine.get_registered_strategies())
            has_cluster = cluster_count >= 1 or hasattr(engine, 'register_strategy')
            return ths_count >= 32 and has_cluster, f"同花顺={ths_count}个, 集群引擎={'✓' if has_cluster else '✗'}, 已注册={cluster_count}个"
        except Exception as e:
            return False, str(e)

    # ── 三、可视化模块（4项）────────────────────────────

    def _check_visual_pages(self):
        missing = []
        for page in self.EXPECTED_PAGES:
            p = os.path.join(self.template_dir, page)
            if os.path.exists(p):
                if os.path.getsize(p) < 100:
                    missing.append(f"{page}(空)")
            else:
                missing.append(page)
        sub_count = 0
        for sub in ["market_intel", "ths_academy"]:
            sd = os.path.join(self.template_dir, sub)
            if os.path.exists(sd):
                sub_count += sum(1 for f in os.listdir(sd) if f.endswith(".html"))
        ok = len(missing) == 0
        return ok, f"主页面={len(self.EXPECTED_PAGES)}个, 子页面={sub_count}个, 缺失={len(missing)}"

    def _check_visual_buttons(self):
        checks = []
        page_checks = {
            "maintenance.html": ["一键巡检", "runOneClickCheck", "执行所选"],
            "aurora_main.html": ["优化器", "optimizer", "策略"],
            "stock_pool.html": ["选股", "入池", "pool"],
            "cluster_selector.html": ["选股", "scan", "热力图"],
            "vibe_analysis.html": ["分析", "智能体", "agent"],
            "dashboard.html": ["Aurora", "策略", "优化"],
        }
        for page, keywords in page_checks.items():
            p = os.path.join(self.template_dir, page)
            if os.path.exists(p):
                with open(p, 'r', encoding='utf-8') as f:
                    content = f.read()
                found = [kw for kw in keywords if kw.lower() in content.lower()]
                status = "✓" if len(found) >= len(keywords) * 0.5 else "△"
                checks.append(f"{page}:{status}({len(found)}/{len(keywords)})")
        ok = all("△" not in c for c in checks)
        return ok, "; ".join(checks)

    def _check_visual_optimizer(self):
        issues = []
        aurora_page = os.path.join(self.template_dir, "aurora_main.html")
        if os.path.exists(aurora_page):
            with open(aurora_page, 'r', encoding='utf-8') as f:
                content = f.read()
            has_opt = "优化器" in content or "optimizer" in content.lower()
            issues.append(f"Aurora页面优化器={'✓' if has_opt else '✗'}")
        else:
            issues.append("Aurora页面缺失")
        gw_path = os.path.join(self.project_root, "api", "gateway.py")
        if os.path.exists(gw_path):
            with open(gw_path, 'r', encoding='utf-8') as f:
                gw_content = f.read()
            has_api = 'optimize' in gw_content or 'optimizer' in gw_content
            issues.append(f"优化器API={'✓' if has_api else '✗'}")
        all_ok = "❌" not in " ".join(issues) and "✗" not in " ".join(issues)
        return all_ok, ", ".join(issues)

    def _check_visual_navigation(self):
        checks = []
        page_links = {
            "maintenance.html": ["dashboard", "aurora_main", "stock_pool", "cluster_selector"],
            "aurora_main.html": ["dashboard", "maintenance", "stock_pool"],
            "dashboard.html": ["aurora_main", "maintenance", "stock_pool"],
            "stock_pool.html": ["dashboard", "aurora_main"],
        }
        for page, expected in page_links.items():
            p = os.path.join(self.template_dir, page)
            if os.path.exists(p):
                with open(p, 'r', encoding='utf-8') as f:
                    content = f.read()
                found = [l for l in expected if l in content.lower() or f"/{l}" in content.lower()]
                status = "✓" if len(found) >= len(expected) * 0.5 else "△"
                checks.append(f"{page}:{status}({len(found)}/{len(expected)})")
        ok = all("△" not in c for c in checks)
        return ok, "; ".join(checks)

    # ── 四、链路通达性（4项）────────────────────────────

    def _check_link_api(self):
        try:
            gw_path = os.path.join(self.project_root, "api", "gateway.py")
            with open(gw_path, 'r', encoding='utf-8') as f:
                content = f.read()
            key_endpoints = [
                "/strategy/list", "/backtest/history", "/optimizer/list",
                "/health/check", "/stock-pool", "/agent/dispatch",
                "/strategy/registry/summary", "/tau/optimize",
                "/auth/login", "/security/config",
            ]
            found = [e for e in key_endpoints if e in content]
            ok = len(found) >= len(key_endpoints) * 0.8
            return ok, f"关键端点={len(found)}/{len(key_endpoints)}"
        except Exception as e:
            return False, str(e)

    def _check_link_select(self):
        try:
            from core.workflow_engine import get_workflow_engine
            engine = get_workflow_engine()
            import inspect
            src = inspect.getsource(engine._stage_cluster_select)
            has_push = "_push_to_stock_pool" in src or "stock_pool" in src.lower()
            from core.stock_pool import get_stock_pool_manager
            pool_mgr = get_stock_pool_manager()
            has_pool = hasattr(pool_mgr, 'add_stock') or hasattr(pool_mgr, 'get_pool_summary')
            return has_push and has_pool, f"自动入池={'✓' if has_push else '✗'}, 池管理={'✓' if has_pool else '✗'}"
        except Exception as e:
            return False, str(e)

    def _check_link_backtest(self):
        issues = []
        try:
            from core.workflow_engine import get_workflow_engine
            engine = get_workflow_engine()
            import inspect
            src = inspect.getsource(engine._stage_backtest)
            has_sharpe = "sharpe" in src.lower()
            issues.append(f"回测验证={'✓' if has_sharpe else '✗'}")
        except:
            issues.append("回测验证❌")
        try:
            from core.integration_bus import get_integration_bus
            bus = get_integration_bus()
            has_auto = hasattr(bus, 'auto_full_workflow')
            issues.append(f"集成总线={'✓' if has_auto else '✗'}")
        except:
            issues.append("集成总线❌")
        try:
            from core.trade_executor import TradeExecutor
            issues.append(f"交易执行器={TradeExecutor().mode}")
        except:
            issues.append("交易执行器❌")
        all_ok = "❌" not in " ".join(issues)
        return all_ok, ", ".join(issues)

    def _check_link_risk(self):
        try:
            from core.risk_control import RiskControlEngine
            rm_ok = True
        except:
            rm_ok = False
        try:
            from core.alert_manager import AlertManager
            alert_ok = True
        except:
            alert_ok = False
        has_cooldown = False
        for mod_name in ["integration_bus", "risk_control"]:
            try:
                import inspect
                mod = __import__(f"core.{mod_name}", fromlist=[mod_name])
                src = inspect.getsource(mod)
                has_cooldown = "cooldown" in src.lower() or "冷却" in src
                if has_cooldown:
                    break
            except:
                pass
        all_ok = rm_ok and alert_ok and has_cooldown
        return all_ok, f"风控={'✓' if rm_ok else '✗'}, 告警={'✓' if alert_ok else '✗'}, 冷却={'✓' if has_cooldown else '✗'}"

    # ── 五、色调风格（4项）──────────────────────────────

    def _check_style_dark(self):
        core_pages = [
            "maintenance.html", "vibe_analysis.html", "login.html",
            "aurora_main.html", "dashboard.html", "cluster_selector.html",
            "stock_pool.html", "index.html", "main_system.html",
            "cline_agent.html", "model_switch.html", "technical_analysis.html",
        ]
        dark_count = 0
        light_pages = []
        for page in core_pages:
            p = os.path.join(self.template_dir, page)
            result = self._analyze_page_style(p)
            if result.get("is_dark"):
                dark_count += 1
                logger.info(f"[EngineeringLoop] 暗色主题检测: {page} -> DARK")
            elif result.get("exists"):
                light_pages.append(page)
                logger.warning(f"[EngineeringLoop] 暗色主题检测: {page} -> LIGHT (非暗色)")
        total = len([p for p in core_pages if os.path.exists(os.path.join(self.template_dir, p))])
        ok = len(light_pages) == 0
        logger.info(f"[EngineeringLoop] 暗色主题一致性: {dark_count}/{total} 暗色, 非暗色={light_pages} -> {'PASS' if ok else 'FAIL'}")
        detail = f"暗色={dark_count}/{total}"
        if light_pages:
            detail += f", 非暗色: {light_pages}"
        return ok, detail

    def _check_style_vars(self):
        pages_with = {}
        pages_without = []
        for page in self.EXPECTED_PAGES:
            p = os.path.join(self.template_dir, page)
            if not os.path.exists(p):
                continue
            with open(p, 'r', encoding='utf-8') as f:
                content = f.read()
            count = len(re.findall(r'--[\w-]+', content))
            if count > 0:
                pages_with[page] = count
            else:
                pages_without.append(page)
        ok = len(pages_without) == 0
        logger.info(f"[EngineeringLoop] CSS变量覆盖: 有变量={len(pages_with)}页, 无变量={len(pages_without)}页 -> {'PASS' if ok else 'FAIL'}")
        if pages_without:
            logger.warning(f"[EngineeringLoop] 无CSS变量页面: {pages_without}")
        return ok, f"有CSS变量={len(pages_with)}页, 无变量={len(pages_without)}页"

    def _check_style_accent(self):
        dark_pages = ["maintenance.html", "vibe_analysis.html", "login.html"]
        accent_colors = {}
        for page in dark_pages:
            p = os.path.join(self.template_dir, page)
            if not os.path.exists(p):
                continue
            with open(p, 'r', encoding='utf-8') as f:
                content = f.read()
            m = re.search(r'--accent-blue:\s*(#[0-9a-fA-F]{3,6})', content)
            if m:
                accent_colors[page] = m.group(1)
        unique = set(accent_colors.values())
        ok = len(unique) <= 2
        logger.info(f"[EngineeringLoop] Accent色系: {accent_colors}, 去重={len(unique)}种 -> {'PASS' if ok else 'FAIL'}")
        return ok, f"accent-blue值: {accent_colors}, 去重={len(unique)}种"

    def _check_style_subpages(self):
        light_pages = []
        for sub in ["market_intel", "ths_academy"]:
            sd = os.path.join(self.template_dir, sub)
            if not os.path.exists(sd):
                continue
            for f in os.listdir(sd):
                if not f.endswith(".html"):
                    continue
                p = os.path.join(sd, f)
                result = self._analyze_page_style(p)
                if result.get("exists") and not result.get("is_dark"):
                    light_pages.append(f"{sub}/{f}")
        ok = len(light_pages) == 0
        detail = f"子页面={len(light_pages)}页非暗色" if light_pages else "全部暗色 ✓"
        return ok, detail

    # ── 色调分析工具 ─────────────────────────────────────

    def _analyze_page_style(self, filepath: str) -> dict:
        if not os.path.exists(filepath):
            return {"exists": False}
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        root_vars = {}
        root_match = re.search(r':root\s*\{([^}]+)\}', content, re.DOTALL)
        if root_match:
            for var in re.finditer(r'--([\w-]+):\s*([^;]+);', root_match.group(1)):
                root_vars[var.group(1)] = var.group(2).strip()
        is_dark = self._detect_dark_theme(content, root_vars, filepath)
        return {"exists": True, "root_vars": root_vars, "is_dark": is_dark}

    def _detect_dark_theme(self, content: str, root_vars: dict, filepath: str) -> bool:
        # 方法1: :root变量
        for key in ['bg-deep', 'bg-dark', 'bg-card', 'bg']:
            bg_val = root_vars.get(key, '')
            if bg_val and bg_val.startswith('#'):
                if self._is_dark_hex(bg_val):
                    return True
        # 方法2: hex背景色
        for bg in re.findall(r'background:\s*(#[0-9a-fA-F]{6})', content)[:3]:
            if self._is_dark_hex(bg):
                return True
        # 方法3: rgba背景色
        for r_str, g_str, b_str in re.findall(r'rgba\((\d+),\s*(\d+),\s*(\d+)', content)[:3]:
            if (int(r_str) + int(g_str) + int(b_str)) / 3 < 64:
                return True
        # 方法4: 外部CSS文件
        css_match = re.search(r'href="([^"]+\.css)"', content)
        if css_match:
            css_path = css_match.group(1)
            if css_path.startswith('/'):
                css_abs = os.path.join(self.template_dir, '..', css_path.lstrip('/'))
            else:
                css_abs = os.path.join(os.path.dirname(filepath), css_path)
            if os.path.exists(css_abs):
                try:
                    with open(css_abs, 'r', encoding='utf-8') as f:
                        css_content = f.read()
                    for key in ['--bg-deep', '--bg-dark', '--bg-card', '--bg']:
                        m = re.search(rf'{key}:\s*(#[0-9a-fA-F]{{6}})', css_content)
                        if m and self._is_dark_hex(m.group(1)):
                            return True
                    body_match = re.search(r'body\s*\{[^}]*background:\s*[^;]*?(#[0-9a-fA-F]{6})', css_content, re.DOTALL)
                    if body_match and self._is_dark_hex(body_match.group(1)):
                        return True
                except:
                    pass
        return False

    @staticmethod
    def _is_dark_hex(hex_color: str) -> bool:
        hex_val = hex_color.lstrip('#')
        if len(hex_val) >= 6:
            r, g, b = int(hex_val[0:2], 16), int(hex_val[2:4], 16), int(hex_val[4:6], 16)
            return (r + g + b) / 3 < 64
        return False

    # ── 报告生成 ─────────────────────────────────────────

    def _build_report(self) -> Dict[str, Any]:
        elapsed = (datetime.now() - self.start_time).total_seconds()
        total = len(self.results)
        passed = sum(1 for r in self.results if r["passed"])
        failed = total - passed
        pct = round(passed / total * 100, 1) if total > 0 else 0

        categories = {}
        for r in self.results:
            name = r["name"]
            cat = next((c for c in ["自适应工程流", "策略入口", "可视化", "链路", "色调"] if c in name), "其他")
            if cat not in categories:
                categories[cat] = {"total": 0, "passed": 0}
            categories[cat]["total"] += 1
            if r["passed"]:
                categories[cat]["passed"] += 1

        if pct >= 95: grade = "优"
        elif pct >= 80: grade = "良"
        elif pct >= 60: grade = "中"
        else: grade = "差"

        logger.info(f"[EngineeringLoop] === 审查完成: {passed}/{total} 通过 ({pct}%), 评级={grade}, 耗时={elapsed:.1f}s ===")
        for cat, stats in categories.items():
            cat_pct = stats["passed"] / stats["total"] * 100 if stats["total"] else 0
            logger.info(f"[EngineeringLoop]   分类统计: {cat} = {stats['passed']}/{stats['total']} ({cat_pct:.0f}%)")

        report = {
            "timestamp": self.start_time.isoformat(),
            "total": total, "passed": passed, "failed": failed,
            "pass_rate": pct, "grade": grade,
            "elapsed_seconds": round(elapsed, 1),
            "categories": {k: {"total": v["total"], "passed": v["passed"]} for k, v in categories.items()},
            "results": self.results,
            "failed_items": [r for r in self.results if not r["passed"]],
        }

        if failed > 0:
            logger.warning(f"[EngineeringLoop] 失败项 ({failed}):")
            for r in self.results:
                if not r["passed"]:
                    logger.warning(f"[EngineeringLoop]   - {r['name']}: {r['detail']}")
                    print(f"    - {r['name']}: {r['detail']}")

        print(f"\n  整体健康度: {grade} ({pct}%) — {passed}/{total} 通过")

        return report

    def save_report(self, report: Dict[str, Any] = None, filename: str = None):
        """保存报告到 data/health_reports/ 目录"""
        if report is None:
            report = self._build_report()
        report_dir = os.path.join(self.project_root, "data", "health_reports")
        os.makedirs(report_dir, exist_ok=True)
        if filename is None:
            ts = self.start_time.strftime('%Y%m%d_%H%M%S') if self.start_time else datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"engineering_loop_{ts}.json"
        path = os.path.join(report_dir, filename)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        return path


# ── 命令行入口 ──────────────────────────────────────────

def main():
    auditor = EngineeringLoopAuditor()
    report = auditor.run_all(verbose=True)
    auditor.save_report(report)
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())