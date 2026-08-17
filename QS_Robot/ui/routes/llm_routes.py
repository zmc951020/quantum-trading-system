# -*- coding: utf-8 -*-
"""LLM 模型切换 API 路由"""
import time as _time
from flask import request, jsonify
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as _FutTimeout


def register_routes(app):
    llm_manager = app.config.get('llm_manager')
    LLM_CONFIG = {'auto_switch': False, 'quant_model': '', 'code_model': '', 'current_model': 'gpt-4o'}
    _LLM_CACHE = {"ts": 0, "models": [], "providers_status": {}, "current_model": "", "current_provider": "none"}
    _LLM_CACHE_TTL = 30

    def _sync_llm_config_from_manager():
        """从 llm_manager.active_provider 同步当前模型到 LLM_CONFIG"""
        try:
            ap = llm_manager.active_provider if llm_manager else None
            if ap is not None:
                model = getattr(ap, 'model', None) or LLM_CONFIG['current_model']
                LLM_CONFIG['current_model'] = model
                LLM_CONFIG['current_provider'] = getattr(ap, 'name', 'unknown')
            else:
                LLM_CONFIG['current_provider'] = 'none'
            providers = llm_manager.providers.items() if llm_manager else []
            def _probe(item):
                name, p = item
                try:
                    avail = bool(p.is_available())
                except Exception:
                    avail = False
                return name, {'available': avail, 'model': getattr(p, 'model', ''), 'name': getattr(p, 'name', name)}
            providers_status = {}
            if providers:
                try:
                    with ThreadPoolExecutor(max_workers=4) as ex:
                        futs = [ex.submit(_probe, item) for item in providers]
                        for fut in as_completed(futs, timeout=2):
                            try:
                                n, s = fut.result(timeout=1)
                                providers_status[n] = s
                            except Exception:
                                pass
                except _FutTimeout:
                    pass
                for name, p in providers:
                    if name not in providers_status:
                        providers_status[name] = {'available': False, 'model': getattr(p, 'model', ''), 'name': name}
            LLM_CONFIG['providers_status'] = providers_status
        except Exception as e:
            import logging as _lg
            _lg.getLogger(__name__).warning(f"[LLM] 同步llm_manager状态失败: {e}")

    def _get_model_description(model_name: str) -> str:
        descriptions = {
            "gpt-4o": "GPT-4o 高性能模型，适合复杂推理和量化分析",
            "gpt-4": "GPT-4 旗舰模型，最强推理能力",
            "gpt-3.5-turbo": "GPT-3.5 Turbo，性价比之选",
            "claude-3-opus": "Claude 3 Opus，超长上下文",
            "claude-3-sonnet": "Claude 3 Sonnet，平衡性能与成本",
            "gemini-1.5-pro": "Gemini 1.5 Pro，多模态能力强",
            "deepseek-chat": "深度求索开源模型，量化专用",
            "qwen-max": "通义千问 Max，中文优化",
            "qwen2.5-coder": "通义千问代码模型",
            "llama3": "Llama 3 开源模型",
            "mistral": "Mistral 开源模型",
        }
        for key, desc in descriptions.items():
            if key in model_name.lower():
                return desc
        return f"EchoBird代理模型: {model_name}"

    @app.route('/api/llm/models', methods=['GET'])
    def api_llm_models():
        """获取可用模型列表"""
        try:
            now = _time.time()
            if _LLM_CACHE["models"] and (now - _LLM_CACHE["ts"]) < _LLM_CACHE_TTL:
                return jsonify({
                    "success": True, "models": _LLM_CACHE["models"],
                    "current_model": _LLM_CACHE["current_model"],
                    "current_provider": _LLM_CACHE["current_provider"],
                    "providers_status": _LLM_CACHE["providers_status"],
                    "message": "模型列表加载成功(缓存)"
                })
            _sync_llm_config_from_manager()
            all_models = []
            current_model = LLM_CONFIG['current_model']
            if llm_manager and llm_manager.providers:
                def _probe_models(item):
                    prov_name, prov = item
                    models = []
                    try:
                        available_models = []
                        if hasattr(prov, 'get_available_models'):
                            available_models = prov.get_available_models() or []
                        if not available_models:
                            m = getattr(prov, 'model', '')
                            if m:
                                available_models = [m]
                        for m in available_models:
                            models.append({
                                "name": m, "provider": getattr(prov, 'name', prov_name).capitalize(),
                                "description": _get_model_description(m),
                                "context": "动态", "performance": "动态",
                                "price": "动态" if prov_name != 'ollama' else "免费",
                                "is_active": (m == current_model) and (prov == llm_manager.active_provider)
                            })
                    except Exception:
                        pass
                    return models
                try:
                    with ThreadPoolExecutor(max_workers=4) as ex:
                        futs = [ex.submit(_probe_models, item) for item in llm_manager.providers.items()]
                        for fut in as_completed(futs, timeout=2):
                            try:
                                all_models.extend(fut.result(timeout=1))
                            except Exception:
                                pass
                except _FutTimeout:
                    pass
            if not all_models:
                default_list = [
                    ("gpt-4o", "GPT-4o 高性能模型，适合复杂推理和量化分析", "128K", "高", "中"),
                    ("gpt-4", "GPT-4 旗舰模型，最强推理能力", "8K", "极高", "高"),
                    ("gpt-3.5-turbo", "GPT-3.5 Turbo，性价比之选", "16K", "中", "低"),
                    ("claude-3-5-sonnet", "Claude 3.5 Sonnet，平衡性能与成本", "200K", "高", "中"),
                    ("qwen2.5-coder", "通义千问代码模型，本地Ollama", "32K", "中", "免费"),
                    ("deepseek-chat", "深度求索开源模型，量化专用", "64K", "中", "免费"),
                ]
                for name, desc, ctx, perf, price in default_list:
                    all_models.append({"name": name, "provider": "EchoBird", "description": desc,
                        "context": ctx, "performance": perf, "price": price,
                        "is_active": name == current_model})
            return jsonify({
                "success": True, "models": all_models,
                "current_model": LLM_CONFIG['current_model'],
                "current_provider": LLM_CONFIG.get('current_provider', 'unknown'),
                "providers_status": LLM_CONFIG.get('providers_status', {}),
                "message": "模型列表加载成功"
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/llm/switch', methods=['POST'])
    def api_llm_switch():
        """切换LLM模型"""
        try:
            data = request.get_json()
            model_name = data.get('model', '')
            if not model_name:
                return jsonify({"success": False, "error": "模型名称不能为空"}), 400
            if not llm_manager.set_active_provider('echobird'):
                if llm_manager.active_provider is None:
                    return jsonify({"success": False, "error": "没有可用的LLM提供者，请检查EchoBird服务是否启动"}), 500
            success = llm_manager.set_model(model_name)
            if success:
                LLM_CONFIG['current_model'] = model_name
                return jsonify({"success": True, "message": f"已成功切换到模型: {model_name}",
                    "current_model": model_name,
                    "provider": llm_manager.active_provider.name if llm_manager.active_provider else "unknown"})
            else:
                LLM_CONFIG['current_model'] = model_name
                return jsonify({"success": True, "message": f"已设置模型: {model_name}（请确保EchoBird服务支持此模型）",
                    "current_model": model_name, "warning": "模型可能不在EchoBird服务列表中"})
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/llm/config', methods=['GET', 'POST'])
    def api_llm_config():
        """获取或保存LLM配置"""
        try:
            if request.method == 'GET':
                _sync_llm_config_from_manager()
                return jsonify({
                    "success": True, "auto_switch": LLM_CONFIG['auto_switch'],
                    "quant_model": LLM_CONFIG['quant_model'], "code_model": LLM_CONFIG['code_model'],
                    "current_model": LLM_CONFIG['current_model'],
                    "current_provider": LLM_CONFIG.get('current_provider', 'unknown'),
                    "providers_status": LLM_CONFIG.get('providers_status', {})
                })
            else:
                data = request.get_json()
                LLM_CONFIG['auto_switch'] = data.get('auto_switch', False)
                LLM_CONFIG['quant_model'] = data.get('quant_model', '')
                LLM_CONFIG['code_model'] = data.get('code_model', '')
                target_model = LLM_CONFIG.get('quant_model') or LLM_CONFIG.get('code_model')
                if target_model and llm_manager:
                    try:
                        for prov_name, prov in llm_manager.providers.items():
                            if getattr(prov, 'model', None) == target_model:
                                llm_manager.set_active_provider(prov_name)
                                break
                        llm_manager.set_model(target_model)
                    except Exception:
                        pass
                return jsonify({"success": True, "message": "配置保存成功", "config": LLM_CONFIG})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
