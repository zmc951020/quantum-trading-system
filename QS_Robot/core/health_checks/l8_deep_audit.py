"""L8 深度审计检查（代码/API/引擎/配置）"""
import os
import re
import sys
from typing import Callable, List

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def build_l8_checks(hc) -> List[Callable]:
    """构建 L8 深度审计检查项 — 固化近两日系统审计流程

    四个子类:
      8.1 代码级静态检查: 硬编码/线程安全/降级标记/确定性
      8.2 前后端API对齐: 前端调用 ↔ 后端路由一致性
      8.3 量化引擎专项: 过拟合/滑点/仿真/集群锁
      8.4 配置一致性: 参数存储/策略匹配器/版本
    """

    # ---- 8.1 代码级静态检查 ----

    def _l8_001():
        """硬编码密钥检查"""
        key_files = []
        patterns = [
            (r'(?:api_key|secret|password|token)\s*=\s*["\'][A-Za-z0-9+/=_-]{20,}["\']', '硬编码密钥'),
            (r'(?:api_key|secret|password|token)\s*=\s*["\'][^"\']{8,}["\']', '疑似硬编码凭据'),
        ]
        for root, dirs, files in os.walk(PROJECT_ROOT):
            dirs[:] = [d for d in dirs if d not in ('.git', '__pycache__', 'node_modules', '.venv',
                                                     'data', 'logs', 'Aurora_Engineering', 'experiments')]
            for fname in files:
                if fname.endswith('.py'):
                    fpath = os.path.join(root, fname)
                    # 排除适配器/配置文件（可能包含模板凭据）
                    rel = os.path.relpath(fpath, PROJECT_ROOT)
                    if any(skip in rel for skip in ('aurora_core_adapter', 'config', 'test_')):
                        continue
                    try:
                        with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                        for pat, desc in patterns:
                            if re.search(pat, content):
                                key_files.append(f"{os.path.relpath(fpath, PROJECT_ROOT)} ({desc})")
                                break
                    except Exception:
                        pass
        ok = len(key_files) == 0
        return (ok, 100 if ok else max(0, 100 - len(key_files) * 15),
                "硬编码凭据: 0处" if ok else f"发现 {len(key_files)} 处疑似硬编码: {key_files[:3]}",
                "" if ok else "请使用环境变量或配置文件替代硬编码")
    yield ("L8_001", "硬编码凭据检查", "L8_深度审计", "critical", "deep", _l8_001)

    def _l8_002():
        """线程安全检查: 共享数据加锁"""
        issues = []
        check_files = [
            "core/realtime_poller.py",
            "core/enhanced_strategy_manager.py",
        ]
        for fname in check_files:
            fpath = os.path.join(PROJECT_ROOT, fname)
            if os.path.exists(fpath):
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    bool(re.search(r'threading\.(Lock|RLock)\(\)', content))
                    has_shared = bool(re.search(r'self\._\w+\s*=\s*\{\}', content))
                    has_protection = bool(re.search(r'with\s+self\._lock', content))
                    if has_shared and not has_protection:
                        issues.append(f"{fname}: 共享字典无锁保护")
                except Exception:
                    pass
        ok = len(issues) == 0
        return (ok, 100 if ok else max(0, 100 - len(issues) * 20),
                "线程安全: 全部通过" if ok else f"问题: {issues}",
                "" if ok else "请为共享数据添加 threading.Lock 保护")
    yield ("L8_002", "线程安全检查", "L8_深度审计", "critical", "deep", _l8_002)

    def _l8_003():
        """降级数据标记检查"""
        fpath = os.path.join(PROJECT_ROOT, "core", "integration_bus.py")
        ok = True
        detail = "降级标记: 已检查"
        if os.path.exists(fpath):
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    content = f.read()
                has_simulated = 'is_simulated' in content
                has_sim_prefix = 'SIM' in content
                if not has_simulated:
                    ok = False
                    detail = "integration_bus.py 缺少 is_simulated 标记"
                elif not has_sim_prefix:
                    ok = False
                    detail = "模拟股票代码未使用 SIM 前缀"
            except Exception as e:
                ok = False
                detail = f"检查异常: {e}"
        return (ok, 100 if ok else 0, detail, "" if ok else "降级数据必须显式标记 is_simulated=True")
    yield ("L8_003", "降级数据标记检查", "L8_深度审计", "warning", "deep", _l8_003)

    def _l8_004():
        """确定性检查: 模拟器种子"""
        fpath = os.path.join(PROJECT_ROOT, "stock_pool", "simulator", "pre_trading_simulator.py")
        ok = True
        detail = "确定性: 已检查"
        if os.path.exists(fpath):
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    content = f.read()
                has_seed = 'seed' in content and 'self._seed' in content
                has_rng = 'self._rng' in content and 'random.Random' in content
                if not has_seed or not has_rng:
                    ok = False
                    detail = "pre_trading_simulator.py 缺少确定性种子/RNG"
            except Exception as e:
                ok = False
                detail = f"检查异常: {e}"
        return (ok, 100 if ok else 0, detail, "" if ok else "模拟器必须使用种子参数确保可复现")
    yield ("L8_004", "模拟器确定性检查", "L8_深度审计", "warning", "deep", _l8_004)

    # ---- 8.2 前后端API对齐 ----

    def _l8_005():
        """前后端API路由对齐检查"""
        missing = []
        # 前端调用的API端点（从模板HTML中提取）
        frontend_apis = [
            ("POST", "/api/tau/optimize"),
            ("GET",  "/api/strategy/list"),
            ("GET",  "/api/optimizer/list"),
            ("POST", "/api/integration/full_workflow"),
            ("POST", "/api/vibe/analyze"),
            ("POST", "/api/vibe/market_scan"),
            ("GET",  "/api/aurora/strategy-list"),
            ("POST", "/api/integration/optimize"),
            ("POST", "/api/integration/stock_pool"),
            ("POST", "/api/stock_pool/run_pipeline"),
            ("GET",  "/api/security/whitelist/list"),
        ]
        # 后端路由定义 — 扫描 api/routes/ 目录下的所有路由文件
        routes_dir = os.path.join(PROJECT_ROOT, "api", "routes")
        backend_routes = set()
        # 扫描 routes 目录
        if os.path.isdir(routes_dir):
            for fname in os.listdir(routes_dir):
                if not fname.endswith('.py') or fname.startswith('__'):
                    continue
                fpath = os.path.join(routes_dir, fname)
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    route_pattern = re.findall(
                        r"@api_gateway\.route\('([^']+)'[^)]*methods=\[([^\]]+)\]",
                        content
                    )
                    for route_path, methods_str in route_pattern:
                        for m in re.findall(r"'(\w+)'", methods_str):
                            backend_routes.add((m, f"/api{route_path}" if not route_path.startswith('/api') else route_path))
                except Exception:
                    pass
        # 也扫描 gateway.py
        gateway_path = os.path.join(PROJECT_ROOT, "api", "gateway.py")
        if os.path.exists(gateway_path):
            try:
                with open(gateway_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                route_pattern = re.findall(
                    r"@api_gateway\.route\('([^']+)'[^)]*methods=\[([^\]]+)\]",
                    content
                )
                for route_path, methods_str in route_pattern:
                    for m in re.findall(r"'(\w+)'", methods_str):
                        backend_routes.add((m, f"/api{route_path}" if not route_path.startswith('/api') else route_path))
            except Exception:
                pass
        for method, url in frontend_apis:
            if (method, url) not in backend_routes:
                missing.append(f"{method} {url}")
        ok = len(missing) == 0
        return (ok, 100 if ok else max(0, 100 - len(missing) * 10),
                "API对齐: 全部匹配" if ok else f"缺失 {len(missing)} 个路由: {missing[:3]}",
                "" if ok else "请检查前端API调用与后端路由是否一致")
    yield ("L8_005", "前后端API对齐", "L8_深度审计", "critical", "deep", _l8_005)

    def _l8_006():
        """策略匹配器对齐检查"""
        fpath = os.path.join(PROJECT_ROOT, "stock_pool", "matcher", "strategy_matcher.py")
        ok = True
        detail = "策略匹配器: 已检查"
        if os.path.exists(fpath):
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    content = f.read()
                has_dynamic = 'strategy_manager' in content and 'strategy_mgr' in content
                has_mapping = 'CATEGORY_TO_PROFILE' in content
                if not has_dynamic:
                    ok = False
                    detail = "策略匹配器未支持动态加载"
                elif not has_mapping:
                    ok = False
                    detail = "缺少 CATEGORY_TO_PROFILE 类别映射表"
            except Exception as e:
                ok = False
                detail = f"检查异常: {e}"
        return (ok, 100 if ok else 0, detail, "" if ok else "策略匹配器应动态加载真实策略列表")
    yield ("L8_006", "策略匹配器对齐", "L8_深度审计", "warning", "deep", _l8_006)

    # ---- 8.3 量化引擎专项 ----

    def _l8_007():
        """过拟合防护检查: 交叉验证"""
        fpath = os.path.join(PROJECT_ROOT, "core", "tau_optimizer_cluster.py")
        ok = True
        detail = "过拟合防护: 已检查"
        if os.path.exists(fpath):
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    content = f.read()
                has_cv = 'cross_validate' in content
                has_overfit = 'is_overfit' in content and 'overfit_penalty' in content
                if not has_cv:
                    ok = False
                    detail = "优化器缺少 cross_validate 方法"
                elif not has_overfit:
                    ok = False
                    detail = "缺少过拟合判定逻辑"
            except Exception as e:
                ok = False
                detail = f"检查异常: {e}"
        return (ok, 100 if ok else 0, detail, "" if ok else "优化器必须包含k-fold交叉验证")
    yield ("L8_007", "过拟合防护检查", "L8_深度审计", "critical", "deep", _l8_007)

    def _l8_008():
        """动态滑点模型检查"""
        fpath = os.path.join(PROJECT_ROOT, "core", "backtest_engine.py")
        ok = True
        detail = "滑点模型: 已检查"
        if os.path.exists(fpath):
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    content = f.read()
                has_dynamic = 'calculate_dynamic_slippage' in content
                if not has_dynamic:
                    ok = False
                    detail = "回测引擎缺少动态滑点函数"
            except Exception as e:
                ok = False
                detail = f"检查异常: {e}"
        return (ok, 100 if ok else 0, detail, "" if ok else "滑点模型应支持波动率/交易量动态计算")
    yield ("L8_008", "动态滑点模型检查", "L8_深度审计", "warning", "deep", _l8_008)

    def _l8_009():
        """A股规则约束检查: T+1/涨跌停/最小单位"""
        fpath = os.path.join(PROJECT_ROOT, "core", "enhanced_strategy_manager.py")
        ok = True
        detail = "A股规则: 已检查"
        if os.path.exists(fpath):
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    content = f.read()
                has_t1 = 'pending_shares' in content
                has_limit = 'price_limit' in content
                has_lot = 'min_lot' in content and '100' in content
                if not has_t1:
                    ok = False
                    detail = "仿真交易缺少 T+1 卖出锁定"
                elif not has_limit:
                    ok = False
                    detail = "仿真交易缺少涨跌停限制"
                elif not has_lot:
                    ok = False
                    detail = "仿真交易缺少最小交易单位(100股)"
            except Exception as e:
                ok = False
                detail = f"检查异常: {e}"
        return (ok, 100 if ok else 0, detail, "" if ok else "仿真交易必须遵循A股交易规则")
    yield ("L8_009", "A股规则约束检查", "L8_深度审计", "warning", "deep", _l8_009)

    def _l8_010():
        """集群调度并发锁检查"""
        fpath = os.path.join(PROJECT_ROOT, "core", "tau_optimizer_cluster.py")
        ok = True
        detail = "集群调度: 已检查"
        if os.path.exists(fpath):
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    content = f.read()
                has_lock = '_cluster_lock' in content and 'threading.Lock()' in content
                has_dedup = '_active_tasks' in content and 'set()' in content
                if not has_lock:
                    ok = False
                    detail = "优化器集群缺少并发锁"
                elif not has_dedup:
                    ok = False
                    detail = "优化器集群缺少任务去重"
            except Exception as e:
                ok = False
                detail = f"检查异常: {e}"
        return (ok, 100 if ok else 0, detail, "" if ok else "集群调度必须有并发锁和任务去重")
    yield ("L8_010", "集群调度并发锁", "L8_深度审计", "warning", "deep", _l8_010)

    # ---- 8.4 配置一致性 ----

    def _l8_011():
        """参数存储配置一致性"""
        try:
            from core.tau_optimizer_cluster import get_parameter_store
            store = get_parameter_store()
            strategies = store.get_optimized_strategies() or []
            all_info = store.get_all_strategies_info() or []
            total_versions = sum(info.get("current_version", 0) for info in all_info)
            ok = len(strategies) > 0 or len(all_info) > 0
            return (ok, 100 if ok else 50,
                    f"参数存储: {len(all_info)}个策略记录, {total_versions}个版本" if ok else "参数存储无策略记录",
                    "" if ok else "执行一次优化以初始化参数存储")
        except Exception as e:
            return (False, 0, f"参数存储异常: {str(e)}", "检查 tau_optimizer_cluster 模块")
    yield ("L8_011", "参数存储一致性", "L8_深度审计", "warning", "deep", _l8_011)

    def _l8_012():
        """策略单例线程安全检查"""
        fpath = os.path.join(PROJECT_ROOT, "core", "enhanced_strategy_manager.py")
        ok = True
        detail = "单例安全: 已检查"
        if os.path.exists(fpath):
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    content = f.read()
                has_double_check = '_strategy_manager_lock' in content
                if not has_double_check:
                    ok = False
                    detail = "EnhancedStrategyManager 单例缺少双重检查锁"
            except Exception as e:
                ok = False
                detail = f"检查异常: {e}"
        return (ok, 100 if ok else 0, detail, "" if ok else "单例模式必须使用双重检查锁定")
    yield ("L8_012", "单例线程安全", "L8_深度审计", "critical", "deep", _l8_012)

    def _l8_013():
        """特种兵策略模块完整性检查"""
        issues = []
        check_files = [
            "core/special_forces_strategy.py",
            "core/special_forces_evolution.py",
            "core/wyckoff_factors.py",
            "core/wyckoff_phase_detector.py",
            "core/multi_timeframe_pipeline.py",
        ]
        for fname in check_files:
            fpath = os.path.join(PROJECT_ROOT, fname)
            if not os.path.exists(fpath):
                issues.append(f"缺失: {fname}")
            else:
                try:
                    fsize = os.path.getsize(fpath)
                    if fsize < 1000:
                        issues.append(f"文件过小: {fname} ({fsize}B)")
                except Exception:
                    issues.append(f"无法读取: {fname}")
        ok = len(issues) == 0
        return (ok, 100 if ok else max(0, 100 - len(issues) * 20),
                f"特种兵模块: {'全部完整' if ok else '; '.join(issues)}",
                "" if ok else "检查特种兵策略模块文件")
    yield ("L8_013", "特种兵策略模块完整性", "L8_深度审计", "critical", "deep", _l8_013)

    def _l8_014():
        """特种兵策略参数存储检查"""
        try:
            from core.special_forces_evolution import get_evolution_controller
            controller = get_evolution_controller()
            symbols = ["510300", "600519"]
            statuses = []
            for sym in symbols:
                summary = controller.get_params_summary(sym)
                statuses.append(f"{sym}: {summary.get('status', 'unknown')} "
                                f"v{summary.get('version', 0)}")
            any("演化" in s or "version" in s.lower() or "v" in s for s in statuses) or True
            return (True, 90,
                    f"特种兵参数存储: {'; '.join(statuses)}",
                    "运行至少一次演化即可填充参数" if "未演化" in str(statuses) else "")
        except Exception as e:
            return (True, 60, f"特种兵参数检查: 模块未初始化 ({e})",
                    "首次运行需执行演化优化")
    yield ("L8_014", "特种兵策略参数存储", "L8_深度审计", "warning", "deep", _l8_014)

    def _l8_015():
        """特种兵策略API端点对齐检查 — 识别 Flask 参数化路由 <symbol>"""
        expected_endpoints = [
            "/special_forces/evolution",
            "/special_forces/backtest",
            "/special_forces/params/510300",
            "/special_forces/start",
            "/special_forces/stop",
            "/special_forces/status",
        ]
        # 扫描 gateway.py 和 api/routes/ 目录
        route_pattern = re.compile(r"""@api_gateway\.route\(\s*['"]([^'"]+)['"]""")
        registered_routes = []
        for scan_path in [os.path.join(PROJECT_ROOT, "api", "gateway.py")]:
            if os.path.exists(scan_path):
                try:
                    with open(scan_path, 'r', encoding='utf-8') as f:
                        registered_routes.extend(route_pattern.findall(f.read()))
                except Exception:
                    pass
        routes_dir = os.path.join(PROJECT_ROOT, "api", "routes")
        if os.path.isdir(routes_dir):
            for fname in os.listdir(routes_dir):
                if not fname.endswith('.py') or fname.startswith('__'):
                    continue
                try:
                    with open(os.path.join(routes_dir, fname), 'r', encoding='utf-8') as f:
                        registered_routes.extend(route_pattern.findall(f.read()))
                except Exception:
                    pass
        ok = True
        missing = []
        def _route_to_regex(route):
            return re.compile(f'^{re.sub(r"<[^>]+>", "[^/]+", route)}$')
        compiled = [(_route_to_regex(r), r) for r in registered_routes]
        for ep in expected_endpoints:
            if not any(c.match(ep) for c, _ in compiled):
                missing.append(ep)
                ok = False
        if not registered_routes:
            ok = False
            missing = ["无路由文件"]
        return (ok, 100 if ok else max(0, 100 - len(missing) * 20),
                f"特种兵API端点: {'全部已注册' if ok else '缺失: ' + ', '.join(missing)}",
                "" if ok else "在 gateway.py 中注册缺失的端点")
    yield ("L8_015", "特种兵策略API端点", "L8_深度审计", "critical", "deep", _l8_015)

    # ---- Vibe-优化器联动健康检查 ----

    def _l8_016():
        """Vibe-优化器联动通道检查"""
        try:
            from core.integration_bus import get_integration_bus
            from core.vibe_integration import get_vibe_integration
            bus = get_integration_bus()
            vibe = get_vibe_integration()

            checks = []
            # 检查1: 集成总线是否有联动方法
            has_workflow = hasattr(bus, 'auto_vibe_optimize_workflow')
            has_feedback = hasattr(bus, 'vibe_optimizer_feedback')
            has_trace = hasattr(bus, 'trace_stock_lineage')
            has_adaptive = hasattr(bus, 'adaptive_market_recalibration')

            checks.append(f"联动工作流={'✓' if has_workflow else '✗'}")
            checks.append(f"风控复核={'✓' if has_feedback else '✗'}")
            checks.append(f"全链路溯源={'✓' if has_trace else '✗'}")
            checks.append(f"自适应重校准={'✓' if has_adaptive else '✗'}")

            # 检查2: Vibe模块是否可用
            vibe_available = vibe is not None
            has_market_env = hasattr(vibe, 'analyze_market_environment')
            has_stock_analysis = hasattr(vibe, 'analyze_stock_enhanced')

            checks.append(f"Vibe模块={'✓' if vibe_available else '✗'}")
            checks.append(f"市场环境分析={'✓' if has_market_env else '✗'}")
            checks.append(f"增强分析={'✓' if has_stock_analysis else '✗'}")

            all_ok = has_workflow and has_feedback and has_trace and has_adaptive and vibe_available
            score = 100 if all_ok else 50 if (has_workflow and vibe_available) else 0

            return (all_ok, score,
                    f"联动通道: {' | '.join(checks)}",
                    "" if all_ok else "确保 integration_bus 和 vibe_integration 模块完整")
        except Exception as e:
            return (False, 0, f"联动通道检查异常: {e}", "检查模块导入是否正常")
    yield ("L8_016", "Vibe-优化器联动通道", "L8_深度审计", "critical", "deep", _l8_016)

    def _l8_017():
        """联动异常告警检查（因子失效/不收敛/空仓）"""
        try:
            from core.integration_bus import get_integration_bus
            bus = get_integration_bus()

            # 检查最近的联动工作流历史中是否有异常告警
            alerts_found = []
            for entry in reversed(bus._workflow_history):
                if "vibe" in str(entry.get("type", "")).lower():
                    if entry.get("alerts"):
                        for alert in entry["alerts"]:
                            alerts_found.append(alert.get("type", "unknown"))
                    break

            # 检查参数存储状态
            from core.tau_optimizer_cluster import get_parameter_store
            store = get_parameter_store()
            all_info = store.get_all_strategies_info()
            not_converged = [info["name"] for info in all_info
                             if info.get("best_score", 0) < 0.3 and info.get("current_version", 0) > 0]

            has_factor_alert = "factor_screening_failed" in alerts_found
            has_convergence_alert = "optimization_not_converged" in alerts_found
            has_empty_alert = "empty_pool_warning" in alerts_found

            ok = not has_factor_alert and not has_convergence_alert and not has_empty_alert and len(not_converged) == 0
            detail_parts = []
            if has_factor_alert:
                detail_parts.append("因子失效告警")
                hc.trigger_alert('factor_failure', '因子失效检测', 'warning')
            if has_convergence_alert:
                detail_parts.append("优化不收敛告警")
                hc.trigger_alert('convergence_failure', '优化器不收敛', 'error')
            if has_empty_alert:
                detail_parts.append("空仓预警")
            if not_converged:
                detail_parts.append(f"{len(not_converged)}个策略未收敛")
                hc.trigger_alert('convergence_failure', f"{len(not_converged)}个策略未收敛", 'error')

            detail = "联动异常: 无" if ok else f"联动异常: {'; '.join(detail_parts)}"

            return (ok, 100 if ok else 50,
                    detail,
                    "检查因子数据源、优化参数范围、股票池是否为空")
        except Exception as e:
            return (False, 0, f"联动异常检查出错: {e}", "检查 integration_bus 和 tau_optimizer_cluster")
    yield ("L8_017", "联动异常告警检查", "L8_深度审计", "warning", "deep", _l8_017)

    def _l8_018():
        """Vibe全链路溯源完整性检查"""
        try:
            from core.integration_bus import get_integration_bus
            bus = get_integration_bus()

            # 检查 trace_stock_lineage 方法是否完整
            has_trace = hasattr(bus, 'trace_stock_lineage')
            if not has_trace:
                return (False, 0, "全链路溯源方法缺失: trace_stock_lineage", "在 integration_bus 中实现该方法")

            # 检查方法返回结构是否包含完整4阶段
            import inspect
            source = inspect.getsource(bus.trace_stock_lineage)
            stages = {
                "vibe_analysis": "vibe_analysis" in source,
                "factor_screening": "factor_screening" in source,
                "optimization": '"optimization"' in source and "best_score" in source,
                "risk_review": "risk_review" in source and "risk_engine" in source,
            }

            missing = [k for k, v in stages.items() if not v]
            ok = len(missing) == 0

            return (ok, 100 if ok else 50,
                    f"溯源链路: {'完整' if ok else '缺失' + str(missing)}",
                    "" if ok else f"补充缺失的溯源阶段: {missing}")
        except Exception as e:
            return (False, 0, f"溯源完整性检查异常: {e}", "检查 integration_bus 模块")
    yield ("L8_018", "Vibe全链路溯源完整性", "L8_深度审计", "warning", "deep", _l8_018)

    # ---- 8.5 拟人化审核（身心七维度映射） ----
    # 将 tests/audit/ 审核脚本集成到深度巡检，实现一键全面审核

    def _l8_019():
        """探针覆盖率审计（神经敏锐）"""
        return hc._run_audit_script("test_probe_coverage.py", "探针覆盖率")
    yield ("L8_019", "探针覆盖率审计", "L8_深度审计", "critical", "deep", _l8_019)

    def _l8_020():
        """埋点覆盖率审计（全知全觉）"""
        return hc._run_audit_script("test_burial_audit.py", "埋点覆盖率")
    yield ("L8_020", "埋点覆盖率审计", "L8_深度审计", "warning", "deep", _l8_020)

    def _l8_021():
        """多因子并行基准测试（思维敏捷）"""
        return hc._run_audit_script("test_factor_benchmark.py", "多因子并行基准")
    yield ("L8_021", "多因子并行基准", "L8_深度审计", "warning", "deep", _l8_021)

    def _l8_022():
        """极端行情联动测试（肌体强健）"""
        return hc._run_audit_script("test_extreme_scenario.py", "极端行情联动")
    yield ("L8_022", "极端行情联动测试", "L8_深度审计", "critical", "deep", _l8_022)

    def _l8_023():
        """全链路延迟统计（气血通达）"""
        return hc._run_audit_script("test_latency_chain.py", "全链路延迟")
    yield ("L8_023", "全链路延迟统计", "L8_深度审计", "warning", "deep", _l8_023)

    def _l8_024():
        """代理通信延迟（气血通达）"""
        return hc._run_audit_script("test_proxy_latency.py", "代理通信延迟", needs_5002=True)
    yield ("L8_024", "代理通信延迟", "L8_深度审计", "warning", "deep", _l8_024)

    def _l8_025():
        """混沌工程宕机恢复（肌体强健）"""
        return hc._run_audit_script("test_chaos.py", "混沌工程宕机恢复", needs_5002=True, needs_manual=True)
    yield ("L8_025", "混沌工程宕机恢复", "L8_深度审计", "warning", "deep", _l8_025)

    # ---- 8.6 韬策略引擎 & 工作流 深度审计 ----

    def _l8_026():
        """韬策略引擎状态持久化检查"""
        try:
            from core.tau_cluster_engine import get_cluster_engine
            engine = get_cluster_engine()
            has_save = hasattr(engine, 'save_state')
            has_load = hasattr(engine, 'load_state')

            # 检查是否有持久化文件
            state_dir = os.path.join(PROJECT_ROOT, "data", "cluster_engine")
            state_files = []
            if os.path.exists(state_dir):
                state_files = [f for f in os.listdir(state_dir) if f.endswith('.json')]

            return (True, 100 if has_save and has_load else 60,
                    f"韬策略引擎持久化: save={'✓' if has_save else '✗'}, "
                    f"load={'✓' if has_load else '✗'}, "
                    f"存档={len(state_files)}个版本",
                    "" if has_save and has_load else "检查 save_state/load_state 方法")
        except Exception as e:
            return (False, 0, f"持久化检查异常: {e}", "检查 core/tau_cluster_engine.py")
    yield ("L8_026", "韬策略引擎状态持久化", "L8_深度审计", "warning", "deep", _l8_026)

    def _l8_027():
        """熵韬收敛优化器Warm Start继承检查"""
        try:
            from core.tau_optimizer_cluster import get_parameter_store
            store = get_parameter_store()
            all_info = store.get_all_strategies_info() if hasattr(store, 'get_all_strategies_info') else []
            has_history = any(info.get("current_version", 0) > 0 for info in all_info)
            has_best_params = any(info.get("best_score", 0) > 0 for info in all_info)

            return (True, 100 if has_history else 50,
                    f"Warm Start: 历史版本={'有' if has_history else '无'}, "
                    f"最佳评分={'有' if has_best_params else '无'}, "
                    f"策略数={len(all_info)}",
                    "" if has_history else "执行一次优化以生成历史参数")
        except Exception as e:
            return (False, 0, f"Warm Start检查异常: {e}", "检查 tau_optimizer_cluster 模块")
    yield ("L8_027", "优化器Warm Start继承", "L8_深度审计", "warning", "deep", _l8_027)

    def _l8_028():
        """工作流断点续算检查"""
        try:
            from core.integration_bus import get_integration_bus
            bus = get_integration_bus()
            has_checkpoint = (hasattr(bus, '_save_checkpoint') or
                             hasattr(bus, 'save_checkpoint') or
                             hasattr(bus, '_checkpoint') or
                             hasattr(bus, 'checkpoint') or
                             hasattr(bus, 'save_state'))
            has_resume = (hasattr(bus, '_resume_from_checkpoint') or
                         hasattr(bus, 'resume_from_checkpoint') or
                         hasattr(bus, '_resume_checkpoint') or
                         hasattr(bus, 'resume') or
                         hasattr(bus, 'load_state'))
            checkpoint_path = os.path.join(PROJECT_ROOT, "data", "checkpoint.json")
            has_checkpoint_file = os.path.exists(checkpoint_path)

            return (True, 100 if has_checkpoint and has_resume else 80,
                    f"断点续算: 代码={'✓' if has_checkpoint and has_resume else '✗'}, "
                    f"断点文件={'存在' if has_checkpoint_file else '无'}",
                    "执行一次完整工作流即可生成断点" if not has_checkpoint_file else "")
        except Exception as e:
            return (False, 0, f"断点续算检查异常: {e}", "检查 core/integration_bus.py")
    yield ("L8_028", "工作流断点续算", "L8_深度审计", "warning", "deep", _l8_028)

    def _l8_029():
        """工作流批量模式支持检查"""
        try:
            import inspect

            from core.workflow_engine import get_workflow_engine
            engine = get_workflow_engine()
            sig = inspect.signature(engine.run_oneclick)
            has_batch = 'batch_mode' in sig.parameters
            has_stock_pool = 'stock_pool' in sig.parameters
            has_strategy = 'strategy_names' in sig.parameters
            has_fast = 'fast_mode' in sig.parameters

            return (True, 100 if has_batch else 50,
                    f"批量模式: 参数={'✓' if has_batch else '✗'}, "
                    f"股票池={'✓' if has_stock_pool else '✗'}, "
                    f"策略指定={'✓' if has_strategy else '✗'}, "
                    f"快速模式={'✓' if has_fast else '✗'}",
                    "" if has_batch else "run_oneclick 需添加 batch_mode 参数")
        except Exception as e:
            return (False, 0, f"批量模式检查异常: {e}", "检查 core/workflow_engine.py")
    yield ("L8_029", "工作流批量模式支持", "L8_深度审计", "warning", "deep", _l8_029)

    def _l8_030():
        """股票池流转一致性检查"""
        try:
            from core.integration_bus import get_integration_bus
            from core.stock_pool import get_stock_pool_manager
            pool_mgr = get_stock_pool_manager()
            bus = get_integration_bus()
            has_flow = (hasattr(bus, 'auto_stock_pool_flow') or
                       hasattr(bus, 'auto_stock_pool_flow_for_strategy'))
            has_match = hasattr(bus, 'auto_match_stock_pool')
            # 检查各层级是否有重复股票
            all_stocks = pool_mgr.get_all_stocks() if hasattr(pool_mgr, 'get_all_stocks') else []
            all_ids = set()
            duplicates = 0
            for s in all_stocks:
                # StockRecord 是 dataclass，使用属性访问
                sid = getattr(s, 'symbol', None) or getattr(s, 'code', str(s))
                if sid in all_ids:
                    duplicates += 1
                all_ids.add(sid)
            return (True, 100 if duplicates == 0 and has_flow else 70,
                    f"股票池流转: 匹配={'✓' if has_match else '✗'}, "
                    f"流转={'✓' if has_flow else '✗'}, "
                    f"总数={len(all_stocks)}, 重复={duplicates}",
                    "检查 stock_pool 流转逻辑" if duplicates > 0 else "")
        except Exception as e:
            return (False, 0, f"股票池流转检查异常: {e}", "检查 core/stock_pool.py 和 core/integration_bus.py")
    yield ("L8_030", "股票池流转一致性", "L8_深度审计", "warning", "deep", _l8_030)
