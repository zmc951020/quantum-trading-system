# -*- coding: utf-8 -*-
"""Tau 优化器 API 路由"""
from flask import request, jsonify


def register_routes(app):
    @app.route('/api/tau/info', methods=['GET'])
    def tau_info():
        """获取韬定律集群信息"""
        try:
            from core.enhanced_strategy_manager import get_strategy_manager
            mgr = get_strategy_manager()
            return jsonify({"success": True, "data": mgr.get_tau_cluster_info()})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/tau/optimize', methods=['POST'])
    def tau_optimize():
        """运行韬定律集群优化"""
        try:
            data = request.get_json()
            strategy_name = data.get('strategy', '')
            param_ranges = data.get('param_ranges')
            coarse_points = int(data.get('coarse_points', 30))
            refined_points = int(data.get('refined_points', 50))
            target = data.get('target', 'sharpe_ratio')
            from core.enhanced_strategy_manager import get_strategy_manager
            mgr = get_strategy_manager()
            result = mgr.run_tau_cluster_optimization(
                strategy_name=strategy_name,
                param_ranges=param_ranges,
                coarse_points=coarse_points,
                refined_points=refined_points,
                target=target
            )
            return jsonify(result)
        except Exception as e:
            import traceback
            return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500

    @app.route('/api/tau/eval', methods=['POST'])
    def tau_eval():
        """单次参数评估（带缓存）"""
        try:
            data = request.get_json()
            strategy_name = data.get('strategy', '')
            params = data.get('params', {})
            from core.enhanced_strategy_manager import get_strategy_manager
            mgr = get_strategy_manager()
            result = mgr.run_tau_single_eval(strategy_name, params)
            return jsonify(result)
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/tau/status', methods=['GET'])
    def tau_status():
        """集群状态和统计"""
        try:
            from core.enhanced_strategy_manager import get_strategy_manager
            mgr = get_strategy_manager()
            info = mgr.get_tau_cluster_info()
            return jsonify({"success": True, "data": info})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/tau/bernoulli', methods=['POST'])
    def tau_bernoulli():
        """韬定律集群: 伯努利-康达策略优化"""
        try:
            data = request.get_json() or {}
            strategy_name = data.get('strategy', '伯努利-康达策略')
            iterations = int(data.get('iterations', 50))
            from core.enhanced_strategy_manager import get_strategy_manager
            mgr = get_strategy_manager()
            result = mgr.run_tau_bernoulli_optimization(strategy_name=strategy_name, iterations=iterations)
            return jsonify(result)
        except Exception as e:
            import traceback
            return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500

    @app.route('/api/tau/shepherd', methods=['POST'])
    def tau_shepherd():
        """韬定律集群: 智能标的轮动68因子优化"""
        try:
            data = request.get_json() or {}
            strategy_name = data.get('strategy', '智能标的轮动')
            coarse = int(data.get('coarse_points', 35))
            refined = int(data.get('refined_per_group', 15))
            from core.enhanced_strategy_manager import get_strategy_manager
            mgr = get_strategy_manager()
            result = mgr.run_tau_shepherd_optimization(
                strategy_name=strategy_name,
                coarse_points=coarse,
                refined_per_group=refined,
            )
            return jsonify(result)
        except Exception as e:
            import traceback
            return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500

    @app.route('/api/tau/modules', methods=['GET'])
    def tau_modules():
        """获取韬定律集群的策略感知模块列表"""
        try:
            from core.enhanced_strategy_manager import get_strategy_manager
            mgr = get_strategy_manager()
            return jsonify(mgr.get_tau_cluster_modules())
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500