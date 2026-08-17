# -*- coding: utf-8 -*-
"""stock_pool_routes - API网关路由"""
from flask import request, jsonify
from api.response_formatter import APIResponse
from api.aurora_core_adapter import get_aurora_adapter, AURORA_BACKEND

from api.middleware.auth import require_auth
from api.middleware.csrf import require_csrf
from api.middleware.rate_limit import rate_limit
from api.middleware.sanitize import sanitize_input
from api.middleware.origin import check_origin
from api.middleware.threat import check_threat
from api.validators import get_input_validator, get_data_masker

import logging
import os
import time
logger = logging.getLogger(__name__)


def register_routes(api_gateway):
    """在蓝图上注册所有路由"""

    def get_adapter():
        from api.gateway import get_adapter as _ga
        return _ga()

    # ============================================================

    @api_gateway.route('/stock-pool', methods=['GET'])
    @require_auth
    def stock_pool():
        """股票池"""
        result = get_adapter().get_stock_pool()
        return jsonify(result)


    @api_gateway.route('/stock-pool/add', methods=['POST'])
    @require_auth
    def stock_pool_add():
        """添加股票"""
        data = request.get_json(silent=True) or {}
        result = get_adapter().add_stock_pool(data)
        return jsonify(result)


    @api_gateway.route('/stock-pool/remove', methods=['POST'])
    @require_auth
    def stock_pool_remove():
        """移除股票"""
        data = request.get_json(silent=True) or {}
        result = get_adapter().remove_stock_pool(data)
        return jsonify(result)


    @api_gateway.route('/stock-pool/move-to-trading', methods=['POST'])
    @require_auth
    def stock_pool_move():
        """移入交易池"""
        data = request.get_json(silent=True) or {}
        result = get_adapter().move_to_trading_pool(data)
        return jsonify(result)


    @api_gateway.route('/stock_pool/summary', methods=['GET'])
    def stock_pool_summary():
        """股票池汇总统计"""
        try:
            from core.stock_pool import get_stock_pool_manager
            pool = get_stock_pool_manager()
            summary = pool.get_pool_summary() if hasattr(pool, 'get_pool_summary') else {}
            return jsonify({"success": True, "data": {"pools": summary}})
        except Exception as e:
            return jsonify({"success": True, "data": {"pools": {"candidate": 0, "classified": 0, "watchlist": 0, "adaptive": 0, "trading": 0}, "note": str(e)}})


    @api_gateway.route('/stock_pool/auto_flow', methods=['POST'])
    def stock_pool_auto_flow():
        """自动流转：触发股票池层级流转"""
        try:
            from core.stock_pool import get_stock_pool_manager
            pool = get_stock_pool_manager()
            flowed = 0
            if hasattr(pool, 'auto_flow'):
                flowed = pool.auto_flow()
            return jsonify({"success": True, "data": {"flowed": flowed}})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})


    @api_gateway.route('/integration/stock_pool', methods=['POST'])
    @require_auth
    def integration_stock_pool():
        """前端 /api/integration/stock_pool — 股票池集成流程"""
        try:
            from core.integration_bus import get_integration_bus
            bus = get_integration_bus()
            data = request.get_json(silent=True) or {}
            strategy_name = data.get("strategy_name", "")
            if not strategy_name:
                strategies = get_adapter().get_strategy_list()
                strategy_name = strategies[0]["name"] if strategies else ""
            result = bus.auto_hybrid_power_flow(strategy_name)
            return jsonify({"success": result.get("success", True), "data": result})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500


    @api_gateway.route('/stock_pool/run_pipeline', methods=['POST'])
    @require_auth
    def stock_pool_run_pipeline():
        """前端 /api/stock_pool/run_pipeline — 股票池完整流程"""
        try:
            from stock_pool.main import StockPoolSystem
            system = StockPoolSystem()
            stocks = system.generate_sample_stocks(20)
            result = system.run_full_pipeline(stocks)
            return jsonify({
                "success": True,
                "data": {
                    "filtered_count": len(result.get("filtered", [])),
                    "matched_count": len(result.get("matched", [])),
                    "simulated_count": len(result.get("simulated", [])),
                    "final_count": len(result.get("final", [])),
                    "final_stocks": [{
                        "code": f["stock"].code,
                        "name": f["stock"].name,
                        "strategy": f["strategy"].name,
                        "score": f["score"],
                        "grade": f["grade"]
                    } for f in result.get("final", [])]
                }
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500


    # ============================================================

