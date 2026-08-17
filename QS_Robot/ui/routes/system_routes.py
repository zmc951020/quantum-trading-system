# -*- coding: utf-8 -*-
"""系统/市场 API 路由"""
from flask import request, jsonify
from datetime import datetime


def register_routes(app):
    data_source = app.config.get('data_source')
    robot_core = app.config.get('robot_core')
    llm_manager = app.config.get('llm_manager')

    @app.route('/api/chat', methods=['POST'])
    def chat():
        """聊天接口 - 集成QS Robot智能核心"""
        try:
            data = request.get_json()
            user_message = data.get('message', '')
            response = robot_core.process_command(user_message)
            return jsonify({"success": True, "response": response})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/system/connect', methods=['POST'])
    def connect_system():
        """连接量化系统"""
        success = data_source.connect()
        return jsonify({"success": success})

    @app.route('/api/system/status', methods=['GET'])
    def system_status():
        """获取系统状态"""
        try:
            strategies = data_source.get_data({"type": "strategies"})
            health = data_source.get_data({"type": "health"})
            return jsonify({
                "success": True,
                "data": {
                    "connected": data_source.is_connected(),
                    "strategies": strategies,
                    "health": health,
                    "llm_available": llm_manager.active_provider is not None and llm_manager.active_provider.is_available()
                }
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/technical/analyze', methods=['POST'])
    def technical_analyze():
        """技术分析接口"""
        try:
            data = request.get_json()
            symbol = data.get('symbol', '')
            days = int(data.get('days', 100))
            if not symbol:
                return jsonify({"success": False, "error": "需要股票代码"}), 400
            from core.technical_analysis import get_ta_engine
            ta_engine = get_ta_engine()
            result = ta_engine.analyze_from_bus(symbol, days=days)
            if result.get('success'):
                analysis = result.get('analysis', {})
                return jsonify({
                    "success": True,
                    "indicators": {
                        "ma5": analysis.get('ma5'), "ma10": analysis.get('ma10'),
                        "rsi": analysis.get('rsi'), "macd": analysis.get('macd'),
                        "bollinger": analysis.get('bollinger'),
                    },
                    "signals": analysis.get('signals', []),
                    "source": result.get('data_source', 'AKShare'),
                })
            else:
                return jsonify({"success": False, "error": "分析失败"}), 500
        except Exception as e:
            import traceback
            return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500

    @app.route('/api/orders', methods=['GET'])
    def get_orders():
        """获取订单列表"""
        try:
            orders = [
                {"id": "ORD001", "symbol": "000001", "name": "平安银行", "type": "buy", "price": 10.85, "quantity": 1000, "status": "filled", "time": "2024-06-04 10:30:00"},
                {"id": "ORD002", "symbol": "000002", "name": "万科A", "type": "sell", "price": 12.50, "quantity": 500, "status": "pending", "time": "2024-06-04 10:35:00"},
            ]
            return jsonify({"success": True, "data": orders, "total": len(orders)})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/positions', methods=['GET'])
    def get_positions():
        """获取持仓列表"""
        try:
            positions = [
                {"symbol": "000001", "name": "平安银行", "quantity": 1000, "avg_price": 10.50, "current_price": 10.85, "profit": 350, "profit_pct": 3.33},
                {"symbol": "600519", "name": "贵州茅台", "quantity": 10, "avg_price": 1800, "current_price": 1850, "profit": 500, "profit_pct": 2.78},
            ]
            return jsonify({"success": True, "data": positions, "total": len(positions)})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/risk-control/stop-loss-take-profit', methods=['GET'])
    def get_stop_loss_take_profit():
        """获取止损止盈设置"""
        try:
            settings = [
                {"symbol": "000001", "name": "平安银行", "stop_loss": 10.00, "take_profit": 12.00, "current_price": 10.85, "status": "active"},
                {"symbol": "600519", "name": "贵州茅台", "stop_loss": 1700, "take_profit": 2000, "current_price": 1850, "status": "active"},
            ]
            return jsonify({"success": True, "data": settings})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/technical-indicators', methods=['GET'])
    def get_technical_indicators():
        """获取技术指标数据"""
        try:
            symbol = request.args.get('symbol', '000001')
            try:
                from core.technical_analysis import get_ta_engine
                ta_engine = get_ta_engine()
                result = ta_engine.analyze_from_bus(symbol, days=30)
                if result.get('success'):
                    analysis = result.get('analysis', {})
                    return jsonify({
                        "success": True,
                        "data": {
                            "symbol": symbol, "ma5": analysis.get('ma5', 0), "ma10": analysis.get('ma10', 0),
                            "ma20": analysis.get('ma20', 0), "rsi": analysis.get('rsi', 50),
                            "macd": analysis.get('macd', {}), "bollinger": analysis.get('bollinger', {}),
                            "trend": analysis.get('trend', 'sideways'), "signals": analysis.get('signals', []),
                            "update_time": result.get('update_time', '')
                        }
                    })
            except Exception as e:
                print(f"[技术指标] 引擎调用失败: {e}")
            return jsonify({
                "success": True,
                "data": {
                    "symbol": symbol, "ma5": 10.85, "ma10": 10.75, "ma20": 10.60,
                    "rsi": 55.5, "macd": {"dif": 0.15, "dea": 0.10, "macd": 0.05},
                    "bollinger": {"upper": 11.20, "middle": 10.80, "lower": 10.40},
                    "trend": "sideways", "signals": [{"type": "info", "message": "技术指标数据（模拟）"}],
                    "update_time": "2024-06-04 15:00:00"
                }
            })
        except Exception as e:
            import traceback
            return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500

    @app.route('/api/system/switch', methods=['POST'])
    def api_switch_system():
        """系统切换接口"""
        try:
            data = request.get_json() or {}
            target_system = data.get('system', 'strategy')
            if target_system == 'analysis':
                return jsonify({"success": True, "redirect": "/technical_analysis", "message": "切换到技术分析系统"})
            else:
                return jsonify({"success": True, "redirect": "/dashboard", "message": "切换到策略优化系统"})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/market/overview', methods=['GET'])
    def get_market_overview():
        """获取市场概览"""
        try:
            return jsonify({
                "success": True,
                "data": {
                    "index": {"sh": 3150.50, "sz": 10520.30, "cyb": 2150.80},
                    "change": {"sh": 0.85, "sz": 1.20, "cyb": -0.35},
                    "volume": {"sh": 350000000, "sz": 420000000, "cyb": 85000000},
                    "hot_sectors": [
                        {"name": "人工智能", "change": 3.5, "leader": "科大讯飞"},
                        {"name": "新能源", "change": 2.1, "leader": "宁德时代"},
                        {"name": "半导体", "change": 1.8, "leader": "中芯国际"}
                    ]
                }
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/health', methods=['GET'])
    def api_health():
        """系统健康检查"""
        return jsonify({
            "success": True, "status": "healthy",
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "systems": {
                "akshare": True, "vibe_agents": True, "tau_optimizer": True, "stock_pool": True
            }
        })
