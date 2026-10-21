# -*- coding: utf-8 -*-
"""misc_routes - API网关路由"""
import logging
import os
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


def register_routes(api_gateway):
    """在蓝图上注册所有路由"""

    def get_adapter():
        from api.gateway import get_adapter as _ga
        return _ga()

    # ============================================================

    @api_gateway.route('/aurora/system/info', methods=['GET'])
    @require_auth
    def aurora_system_info():
        """Aurora系统概览 — 直接调用"""
        adapter = get_adapter()
        import_status = adapter.get_import_status()
        strategy_list = adapter.get_strategy_list()

        return jsonify(APIResponse.success({
            "aurora": {
                "direct_import": True,
                "connected": adapter.is_connected(),
                "strategy_count": len(strategy_list),
                "import_status": import_status.get("data", {}).get("import_status", {}),
            },
            "strategies": strategy_list[:10]
        }))


    # ============================================================

    @api_gateway.route('/fund/validate', methods=['POST'])
    @require_auth
    def fund_validate():
        data = request.get_json(silent=True) or {}
        result = get_adapter().validate_fund(data)
        return jsonify(result)


    @api_gateway.route('/fund/block-all', methods=['POST'])
    @require_auth
    def fund_block_all():
        result = get_adapter().block_all_funds()
        return jsonify(result)


    @api_gateway.route('/fund/blacklist/add', methods=['POST'])
    @require_auth
    def fund_blacklist_add():
        data = request.get_json(silent=True) or {}
        result = get_adapter().add_blacklist(data)
        return jsonify(result)


    @api_gateway.route('/fund/mode/only-trading', methods=['POST'])
    @require_auth
    def fund_mode_trading():
        data = request.get_json(silent=True) or {}
        mode = data.get("mode", "only-trading")
        result = get_adapter().set_fund_mode(mode)
        return jsonify(result)


    @api_gateway.route('/fund/config', methods=['GET'])
    @require_auth
    def fund_config():
        result = get_adapter().get_fund_config()
        return jsonify(result)


    # ============================================================

    @api_gateway.route('/ml-grid/data', methods=['GET'])
    @require_auth
    def ml_grid_data():
        result = get_adapter().get_ml_grid_data()
        return jsonify(result)


    @api_gateway.route('/ml-grid/optimize', methods=['POST'])
    @require_auth
    def ml_grid_optimize():
        data = request.get_json(silent=True) or {}
        result = get_adapter().optimize_ml_grid(data)
        return jsonify(result)


    # ============================================================

    @api_gateway.route('/deepseek/chat', methods=['POST'])
    @require_auth
    def deepseek_chat():
        data = request.get_json(silent=True) or {}
        message = data.get("message", "")
        history = data.get("history", [])
        result = get_adapter().deepseek_chat(message, history)
        return jsonify(result)


    # ============================================================

    @api_gateway.route('/accounts', methods=['GET'])
    @require_auth
    def accounts_list():
        result = get_adapter().get_accounts()
        return jsonify(APIResponse.success({"accounts": result}))


    @api_gateway.route('/accounts', methods=['POST'])
    @require_auth
    def accounts_create():
        data = request.get_json(silent=True) or {}
        result = get_adapter().create_account(data)
        return jsonify(result)


    @api_gateway.route('/accounts/<account_id>/switch', methods=['POST'])
    @require_auth
    def accounts_switch(account_id):
        result = get_adapter().switch_account(account_id)
        return jsonify(result)


    # ============================================================

    @api_gateway.route('/performance-data', methods=['GET'])
    def api_performance_data():
        """绩效数据"""
        result = get_adapter().get_performance_data()
        return jsonify(result)


    @api_gateway.route('/kline', methods=['GET'])
    @require_auth
    def kline():
        """K线数据"""
        symbol = request.args.get("symbol", "000001")
        period = request.args.get("period", "daily")
        days = request.args.get("days", 500, type=int)
        adjust = request.args.get("adjust", "qfq")
        result = get_adapter().get_kline(symbol, period, days, adjust)
        return jsonify(result)


    @api_gateway.route('/realtime/<symbol>', methods=['GET'])
    @require_auth
    def realtime(symbol):
        """实时行情"""
        result = get_adapter().get_realtime(symbol)
        return jsonify(result)


    @api_gateway.route('/financial/<symbol>', methods=['GET'])
    @require_auth
    def financial(symbol):
        """财务数据"""
        result = get_adapter().get_financial(symbol)
        return jsonify(result)


    @api_gateway.route('/trading-pool', methods=['GET'])
    @require_auth
    def trading_pool():
        """交易池"""
        result = get_adapter().get_trading_pool()
        return jsonify(result)


    @api_gateway.route('/trading-pool/close', methods=['POST'])
    @require_auth
    def trading_pool_close():
        """关闭持仓"""
        data = request.get_json(silent=True) or {}
        result = get_adapter().close_trading_pool(data)
        return jsonify(result)


    # ============================================================

    @api_gateway.route('/walk-forward', methods=['POST'])
    @require_auth
    def walk_forward():
        """步进优化"""
        data = request.get_json(silent=True) or {}
        result = get_adapter().walk_forward(data)
        return jsonify(result)


    # ============================================================

    @api_gateway.route('/llm/models', methods=['GET'])
    @require_auth
    def llm_models():
        """LLM模型列表"""
        result = get_adapter().get_llm_models()
        return jsonify(result)


    @api_gateway.route('/llm/switch', methods=['POST'])
    @require_auth
    def llm_switch():
        """切换LLM"""
        data = request.get_json(silent=True) or {}
        result = get_adapter().switch_llm(data.get("model", ""))
        return jsonify(result)


    @api_gateway.route('/llm/config', methods=['GET'])
    @require_auth
    def llm_config():
        """LLM配置"""
        result = get_adapter().get_llm_config()
        return jsonify(result)


    # ============================================================

    @api_gateway.route('/account/stocks', methods=['GET'])
    @require_auth
    def account_stocks():
        """账户股票"""
        result = get_adapter().get_account_stocks()
        return jsonify(result)


    @api_gateway.route('/account/reset-risk', methods=['POST'])
    @require_auth
    def account_reset_risk():
        """重置风控"""
        data = request.get_json(silent=True) or {}
        result = get_adapter().reset_account_risk(data.get("name"))
        return jsonify(result)



    @api_gateway.route('/tau/optimize', methods=['POST'])
    @require_auth
    def tau_optimize():
        """韬定律优化 — 前端 /api/tau/optimize 的别名，转发到 /api/optimizer/run"""
        return _forward_optimize()

    @api_gateway.route('/integration/optimize', methods=['POST'])
    @require_auth
    def integration_optimize():
        """前端 /api/integration/optimize 的别名，转发到 /api/optimizer/run"""
        return _forward_optimize()

    def _forward_optimize():
        """优化任务转发（2026-10-21 补：原引用 optimizer_routes 内部函数不可达，改为直接转发 adapter）"""
        data = request.get_json(silent=True) or {}
        params = data.get("params", {})
        if not params:
            params = {k: v for k, v in data.items() if k not in ("strategy", "strategy_name", "optimizer", "optimizer_id", "symbol")}
        result = get_adapter().run_optimizer_task(
            strategy_name=data.get("strategy", data.get("strategy_name", "")),
            optimizer_id=data.get("optimizer", data.get("optimizer_id", "tau_cluster")),
            symbol=data.get("symbol", "600000.SH"),
            params=params,
        )
        return jsonify(result)


    @api_gateway.route('/integration/full_workflow', methods=['POST'])
    @require_auth
    def integration_full_workflow():
        """前端 /api/integration/full_workflow — 完整集成流程"""
        try:
            from core.integration_bus import get_integration_bus
            bus = get_integration_bus()
            data = request.get_json(silent=True) or {}
            strategy_names = data.get("strategies", [])
            result = bus.auto_batch_optimize(strategy_names) if strategy_names else \
                     {"success": False, "error": "请指定策略列表"}
            return jsonify({"success": result.get("success", True), "data": result})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500


    @api_gateway.route('/model-versions', methods=['GET'])
    @require_auth
    def model_versions():
        """模型版本 — 代理到5002"""
        try:
            import requests as req
            r = req.get(f"{AURORA_BACKEND}/api/model-versions", timeout=5)
            return jsonify(r.json()), r.status_code
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500


    @api_gateway.route('/cluster/ths', methods=['GET'])
    def cluster_ths_list():
        """同花顺集群策略列表 - 独立API端点"""
        try:
            from api.ths_bridge.signal_collector import SignalCollector
            collector = SignalCollector()
            strategies = collector.list_strategies() if hasattr(collector, 'list_strategies') else []
            return jsonify({"success": True, "data": {"strategies": strategies, "count": len(strategies)}})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500



    @api_gateway.route('/ths', methods=['GET'])
    def ths_root():
        """同花顺入口根端点"""
        try:
            from api.ths_bridge.signal_collector import SignalCollector
            collector = SignalCollector()
            status = {"available": True, "strategies": 14, "advanced": 18, "total": 32}
            return jsonify({"success": True, "data": status})
        except Exception as e:
            return jsonify({"success": True, "data": {"available": False, "note": str(e)}})



