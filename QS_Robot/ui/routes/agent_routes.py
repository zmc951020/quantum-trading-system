# -*- coding: utf-8 -*-
"""Agent/Robot API 路由"""
from flask import request, jsonify
from datetime import datetime
import logging
logger = logging.getLogger(__name__)


def register_routes(app):
    # Import agent core functions from the core module
    from ui.routes.agent_core import agent_execute

    @app.route('/api/robot/chat', methods=['POST'])
    def robot_chat():
        """机器人对话接口 - 使用智能体系统（意图识别+工具调用+思考呈现）"""
        try:
            data = request.get_json()
            message = data.get('message', '').strip()
            if not message:
                return jsonify({"success": False, "error": "消息不能为空"}), 400
            agent_result = agent_execute(message)
            return jsonify(agent_result)
        except Exception as e:
            import traceback
            return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500

    @app.route('/api/agent/execute', methods=['POST'])
    def agent_execute_api():
        """智能体执行接口"""
        try:
            data = request.get_json()
            message = data.get('message', '').strip()
            if not message:
                return jsonify({"success": False, "error": "消息不能为空"}), 400
            agent_result = agent_execute(message)
            return jsonify(agent_result)
        except Exception as e:
            import traceback
            return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500

    @app.route('/api/robot/status', methods=['GET'])
    def robot_status():
        """获取系统状态（显示在浮标中）"""
        try:
            return jsonify({
                "success": True,
                "systems": {
                    "aurora": {"status": "online", "name": "Aurora 主系统", "message": "运行正常"},
                    "vibe": {"status": "online", "name": "港大智能体", "message": "29个智能体就绪"},
                    "optimizer": {"status": "online", "name": "韬定律优化器", "message": "等待任务"},
                    "stock_pool": {"status": "online", "name": "股票池系统", "message": "5层池可用"},
                    "technical": {"status": "online", "name": "技术分析", "message": "数据实时"}
                },
                "tasks_running": 0, "tasks_completed_today": 12,
                "market_status": "open",
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/robot/quick_command', methods=['POST'])
    def robot_quick_command():
        """快捷命令执行"""
        try:
            data = request.get_json()
            command = data.get('command', '')
            symbol = data.get('symbol', '')
            command_map = {
                'tau_optimize': '优化策略参数',
                'vibe_analyze': f'分析股票 {symbol}' if symbol else '分析600519',
                'stock_pool': '筛选股票池',
                'backtest': '执行策略回测',
                'risk_check': '检查系统风险',
                'full_flow': f'完整流程分析 {symbol}' if symbol else '完整流程600519',
                'system_status': '检查系统状态',
            }
            command_lower = command.lower()
            if command in command_map:
                message = command_map[command]
            elif command_lower == 'help':
                message = '有什么功能可以使用'
            else:
                message = command
            agent_result = agent_execute(message)
            return jsonify(agent_result)
        except Exception as e:
            import traceback
            return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500

    @app.route('/api/robot/notifications', methods=['GET'])
    def robot_notifications():
        """获取最近通知"""
        try:
            notifications = [
                {"id": 1, "type": "success", "title": "策略优化完成", "content": "策略双均线-600519优化完成，夏普比率提升至1.87", "time": "5分钟前"},
                {"id": 2, "type": "info", "title": "股票池更新", "content": "候选池新增3只股票，测试池移除2只", "time": "22分钟前"},
                {"id": 3, "type": "warning", "title": "市场波动提醒", "content": "上证50波动率上升，建议降低仓位", "time": "1小时前"},
                {"id": 4, "type": "info", "title": "港大智能体分析完成", "content": "600519茅台 - 综合评分87/100 - 建议进入测试池", "time": "2小时前"}
            ]
            return jsonify({"success": True, "notifications": notifications})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/agent/dispatch', methods=['POST'])
    def agent_dispatch():
        """Agent自由调度接口"""
        import time as _time
        t0 = _time.time()
        try:
            data = request.get_json()
            message = data.get('message', '').strip()
            logger.info(f"[API] /api/agent/dispatch 收到: '{message[:80]}...'")
            if not message:
                return jsonify({"success": False, "error": "消息不能为空"}), 400
            from core.agent_dispatcher import dispatch
            result = dispatch(message)
            elapsed = round((_time.time() - t0) * 1000, 0)
            logger.info(f"[API] /api/agent/dispatch 完成({elapsed}ms): success={result.get('success')}, mode={result.get('mode', 'N/A')}")
            return jsonify(result)
        except Exception as e:
            import traceback
            elapsed = round((_time.time() - t0) * 1000, 0)
            logger.error(f"[API] /api/agent/dispatch 异常({elapsed}ms): {e}\n{traceback.format_exc()}")
            return jsonify({"success": False, "error": str(e), "elapsed_ms": elapsed}), 500

    @app.route('/api/agent/registry', methods=['GET'])
    def agent_registry_api():
        """获取Agent+技能注册表"""
        try:
            from core.agent_dispatcher import get_registry
            registry = get_registry()
            return jsonify({"success": True, "registry": registry})
        except Exception as e:
            import traceback
            return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500

    @app.route('/api/agent/search', methods=['GET'])
    def agent_search():
        """搜索Agent/技能"""
        try:
            q = request.args.get('q', '').strip()
            search_type = request.args.get('type', 'all')
            if not q:
                return jsonify({"success": False, "error": "搜索关键词不能为空"}), 400
            from core.agent_registry import get_agents_by_keyword, get_skills_by_keyword
            result = {}
            if search_type in ('agent', 'all'):
                agents = get_agents_by_keyword(q)
                result['agents'] = [{"id": a.agent_id, "name": a.name, "group": a.group,
                    "description": a.description, "tags": a.tags} for a in agents]
            if search_type in ('skill', 'all'):
                skills = get_skills_by_keyword(q)
                result['skills'] = [{"id": s.skill_id, "name": s.name, "category": s.category,
                    "description": s.description, "tags": s.tags} for s in skills]
            return jsonify({"success": True, "query": q, "type": search_type, "result": result})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/agent/orchestrate', methods=['POST'])
    def agent_orchestrate():
        """Agent智能编排接口"""
        import time as _time
        t0 = _time.time()
        try:
            data = request.get_json()
            message = data.get('message', '').strip()
            logger.info(f"[API] /api/agent/orchestrate 收到: '{message[:80]}...'")
            if not message:
                return jsonify({"success": False, "error": "消息不能为空"}), 400
            from core.agent_orchestrator import orchestrate
            result = orchestrate(message)
            elapsed = round((_time.time() - t0) * 1000, 0)
            logger.info(f"[API] /api/agent/orchestrate 完成({elapsed}ms): success={result.get('success')}, degraded={result.get('degraded', False)}")
            return jsonify(result)
        except Exception as e:
            import traceback
            elapsed = round((_time.time() - t0) * 1000, 0)
            logger.error(f"[API] /api/agent/orchestrate 异常({elapsed}ms): {e}\n{traceback.format_exc()}")
            return jsonify({"success": False, "error": str(e), "elapsed_ms": elapsed}), 500

    @app.route('/api/integration/hybrid_power', methods=['POST'])
    def integration_hybrid_power():
        """流程10: 强强联合流程（韬定律优化+港大分析+股票池+风控）"""
        try:
            data = request.get_json() or {}
            strategy_name = data.get('strategy', '')
            if not strategy_name:
                return jsonify({"success": False, "error": "需要策略名称参数"}), 400
            from core.integration_bus import get_integration_bus
            bus = get_integration_bus()
            result = bus.auto_hybrid_power_flow(strategy_name)
            return jsonify(result)
        except Exception as e:
            import traceback
            return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500
