# -*- coding: utf-8 -*-
"""technical_routes - API网关路由"""
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

    @api_gateway.route('/technical/analyze', methods=['POST'])
    @require_auth
    def technical_analyze():
        """技术分析"""
        data = request.get_json(silent=True) or {}
        result = get_adapter().get_technical_analysis(
            symbol=data.get("symbol", "600000.SH"),
            days=data.get("days", 100),
        )
        return jsonify(result)


    @api_gateway.route('/technical/batch', methods=['POST'])
    @require_auth
    def technical_batch():
        """批量技术分析"""
        data = request.get_json(silent=True) or {}
        result = get_adapter().get_technical_batch(
            symbols=data.get("symbols", []),
            days=data.get("days", 100),
        )
        return jsonify(result)


    @api_gateway.route('/technical/data/<symbol>', methods=['GET'])
    @require_auth
    def technical_data(symbol):
        """技术数据"""
        result = get_adapter().get_technical_data(symbol)
        return jsonify(result)


    # ============================================================

    @api_gateway.route('/technical-indicators', methods=['GET'])
    @require_auth
    def technical_indicators():
        """技术指标"""
        symbol = request.args.get("symbol", "000001.SZ")
        result = get_adapter().get_technical_indicators(symbol)
        return jsonify(result)


    # ============================================================

