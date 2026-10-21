# -*- coding: utf-8 -*-
"""optimizer_routes - API网关路由"""
import json
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

    @api_gateway.route('/optimizer/run', methods=['POST'])
    @require_auth
    def optimizer_run():
        """执行优化器"""
        data = request.get_json(silent=True) or {}
        # 如果没有显式指定params字段，将整个data作为params传递
        params = data.get("params", {})
        if not params:
            params = {k: v for k, v in data.items() if k not in ("strategy", "strategy_name", "optimizer", "optimizer_id", "symbol")}
        result = get_adapter().run_optimizer_task(
            strategy_name=data.get("strategy", data.get("strategy_name", "")),
            optimizer_id=data.get("optimizer", data.get("optimizer_id", "tau_cluster")),
            symbol=data.get("symbol", "600000.SH"),
            params=params,
        )
        return jsonify(result)


    @api_gateway.route('/optimizer/result/<task_id>', methods=['GET'])
    @require_auth
    def optimizer_result(task_id):
        """优化结果"""
        result = get_adapter().get_optimizer_task_result(task_id)
        return jsonify(result)


    @api_gateway.route('/optimizer/evolve', methods=['POST'])
    @require_auth
    def optimizer_evolve():
        """自进化优化"""
        data = request.get_json(silent=True) or {}
        result = get_adapter().evolve_optimizer(data)
        return jsonify(result)


    @api_gateway.route('/optimizer/trace/<strategy_name>', methods=['GET'])
    @require_auth
    def optimizer_trace(strategy_name):
        """获取优化收敛轨迹"""
        import glob as _glob
        trace_dir = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), 'data', 'optimization_traces')
        pattern = os.path.join(trace_dir, f"{strategy_name}_*.json")
        trace_files = sorted(_glob.glob(pattern), reverse=True)
    
        if not trace_files:
            return jsonify({"success": True, "traces": [], "message": "无轨迹数据"})
    
        traces = []
        for tf in trace_files[:10]:  # 最多返回最近10个
            try:
                with open(tf, 'r', encoding='utf-8') as f:
                    traces.append(json.load(f))
            except Exception:
                pass
    
        return jsonify({
            "success": True,
            "strategy_name": strategy_name,
            "total_files": len(trace_files),
            "traces": traces,
        })


    # ============================================================

