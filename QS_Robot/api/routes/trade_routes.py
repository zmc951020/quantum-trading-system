# -*- coding: utf-8 -*-
"""trade_routes - API网关路由"""
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

    @api_gateway.route('/trade/validate', methods=['POST'])
    @require_auth
    def trade_validate():
        data = request.get_json(silent=True) or {}
        result = get_adapter().validate_trade(data)
        return jsonify(result)


    @api_gateway.route('/trade/execute', methods=['POST'])
    @require_auth
    @require_csrf
    @sanitize_input
    @rate_limit(max_requests=5, window_seconds=60)
    def trade_execute():
        data = request.get_json(silent=True) or {}
        result = get_adapter().execute_trade(data)
        return jsonify(result)


    @api_gateway.route('/trade/report', methods=['GET'])
    @require_auth
    def trade_report():
        result = get_adapter().get_trade_report()
        return jsonify(result)


    @api_gateway.route('/trade/positions', methods=['GET'])
    def trade_positions():
        try:
            from core.trade_executor import TradeExecutor
            executor = TradeExecutor()
            positions = []
            if hasattr(executor, 'get_positions'):
                positions = executor.get_positions() or []
            elif hasattr(executor, 'positions'):
                positions = list(executor.positions.values()) if isinstance(executor.positions, dict) else []
            return jsonify({"success": True, "data": {"positions": positions, "mode": getattr(executor, 'mode', 'simulated')}})
        except Exception as e:
            return jsonify({"success": True, "data": {"positions": [], "mode": "simulated", "note": str(e)}})


    @api_gateway.route('/trade/critical/validate', methods=['POST'])
    @require_auth
    def trade_critical_validate():
        result = get_adapter().critical_validate()
        return jsonify(result)


    @api_gateway.route('/trade/critical/refresh', methods=['POST'])
    @require_auth
    def trade_critical_refresh():
        result = get_adapter().critical_refresh()
        return jsonify(result)


    # ============================================================

    @api_gateway.route('/vibe/drill/trades', methods=['GET'])
    @require_auth
    def vibe_drill_trades():
        """GET /api/vibe/drill/trades?strategy=xxx
        策略交易汇总
        """
        try:
            from core.drill_down import get_drill_engine
            engine = get_drill_engine()
            strategy = request.args.get("strategy", None)
            data = engine.get_strategy_trades(strategy)
            return jsonify({"success": True, "data": data})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500



    @api_gateway.route('/vibe/drill/trade/<int:trade_index>', methods=['GET'])
    @require_auth
    def vibe_drill_trade_detail(trade_index):
        """GET /api/vibe/drill/trade/<trade_index>
        单笔交易详情
        """
        try:
            from core.drill_down import get_drill_engine
            engine = get_drill_engine()
            data = engine.get_trade_detail(trade_index)
            if "error" in data:
                return jsonify({"success": False, "error": data["error"], "data": data}), 400
            return jsonify({"success": True, "data": data})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500



    @api_gateway.route('/vibe/trade/live', methods=['POST'])
    @require_auth
    def vibe_trade_live():
        """POST /api/vibe/trade/live
        实盘成交回写：记录实盘成交数据
        Body: {"symbol": "600519", "action": "buy", "price": 1800, "quantity": 100, "timestamp": "..."}
        """
        try:
            from core.infrastructure import get_trade_writer
            tw = get_trade_writer()
            data = request.get_json(silent=True) or {}
            result = tw.record_live_trade(data)
            if result["success"]:
                return jsonify({"success": True, "data": result})
            return jsonify({"success": False, "error": result["error"]}), 400
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500



    @api_gateway.route('/vibe/trade/summary', methods=['GET'])
    @require_auth
    def vibe_trade_summary():
        """GET /api/vibe/trade/summary?hours=24&symbol=600519
        实盘成交摘要
        """
        try:
            from core.infrastructure import get_trade_writer
            tw = get_trade_writer()
            hours = request.args.get("hours", 24, type=int)
            symbol = request.args.get("symbol", None)
            summary = tw.get_trade_summary(hours)
            if symbol:
                trades = tw.get_recent_trades(hours, symbol)
                return jsonify({"success": True, "data": {"summary": summary, "trades": trades}})
            return jsonify({"success": True, "data": {"summary": summary}})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500



