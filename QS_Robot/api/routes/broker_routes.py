# -*- coding: utf-8 -*-
"""
经纪商路由
=========
经纪商相关的API路由
"""

from flask import Blueprint, request, jsonify
from api.aurora_adapter import get_aurora_adapter
from api.response_formatter import APIResponse

broker_routes = Blueprint('broker_routes', __name__, url_prefix='/broker')


@broker_routes.route('/list', methods=['GET'])
def broker_list():
    """获取经纪商列表"""
    adapter = get_aurora_adapter()
    result = adapter.get("/api/broker/list")

    return jsonify(result)


@broker_routes.route('/switch', methods=['POST'])
def broker_switch():
    """切换经纪商"""
    adapter = get_aurora_adapter()
    data = request.get_json(silent=True) or {}
    result = adapter.post("/api/broker/switch", data=data)

    return jsonify(result)


@broker_routes.route('/orders', methods=['GET'])
def broker_orders():
    """获取订单列表"""
    adapter = get_aurora_adapter()
    params = dict(request.args)
    result = adapter.get("/api/broker/orders", params=params)

    return jsonify(result)
