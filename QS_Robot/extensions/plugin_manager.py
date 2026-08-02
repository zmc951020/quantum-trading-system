#!/usr/bin/env python3
"""
插件管理器 (Plugin Manager)
============================
支持优化器、数据源、LLM提供者的热插拔加载。

插件规范：
  每个插件是一个 Python 包，包含 plugin.json 描述文件。
  插件目录位于 extensions/plugins/ 下。

插件类型: optimizer, data_source, llm_provider
"""

import os
import sys
import json
import logging
import importlib
from typing import Dict, List, Optional, Any, Type
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGINS_DIR = os.path.join(PROJECT_ROOT, 'extensions', 'plugins')


# ============================================================
# 插件基类
# ============================================================

class BasePlugin(ABC):
    """插件基类 - 所有插件必须继承此类"""
    
    name: str = ""
    type: str = ""  # optimizer | data_source | llm_provider
    version: str = "1.0.0"
    description: str = ""
    
    @abstractmethod
    def initialize(self, config: Dict = None) -> bool:
        """初始化插件"""
        ...
    
    @abstractmethod
    def shutdown(self):
        """关闭插件"""
        ...
    
    def is_available(self) -> bool:
        """检查插件是否可用"""
        return True
    
    def get_info(self) -> Dict[str, Any]:
        """获取插件信息"""
        return {
            'name': self.name,
            'type': self.type,
            'version': self.version,
            'description': self.description,
        }


# ============================================================
# 插件清单 (UI动态加载)
# ============================================================

class PluginManifest:
    """插件清单 - 描述插件元信息
    
    对应 plugin.json 文件结构，用于插件的UI展示和动态加载。
    """
    
    def __init__(self, name: str, version: str = "1.0.0",
                 plugin_type: str = "optimizer", description: str = "",
                 author: str = "", entry_point: str = "",
                 ui: Dict = None, dependencies: List[str] = None):
        self.name = name
        self.version = version
        self.plugin_type = plugin_type
        self.description = description
        self.author = author
        self.entry_point = entry_point
        self.ui = ui or {}
        self.dependencies = dependencies or []
    
    @classmethod
    def from_dict(cls, data: Dict) -> "PluginManifest":
        return cls(
            name=data.get("name", ""),
            version=data.get("version", "1.0.0"),
            plugin_type=data.get("type", "optimizer"),
            description=data.get("description", ""),
            author=data.get("author", ""),
            entry_point=data.get("entry_point", ""),
            ui=data.get("ui", {}),
            dependencies=data.get("dependencies", []),
        )
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "version": self.version,
            "type": self.plugin_type,
            "description": self.description,
            "author": self.author,
            "entry_point": self.entry_point,
            "ui": self.ui,
            "dependencies": self.dependencies,
        }
    
    def validate(self) -> List[str]:
        issues = []
        if not self.name:
            issues.append("缺少插件名称")
        if not self.entry_point:
            issues.append("缺少入口点(entry_point)")
        if self.plugin_type not in ("optimizer", "data_source", "llm_provider"):
            issues.append(f"未知插件类型: {self.plugin_type}")
        return issues


class OptimizerPlugin(BasePlugin):
    """优化器插件基类"""
    type = "optimizer"
    
    @abstractmethod
    def optimize(self, strategy_name: str, params: Dict, **kwargs) -> Dict[str, Any]:
        """执行优化"""
        ...
    
    @abstractmethod
    def get_supported_strategies(self) -> List[str]:
        """获取支持的策略类型"""
        ...


class DataSourcePlugin(BasePlugin):
    """数据源插件基类"""
    type = "data_source"
    
    @abstractmethod
    def fetch_kline(self, symbol: str, days: int, period: str = "daily") -> Dict[str, Any]:
        """获取K线数据"""
        ...
    
    @abstractmethod
    def fetch_realtime(self, symbol: str) -> Dict[str, Any]:
        """获取实时行情"""
        ...


class LLMProviderPlugin(BasePlugin):
    """LLM提供者插件基类"""
    type = "llm_provider"
    
    @abstractmethod
    def chat(self, messages: List[Dict], **kwargs) -> Dict[str, Any]:
        """对话接口"""
        ...
    
    @abstractmethod
    def list_models(self) -> List[str]:
        """列出可用模型"""
        ...


# ============================================================
# 插件管理器
# ============================================================

