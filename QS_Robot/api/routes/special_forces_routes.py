# -*- coding: utf-8 -*-
"""special_forces_routes - API网关路由"""
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

    @api_gateway.route('/special_forces/evolution', methods=['POST'])
    @require_auth
    def special_forces_evolution():
        """运行特种兵策略自演进优化"""
        data = request.get_json(silent=True) or {}
        symbol = data.get("symbol", "510300")
        population_size = data.get("population_size", 20)
        max_generations = data.get("max_generations", 30)
        force_refresh = data.get("force_refresh", False)
        incremental = data.get("incremental", False)

        try:
            from core.enhanced_strategy_manager import get_strategy_manager
            mgr = get_strategy_manager()
            result = mgr.run_special_forces_evolution(
                symbol=symbol,
                population_size=population_size,
                max_generations=max_generations,
                force_refresh=force_refresh,
                incremental=incremental,
            )
            return jsonify(result)
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500


    @api_gateway.route('/special_forces/backtest', methods=['POST'])
    @require_auth
    def special_forces_backtest():
        """运行特种兵策略回测"""
        data = request.get_json(silent=True) or {}
        symbol = data.get("symbol", "510300")
        params = data.get("params", None)
        initial_capital = data.get("initial_capital", 100000.0)
        use_optimized = data.get("use_optimized", True)

        try:
            from core.enhanced_strategy_manager import get_strategy_manager
            mgr = get_strategy_manager()
            result = mgr.run_special_forces_backtest(
                symbol=symbol,
                params=params,
                initial_capital=initial_capital,
                use_optimized=use_optimized,
            )
            return jsonify(result)
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500


    @api_gateway.route('/special_forces/params/<symbol>', methods=['GET'])
    @require_auth
    def special_forces_params(symbol):
        """获取特种兵策略参数"""
        try:
            from core.enhanced_strategy_manager import get_strategy_manager
            mgr = get_strategy_manager()
            result = mgr.get_special_forces_params(symbol)
            return jsonify(result)
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500


    @api_gateway.route('/special_forces/start', methods=['POST'])
    @require_auth
    def special_forces_start():
        """启动特种兵策略"""
        data = request.get_json(silent=True) or {}
        symbol = data.get("symbol", "510300")
        balance = data.get("balance", 100000.0)
        use_optimized_params = data.get("use_optimized_params", True)

        try:
            from core.enhanced_strategy_manager import get_strategy_manager
            mgr = get_strategy_manager()
            success, message = mgr.start_special_forces(
                symbol=symbol,
                balance=balance,
                use_optimized_params=use_optimized_params,
            )
            return jsonify({"success": success, "message": message})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500


    @api_gateway.route('/special_forces/stop', methods=['POST'])
    @require_auth
    def special_forces_stop():
        """停止特种兵策略"""
        data = request.get_json(silent=True) or {}
        symbol = data.get("symbol", "510300")

        try:
            from core.enhanced_strategy_manager import get_strategy_manager
            mgr = get_strategy_manager()
            strategy_name = f"special_forces_{symbol}"
            mgr._active_strategies.pop(strategy_name, None)
            return jsonify({"success": True, "message": f"特种兵策略 {symbol} 已停止"})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500


    @api_gateway.route('/special_forces/status', methods=['GET'])
    @require_auth
    def special_forces_status():
        """获取特种兵策略运行状态"""
        symbol = request.args.get("symbol", "510300")

        try:
            from core.enhanced_strategy_manager import get_strategy_manager
            mgr = get_strategy_manager()
            strategy_name = f"special_forces_{symbol}"
            active = strategy_name in mgr._active_strategies
            info = mgr._active_strategies.get(strategy_name)
            return jsonify({
                "success": True,
                "data": {
                    "symbol": symbol,
                    "active": active,
                    "status": info.status.value if info and hasattr(info, 'status') else "stopped",
                    "best_params": info.best_params if info else {},
                    "best_score": info.best_score if info else 0,
                }
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500


    # ============================================================