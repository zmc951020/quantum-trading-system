# -*- coding: utf-8 -*-
"""
回测路由
========
回测相关的API路由
"""

from flask import Blueprint, request, jsonify
from api.aurora_adapter import get_aurora_adapter
from api.response_formatter import APIResponse

backtest_routes = Blueprint('backtest_routes', __name__, url_prefix='/backtest')


@backtest_routes.route('/run', methods=['POST'])
def run_backtest():
    """执行回测"""
    adapter = get_aurora_adapter()
    data = request.get_json(silent=True) or {}
    result = adapter.post("/api/backtest/run", data=data)

    return jsonify(result)


@backtest_routes.route('/history', methods=['GET'])
def backtest_history():
    """获取回测历史"""
    adapter = get_aurora_adapter()
    params = dict(request.args)
    result = adapter.get("/api/backtest/history", params=params)

    return jsonify(result)