class PluginManager:
    """插件管理器
    
    负责扫描、加载、激活、卸载插件。
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._plugins: Dict[str, BasePlugin] = {}
        self._plugins_by_type: Dict[str, List[str]] = {
            'optimizer': [],
            'data_source': [],
            'llm_provider': [],
        }
        self._plugin_registry: Dict[str, Dict] = {}
    
    def scan_plugins(self) -> List[Dict]:
        """扫描插件目录"""
        discovered = []
        if not os.path.exists(PLUGINS_DIR):
            os.makedirs(PLUGINS_DIR, exist_ok=True)
            logger.info(f"[插件] 插件目录已创建: {PLUGINS_DIR}")
            return discovered
        
        for item in os.listdir(PLUGINS_DIR):
            plugin_dir = os.path.join(PLUGINS_DIR, item)
            if not os.path.isdir(plugin_dir):
                continue
            
            plugin_json = os.path.join(plugin_dir, 'plugin.json')
            if not os.path.exists(plugin_json):
                continue
            
            try:
                with open(plugin_json, 'r', encoding='utf-8') as f:
                    info = json.load(f)
                info['_path'] = plugin_dir
                info['_valid'] = self._validate_plugin_info(info)
                discovered.append(info)
                
                # 注册到 registry
                self._plugin_registry[info['name']] = info
            except Exception as e:
                logger.warning(f"[插件] 解析 {plugin_json} 失败: {e}")
        
        logger.info(f"[插件] 扫描到 {len(discovered)} 个插件")
        return discovered
    
    def _validate_plugin_info(self, info: Dict) -> Dict:
        """校验插件信息"""
        errors = []
        required = ['name', 'type', 'version', 'entry_point']
        for field in required:
            if field not in info:
                errors.append(f"缺少必需字段: {field}")
        
        if info.get('type') not in ('optimizer', 'data_source', 'llm_provider'):
            errors.append(f"无效的插件类型: {info.get('type')}")
        
        return {'valid': len(errors) == 0, 'errors': errors}
    
    def load_plugin(self, plugin_name: str) -> bool:
        """加载插件
        
        Args:
            plugin_name: 插件名称
            
        Returns:
            bool: 是否加载成功
        """
        info = self._plugin_registry.get(plugin_name)
        if not info:
            logger.warning(f"[插件] 未找到: {plugin_name}")
            return False
        
        if not info['_valid']['valid']:
            logger.warning(f"[插件] 校验失败: {plugin_name}, {info['_valid']['errors']}")
            return False
        
        plugin_dir = info['_path']
        entry_point = info['entry_point']
        
        try:
            # 将插件目录加入 sys.path
            if plugin_dir not in sys.path:
                sys.path.insert(0, plugin_dir)
            
            # 动态导入
            module = importlib.import_module('plugin_module')
            plugin_class = getattr(module, entry_point)
            plugin_instance = plugin_class()
            
            # 初始化
            if plugin_instance.initialize(info.get('config', {})):
                self._plugins[plugin_name] = plugin_instance
                self._plugins_by_type[info['type']].append(plugin_name)
                logger.info(f"[插件] 已加载: {plugin_name} v{info['version']} (type={info['type']})")
                return True
            else:
                logger.warning(f"[插件] 初始化失败: {plugin_name}")
                return False
                
        except Exception as e:
            logger.error(f"[插件] 加载失败: {plugin_name}, {e}")
            return False
    
    def unload_plugin(self, plugin_name: str):
        """卸载插件"""
        plugin = self._plugins.get(plugin_name)
        if plugin:
            try:
                plugin.shutdown()
            except Exception as e:
                logger.warning(f"[插件] 关闭异常: {plugin_name}, {e}")
            del self._plugins[plugin_name]
            
            for ptype, names in self._plugins_by_type.items():
                if plugin_name in names:
                    names.remove(plugin_name)
            
            logger.info(f"[插件] 已卸载: {plugin_name}")
    
    def load_all(self) -> Dict[str, Any]:
        """加载所有已扫描的插件"""
        self.scan_plugins()
        loaded = []
        failed = []
        for name in self._plugin_registry:
            if self.load_plugin(name):
                loaded.append(name)
            else:
                failed.append(name)
        return {
            'loaded': loaded,
            'failed': failed,
            'total': len(loaded) + len(failed),
        }
    
    def get_plugin(self, plugin_name: str) -> Optional[BasePlugin]:
        """获取已加载的插件"""
        return self._plugins.get(plugin_name)
    
    def get_plugins_by_type(self, plugin_type: str) -> List[BasePlugin]:
        """获取指定类型的所有插件"""
        names = self._plugins_by_type.get(plugin_type, [])
        return [self._plugins[n] for n in names if n in self._plugins]
    
    def get_optimizer_plugins(self) -> List[OptimizerPlugin]:
        return self.get_plugins_by_type('optimizer')
    
    def get_data_source_plugins(self) -> List[DataSourcePlugin]:
        return self.get_plugins_by_type('data_source')
    
    def get_llm_plugins(self) -> List[LLMProviderPlugin]:
        return self.get_plugins_by_type('llm_provider')
    
    def get_status(self) -> Dict[str, Any]:
        """获取插件状态"""
        return {
            'total_registered': len(self._plugin_registry),
            'total_loaded': len(self._plugins),
            'by_type': {
                ptype: {
                    'registered': len([n for n, info in self._plugin_registry.items() if info['type'] == ptype]),
                    'loaded': len(names),
                }
                for ptype, names in self._plugins_by_type.items()
            },
            'plugins': {
                name: plugin.get_info()
                for name, plugin in self._plugins.items()
            },
        }


# ============================================================
# 全局单例
# ============================================================

_plugin_manager: Optional[PluginManager] = None

def get_plugin_manager() -> PluginManager:
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
    return _plugin_manager