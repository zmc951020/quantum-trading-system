#!/usr/bin/env python3
"""
模式切换器
管理系统运行模式切换，控制各模式下的行为差异

功能：
1. 模式注册与切换
2. 模式下的行为约束（如 emergency 禁止交易）
3. 模式依赖检查（如 live 模式需要 data_source 在线）
4. 模式过渡钩子（before_switch / after_switch）
5. 与其他切换器联动
"""

import threading
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime
from enum import Enum
import logging

from utils.switch_event_bus import get_event_bus, EventType
from utils.switch_config import get_switch_config

logger = logging.getLogger(__name__)


class SystemMode(Enum):
    """系统运行模式"""
    NORMAL = 'normal'
    BACKTEST = 'backtest'
    SIMULATION = 'simulation'
    LIVE = 'live'
    MAINTENANCE = 'maintenance'
    EMERGENCY = 'emergency'


@dataclass
class ModeBehavior:
    """模式行为定义"""
    allow_trading: bool = True
    allow_data_fetch: bool = True
    allow_signal_generation: bool = True
    allow_auto_switch: bool = True
    require_data_source: bool = True
    require_strategy: bool = True
    log_level: str = 'INFO'
    description: str = ''


class ModeSwitcher:
    """
    模式切换器（单例）
    """
    
    _instance: Optional['ModeSwitcher'] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._current_mode = SystemMode.NORMAL
        self._previous_mode: Optional[SystemMode] = None
        self._mode_behaviors: Dict[SystemMode, ModeBehavior] = {}
        self._before_hooks: List[Callable] = []
        self._after_hooks: List[Callable] = []
        self._mode_lock = threading.RLock()
        self._config = get_switch_config()
        self._event_bus = get_event_bus()
        self._mode_switch_count = 0
        self._last_mode_switch: Optional[datetime] = None
        self._initialized = True
        
        # 默认行为定义
        self._init_mode_behaviors()
        
        logger.info("[ModeSwitcher] 模式切换器已初始化")
    
    def _init_mode_behaviors(self):
        """初始化各模式行为"""
        self._mode_behaviors = {
            SystemMode.NORMAL: ModeBehavior(
                allow_trading=False,
                allow_data_fetch=True,
                allow_signal_generation=True,
                allow_auto_switch=True,
                require_data_source=True,
                require_strategy=True,
                description='正常运行模式（不实盘）',
            ),
            SystemMode.BACKTEST: ModeBehavior(
                allow_trading=False,
                allow_data_fetch=True,
                allow_signal_generation=True,
                allow_auto_switch=False,
                require_data_source=True,
                require_strategy=True,
                description='回测模式',
            ),
            SystemMode.SIMULATION: ModeBehavior(
                allow_trading=False,
                allow_data_fetch=True,
                allow_signal_generation=True,
                allow_auto_switch=True,
                require_data_source=True,
                require_strategy=True,
                description='仿真交易模式（模拟下单）',
            ),
            SystemMode.LIVE: ModeBehavior(
                allow_trading=True,
                allow_data_fetch=True,
                allow_signal_generation=True,
                allow_auto_switch=True,
                require_data_source=True,
                require_strategy=True,
                description='实盘交易模式',
            ),
            SystemMode.MAINTENANCE: ModeBehavior(
                allow_trading=False,
                allow_data_fetch=False,
                allow_signal_generation=False,
                allow_auto_switch=False,
                require_data_source=False,
                require_strategy=False,
                description='维护模式',
            ),
            SystemMode.EMERGENCY: ModeBehavior(
                allow_trading=False,
                allow_data_fetch=False,
                allow_signal_generation=False,
                allow_auto_switch=False,
                require_data_source=False,
                require_strategy=False,
                description='紧急模式（暂停所有操作）',
            ),
        }
    
    def register_before_hook(self, hook: Callable):
        """注册模式切换前钩子"""
        self._before_hooks.append(hook)
        logger.info(f"[ModeSwitcher] 已注册切换前钩子: {hook.__name__}")
    
    def register_after_hook(self, hook: Callable):
        """注册模式切换后钩子"""
        self._after_hooks.append(hook)
        logger.info(f"[ModeSwitcher] 已注册切换后钩子: {hook.__name__}")
    
    def apply_mode(self, mode: SystemMode) -> Dict[str, Any]:
        """
        切换系统模式
        
        Args:
            mode: 目标模式
        
        Returns:
            切换结果
        """
        with self._mode_lock:
            if mode == self._current_mode:
                return {'success': True, 'message': f'已在 {mode.value} 模式'}
            
            old_mode = self._current_mode
            behavior = self._mode_behaviors.get(mode)
            
            if behavior is None:
                return {'success': False, 'error': f'未定义的模式: {mode.value}'}
            
            # 执行切换前钩子
            for hook in self._before_hooks:
                try:
                    hook(old_mode, mode)
                except Exception as e:
                    logger.error(f"[ModeSwitcher] 切换前钩子异常: {e}")
            
            try:
                self._current_mode = mode
                self._previous_mode = old_mode
                self._last_mode_switch = datetime.now()
                self._mode_switch_count += 1
                
                # 执行切换后钩子
                for hook in self._after_hooks:
                    try:
                        hook(old_mode, mode)
                    except Exception as e:
                        logger.error(f"[ModeSwitcher] 切换后钩子异常: {e}")
                
                logger.info(f"[ModeSwitcher] 模式切换完成: {old_mode.value} -> {mode.value}")
                
                return {
                    'success': True,
                    'from': old_mode.value,
                    'to': mode.value,
                    'behavior': {
                        'allow_trading': behavior.allow_trading,
                        'allow_data_fetch': behavior.allow_data_fetch,
                        'allow_signal_generation': behavior.allow_signal_generation,
                        'allow_auto_switch': behavior.allow_auto_switch,
                    }
                }
                
            except Exception as e:
                # 恢复旧模式
                self._current_mode = old_mode
                logger.error(f"[ModeSwitcher] 模式切换失败: {e}")
                return {'success': False, 'error': str(e)}
    
    def switch_to_mode(self, mode_name: str) -> Dict[str, Any]:
        """
        按名称切换模式（对外接口）
        
        Args:
            mode_name: 模式名称
        
        Returns:
            切换结果
        """
        try:
            mode = SystemMode(mode_name)
        except ValueError:
            return {'success': False, 'error': f'未知模式: {mode_name}'}
        
        return self.apply_mode(mode)
    
    def get_behavior(self, mode: SystemMode = None) -> Dict[str, Any]:
        """获取模式行为"""
        target = mode or self._current_mode
        behavior = self._mode_behaviors.get(target)
        if behavior is None:
            return {}
        return {
            'allow_trading': behavior.allow_trading,
            'allow_data_fetch': behavior.allow_data_fetch,
            'allow_signal_generation': behavior.allow_signal_generation,
            'allow_auto_switch': behavior.allow_auto_switch,
            'require_data_source': behavior.require_data_source,
            'require_strategy': behavior.require_strategy,
            'description': behavior.description,
        }
    
    # 便捷方法
    @property
    def allow_trading(self) -> bool:
        behavior = self._mode_behaviors.get(self._current_mode)
        return behavior.allow_trading if behavior else False
    
    @property
    def allow_data_fetch(self) -> bool:
        behavior = self._mode_behaviors.get(self._current_mode)
        return behavior.allow_data_fetch if behavior else False
    
    @property
    def allow_signal_generation(self) -> bool:
        behavior = self._mode_behaviors.get(self._current_mode)
        return behavior.allow_signal_generation if behavior else False
    
    @property
    def allow_auto_switch(self) -> bool:
        behavior = self._mode_behaviors.get(self._current_mode)
        return behavior.allow_auto_switch if behavior else False
    
    @property
    def current_mode(self) -> str:
        return self._current_mode.value
    
    @property
    def is_live(self) -> bool:
        return self._current_mode == SystemMode.LIVE
    
    @property
    def is_emergency(self) -> bool:
        return self._current_mode == SystemMode.EMERGENCY
    
    @property
    def is_backtest(self) -> bool:
        return self._current_mode == SystemMode.BACKTEST
    
    def switch_to(self, mode_name: str) -> Dict[str, Any]:
        """别名，兼容旧接口"""
        return self.switch_to_mode(mode_name)
    
    def list_modes(self) -> List[Dict]:
        """列出所有可用模式"""
        return [
            {
                'name': mode.value,
                'is_current': mode == self._current_mode,
                'behavior': self.get_behavior(mode),
            }
            for mode in SystemMode
        ]
    
    def get_status(self) -> Dict[str, Any]:
        """获取模式状态"""
        return {
            'current_mode': self._current_mode.value,
            'previous_mode': self._previous_mode.value if self._previous_mode else None,
            'mode_switch_count': self._mode_switch_count,
            'last_switch': self._last_mode_switch.isoformat() if self._last_mode_switch else None,
            'behavior': self.get_behavior(),
            'is_live': self.is_live,
            'is_emergency': self.is_emergency,
        }


# 全局实例
_global_mode_switcher: Optional[ModeSwitcher] = None


def get_mode_switcher() -> ModeSwitcher:
    """获取全局模式切换器实例（单例）"""
    global _global_mode_switcher
    if _global_mode_switcher is None:
        _global_mode_switcher = ModeSwitcher()
    return _global_mode_switcher