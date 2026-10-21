# -*- coding: utf-8 -*-
"""workflow_routes - API网关路由"""
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

    @api_gateway.route('/workflow/run', methods=['POST'])
    @require_auth
    @sanitize_input
    def workflow_run():
        """一键执行选股工作流"""
        try:
            from core.workflow_engine import get_workflow_engine
            engine = get_workflow_engine()

            data = request.get_json(silent=True) or {}
            stock_pool = data.get("stock_pool", None)
            strategy_names = data.get("strategies", None)
            fast_mode = data.get("fast_mode", False)
            batch_mode = data.get("batch_mode", False)

            import threading
            def _run():
                engine.run_oneclick(
                    stock_pool=stock_pool,
                    strategy_names=strategy_names,
                    fast_mode=fast_mode,
                    batch_mode=batch_mode,
                )

            threading.Thread(target=_run, daemon=True).start()
            return jsonify(APIResponse.success({
                "message": "工作流已启动",
                "fast_mode": fast_mode,
                "batch_mode": batch_mode,
            }))
        except Exception as e:
            return jsonify(APIResponse.error(str(e))), 500



    @api_gateway.route('/workflow/history', methods=['GET'])
    @require_auth
    def workflow_history():
        """获取工作流历史记录"""
        try:
            from core.workflow_engine import get_workflow_engine
            engine = get_workflow_engine()
            return jsonify(APIResponse.success(engine.get_history()))
        except Exception as e:
            return jsonify(APIResponse.error(str(e))), 500



    @api_gateway.route('/workflow/step', methods=['POST'])
    @require_auth
    @sanitize_input
    def workflow_step():
        """执行单个工作流步骤"""
        try:
            from core.workflow_engine import get_workflow_engine
            engine = get_workflow_engine()
            data = request.get_json(silent=True) or {}
            step = data.get("step", "discover")
            result = engine.run_step(step)
            return jsonify(APIResponse.success({
                "name": result.name,
                "status": result.status,
                "message": result.message,
                "data": result.data,
                "error": result.error,
            }))
        except Exception as e:
            return jsonify(APIResponse.error(str(e))), 500


    # ============================================================

