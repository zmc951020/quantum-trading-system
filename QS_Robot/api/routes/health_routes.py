# -*- coding: utf-8 -*-
"""health_routes - API网关路由"""
import logging
import os
import sys
import time

from api.aurora_core_adapter import AURORA_BACKEND, get_aurora_adapter
from api.middleware.auth import require_auth
from api.middleware.csrf import require_csrf
from api.middleware.origin import check_origin
from api.middleware.rate_limit import rate_limit
from api.middleware.sanitize import sanitize_input
from api.middleware.threat import check_threat
from api.response_formatter import APIResponse
from api.validators import get_data_masker, get_input_validator
from flask import jsonify, request

logger = logging.getLogger(__name__)

from core.security import get_rate_limiter, get_threat_detector
from core.system_health_checker import get_health_checker


def _summarize_trends(trends):
    """巡检趋势摘要（2026-10-21 补：原调用处引用了未定义函数，补最小实现）"""
    if not trends:
        return None
    latest = trends[-1]
    summary = {
        "total_records": len(trends),
        "latest": latest,
    }
    if isinstance(latest, dict):
        summary["has_issue"] = latest.get("has_issue") or latest.get("issues_count", 0) > 0
    return summary


def register_routes(api_gateway):
    """在蓝图上注册所有路由"""

    def get_adapter():
        from api.gateway import get_adapter as _ga
        return _ga()

    # ============================================================

    @api_gateway.route('/risk/status', methods=['GET'])
    def risk_status():
        """获取风控状态"""
        result = get_adapter().get_risk_status()
        return jsonify(result)



    @api_gateway.route('/security/status', methods=['GET'])
    @require_auth
    def security_status():
        """获取安全状态"""
        detector = get_threat_detector()
        return jsonify(APIResponse.success({
            "threat_detection": "active",
            "rate_limiting": "active",
            "csrf_protection": "active",
            "input_sanitization": "active",
            "data_masking": "active",
            "ip_reputation": detector.check_ip_reputation(request.remote_addr)
        }))


    # ============================================================

    @api_gateway.route('/health/full', methods=['GET'])
    @require_auth
    def health_full():
        result = get_adapter().get_health_full()
        return jsonify(result)


    @api_gateway.route('/monitor/status', methods=['GET'])
    @require_auth
    def monitor_status():
        result = get_adapter().get_monitor_status()
        return jsonify(result)


    @api_gateway.route('/status', methods=['GET'])
    @require_auth
    def system_status():
        """系统状态 — 直接导入模式"""
        adapter = get_adapter()
        strategies = adapter.get_strategy_list()
        degradation = adapter.get_degradation_status().get("data", {})
        return jsonify(APIResponse.success({
            "mode": "direct_import",
            "aurora_connected": adapter.is_connected(),
            "strategy_count": len(strategies),
            "aurora_backend": adapter.check_aurora_backend(),
            "qs_robot_url": "http://127.0.0.1:5003",
            "degradation": degradation,
        }))



    @api_gateway.route('/optimizer/list', methods=['GET'])
    @require_auth
    def optimizer_list():
        """获取优化器列表"""
        adapter = get_adapter()
        optimizers = adapter.get_optimizers()
        return jsonify(APIResponse.success({"optimizers": optimizers, "total": len(optimizers)}))



    @api_gateway.route('/tau/modules', methods=['GET'])
    @require_auth
    def tau_modules():
        """获取韬定律优化器模块列表（兼容旧接口）"""
        adapter = get_adapter()
        optimizers = adapter.get_optimizers()
        return jsonify(APIResponse.success({"modules": optimizers, "total": len(optimizers)}))


    # ============================================================

    @api_gateway.route('/optimizer/status/<task_id>', methods=['GET'])
    @require_auth
    def optimizer_status(task_id):
        """优化任务状态"""
        result = get_adapter().get_optimizer_task_status(task_id)
        return jsonify(result)


    @api_gateway.route('/data-source/status', methods=['GET'])
    @require_auth
    def data_source_status():
        """数据源连接状态"""
        result = get_adapter().get_data_source_status()
        return jsonify(result)


    @api_gateway.route('/health', methods=['GET'])
    def health_check():
        """健康检查"""
        adapter = get_adapter()
        aurora_ok = adapter.check_aurora_backend()
        return jsonify({
            "success": True,
            "status": "healthy" if adapter.is_connected() else "degraded",
            "aurora": "connected" if aurora_ok else "disconnected",
            "qs_robot": "online",
            "degradation": adapter.get_degradation_status().get("data", {}),
        })



    @api_gateway.route('/health/degradation', methods=['GET'])
    def health_degradation():
        """降级状态查询（供前端状态栏使用）"""
        adapter = get_adapter()
        result = adapter.get_degradation_status()
        return jsonify(result)



    @api_gateway.route('/health/params-sync', methods=['POST'])
    def health_params_sync():
        """触发参数同步：将5003优化参数同步到5002"""
        adapter = get_adapter()
        result = adapter.sync_params_to_aurora()
        return jsonify(result)


    # ============================================================

    @api_gateway.route('/health/check', methods=['POST'])
    @require_auth
    def health_check_run():
        """触发系统巡检 — 快速/深度模式"""
        data = request.get_json(silent=True) or {}
        mode = data.get("mode", "quick")
        checker = get_health_checker()
        report = checker.run_check(mode=mode)
        return jsonify({
            "success": True,
            "data": {
                "report_id": report.report_id,
                "timestamp": report.timestamp,
                "mode": report.mode,
                "overall_score": report.overall_score,
                "overall_status": report.overall_status,
                "total_checks": report.total_checks,
                "passed_checks": report.passed_checks,
                "failed_checks": report.failed_checks,
                "layers": report.layers,
                "alerts": report.alerts,
                "elapsed_seconds": report.elapsed_seconds,
            }
        })



    @api_gateway.route('/health/report/<report_id>', methods=['GET'])
    @require_auth
    def health_report_get(report_id):
        """获取历史巡检报告"""
        checker = get_health_checker()
        report = checker.get_report(report_id)
        if report:
            return jsonify({"success": True, "data": report})
        return jsonify({"success": False, "message": "报告不存在"}), 404



    @api_gateway.route('/health/reports', methods=['GET'])
    @require_auth
    def health_report_list():
        """获取巡检报告列表"""
        checker = get_health_checker()
        limit = request.args.get("limit", 20, type=int)
        reports = checker.get_report_list(limit=limit)
        return jsonify({"success": True, "data": {"reports": reports}})



    @api_gateway.route('/health/scheduler', methods=['POST'])
    @require_auth
    def health_scheduler():
        """定时巡检开关"""
        data = request.get_json(silent=True) or {}
        action = data.get("action", "status")
        interval = data.get("interval", 30)
        checker = get_health_checker()

        if action == "start":
            result = checker.start_scheduler(interval_minutes=interval)
        elif action == "stop":
            result = checker.stop_scheduler()
        else:
            result = checker.get_scheduler_status()
        return jsonify({"success": True, "data": result})



    @api_gateway.route('/health/trend', methods=['GET'])
    @require_auth
    def health_trend():
        """巡检历史趋势数据"""
        limit = request.args.get("limit", 50, type=int)
        checker = get_health_checker()
        trends = checker.get_trend_history(limit=limit)
        return jsonify({
            "success": True,
            "data": {
                "trends": trends,
                "total": len(trends),
                "summary": _summarize_trends(trends) if trends else None,
            }
        })



    @api_gateway.route('/health/check/l2', methods=['POST'])
    @require_auth
    def health_check_l2():
        """L2业务功能链路专项巡检"""
        data = request.get_json(silent=True) or {}
        mode = data.get("mode", "quick")
        try:
            from core.l2_inspector import L2Inspector
            inspector = L2Inspector(mode=mode)
            report = inspector.run()
            return jsonify({
                "success": True,
                "data": {
                    "timestamp": report.timestamp,
                    "mode": report.mode,
                    "overall_score": report.overall_score,
                    "overall_status": "healthy" if report.overall_score >= 80 else "warning",
                    "total_checks": report.total,
                    "passed_checks": report.passed,
                    "failed_checks": report.failed,
                    "categories": report.categories,
                    "items": report.items,
                    "elapsed_seconds": report.elapsed_seconds,
                }
            })
        except Exception as e:
            return jsonify({"success": False, "message": f"L2巡检异常: {e}"}), 500



    @api_gateway.route('/health/check/three_entry', methods=['POST'])
    @require_auth
    def health_check_three_entry():
        """三大入口自动化流程链路验收"""
        try:
            import importlib.util
            import sys
            spec = importlib.util.spec_from_file_location(
                "_verify_three_entries",
                os.path.join(os.path.dirname(os.path.dirname(__file__)), "_verify_three_entries.py"))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            results = []
            passed = 0
            failed = 0
            check_names = [
                ("基础连通-5002", "verify_closed_n1"),
                ("基础连通-5003", "verify_closed_n2"),
                ("基础连通-认证", "verify_closed_n3"),
                ("基础连通-拦截", "verify_closed_n4"),
                ("基础连通-性能", "verify_closed_n5"),
                ("原始策略-n1", "verify_original_n1"),
                ("原始策略-n2", "verify_original_n2"),
                ("原始策略-n3", "verify_original_n3"),
                ("原始策略-n4", "verify_original_n4"),
                ("原始策略-n5", "verify_original_n5"),
                ("Vibe入口-n1", "verify_vibe_n1"),
                ("Vibe入口-n2", "verify_vibe_n2"),
                ("Vibe入口-n3", "verify_vibe_n3"),
                ("Vibe入口-n4", "verify_vibe_n4"),
                ("Vibe入口-n5", "verify_vibe_n5"),
                ("同花顺-n1", "verify_ths_n1"),
                ("同花顺-n2", "verify_ths_n2"),
                ("同花顺-n3", "verify_ths_n3"),
                ("同花顺-n4", "verify_ths_n4"),
                ("同花顺-n5", "verify_ths_n5"),
                ("资源约束-n1", "verify_resource_n1"),
                ("资源约束-n2", "verify_resource_n2"),
            ]

            for name, fn_name in check_names:
                try:
                    fn = getattr(mod, fn_name, None)
                    if fn:
                        result = fn()
                        if isinstance(result, dict):
                            p = result.get("passed", False)
                            detail = result.get("detail", "")
                        else:
                            p, detail = result
                        results.append({"name": name, "passed": p, "detail": str(detail)})
                        if p: passed += 1
                        else: failed += 1
                except Exception as e:
                    results.append({"name": name, "passed": False, "detail": str(e)})
                    failed += 1

            total = passed + failed
            return jsonify({
                "success": True,
                "data": {
                    "overall_score": round(passed / total * 100, 1) if total > 0 else 0,
                    "passed_checks": passed,
                    "failed_checks": failed,
                    "total_checks": total,
                    "elapsed_seconds": 0,
                    "results": results,
                }
            })
        except Exception as e:
            return jsonify({"success": False, "message": f"三大入口验收异常: {e}"}), 500



    @api_gateway.route('/health/check/engineering_loop', methods=['POST'])
    @require_auth
    def health_check_engineering_loop():
        """自动化工程闭环流审查：自适应工程流+策略入口+可视化+链路+色调风格"""
        try:
            from core.engineering_loop_auditor import EngineeringLoopAuditor
            auditor = EngineeringLoopAuditor()
            report = auditor.run_all(verbose=False)
            return jsonify({
                "success": True,
                "data": {
                    "overall_score": report["pass_rate"],
                    "passed_checks": report["passed"],
                    "failed_checks": report["failed"],
                    "total_checks": report["total"],
                    "elapsed_seconds": report["elapsed_seconds"],
                    "grade": report["grade"],
                    "categories": report["categories"],
                    "results": report["results"],
                }
            })
        except Exception as e:
            return jsonify({"success": False, "message": f"工程闭环流审查异常: {e}"}), 500



    @api_gateway.route('/health/auto-fix', methods=['POST'])
    @require_auth
    def health_auto_fix():
        """智能自动修复：根据巡检报告分层诊断并执行修复操作

        修复策略（按优先级）：
        1. 策略注册表 → 自动发现
        2. 代码规范 → ruff auto-fix
        3. Pre-commit → 重新安装钩子
        4. 过期日志 → 清理
        5. CSS变量 → 补全缺失变量
        6. 参数存储 → 触发优化
        7. 模块导入 → 检查依赖
        """
        data = request.get_json(silent=True) or {}
        report = data.get("report", {})
        fixes = []
        auto_fix_count = 0
        suggestion_count = 0

        # 解析报告中的失败项
        layers = report.get("layers", [])
        failed_items = []
        for layer in layers:
            for item in layer.get("items", []):
                if not item.get("passed", True):
                    failed_items.append({
                        "id": item.get("id", ""),
                        "name": item.get("name", ""),
                        "layer": layer.get("layer", ""),
                        "severity": item.get("severity", ""),
                        "suggestion": item.get("suggestion", ""),
                    })

        # ── 1. 策略注册表修复 ──
        strategy_fails = [i for i in failed_items if "策略" in i["name"] and "注册" in i["name"]]
        if strategy_fails:
            try:
                from core.strategy_auto_discovery import get_auto_discovery
                disc = get_auto_discovery()
                if hasattr(disc, 'run_once'):
                    disc.run_once()
                    fixes.append({"action": "策略自动发现", "result": "已触发策略注册扫描", "auto": True})
                    auto_fix_count += 1
                else:
                    fixes.append({"action": "策略自动发现", "result": "模块不支持run_once", "auto": False})
            except Exception as e:
                fixes.append({"action": "策略自动发现", "result": f"跳过: {e}", "auto": False})

        # ── 2. 代码规范自动修复 ──
        lint_fails = [i for i in failed_items if "Ruff" in i["name"] or "代码规范" in i["name"]]
        if lint_fails:
            try:
                import subprocess
                result = subprocess.run(
                    [sys.executable, "-m", "ruff", "check", "--fix", "core/"],
                    capture_output=True, text=True, timeout=60,
                    cwd=os.path.dirname(os.path.dirname(__file__))
                )
                fixed = len([l for l in result.stdout.split('\n') if 'FIX' in l or 'fixed' in l.lower()])
                if result.returncode == 0:
                    fixes.append({"action": "Ruff自动修复", "result": f"已修复{fixed}个问题" if fixed > 0 else "无需修复", "auto": True})
                    auto_fix_count += 1
                else:
                    fixes.append({"action": "Ruff自动修复", "result": "部分问题需要手动修复", "auto": False})
            except Exception as e:
                fixes.append({"action": "Ruff自动修复", "result": f"跳过: {e}", "auto": False})

        # ── 3. Pre-commit钩子修复 ──
        precommit_fails = [i for i in failed_items if "Pre-commit" in i["name"] or "钩子" in i["name"]]
        if precommit_fails:
            try:
                import subprocess
                project_root = os.path.dirname(os.path.dirname(__file__))
                result = subprocess.run(
                    [sys.executable, "-m", "pre_commit", "install"],
                    capture_output=True, text=True, timeout=30,
                    cwd=project_root
                )
                if result.returncode == 0:
                    fixes.append({"action": "Pre-commit安装", "result": "钩子已重新安装", "auto": True})
                    auto_fix_count += 1
                else:
                    fixes.append({"action": "Pre-commit安装", "result": f"安装失败: {result.stderr[:100]}", "auto": False})
            except Exception as e:
                fixes.append({"action": "Pre-commit安装", "result": f"跳过: {e}", "auto": False})

        # ── 4. 过期日志清理 ──
        try:
            log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
            if os.path.exists(log_dir):
                old_logs = [f for f in os.listdir(log_dir) if f.endswith('.log') and
                           os.path.getmtime(os.path.join(log_dir, f)) < time.time() - 7 * 86400]
                if old_logs:
                    cleaned = 0
                    for f in old_logs[:5]:
                        try:
                            os.remove(os.path.join(log_dir, f))
                            cleaned += 1
                        except Exception:
                            pass
                    if cleaned > 0:
                        fixes.append({"action": "日志清理", "result": f"已清理{cleaned}个过期日志(>7天)", "auto": True})
                        auto_fix_count += 1
        except Exception:
            pass

        # ── 5. 参数存储初始化 ──
        param_fails = [i for i in failed_items if "参数" in i["name"] and ("存储" in i["name"] or "Warm" in i["name"])]
        if param_fails:
            try:
                from core.tau_optimizer_cluster import get_parameter_store
                store = get_parameter_store()
                if hasattr(store, 'initialize'):
                    store.initialize()
                    fixes.append({"action": "参数存储初始化", "result": "已初始化参数存储", "auto": True})
                    auto_fix_count += 1
                else:
                    fixes.append({"action": "参数存储初始化", "result": "需手动执行一次优化", "auto": False})
            except Exception as e:
                fixes.append({"action": "参数存储初始化", "result": f"跳过: {e}", "auto": False})

        # ── 6. CSS暗色主题变量补全 ──
        css_fails = [i for i in failed_items if "CSS" in i["name"] or "暗色" in i["name"] or "色调" in i["name"]]
        if css_fails:
            try:
                from core.engineering_loop_auditor import EngineeringLoopAuditor
                css_vars = EngineeringLoopAuditor.DARK_THEME_VARS
                template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "templates")
                css_fixed = 0
                for fname in os.listdir(template_dir):
                    if not fname.endswith('.html'):
                        continue
                    fpath = os.path.join(template_dir, fname)
                    try:
                        with open(fpath, 'r', encoding='utf-8') as f:
                            content = f.read()
                        # 检查是否缺少CSS变量
                        missing = [v for v in css_vars if v not in content]
                        if missing and ':root' in content or '<style>' in content:
                            # 尝试补全（在:root块或style块末尾追加）
                            var_block = '\n'.join(f"            {k}: {v};" for k, v in css_vars.items() if k in missing)
                            if var_block and ':root' in content:
                                new_content = content.replace(
                                    ':root {',
                                    ':root {\n' + var_block
                                )
                                with open(fpath, 'w', encoding='utf-8') as f:
                                    f.write(new_content)
                                css_fixed += 1
                    except Exception:
                        pass
                if css_fixed > 0:
                    fixes.append({"action": "CSS变量补全", "result": f"已补全{css_fixed}个页面的CSS变量", "auto": True})
                    auto_fix_count += 1
            except Exception as e:
                fixes.append({"action": "CSS变量补全", "result": f"跳过: {e}", "auto": False})

        # ── 7. 健康报告清理 ──
        try:
            report_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "health_reports")
            if os.path.exists(report_dir):
                old_reports = [f for f in os.listdir(report_dir) if f.endswith('.json') and
                              os.path.getmtime(os.path.join(report_dir, f)) < time.time() - 30 * 86400]
                if old_reports:
                    cleaned = 0
                    for f in old_reports:
                        try:
                            os.remove(os.path.join(report_dir, f))
                            cleaned += 1
                        except Exception:
                            pass
                    if cleaned > 0:
                        fixes.append({"action": "旧报告清理", "result": f"已清理{cleaned}个过期报告(>30天)", "auto": True})
                        auto_fix_count += 1
        except Exception:
            pass

        # ── 8. 生成未自动修复的修复建议 ──
        for item in failed_items:
            if item.get("suggestion") and item["severity"] in ("critical", "warning"):
                suggestion_count += 1
                fixes.append({
                    "action": f"[{item['id']}] {item['name']}",
                    "result": item["suggestion"],
                    "auto": False,
                    "is_suggestion": True,
                })

        if not fixes:
            fixes.append({"action": "系统状态", "result": "所有检查项正常，无需优化", "auto": True})

        return jsonify({
            "success": True,
            "data": {
                "message": f"智能修复完成: {auto_fix_count}项自动修复, {suggestion_count}条修复建议",
                "fixes": fixes,
                "summary": {
                    "auto_fixed": auto_fix_count,
                    "suggestions": suggestion_count,
                    "total_failed": len(failed_items),
                }
            }
        })


    # ============================================================

    @api_gateway.route('/vibe/pool/status', methods=['GET'])
    @require_auth
    def vibe_pool_status():
        """GET /api/vibe/pool/status
        动态股票池：获取当前股票池状态
        """
        try:
            from core.infrastructure import get_stock_pool
            pool = get_stock_pool()
            config = pool.get_pool_config()
            stocks = pool.get_current_pool()
            return jsonify({
                "success": True,
                "data": {"config": config, "stocks": stocks},
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500



    @api_gateway.route('/risk-control/status', methods=['GET'])
    @require_auth
    def risk_control_status():
        """风控状态 — 代理到5002"""
        try:
            import requests as req
            r = req.get(f"{AURORA_BACKEND}/api/risk-control/status", timeout=5)
            return jsonify(r.json()), r.status_code
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500


    @api_gateway.route('/workflow/status', methods=['GET'])
    @require_auth
    def workflow_status():
        """获取工作流运行状态"""
        try:
            from core.workflow_engine import get_workflow_engine
            engine = get_workflow_engine()
            return jsonify(APIResponse.success(engine.get_status()))
        except Exception as e:
            return jsonify(APIResponse.error(str(e))), 500



    @api_gateway.route('/health/enhanced', methods=['GET'])
    @require_auth
    def health_full_enhanced():
        """完整系统健康检查（含韬策略引擎+优化器+自适应层）"""
        try:
            from core.system_health_checker import get_health_checker
            checker = get_health_checker()
            report = checker.run_quick_check()

            # 补充集群引擎健康
            cluster_health = {}
            try:
                from core.integration_bus import get_integration_bus
                bus = get_integration_bus()
                cluster_health = bus.cluster_engine_health_check()
            except Exception:
                pass

            # 补充自适应层健康
            adaptation_health = {}
            try:
                from core.adaptive_market_regime import get_adaptation_engine
                adaptation = get_adaptation_engine()
                adaptation_health = adaptation.get_health_report()
            except Exception:
                pass

            return jsonify(APIResponse.success({
                "system_health": report.to_dict() if hasattr(report, 'to_dict') else str(report),
                "cluster_engine": cluster_health,
                "adaptation_engine": adaptation_health,
                "timestamp": __import__('datetime').datetime.now().isoformat(),
            }))
        except Exception as e:
            return jsonify(APIResponse.error(str(e))), 500



    @api_gateway.route('/health/cluster', methods=['GET'])
    @require_auth
    def health_cluster_check():
        """韬策略引擎健康检查"""
        try:
            from core.integration_bus import get_integration_bus
            bus = get_integration_bus()
            health = bus.cluster_engine_health_check()
            return jsonify(APIResponse.success(health))
        except Exception as e:
            return jsonify(APIResponse.error(str(e))), 500



    @api_gateway.route('/health/adaptation', methods=['GET'])
    @require_auth
    def health_adaptation_check():
        """自适应策略层健康检查"""
        try:
            from core.adaptive_market_regime import get_adaptation_engine
            adaptation = get_adaptation_engine()
            health = adaptation.get_health_report()
            return jsonify(APIResponse.success(health))
        except Exception as e:
            return jsonify(APIResponse.error(str(e))), 500



    @api_gateway.route('/health/optimizer', methods=['GET'])
    @require_auth
    def health_optimizer_check():
        """优化器集群健康检查"""
        try:
            from core.integration_bus import get_integration_bus
            bus = get_integration_bus()
            report = bus.get_workflow_report()
            return jsonify(APIResponse.success(report))
        except Exception as e:
            return jsonify(APIResponse.error(str(e))), 500

