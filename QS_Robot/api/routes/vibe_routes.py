# -*- coding: utf-8 -*-
"""vibe_routes - API网关路由"""
from flask import request, jsonify
from api.response_formatter import APIResponse

from api.middleware.auth import require_auth

import logging
logger = logging.getLogger(__name__)


def register_routes(api_gateway):
    """在蓝图上注册所有路由"""

    def get_adapter():
        from api.gateway import get_adapter as _ga
        return _ga()

    # ============================================================

    @api_gateway.route('/vibe/analyze', methods=['POST'])
    @require_auth
    def vibe_analyze():
        """前端 /api/vibe/analyze — 股票智能分析"""
        try:
            from core.integration_bus import get_integration_bus
            bus = get_integration_bus()
            data = request.get_json(silent=True) or {}
            stock_code = data.get("code", data.get("symbol", ""))
            strategy_name = data.get("strategy", data.get("strategy_name", ""))
            if not stock_code:
                return jsonify({"success": False, "error": "请提供股票代码"}), 400
            # 使用选股流程进行标的分析
            result = bus.auto_vibe_stock_selection(
                market_scope=data.get("market", "all"),
                strategy_name=strategy_name,
                target_count=data.get("count", 10)
            )
            return jsonify({"success": True, "data": result})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500


    @api_gateway.route('/vibe/market_scan', methods=['POST'])
    @require_auth
    def vibe_market_scan():
        """前端 /api/vibe/market_scan — 全市场扫描"""
        try:
            from core.integration_bus import get_integration_bus
            bus = get_integration_bus()
            data = request.get_json(silent=True) or {}
            result = bus.auto_vibe_stock_selection(
                symbol_list=data.get("symbols"),
                auto_into_pool=data.get("auto_into_pool", True),
                top_n=data.get("count", 20),
                max_analyze=data.get("max_analyze", 200),
            )
            return jsonify({"success": True, "data": result})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500


    # ============================================================
    @api_gateway.route('/vibe/analyze_and_optimize', methods=['POST'])
    @require_auth
    def vibe_analyze_and_optimize():
        """POST /api/vibe/analyze_and_optimize
        Vibe多智能体分析 → 熵韬收敛优化 → 风控复核 完整闭环

        接收: {symbols: ["000001", "600519"], use_optimizer: true}
        """
        try:
            from core.integration_bus import get_integration_bus
            bus = get_integration_bus()
            data = request.get_json(silent=True) or {}
            symbols = data.get("symbols", None)
            use_optimizer = data.get("use_optimizer", True)

            if use_optimizer:
                result = bus.auto_vibe_optimize_workflow(symbols=symbols)
            else:
                # 仅Vibe分析，不做优化
                result = bus.auto_vibe_stock_selection(
                    symbol_list=symbols,
                    auto_into_pool=False,
                    top_n=data.get("count", 20),
                    max_analyze=data.get("max_analyze", 100),
                )

            return jsonify(result)
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500



    @api_gateway.route('/vibe/optimize_with_feedback', methods=['POST'])
    @require_auth
    def vibe_optimize_with_feedback():
        """POST /api/vibe/optimize_with_feedback
        优化器精选股票池 → Vibe风控Agent二次复核

        接收: {optimized_pool: [...], require_vibe_review: true}
        """
        try:
            from core.integration_bus import get_integration_bus
            bus = get_integration_bus()
            data = request.get_json(silent=True) or {}
            optimized_pool = data.get("optimized_pool", [])
            require_vibe_review = data.get("require_vibe_review", True)

            if not optimized_pool:
                return jsonify({"success": False, "error": "请提供optimized_pool"}), 400

            if require_vibe_review:
                result = bus.vibe_optimizer_feedback(optimized_pool)
            else:
                result = {
                    "success": True,
                    "data": {"approved_pool": optimized_pool, "approved_count": len(optimized_pool)},
                    "message": "跳过Vibe复核",
                    "elapsed_seconds": 0,
                }

            return jsonify(result)
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500



    @api_gateway.route('/vibe/trace/<stock_code>', methods=['GET'])
    @require_auth
    def vibe_trace_lineage(stock_code):
        """获取股票全链路溯源：哪个Agent推荐、评分、技能、优化轮次、风控审核"""
        try:
            from core.integration_bus import StrategyIntegrationBus
            bus = StrategyIntegrationBus()
            trace = bus.trace_stock_lineage(stock_code)
            return jsonify(APIResponse.success(trace))
        except Exception as e:
            logger.error(f"溯源失败: {e}")
            return jsonify(APIResponse.error(f"溯源失败: {str(e)}")), 500



    @api_gateway.route('/vibe/convergence_status', methods=['GET'])
    @require_auth
    def vibe_convergence_status():
        """GET /api/vibe/convergence_status
        返回当前优化器收敛状态（迭代次数、熵值、方差、是否收敛）
        """
        try:
            from core.tau_optimizer_cluster import get_parameter_store
            store = get_parameter_store()
            all_info = store.get_all_strategies_info()

            strategies_status = []
            for info in all_info:
                name = info.get("name", "")
                if name:
                    best_params = store.get_best_params(name)
                    strategies_status.append({
                        "strategy": name,
                        "version": info.get("current_version", 0),
                        "best_score": info.get("best_score", 0),
                        "convergence_iterations": best_params.get("convergence_iterations", "N/A") if best_params else "N/A",
                        "entropy": best_params.get("entropy", "N/A") if best_params else "N/A",
                        "variance": best_params.get("variance", "N/A") if best_params else "N/A",
                        "converged": info.get("best_score", 0) > 0.5,
                        "last_optimized": info.get("last_optimized", ""),
                    })

            return jsonify({
                "success": True,
                "data": {
                    "total_strategies": len(strategies_status),
                    "converged_count": sum(1 for s in strategies_status if s["converged"]),
                    "strategies": strategies_status,
                },
                "message": f"优化器收敛状态: {sum(1 for s in strategies_status if s['converged'])}/{len(strategies_status)}已收敛",
                "elapsed_seconds": 0,
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500



    @api_gateway.route('/vibe/auto_adaptive', methods=['POST'])
    @require_auth
    def vibe_auto_adaptive():
        """POST /api/vibe/auto_adaptive
        自适应市场重校准：检测市场状态变化，自动触发优化器重收敛
        """
        try:
            from core.integration_bus import get_integration_bus
            bus = get_integration_bus()
            result = bus.adaptive_market_recalibration()
            return jsonify(result)
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500



    @api_gateway.route('/vibe/market_environment', methods=['GET'])
    @require_auth
    def vibe_market_environment():
        """GET /api/vibe/market_environment
        返回当前Vibe判定的市场环境（震荡/趋势/高波动）及置信度
        """
        try:
            from core.vibe_integration import get_vibe_integration
            vibe = get_vibe_integration()

            if hasattr(vibe, 'analyze_market_environment'):
                me_result = vibe.analyze_market_environment()
            else:
                me_result = {"regime": "震荡", "confidence": 0.5, "volatility": "medium", "trend": "neutral"}

            return jsonify({
                "success": True,
                "data": {
                    "regime": me_result.get("regime", "震荡"),
                    "confidence": me_result.get("confidence", 0.5),
                    "volatility": me_result.get("volatility", "medium"),
                    "trend": me_result.get("trend", "neutral"),
                    "timestamp": me_result.get("timestamp", ""),
                },
                "message": f"当前市场环境: {me_result.get('regime', '震荡')} (置信度={me_result.get('confidence', 0.5):.2f})",
                "elapsed_seconds": 0,
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500



    @api_gateway.route('/vibe/nlp/parse', methods=['POST'])
    @require_auth
    def vibe_nlp_parse():
        """POST /api/vibe/nlp/parse
        解析自然语言指令，返回意图识别、技能映射、错配检测结果

        Body: {"text": "分析贵州茅台"}
        """
        try:
            data = request.get_json(silent=True) or {}
            text = data.get("text", "")

            from core.nlp_commander import parse_command
            result = parse_command(text)

            return jsonify({
                "success": True,
                "data": result,
                "message": f"意图: {result['intent_type']} (置信度: {result['confidence']:.0%})",
            })
        except Exception as e:
            logger.error(f"NLP解析失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500



    @api_gateway.route('/vibe/nlp/skills', methods=['GET'])
    @require_auth
    def vibe_nlp_skills():
        """GET /api/vibe/nlp/skills?category=技术分析
        列出可用技能及分类
        """
        try:
            from core.nlp_commander import get_nlp_commander
            cmd = get_nlp_commander()
            category = request.args.get("category", None)
            skills = cmd.list_available_skills(category)
            categories = cmd.get_skill_categories()

            return jsonify({
                "success": True,
                "data": {
                    "skills": skills,
                    "categories": categories,
                    "total": len(skills),
                },
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500



    @api_gateway.route('/vibe/nlp/help', methods=['GET'])
    def vibe_nlp_help():
        """GET /api/vibe/nlp/help
        返回NLP指令系统帮助文本
        """
        try:
            from core.nlp_commander import get_nlp_commander
            cmd = get_nlp_commander()
            return jsonify({
                "success": True,
                "data": {"help_text": cmd.get_help_text()},
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @api_gateway.route('/vibe/session/history', methods=['GET'])
    @require_auth
    def vibe_session_history():
        """GET /api/vibe/session/history?limit=50
        获取当前会话历史
        """
        try:
            from core.session_memory import get_memory_manager
            mgr = get_memory_manager()
            limit = request.args.get("limit", 50, type=int)
            history = mgr.get_history(limit)
            return jsonify({
                "success": True,
                "data": {"session_id": mgr.session_id, "history": history, "count": len(history)},
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500



    @api_gateway.route('/vibe/session/new', methods=['POST'])
    @require_auth
    def vibe_session_new():
        """POST /api/vibe/session/new
        创建新会话
        """
        try:
            from core.session_memory import get_memory_manager
            mgr = get_memory_manager()
            sid = mgr.new_session()
            return jsonify({"success": True, "data": {"session_id": sid}})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500



    @api_gateway.route('/vibe/reasoning/<agent_name>', methods=['GET'])
    @require_auth
    def vibe_reasoning_by_agent(agent_name):
        """GET /api/vibe/reasoning/<agent_name>?limit=20
        获取指定智能体的推理历史
        """
        try:
            from core.session_memory import get_memory_manager
            mgr = get_memory_manager()
            limit = request.args.get("limit", 20, type=int)
            logs = mgr.get_agent_reasoning(agent_name, limit)
            return jsonify({
                "success": True,
                "data": {"agent": agent_name, "logs": logs, "count": len(logs)},
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500



    @api_gateway.route('/vibe/reasoning/symbol/<symbol>', methods=['GET'])
    @require_auth
    def vibe_reasoning_by_symbol(symbol):
        """GET /api/vibe/reasoning/symbol/<symbol>?limit=20
        获取指定股票的推理历史
        """
        try:
            from core.session_memory import get_memory_manager
            mgr = get_memory_manager()
            limit = request.args.get("limit", 20, type=int)
            logs = mgr.get_symbol_reasoning(symbol, limit)
            return jsonify({
                "success": True,
                "data": {"symbol": symbol, "logs": logs, "count": len(logs)},
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500



    @api_gateway.route('/vibe/task/progress', methods=['GET'])
    @require_auth
    def vibe_task_progress():
        """GET /api/vibe/task/progress?task_id=xxx
        获取任务进度
        """
        try:
            from core.session_memory import get_memory_manager
            mgr = get_memory_manager()
            task_id = request.args.get("task_id", "")
            if task_id:
                status = mgr.get_task_status(task_id)
                return jsonify({"success": True, "data": status})
            else:
                active = mgr.get_active_tasks()
                return jsonify({
                    "success": True,
                    "data": {"active_tasks": active, "count": len(active)},
                })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500



    @api_gateway.route('/vibe/task/cancel', methods=['POST'])
    @require_auth
    def vibe_task_cancel():
        """POST /api/vibe/task/cancel
        Body: {"task_id": "xxx"}
        """
        try:
            from core.session_memory import get_memory_manager
            mgr = get_memory_manager()
            data = request.get_json(silent=True) or {}
            task_id = data.get("task_id", "")
            if not task_id:
                return jsonify({"success": False, "error": "缺少task_id"}), 400
            mgr.cancel_task(task_id)
            return jsonify({"success": True, "message": f"任务 {task_id} 已取消"})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @api_gateway.route('/vibe/drill/macro', methods=['GET'])
    @require_auth
    def vibe_drill_macro():
        """GET /api/vibe/drill/macro
        宏观市场全景（行业板块概览）
        """
        try:
            from core.drill_down import get_drill_engine
            engine = get_drill_engine()
            data = engine.get_macro_overview()
            return jsonify({"success": True, "data": data})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500



    @api_gateway.route('/vibe/drill/industry/<sector_name>', methods=['GET'])
    @require_auth
    def vibe_drill_industry(sector_name):
        """GET /api/vibe/drill/industry/<sector_name>
        行业板块详情（个股列表）
        """
        try:
            from core.drill_down import get_drill_engine
            engine = get_drill_engine()
            data = engine.get_industry_detail(sector_name)
            if "error" in data:
                return jsonify({"success": False, "error": data["error"], "data": data}), 400
            return jsonify({"success": True, "data": data})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500



    @api_gateway.route('/vibe/drill/stock/<symbol>', methods=['GET'])
    @require_auth
    def vibe_drill_stock(symbol):
        """GET /api/vibe/drill/stock/<symbol>
        个股详情
        """
        try:
            from core.drill_down import get_drill_engine
            engine = get_drill_engine()
            data = engine.get_stock_detail(symbol)
            return jsonify({"success": True, "data": data})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500



    @api_gateway.route('/vibe/drill/factor/<symbol>', methods=['GET'])
    @require_auth
    def vibe_drill_factor_overview(symbol):
        """GET /api/vibe/drill/factor/<symbol>
        因子全景（策略评分分解）
        """
        try:
            from core.drill_down import get_drill_engine
            engine = get_drill_engine()
            data = engine.get_factor_overview(symbol)
            return jsonify({"success": True, "data": data})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500



    @api_gateway.route('/vibe/drill/factor/<symbol>/<factor_id>', methods=['GET'])
    @require_auth
    def vibe_drill_factor_detail(symbol, factor_id):
        """GET /api/vibe/drill/factor/<symbol>/<factor_id>
        单因子详情（因子分解）
        """
        try:
            from core.drill_down import get_drill_engine
            engine = get_drill_engine()
            data = engine.get_factor_detail(symbol, factor_id)
            if "error" in data:
                return jsonify({"success": False, "error": data["error"], "data": data}), 400
            return jsonify({"success": True, "data": data})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500



    @api_gateway.route('/vibe/drill/timeline', methods=['GET'])
    @require_auth
    def vibe_drill_timeline():
        """GET /api/vibe/drill/timeline?strategy=xxx
        交易时间线（按日汇总）
        """
        try:
            from core.drill_down import get_drill_engine
            engine = get_drill_engine()
            strategy = request.args.get("strategy", None)
            data = engine.get_trade_timeline(strategy)
            return jsonify({"success": True, "data": data})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @api_gateway.route('/vibe/trace/full/<node_id>', methods=['GET'])
    @require_auth
    def vibe_trace_full(node_id):
        """GET /api/vibe/trace/full/<node_id>
        反向溯源：获取数据节点的完整溯源链路
        """
        try:
            from core.infrastructure import get_traceability
            trace = get_traceability()
            lineage = trace.get_full_lineage(node_id)
            return jsonify({"success": True, "data": lineage})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500



    @api_gateway.route('/vibe/computation/<comp_id>', methods=['GET'])
    @require_auth
    def vibe_computation_steps(comp_id):
        """GET /api/vibe/computation/<comp_id>
        中间运算过程：获取计算步骤记录
        """
        try:
            from core.infrastructure import get_visualizer
            viz = get_visualizer()
            steps = viz.get_computation_steps(comp_id)
            return jsonify({
                "success": True,
                "data": {"comp_id": comp_id, "steps": steps, "count": len(steps)},
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500



    @api_gateway.route('/vibe/anomaly/check', methods=['POST'])
    @require_auth
    def vibe_anomaly_check():
        """POST /api/vibe/anomaly/check
        手动触发异常检测
        Body: {"symbol": "600519", "price": 2000, "prev_close": 1800, "volume": 1e8, "avg_volume": 2e7}
        """
        try:
            from core.infrastructure import get_anomaly_detector
            ad = get_anomaly_detector()
            data = request.get_json(silent=True) or {}
            results = {}

            if "price" in data and "prev_close" in data:
                r = ad.check_price_anomaly(data.get("symbol", ""), data["price"], data["prev_close"])
                if r:
                    results["price"] = r

            if "volume" in data and "avg_volume" in data:
                r = ad.check_volume_anomaly(data.get("symbol", ""), data["volume"], data["avg_volume"])
                if r:
                    results["volume"] = r

            return jsonify({
                "success": True,
                "data": {"anomalies": results, "anomaly_count": len(results)},
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500



    @api_gateway.route('/vibe/pool/update', methods=['POST'])
    @require_auth
    def vibe_pool_update():
        """POST /api/vibe/pool/update
        动态股票池：触发股票池更新
        Body: {"regime": "bull"}
        """
        try:
            from core.infrastructure import get_stock_pool
            pool = get_stock_pool()
            data = request.get_json(silent=True) or {}
            regime = data.get("regime", "range")
            pool.update_regime(regime, data.get("market_data"))
            config = pool.get_pool_config()
            return jsonify({
                "success": True,
                "data": config,
                "message": f"股票池已切换至 {regime} ({config['config']['name']})",
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500



    @api_gateway.route('/vibe/feedback/record', methods=['POST'])
    @require_auth
    def vibe_feedback_record():
        """POST /api/vibe/feedback/record
        Agent迭代修正：记录预测vs实际
        Body: {"agent": "trend", "symbol": "600519", "prediction": {...}, "actual": {...}}
        """
        try:
            from core.infrastructure import get_feedback_loop
            fb = get_feedback_loop()
            data = request.get_json(silent=True) or {}
            result = fb.record_prediction(
                data.get("agent", "unknown"),
                data.get("symbol", ""),
                data.get("prediction", {}),
                data.get("actual", {}),
            )
            return jsonify({"success": True, "data": result})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500



    @api_gateway.route('/vibe/feedback/performance/<agent_name>', methods=['GET'])
    @require_auth
    def vibe_feedback_performance(agent_name):
        """GET /api/vibe/feedback/performance/<agent_name>
        Agent迭代修正：获取Agent表现统计
        """
        try:
            from core.infrastructure import get_feedback_loop
            fb = get_feedback_loop()
            perf = fb.get_agent_performance(agent_name)
            stats = fb.get_correction_stats()
            return jsonify({
                "success": True,
                "data": {"performance": perf, "correction_stats": stats},
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500


    # ============================================================
    # Vibe模块列表API（L9_026/L9_029/L9_032依赖）
    # ============================================================

    @api_gateway.route('/vibe/modules', methods=['GET'])
    @require_auth
    def vibe_modules_list():
        """GET /api/vibe/modules — 返回所有Vibe模块注册信息"""
        try:
            from core.vibe_module_registry import VIBE_MODULES
            modules = {}
            for name, info in VIBE_MODULES.items():
                modules[name] = {
                    "module": info.get("module", ""),
                    "class": info.get("class", ""),
                    "desc": info.get("desc", ""),
                    "category": info.get("category", "unknown"),
                }
            categories = {}
            for name, info in VIBE_MODULES.items():
                cat = info.get("category", "unknown")
                categories.setdefault(cat, 0)
                categories[cat] += 1
            return jsonify({
                "success": True,
                "data": {
                    "modules": modules,
                    "categories": categories,
                    "total": len(modules),
                },
                "message": f"Vibe模块列表: {len(modules)}个模块",
            })
        except Exception as e:
            logger.error(f"Vibe模块列表获取失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500


    @api_gateway.route('/vibe/module/<name>', methods=['GET'])
    @require_auth
    def vibe_module_detail(name):
        """GET /api/vibe/module/<name> — 返回单个Vibe模块详情"""
        try:
            from core.vibe_module_registry import VIBE_MODULES
            if name not in VIBE_MODULES:
                return jsonify({"success": False, "error": f"模块 {name} 不存在"}), 404
            info = VIBE_MODULES[name]
            module_path = info.get("module", "")
            class_name = info.get("class", "")
            importable = False
            try:
                import importlib
                mod = importlib.import_module(module_path)
                importable = hasattr(mod, class_name)
            except Exception:
                pass
            return jsonify({
                "success": True,
                "data": {
                    "name": name,
                    "module": module_path,
                    "class": class_name,
                    "desc": info.get("desc", ""),
                    "category": info.get("category", "unknown"),
                    "importable": importable,
                },
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

