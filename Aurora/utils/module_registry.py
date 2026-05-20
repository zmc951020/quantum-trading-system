#!/usr/bin/env python3
"""
模块注册表 - 增量模块无缝集成核心
统一管理所有增量模块的初始化、生命周期和依赖关系

设计原则：
1. 零侵入集成 - 不修改现有代码，只在末尾添加初始化
2. 自动依赖管理 - 拓扑排序确保正确初始化顺序
3. 统一生命周期 - 启动、停止、状态管理统一
4. 命名空间隔离 - 避免API冲突
"""

from typing import Dict, List, Callable, Optional, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class BaseModule:
    """增量模块基类 - 所有增量模块必须继承此类"""
    
    def __init__(self, app=None):
        """
        初始化模块
        
        Args:
            app: Flask应用实例（可选，用于注册路由）
        """
        self.app = app
        self.enabled = False
        self._initialized_at = datetime.now() if app else None
    
    def register_routes(self, app):
        """
        注册路由（子类重写）
        
        Args:
            app: Flask应用实例
        """
        pass
    
    def register_hooks(self, app):
        """
        注册钩子（子类重写）
        
        Args:
            app: Flask应用实例
        """
        pass
    
    def start(self):
        """启动模块"""
        self.enabled = True
        logger.info(f"[{self.__class__.__name__}] 模块已启动")
    
    def stop(self):
        """停止模块"""
        self.enabled = False
        logger.info(f"[{self.__class__.__name__}] 模块已停止")
    
    def get_status(self) -> Dict[str, Any]:
        """获取模块状态"""
        return {
            'enabled': self.enabled,
            'class': self.__class__.__name__,
            'initialized_at': self._initialized_at.isoformat() if self._initialized_at else None
        }


