# -*- coding: utf-8 -*-
"""Cline Agent API 路由"""
import os
from flask import request, jsonify, session


def register_routes(app):
    llm_manager = app.config.get('llm_manager')
    robot_core = app.config.get('robot_core')
    LLM_CONFIG = {'auto_switch': False, 'quant_model': '', 'code_model': '', 'current_model': 'gpt-4o', 'current_provider': 'unknown'}

    def _sync_llm_config_from_manager():
        """同步 LLM 状态"""
        try:
            from ui.routes.llm_routes import _sync_llm_config_from_manager as _sync
            _sync()
        except Exception:
            pass

    @app.route('/api/cline/chat', methods=['POST'])
    def api_cline_chat():
        """Cline智能体聊天接口"""
        try:
            data = request.get_json()
            user_message = data.get('message', '')
            if not user_message:
                return jsonify({"success": False, "error": "消息内容不能为空"}), 400
            _sync_llm_config_from_manager()
            used_provider = LLM_CONFIG.get('current_provider', 'unknown')
            used_model = LLM_CONFIG['current_model']
            response_text = None
            if llm_manager and llm_manager.active_provider is not None:
                prov_name = getattr(llm_manager.active_provider, 'name', '')
                if prov_name == 'cline':
                    try:
                        messages = [{"role": "user", "content": user_message}]
                        response_text = llm_manager.active_provider.chat(messages, stream=False)
                    except Exception as ce:
                        print(f"[Cline] provider调用失败，回退到robot_core: {ce}")
                        response_text = None
            if response_text is None:
                response_text = robot_core.process_command(user_message)
            return jsonify({"success": True, "response": response_text, "model": used_model, "provider": used_provider})
        except Exception as e:
            import traceback
            return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500

    @app.route('/api/cline/task/submit', methods=['POST'])
    def cline_task_submit():
        """提交Cline任务"""
        try:
            data = request.get_json()
            message = data.get('message', '').strip()
            priority = data.get('priority', 'CLINE_DEV')
            environment = data.get('environment', 'simulation')
            symbol = data.get('symbol', '')
            user = data.get('user', session.get('username', 'anonymous'))
            if not message:
                return jsonify({"success": False, "error": "任务描述不能为空"}), 400
            from core.agent_dispatcher import get_task_manager, TaskPriority, TaskEnvironment
            tm = get_task_manager()
            try:
                pri = TaskPriority[priority.upper()]
            except KeyError:
                pri = TaskPriority.CLINE_DEV
            try:
                env = TaskEnvironment(environment)
            except ValueError:
                env = TaskEnvironment.SIMULATION
            result = tm.submit_task(message=message, priority=pri, environment=env, user=user, symbol=symbol or None)
            return jsonify(result)
        except Exception as e:
            import traceback
            return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500

    @app.route('/api/cline/task/status', methods=['GET'])
    def cline_task_status():
        """获取任务状态"""
        try:
            task_id = request.args.get('task_id', '')
            from core.agent_dispatcher import get_task_manager
            tm = get_task_manager()
            result = tm.get_task_status(task_id if task_id else None)
            return jsonify({"success": True, "data": result})
        except Exception as e:
            import traceback
            return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500

    @app.route('/api/cline/task/cancel', methods=['POST'])
    def cline_task_cancel():
        """取消任务"""
        try:
            data = request.get_json()
            task_id = data.get('task_id', '')
            if not task_id:
                return jsonify({"success": False, "error": "需要task_id"}), 400
            from core.agent_dispatcher import get_task_manager
            tm = get_task_manager()
            result = tm.cancel_task(task_id)
            return jsonify(result)
        except Exception as e:
            import traceback
            return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500

    @app.route('/api/cline/audit', methods=['GET'])
    def cline_audit_log():
        """获取操作审计日志"""
        try:
            limit = request.args.get('limit', 50, type=int)
            from core.agent_dispatcher import get_task_manager
            tm = get_task_manager()
            logs = tm.get_audit_log(limit)
            return jsonify({"success": True, "data": logs, "count": len(logs)})
        except Exception as e:
            import traceback
            return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500

    @app.route('/api/cline/environment', methods=['GET', 'POST'])
    def cline_environment():
        """获取/切换Cline运行环境"""
        if request.method == 'GET':
            env = getattr(request, 'cline_environment', 'simulation')
            return jsonify({
                "success": True, "environment": env,
                "is_live": env == 'live',
                "restrictions": [
                    "禁止批量下单", "禁止全量重优化", "禁止全市场回测",
                    "禁止批量修改策略", "代码变更需人工确认+回测校验"
                ] if env == 'live' else []
            })
        elif request.method == 'POST':
            data = request.get_json()
            new_env = data.get('environment', 'simulation')
            if new_env not in ('simulation', 'live'):
                return jsonify({"success": False, "error": "环境必须是simulation或live"}), 400
            request.cline_environment = new_env
            from core.agent_dispatcher import get_task_manager
            tm = get_task_manager()
            tm._log_audit("ENV_SWITCH", None, {"environment": new_env})
            return jsonify({"success": True, "environment": new_env, "message": f"已切换到{'实盘' if new_env == 'live' else '模拟'}环境"})

    @app.route('/api/cline/context', methods=['POST'])
    def cline_chart_context():
        """接收技术分析页面的图表上下文"""
        try:
            data = request.get_json()
            symbol = data.get('symbol', '')
            period = data.get('period', 'daily')
            timeframe = data.get('timeframe', '')
            indicators = data.get('indicators', {})
            action = data.get('action', 'analyze')
            if not symbol:
                return jsonify({"success": False, "error": "需要股票代码"}), 400
            if action == 'analyze':
                context_msg = f"基于当前图表分析{symbol}（{period}周期）"
                if indicators:
                    ind_desc = ', '.join([f"{k}={v}" for k, v in indicators.items() if v])
                    context_msg += f"，当前指标: {ind_desc}"
                context_msg += "，请给出综合研判"
            elif action == 'optimize':
                strategy = data.get('strategy', '')
                context_msg = f"基于{symbol}的{period}K线数据，优化{strategy}策略，降低最大回撤"
            elif action == 'develop':
                task = data.get('task', '')
                context_msg = f"为{symbol}编写{task}"
            else:
                context_msg = f"分析{symbol}"
            return jsonify({"success": True, "symbol": symbol, "context_message": context_msg, "period": period})
        except Exception as e:
            import traceback
            return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500

    @app.route('/api/cline/files', methods=['GET'])
    def cline_file_list():
        """获取项目文件列表"""
        try:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            strategy_dir = os.path.join(project_root, 'strategies') if os.path.exists(
                os.path.join(project_root, 'strategies')) else project_root
            files = []
            for root, dirs, filenames in os.walk(strategy_dir):
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('__pycache__', 'node_modules', '.git')]
                for f in filenames:
                    if f.endswith('.py') and not f.startswith('test_') and 'backup' not in f.lower():
                        full_path = os.path.join(root, f)
                        rel_path = os.path.relpath(full_path, project_root)
                        files.append({"name": f, "path": rel_path, "size": os.path.getsize(full_path)})
            core_dir = os.path.join(project_root, 'core')
            if os.path.exists(core_dir):
                for f in os.listdir(core_dir):
                    if f.endswith('.py') and not f.startswith('_'):
                        full_path = os.path.join(core_dir, f)
                        rel_path = os.path.relpath(full_path, project_root)
                        files.append({"name": f"[core] {f}", "path": rel_path, "size": os.path.getsize(full_path)})
            return jsonify({"success": True, "files": files[:50], "count": len(files)})
        except Exception as e:
            import traceback
            return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500

    @app.route('/api/cline/file', methods=['GET', 'POST'])
    def cline_file_io():
        """代码文件读写"""
        try:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if request.method == 'GET':
                file_path = request.args.get('path', '')
                if not file_path:
                    return jsonify({"success": False, "error": "需要文件路径"}), 400
                full_path = os.path.normpath(os.path.join(project_root, file_path))
                if not full_path.startswith(project_root):
                    return jsonify({"success": False, "error": "非法的文件路径"}), 403
                if not os.path.exists(full_path):
                    return jsonify({"success": False, "error": "文件不存在"}), 404
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                lines = content.count('\n') + 1
                return jsonify({"success": True, "path": file_path, "content": content, "lines": lines, "size": len(content.encode('utf-8'))})
            elif request.method == 'POST':
                data = request.get_json()
                file_path = data.get('path', '')
                content = data.get('content', '')
                if not file_path:
                    return jsonify({"success": False, "error": "需要文件路径"}), 400
                full_path = os.path.normpath(os.path.join(project_root, file_path))
                if not full_path.startswith(project_root):
                    return jsonify({"success": False, "error": "非法的文件路径"}), 403
                if os.path.exists(full_path):
                    backup_path = full_path + '.bak'
                    os.replace(full_path, backup_path)
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                from core.agent_dispatcher import get_task_manager
                tm = get_task_manager()
                tm._log_audit("FILE_SAVE", None, {"path": file_path, "size": len(content)})
                return jsonify({"success": True, "message": "文件已保存", "path": file_path})
        except Exception as e:
            import traceback
            return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500
