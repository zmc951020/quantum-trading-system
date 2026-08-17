# -*- coding: utf-8 -*-
"""risk_routes - API网关路由"""
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

    @api_gateway.route('/risk/check', methods=['POST'])
    @require_auth
    def risk_check():
        """执行风控检查"""
        data = request.get_json(silent=True) or {}
        result = get_adapter().check_risk(data)
        return jsonify(result)


    # ============================================================

    @api_gateway.route('/risk/assess', methods=['POST'])
    @require_auth
    def risk_assess():
        """风险评估"""
        data = request.get_json(silent=True) or {}
        symbol = data.get("symbol", "")
        strategy_name = data.get("strategy", "")
        backtest_result = data.get("backtest_result", {})
        position_info = data.get("position_info", {})
        result = get_adapter().risk_assess(symbol, strategy_name, backtest_result, position_info)
        return jsonify(result)


    # ============================================================

    @api_gateway.route('/risk/stop-loss', methods=['GET'])
    @require_auth
    def risk_stop_loss():
        """止损止盈"""
        result = get_adapter().get_risk_stop_loss()
        return jsonify(result)


    # ============================================================

