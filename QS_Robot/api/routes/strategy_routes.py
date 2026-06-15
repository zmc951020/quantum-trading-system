# -*- coding: utf-8 -*-
"""
策略路由
========
策略相关的API路由
"""

from flask import Blueprint, request, jsonify
from api.aurora_adapter import get_aurora_adapter
from api.response_formatter import APIResponse

strategy_routes = Blueprint('strategy_routes', __name__, url_prefix='/strategy')


@strategy_routes.route('/list', methods=['GET'])
def list_strategies():
    """获取策略列表"""
    adapter = get_aurora_adapter()
    result = adapter.get_strategy_list()

    if isinstance(result, list):
        return jsonify(APIResponse.success({
            "strategies": result,
            "total": len(result)
        }))

    return jsonify(APIResponse.success({"strategies": [], "total": 0}))


@strategy_routes.route('/tree', methods=['GET'])
def strategy_tree():
    """获取策略分类树"""
    adapter = get_aurora_adapter()
    result = adapter.get_strategy_tree()

    return jsonify(APIResponse.success(result))
