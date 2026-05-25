#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动修复引擎 - Aurora系统自修复组件
检测到异常后自动执行修复操作
"""

import logging
import os
import sys
import time
import json
import importlib
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class HealAction(Enum):
    RESTART_MODULE = "restart_module"
    RELOAD_CONFIG = "reload_config"
    CLEAR_CACHE = "clear_cache"
    RESET_CONNECTION = "reset_connection"
    FALLBACK_DATASOURCE = "fallback_datasource"
    ROLLBACK_PARAMS = "rollback_params"


class AutoHealer:
    """系统自动修复引擎"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.heal_history: List[Dict[str, Any]] = []
        self.max_retries = 3
        self.cooldown_seconds = 60  # 同一模块修复冷却时间
        self._last_heal_time: Dict[str, float] = {}
        self._heal_registry: Dict[str, Callable] = {
            "restart_module": self._restart_module,
            "reload_config": self._reload_config,
            "clear_cache": self._clear_cache,
            "reset_connection": self._reset_db_connection,
            "fallback_datasource": self._fallback_datasource,
            "rollback_params": self._rollback_params,
        }

    def diagnose_and_heal(self, module_name: str, error_info: Dict[str, Any]) -> Dict[str, Any]:
        """诊断并自动修复指定模块"""
        # 冷却检查
        now = time.time()
        if module_name in self._last_heal_time:
            if now - self._last_heal_time[module_name] < self.cooldown_seconds:
                return {
                    "status": "cooldown",
                    "message": f"模块 {module_name} 处于修复冷却期",
                }

        # 确定修复策略
        error_type = error_info.get("type", "unknown")
        actions = self._determine_actions(module_name, error_type)

        results = []
        for action in actions:
            try:
                result = self._execute_heal(action, module_name, error_info)
                results.append(result)
                self.heal_history.append({
                    "module": module_name,
                    "action": action.value,
                    "result": result,
                    "timestamp": datetime.now().isoformat(),
                })
                if result["success"]:
                    break  # 修复成功，停止尝试
            except Exception as e:
                logger.error(f"修复 {module_name} 失败: {e}")
                results.append({"action": action.value, "success": False, "error": str(e)})

        self._last_heal_time[module_name] = now

        return {
            "module": module_name,
            "status": "healed" if any(r["success"] for r in results) else "failed",
            "actions_taken": results,
            "timestamp": datetime.now().isoformat(),
        }

    def _determine_actions(self, module_name: str, error_type: str) -> List[HealAction]:
        """根据错误类型确定修复操作序列"""
        action_map = {
            "import_error": [HealAction.RESTART_MODULE, HealAction.RELOAD_CONFIG],
            "connection_error": [HealAction.RESET_CONNECTION, HealAction.FALLBACK_DATASOURCE],
            "config_error": [HealAction.RELOAD_CONFIG, HealAction.ROLLBACK_PARAMS],
            "memory_error": [HealAction.CLEAR_CACHE, HealAction.RESTART_MODULE],
            "timeout": [HealAction.RESET_CONNECTION, HealAction.FALLBACK_DATASOURCE],
        }
        return action_map.get(error_type, [HealAction.RESTART_MODULE])

    def _execute_heal(self, action: HealAction, module_name: str, error_info: Dict) -> Dict[str, Any]:
        """执行修复操作"""
        handler = self._heal_registry.get(action.value)
        if handler:
            return handler(module_name, error_info)
        return {"action": action.value, "success": False, "error": "未知操作"}

    def _restart_module(self, module_name: str, error_info: Dict) -> Dict[str, Any]:
        """重新加载模块"""
        try:
            if module_name in sys.modules:
                importlib.reload(sys.modules[module_name])
                logger.info(f"模块 {module_name} 已重新加载")
                return {"action": "restart_module", "success": True}
        except Exception as e:
            logger.warning(f"模块 {module_name} 重载失败: {e}")
        return {"action": "restart_module", "success": False, "error": "无法重载模块"}

    def _reload_config(self, module_name: str, error_info: Dict) -> Dict[str, Any]:
        """重新加载配置"""
        try:
            config_path = self.config.get("config_path", "config/config.json")
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    self.config.update(json.load(f))
                return {"action": "reload_config", "success": True}
        except Exception as e:
            return {"action": "reload_config", "success": False, "error": str(e)}
        return {"action": "reload_config", "success": False, "error": "配置文件不存在"}

    def _clear_cache(self, module_name: str, error_info: Dict) -> Dict[str, Any]:
        """清理缓存"""
        cache_dirs = ["__pycache__", "data_cache", ".cache"]
        for d in cache_dirs:
            cache_path = os.path.join(os.path.dirname(__file__), d)
            if os.path.exists(cache_path):
                for root, dirs, files in os.walk(cache_path, topdown=False):
                    for f in files:
                        if f.endswith(".pyc") or f.endswith(".pyo"):
                            os.remove(os.path.join(root, f))
                logger.info(f"缓存清理完成: {d}")
        return {"action": "clear_cache", "success": True}

    def _reset_db_connection(self, module_name: str, error_info: Dict) -> Dict[str, Any]:
        """重置数据库连接"""
        try:
            from utils.database_manager import DatabaseManager
            db = DatabaseManager()
            db.reset_connection()
            return {"action": "reset_connection", "success": True}
        except Exception as e:
            return {"action": "reset_connection", "success": False, "error": str(e)}

    def _fallback_datasource(self, module_name: str, error_info: Dict) -> Dict[str, Any]:
        """切换到备用数据源"""
        try:
            from utils.data_source_manager import DataSourceManager
            ds = DataSourceManager()
            ds.switch_to_fallback()
            return {"action": "fallback_datasource", "success": True}
        except Exception as e:
            return {"action": "fallback_datasource", "success": False, "error": str(e)}

    def _rollback_params(self, module_name: str, error_info: Dict) -> Dict[str, Any]:
        """回滚参数到上一个已知良好的状态"""
        # TODO: 实现参数版本回滚
        return {"action": "rollback_params", "success": False, "error": "参数回滚尚未实现"}

    def get_heal_report(self) -> Dict[str, Any]:
        """获取修复报告"""
        return {
            "total_heals": len(self.heal_history),
            "recent_heals": self.heal_history[-50:],
            "generated_at": datetime.now().isoformat(),
        }


__all__ = ["AutoHealer", "HealAction"]