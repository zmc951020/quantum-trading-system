# -*- coding: utf-8 -*-
"""backtest_routes - API网关路由"""
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

    @api_gateway.route('/backtest/run', methods=['POST'])
    @require_auth
    def backtest_run():
        """执行回测"""
        data = request.get_json(silent=True) or {}
        result = get_adapter().run_backtest(
            strategy_name=data.get("strategy"),
            params=data.get("params")
        )
        if result.get("success"):
            return jsonify(result)
        return jsonify(APIResponse.error(result.get("error", "回测执行失败"))), 500



    @api_gateway.route('/backtest/history', methods=['GET'])
    @require_auth
    def backtest_history():
        """获取回测历史"""
        result = get_adapter().get_backtest_history()
        return jsonify(result)


    # ============================================================

    @api_gateway.route('/backtest/best', methods=['GET'])
    @require_auth
    def backtest_best():
        """最佳回测 — 代理到5002"""
        try:
            import requests as req
            r = req.get(f"{AURORA_BACKEND}/api/backtest/best", timeout=5)
            return jsonify(r.json()), r.status_code
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500


