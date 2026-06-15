# -*- coding: utf-8 -*-
"""
风控路由
========
风控相关的API路由
"""

from flask import Blueprint, request, jsonify
from api.aurora_adapter import get_aurora_adapter
from api.response_formatter import APIResponse

risk_routes = Blueprint('risk_routes', __name__, url_prefix='/risk')


@risk_routes.route('/status', methods=['GET'])
def risk_status():
    """获取风控状态"""
    adapter = get_aurora_adapter()
    result = adapter.get_risk_status()

    return jsonify(APIResponse.success(result))


@risk_routes.route('/check', methods=['POST'])
def risk_check():
    """执行风控检查"""
    adapter = get_aurora_adapter()
    data = request.get_json(silent=True) or {}
    result = adapter.post("/api/risk-control/check", data=data)

    return jsonify(result)
