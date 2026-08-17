# -*- coding: utf-8 -*-
"""strategy_routes - API网关路由"""
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

    @api_gateway.route('/strategy/list', methods=['GET'])
    @require_auth
    def strategy_list():
        """获取策略列表 — 直接调用"""
        adapter = get_adapter()
        strategies = adapter.get_strategy_list()
        return jsonify(APIResponse.success({
            "strategies": strategies,
            "total": len(strategies)
        }))



    @api_gateway.route('/strategy/tree', methods=['GET'])
    @require_auth
    def strategy_tree():
        """获取策略分类树 — 使用StrategyRegistry三分类"""
        adapter = get_adapter()
        tree = adapter.get_strategy_tree()
        if tree:
            return jsonify(APIResponse.success(tree))
        # fallback: 从策略列表构建
        strategies = adapter.get_strategy_list()
        tree = {}
        for s in strategies:
            cat = s.get("strategy_type", s.get("type", "其他"))
            if cat not in tree:
                tree[cat] = []
            tree[cat].append(s)
        return jsonify(APIResponse.success(tree))



    @api_gateway.route('/strategy/registry/summary', methods=['GET'])
    @require_auth
    def strategy_registry_summary():
        """获取策略注册表摘要（类型分布、状态分布等）"""
        adapter = get_adapter()
        summary = adapter.get_strategy_registry_summary()
        return jsonify(APIResponse.success(summary))



    @api_gateway.route('/strategy/type/<strategy_type>', methods=['GET'])
    @require_auth
    def strategy_by_type(strategy_type):
        """按类型获取策略列表"""
        adapter = get_adapter()
        strategies = adapter.get_strategies_by_type(strategy_type)
        return jsonify(APIResponse.success({"strategies": strategies, "total": len(strategies)}))



    @api_gateway.route('/strategy/enabled', methods=['GET'])
    @require_auth
    def strategy_enabled():
        """获取已启用的策略列表"""
        adapter = get_adapter()
        strategies = adapter.get_enabled_strategies()
        return jsonify(APIResponse.success({"strategies": strategies, "total": len(strategies)}))



    @api_gateway.route('/strategy/<name>/info', methods=['GET'])
    @require_auth
    def strategy_info(name):
        """获取策略详情"""
        adapter = get_adapter()
        result = adapter.get_strategy_info(name)
        if result:
            return jsonify(result)
        return jsonify(APIResponse.error("策略不存在")), 404



    @api_gateway.route('/strategy/<name>/start', methods=['POST'])
    @require_auth
    @require_csrf
    @sanitize_input
    def strategy_start(name):
        """启动策略"""
        data = request.get_json(silent=True) or {}
        result = get_adapter().start_strategy(name, data.get("params"))
        return jsonify(result)



    @api_gateway.route('/strategy/<name>/stop', methods=['POST'])
    @require_auth
    @require_csrf
    @sanitize_input
    def strategy_stop(name):
        """停止策略"""
        result = get_adapter().stop_strategy(name)
        return jsonify(result)


    # ============================================================

    @api_gateway.route('/strategy-status', methods=['GET'])
    @require_auth
    def strategy_status():
        """策略运行状态"""
        result = get_adapter().get_strategy_status()
        return jsonify(result)


    @api_gateway.route('/strategy/test', methods=['POST'])
    @require_auth
    def strategy_test():
        """策略测试"""
        data = request.get_json(silent=True) or {}
        result = get_adapter().strategy_test(
            strategy_name=data.get("strategy_name", data.get("strategy", "")),
            params=data.get("params", {}),
        )
        return jsonify(result)


    @api_gateway.route('/strategy/docs/<strategy_name>', methods=['GET'])
    @require_auth
    def strategy_docs(strategy_name):
        """策略文档"""
        result = get_adapter().strategy_docs(strategy_name)
        return jsonify(result)


    @api_gateway.route('/aurora/strategy-list', methods=['GET'])
    @require_auth
    def aurora_strategy_list():
        """前端 /api/aurora/strategy-list 的别名，转发到 /api/strategy/list"""
        return strategy_list()


    @api_gateway.route('/strategy/library', methods=['GET'])
    @require_auth
    def strategy_library():
        """策略库 — 代理到5002"""
        try:
            import requests as req
            r = req.get(f"{AURORA_BACKEND}/api/strategy/library", timeout=5)
            return jsonify(r.json()), r.status_code
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500


    @api_gateway.route('/strategy-params', methods=['GET'])
    @require_auth
    def strategy_params():
        """策略参数 — 代理到5002"""
        try:
            import requests as req
            r = req.get(f"{AURORA_BACKEND}/api/strategy-params", timeout=5)
            return jsonify(r.json()), r.status_code
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500


