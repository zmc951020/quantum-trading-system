# -*- coding: utf-8 -*-
"""集成总线 API 路由"""
from flask import request, jsonify


def register_routes(app):
    @app.route('/api/integration/info', methods=['GET'])
    def integration_info():
        """获取集成总线状态信息"""
        try:
            from core.integration_bus import get_integration_bus
            bus = get_integration_bus()
            return jsonify(bus.get_workflow_report())
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/integration/optimize', methods=['POST'])
    def integration_optimize():
        """流程1: 单策略韬定律自动优化"""
        try:
            data = request.get_json() or {}
            strategy_name = data.get('strategy', '')
            if not strategy_name:
                return jsonify({"success": False, "error": "需要策略名称参数"}), 400
            coarse_points = int(data.get('coarse_points', 30))
            refined_points = int(data.get('refined_points', 15))
            from core.integration_bus import get_integration_bus
            bus = get_integration_bus()
            result = bus.auto_optimize_strategy(
                strategy_name=strategy_name,
                coarse_points=coarse_points,
                refined_points_per_region=refined_points
            )
            return jsonify(result)
        except Exception as e:
            import traceback
            return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500

    @app.route('/api/integration/stock_pool', methods=['POST'])
    def integration_stock_pool():
        """流程2: 策略-股票池自动匹配"""
        try:
            data = request.get_json() or {}
            strategy_name = data.get('strategy', '')
            if not strategy_name:
                return jsonify({"success": False, "error": "需要策略名称参数"}), 400
            stock_count = int(data.get('stock_count', 20))
            from core.integration_bus import get_integration_bus
            bus = get_integration_bus()
            result = bus.auto_match_stock_pool(
                strategy_name=strategy_name,
                stock_count=stock_count
            )
            return jsonify(result)
        except Exception as e:
            import traceback
            return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500

    @app.route('/api/integration/full_workflow', methods=['POST'])
    def integration_full_workflow():
        """流程3: 完整自动化流程 (优化→股票池→交易配置)"""
        try:
            data = request.get_json() or {}
            strategy_name = data.get('strategy', '')
            if not strategy_name:
                return jsonify({"success": False, "error": "需要策略名称参数"}), 400
            coarse_points = int(data.get('coarse_points', 25))
            refined_points = int(data.get('refined_points', 10))
            from core.integration_bus import get_integration_bus
            bus = get_integration_bus()
            result = bus.auto_full_workflow(
                strategy_name=strategy_name,
                coarse_points=coarse_points,
                refined_points_per_region=refined_points
            )
            return jsonify(result)
        except Exception as e:
            import traceback
            return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500

    @app.route('/api/integration/batch_optimize', methods=['POST'])
    def integration_batch_optimize():
        """流程4: 批量优化多个策略"""
        try:
            data = request.get_json() or {}
            strategy_names = data.get('strategies', [])
            if not strategy_names:
                return jsonify({"success": False, "error": "需要策略名称列表参数"}), 400
            coarse_points = int(data.get('coarse_points', 20))
            refined_points = int(data.get('refined_points', 10))
            from core.integration_bus import get_integration_bus
            bus = get_integration_bus()
            result = bus.auto_batch_optimize(
                strategy_names=strategy_names,
                coarse_points=coarse_points,
                refined_points_per_region=refined_points
            )
            return jsonify(result)
        except Exception as e:
            import traceback
            return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500

    @app.route('/api/integration/apply', methods=['POST'])
    def integration_apply():
        """流程5: 应用优化结果到交易配置"""
        try:
            data = request.get_json() or {}
            strategy_name = data.get('strategy', '')
            if not strategy_name:
                return jsonify({"success": False, "error": "需要策略名称参数"}), 400
            min_score = float(data.get('min_score', 0.3))
            from core.integration_bus import get_integration_bus
            bus = get_integration_bus()
            result = bus.auto_apply_optimization(
                strategy_name=strategy_name,
                min_score_threshold=min_score
            )
            return jsonify(result)
        except Exception as e:
            import traceback
            return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500

    @app.route('/api/integration/health_check', methods=['GET'])
    def integration_health_check():
        """流程6: 系统健康检查与重优化"""
        try:
            from core.integration_bus import get_integration_bus
            bus = get_integration_bus()
            force = request.args.get('force', '').lower() in ['true', '1', 'yes']
            result = bus.check_and_reoptimize(force_reoptimize=force)
            return jsonify(result)
        except Exception as e:
            import traceback
            return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500