class ModuleRegistry:
    """
    增量模块注册表（单例模式）
    负责所有增量模块的注册、初始化、状态管理
    """
    
    _instance: Optional['ModuleRegistry'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._modules: Dict[str, Dict[str, Any]] = {}
            cls._instance._initialized = False
            cls._instance._init_order: List[str] = []
        return cls._instance
    
    def register(self, name: str, module_class: Callable, dependencies: List[str] = None):
        """
        注册模块
        
        Args:
            name: 模块名称（唯一标识）
            module_class: 模块类（必须是BaseModule的子类）
            dependencies: 依赖模块列表（模块名称列表）
        """
        if name in self._modules:
            logger.warning(f"[ModuleRegistry] 模块 '{name}' 已存在，将覆盖")
        
        self._modules[name] = {
            'class': module_class,
            'instance': None,
            'dependencies': dependencies or [],
            'enabled': False,
            'registered_at': datetime.now()
        }
        logger.info(f"[ModuleRegistry] 注册模块: '{name}' (依赖: {dependencies or '无'})")
    
    def initialize_all(self, app=None) -> bool:
        """
        按依赖顺序初始化所有已注册模块
        
        Args:
            app: Flask应用实例
            
        Returns:
            bool: 是否全部初始化成功
        """
        if self._initialized:
            logger.info("[ModuleRegistry] 模块已初始化，跳过重复初始化")
            return True
        
        logger.info("[ModuleRegistry] ========== 开始初始化所有模块 ==========")
        
        # 拓扑排序解决依赖
        try:
            sorted_modules = self._topological_sort()
        except Exception as e:
            logger.error(f"[ModuleRegistry] 依赖排序失败: {e}")
            return False
        
        all_success = True
        for module_name in sorted_modules:
            success = self._initialize_module(module_name, app)
            if not success:
                all_success = False
        
        self._initialized = True
        self._init_order = sorted_modules
        
        # 打印初始化摘要
        logger.info("[ModuleRegistry] ========== 模块初始化完成 ==========")
        self._print_summary()
        
        return all_success
    
    def _initialize_module(self, name: str, app) -> bool:
        """初始化单个模块"""
        module_info = self._modules[name]
        module_class = module_info['class']
        
        try:
            # 检查依赖是否都已初始化
            for dep in module_info['dependencies']:
                if dep in self._modules and not self._modules[dep]['enabled']:
                    logger.warning(f"[ModuleRegistry] 模块 '{name}' 的依赖 '{dep}' 未启用，尝试强制初始化")
                    self._initialize_module(dep, app)
            
            # 创建实例
            instance = module_class(app)
            module_info['instance'] = instance
            
            # 注册路由和钩子
            if app and hasattr(instance, 'register_routes'):
                instance.register_routes(app)
            if app and hasattr(instance, 'register_hooks'):
                instance.register_hooks(app)
            
            # 启动模块
            if hasattr(instance, 'start'):
                instance.start()
            
            module_info['enabled'] = True
            logger.info(f"  [OK] '{name}' - 初始化成功")
            return True
            
        except Exception as e:
            logger.error(f"  [FAIL] '{name}' - 初始化失败: {e}")
            module_info['enabled'] = False
            return False
    
    def _topological_sort(self) -> List[str]:
        """
        拓扑排序 - 按依赖关系确定初始化顺序
        使用Kahn算法
        
        Returns:
            List[str]: 排序后的模块名称列表
        """
        # 构建入度表
        in_degree = {name: 0 for name in self._modules}
        adjacency = {name: [] for name in self._modules}
        
        for name, info in self._modules.items():
            for dep in info['dependencies']:
                if dep in self._modules:
                    adjacency[dep].append(name)
                    in_degree[name] += 1
        
        # 找出所有入度为0的节点
        queue = [name for name, degree in in_degree.items() if degree == 0]
        result = []
        
        while queue:
            node = queue.pop(0)
            result.append(node)
            
            for neighbor in adjacency[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        # 如果有循环依赖，将剩余节点追加到末尾
        if len(result) < len(self._modules):
            remaining = [name for name in self._modules if name not in result]
            logger.warning(f"[ModuleRegistry] 检测到循环依赖! 剩余模块: {remaining}")
            result.extend(remaining)
        
        return result
    
    def _print_summary(self):
        """打印模块初始化摘要"""
        lines = ["=" * 55,
                 f"{'模块名称':<20} {'状态':<8} {'依赖':<20}",
                 "-" * 55]
        for name in self._init_order:
            info = self._modules[name]
            status = "启用" if info['enabled'] else "禁用"
            deps = ", ".join(info['dependencies']) if info['dependencies'] else "无"
            lines.append(f"  {name:<18} {status:<8} {deps:<20}")
        lines.append("=" * 55)
        for line in lines:
            logger.info(line)
    
    def get_module(self, name: str) -> Optional[Any]:
        """获取模块实例"""
        if name in self._modules:
            return self._modules[name]['instance']
        return None
    
    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """获取所有模块状态"""
        return {
            name: {
                'enabled': info['enabled'],
                'dependencies': info['dependencies'],
                'registered_at': info['registered_at'].isoformat()
            }
            for name, info in self._modules.items()
        }
    
    def get_enabled_modules(self) -> List[str]:
        """获取已启用的模块列表"""
        return [name for name, info in self._modules.items() if info['enabled']]
    
    def is_module_enabled(self, name: str) -> bool:
        """检查模块是否启用"""
        if name in self._modules:
            return self._modules[name]['enabled']
        return False
    
    def shutdown_all(self):
        """按逆序关闭所有模块"""
        logger.info("[ModuleRegistry] ========== 开始关闭所有模块 ==========")
        
        # 逆序关闭（先关闭依赖它的模块）
        for name in reversed(self._init_order):
            info = self._modules[name]
            if info['enabled'] and info['instance']:
                try:
                    if hasattr(info['instance'], 'stop'):
                        info['instance'].stop()
                    info['enabled'] = False
                    logger.info(f"  [OK] '{name}' - 已停止")
                except Exception as e:
                    logger.error(f"  [FAIL] '{name}' - 停止失败: {e}")
        
        self._initialized = False
        logger.info("[ModuleRegistry] ========== 所有模块已关闭 ==========")


# ==================== 全局函数 ====================

_global_registry: Optional[ModuleRegistry] = None


def get_module_registry() -> ModuleRegistry:
    """获取全局模块注册表实例（单例）"""
    global _global_registry
    if _global_registry is None:
        _global_registry = ModuleRegistry()
    return _global_registry


def register_module(name: str, dependencies: List[str] = None):
    """
    模块注册装饰器
    用于自动注册增量模块
    
    用法:
        @register_module('my_module', dependencies=['utils'])
        class MyModule(BaseModule):
            ...
    """
    def decorator(module_class):
        registry = get_module_registry()
        registry.register(name, module_class, dependencies)
        return module_class
    return decorator


def initialize_modules(app=None) -> ModuleRegistry:
    """
    一键初始化所有增量模块
    
    使用方法（在 visualization.py 或 main.py 中）:
        from utils.module_registry import initialize_modules
        registry = initialize_modules(app)
    
    Args:
        app: Flask应用实例
        
    Returns:
        ModuleRegistry: 模块注册表实例
    """
    # 导入所有模块（导入即自动注册）
    _import_all_modules()
    
    # 初始化所有已注册模块
    registry = get_module_registry()
    registry.initialize_all(app)
    
    return registry


def _import_all_modules():
    """导入所有增量模块（触发自动注册）"""
    import_errors = []
    
    # 尝试导入各模块
    module_imports = [
        ('utils.database_module', 'DatabaseModule'),
        ('risk.security_module', 'SecurityModule'),
        ('monitor.monitor_module', 'MonitorModule'),
    ]
    
    for module_path, class_name in module_imports:
        try:
            __import__(module_path)
            logger.info(f"[ModuleRegistry] 已加载模块: {module_path}")
        except Exception as e:
            import_errors.append(f"{module_path}: {e}")
            logger.warning(f"[ModuleRegistry] 模块加载失败: {module_path} - {e}")
    
    if import_errors:
        logger.warning(f"[ModuleRegistry] 以下模块加载失败: {import_errors}")