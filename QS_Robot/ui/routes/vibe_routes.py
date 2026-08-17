# -*- coding: utf-8 -*-
"""Vibe 分析 API 路由"""
from flask import request, jsonify
from datetime import datetime


def register_routes(app):
    # Import vibe_manager for process management routes
    from ui.managers.vibe_manager import (
        start_vibe_api, stop_vibe_api, get_vibe_api_status,
        start_vibe_mcp, stop_vibe_mcp, get_vibe_mcp_status,
    )

    @app.route('/api/vibe/analyze', methods=['POST'])
    def vibe_analyze():
        """港大Vibe智能体分析接口（整合基础分析+29智能体投票）"""
        try:
            data = request.get_json()
            symbol = data.get('symbol', '')
            if not symbol:
                return jsonify({"success": False, "error": "需要股票代码"}), 400
            from core.vibe_integration import get_vibe_integration
            vibe = get_vibe_integration()
            result = vibe.analyze_stock(symbol)
            vote_result = vibe.get_29_agents_vote_matrix(symbol)
            enhanced_result = vibe.analyze_stock_enhanced(symbol)
            combined_result = {**result, 'enhanced_analysis': enhanced_result.get('enhanced_analysis', {}), 'vibe_result': vote_result}
            return jsonify({"success": True, **combined_result})
        except Exception as e:
            import traceback
            return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500

    @app.route('/api/vibe/analyze_enhanced', methods=['POST'])
    def vibe_analyze_enhanced():
        """港大Vibe智能体增强版分析（含综合评分+股票池推荐）"""
        try:
            data = request.get_json()
            symbol = data.get('symbol', '')
            if not symbol:
                return jsonify({"success": False, "error": "需要股票代码"}), 400
            from core.vibe_integration import get_vibe_integration
            vibe = get_vibe_integration()
            result = vibe.analyze_stock_enhanced(symbol)
            return jsonify({"success": True, **result})
        except Exception as e:
            import traceback
            return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500

    @app.route('/api/vibe/29_agents_vote', methods=['POST'])
    def vibe_29_agents_vote():
        """港大29个智能体投票矩阵分析"""
        try:
            data = request.get_json()
            symbol = data.get('symbol', '')
            if not symbol:
                return jsonify({"success": False, "error": "需要股票代码"}), 400
            from core.vibe_integration import get_vibe_integration
            vibe = get_vibe_integration()
            result = vibe.get_29_agents_vote_matrix(symbol)
            return jsonify(result)
        except Exception as e:
            import traceback
            return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500

    @app.route('/api/vibe/market_scan', methods=['POST'])
    def vibe_market_scan():
        """全市场扫描 - 使用港大智能体筛选优质股票"""
        try:
            data = request.get_json() or {}
            top_n = int(data.get('top_n', 20))
            from core.integration_bus import get_integration_bus
            bus = get_integration_bus()
            result = bus.auto_vibe_stock_selection(symbol_list=None, use_market_scan=True, auto_into_pool=False, top_n=top_n)
            return jsonify(result)
        except Exception as e:
            import traceback
            return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500

    @app.route('/api/vibe/status')
    def vibe_status():
        """Vibe-Trading 状态查询"""
        try:
            from core.vibe_integration import get_vibe_integration, VIBE_AVAILABLE, VIBE_ENGINES, VIBE_LOADERS
            vibe = get_vibe_integration()
            return jsonify({
                "success": True, "installed": VIBE_AVAILABLE, "version": "0.1.12",
                "engines": [k for k, v in VIBE_ENGINES.items() if v],
                "loaders": [k for k, v in VIBE_LOADERS.items() if v],
                "agents": len(vibe.get_agent_info().get('agents', [])),
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/vibe/backtest', methods=['POST'])
    def vibe_backtest():
        """Vibe-Trading 回测"""
        try:
            data = request.get_json() or {}
            symbol = data.get('symbol', '600519')
            days = int(data.get('days', 120))
            from core.vibe_integration import get_vibe_integration
            vibe = get_vibe_integration()
            result = vibe.run_backtest(symbol=symbol, days=days)
            return jsonify({"success": True, **result})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    # Vibe-Trading FastAPI 子进程管理
    @app.route('/api/vibe/web_ui/start', methods=['POST'])
    def vibe_web_ui_start():
        """启动 Vibe-Trading FastAPI API Server"""
        try:
            result = start_vibe_api()
            return jsonify(result) if result.get('success') else (jsonify(result), 500)
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/vibe/web_ui/status')
    def vibe_web_ui_status():
        """Vibe-Trading FastAPI 状态查询"""
        return jsonify(get_vibe_api_status())

    @app.route('/api/vibe/web_ui/stop', methods=['POST'])
    def vibe_web_ui_stop():
        """停止 Vibe-Trading FastAPI"""
        try:
            result = stop_vibe_api()
            return jsonify(result)
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    # Vibe-Trading MCP Server 管理
    @app.route('/api/vibe/mcp/start', methods=['POST'])
    def vibe_mcp_start():
        """启动 Vibe-Trading MCP Server"""
        try:
            result = start_vibe_mcp()
            return jsonify(result) if result.get('success') else (jsonify(result), 500)
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/vibe/mcp/status')
    def vibe_mcp_status():
        """Vibe-Trading MCP Server 状态查询"""
        return jsonify(get_vibe_mcp_status())

    @app.route('/api/vibe/mcp/stop', methods=['POST'])
    def vibe_mcp_stop():
        """停止 Vibe-Trading MCP Server"""
        try:
            result = stop_vibe_mcp()
            return jsonify(result)
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
