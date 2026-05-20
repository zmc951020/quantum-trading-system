#!/usr/bin/env python3
"""
系统统一切换控制器
对外提供统一的切换操作接口，内部协调各子切换器

功能：
1. 统一的数据源切换接口
2. 统一的策略切换接口
3. 统一的运行模式切换接口
4. 切换历史查询
5. 配置管理
6. 健康状态聚合
7. 事件总线集成
"""

import threading
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime
from enum import Enum
import logging

from utils.switch_config import get_switch_config
from utils.switch_event_bus import get_event_bus, EventType
from utils.switch_history import get_switch_history
from utils.data_source_switcher import get_data_source_switcher

logger = logging.getLogger(__name__)


class SystemMode(Enum):
    """系统运行模式"""
    NORMAL = 'normal'           # 正常模式
    BACKTEST = 'backtest'       # 回测模式
    SIMULATION = 'simulation'   # 仿真模式
    LIVE = 'live'               # 实盘模式
    MAINTENANCE = 'maintenance' # 维护模式
    EMERGENCY = 'emergency'     # 紧急模式（暂停交易）


class SystemSwitcher:
    """
    统一切换控制器（单例模式）
    统一管理所有切换操作，是外部调用的主入口
    """
    
    _instance: Optional['SystemSwitcher'] = None
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
        
        self._config = get_switch_config()
        self._event_bus = get_event_bus()
        self._history = get_switch_history()
        self._data_source_switcher = get_data_source_switcher()
        self._strategy_switcher = None       # 延迟加载
        self._mode_switcher = None           # 延迟加载
        
        self._current_mode = SystemMode.NORMAL
        self._on_switch_callbacks: List[Callable] = []
        self._switch_lock = threading.RLock()
        self._last_health_check: Optional[datetime] = None
        self._initialized = True
        
        # 订阅系统事件
        self._event_bus.subscribe_all(self._on_global_event)
        
        logger.info("[SystemSwitcher] 统一切换控制器已初始化")
    
    def _get_strategy_switcher(self):
        """延迟加载策略切换器"""
        if self._strategy_switcher is None:
            try:
                from utils.strategy_switcher import get_strategy_switcher
                self._strategy_switcher = get_strategy_switcher()
            except ImportError:
                logger.warning("[SystemSwitcher] 策略切换器不可用")
        return self._strategy_switcher
    
    def _get_mode_switcher(self):
        """延迟加载模式切换器"""
        if self._mode_switcher is None:
            try:
                from utils.mode_switcher import get_mode_switcher
                self._mode_switcher = get_mode_switcher()
            except ImportError:
                logger.warning("[SystemSwitcher] 模式切换器不可用")
        return self._mode_switcher
    
    # ==================== 数据源切换 ====================
    
    def get_current_source(self) -> Dict[str, Any]:
        """获取当前数据源信息"""
        return self._data_source_switcher.get_status() if self._data_source_switcher else {}
    
    def list_data_sources(self) -> List[Dict]:
        """列出所有数据源"""
        return self._data_source_switcher.get_all_sources() if self._data_source_switcher else []
    
    def switch_data_source(self, target: str) -> Dict[str, Any]:
        """切换数据源"""
        with self._switch_lock:
            return self._data_source_switcher.manual_switch(target)
    
    def check_data_source_health(self, source: str = None) -> Dict[str, Any]:
        """检查数据源健康"""
        return self._data_source_switcher.health_check(source)
    
    def register_data_source(self, name: str, fetcher: Callable, priority: int = 0):
        """注册数据源"""
        self._data_source_switcher.register_source(name, fetcher, priority)
    
    # ==================== 策略切换 ====================
    
    def get_current_strategy(self) -> Dict[str, Any]:
        """获取当前策略信息"""
        switcher = self._get_strategy_switcher()
        return switcher.get_current_strategy_info() if switcher else {}
    
    def list_strategies(self) -> List[Dict]:
        """列出所有策略"""
        switcher = self._get_strategy_switcher()
        return switcher.list_strategies() if switcher else []
    
    def switch_strategy(self, target: str, warmup: bool = True) -> Dict[str, Any]:
        """切换策略"""
        with self._switch_lock:
            switcher = self._get_strategy_switcher()
            if switcher:
                return switcher.switch_to(target, warmup=warmup)
            return {'success': False, 'error': '策略切换器不可用'}
    
    def register_strategy(self, name: str, strategy_instance: Any, 
                          market_regimes: List[str] = None):
        """注册策略"""
        switcher = self._get_strategy_switcher()
        if switcher:
            switcher.register_strategy(name, strategy_instance, market_regimes or [])
    
    # ==================== 模式切换 ====================
    
    def get_current_mode(self) -> Dict[str, Any]:
        """获取当前模式"""
        return {
            'mode': self._current_mode.value,
            'available_modes': [m.value for m in SystemMode],
            'mode_description': self._get_mode_description(self._current_mode),
        }
    
    def switch_mode(self, target_mode: str) -> Dict[str, Any]:
        """
        切换系统运行模式
        
        Args:
            target_mode: 目标模式（normal/backtest/simulation/live/maintenance/emergency）
        
        Returns:
            切换结果
        """
        with self._switch_lock:
            try:
                new_mode = SystemMode(target_mode)
            except ValueError:
                return {'success': False, 'error': f'未知模式: {target_mode}'}
            
            if new_mode == self._current_mode:
                return {'success': True, 'message': f'已在 {target_mode} 模式'}
            
            old_mode = self._current_mode
            self._current_mode = new_mode
            
            # 记录历史
            self._history.record(
                switch_type='mode',
                from_value=old_mode.value,
                to_value=new_mode.value,
                reason=f'切换到{self._get_mode_description(new_mode)}',
                triggered_by='manual'
            )
            
            # 发布事件
            self._event_bus.publish_immediate(
                EventType.MODE_SWITCHED,
                source='SystemSwitcher',
                data={
                    'from': old_mode.value,
                    'to': new_mode.value,
                }
            )
            
            # 通知模式切换器
            mode_switcher = self._get_mode_switcher()
            if mode_switcher:
                mode_switcher.apply_mode(new_mode)
            
            logger.info(f"[SystemSwitcher] 模式切换: {old_mode.value} -> {new_mode.value}")
            
            return {
                'success': True,
                'from': old_mode.value,
                'to': new_mode.value,
                'description': self._get_mode_description(new_mode),
            }
    
    def _get_mode_description(self, mode: SystemMode) -> str:
        """获取模式描述"""
        descriptions = {
            SystemMode.NORMAL: '正常运行模式',
            SystemMode.BACKTEST: '回测模式',
            SystemMode.SIMULATION: '仿真交易模式',
            SystemMode.LIVE: '实盘交易模式',
            SystemMode.MAINTENANCE: '维护模式',
            SystemMode.EMERGENCY: '紧急模式（暂停所有交易）',
        }
        return descriptions.get(mode, '未知模式')
    
    # ==================== 切换开关控制 ====================
    
    def enable_auto_switch(self, switch_type: str) -> Dict[str, Any]:
        """启用自动切换"""
        config_key = {
            'data_source': 'auto_failover',
            'strategy': 'auto_strategy_switch',
            'mode': 'auto_mode_switch',
        }
        key = config_key.get(switch_type)
        if key:
            self._config.set(key, True)
            return {'success': True, 'message': f'{switch_type} 自动切换已启用'}
        return {'success': False, 'error': f'未知切换类型: {switch_type}'}
    
    def disable_auto_switch(self, switch_type: str) -> Dict[str, Any]:
        """禁用自动切换"""
        config_key = {
            'data_source': 'auto_failover',
            'strategy': 'auto_strategy_switch',
            'mode': 'auto_mode_switch',
        }
        key = config_key.get(switch_type)
        if key:
            self._config.set(key, False)
            return {'success': True, 'message': f'{switch_type} 自动切换已禁用'}
        return {'success': False, 'error': f'未知切换类型: {switch_type}'}
    
    # ==================== 查询接口 ====================
    
    def get_switch_history(self, switch_type: str = None, limit: int = 100) -> List[Dict]:
        """获取切换历史"""
        return self._history.query(switch_type=switch_type, limit=limit)
    
    def get_switch_statistics(self, hours: int = 24) -> Dict[str, Any]:
        """获取切换统计"""
        return self._history.get_statistics(hours)
    
    def get_switch_config(self) -> Dict[str, Any]:
        """获取切换配置"""
        return self._config.export()
    
    def update_switch_config(self, key: str, value: Any) -> Dict[str, Any]:
        """更新切换配置"""
        success = self._config.set(key, value)
        return {'success': success, 'key': key, 'value': value}
    
    def get_system_health(self) -> Dict[str, Any]:
        """获取系统整体健康状态"""
        self._last_health_check = datetime.now()
        
        health = {
            'timestamp': self._last_health_check.isoformat(),
            'mode': self._current_mode.value,
            'data_source': {},
            'strategy': {},
        }
        
        # 数据源健康
        try:
            source_status = self._data_source_switcher.get_status() if self._data_source_switcher else {}
            health['data_source'] = source_status
        except Exception as e:
            health['data_source'] = {'error': str(e)}
        
        # 策略健康
        try:
            strategy_switcher = self._get_strategy_switcher()
            if strategy_switcher:
                health['strategy'] = strategy_switcher.get_current_strategy_info()
        except Exception as e:
            health['strategy'] = {'error': str(e)}
        
        return health
    
    def get_current_state(self) -> Dict[str, Any]:
        """获取当前系统完整状态"""
        return {
            'mode': self._current_mode.value,
            'data_source': self._data_source_switcher.current_source_name if self._data_source_switcher else 'unknown',
            'strategy': self._get_strategy_switcher().current_strategy if self._get_strategy_switcher() else 'unknown',
            'config': self._config.export(),
        }
    
    # ==================== 事件处理 ====================
    
    def _on_global_event(self, event):
        """处理全局事件（日志记录）"""
        if event.event_type in [
            EventType.DATA_SOURCE_SWITCHED,
            EventType.STRATEGY_SWITCHED,
            EventType.MODE_SWITCHED,
        ]:
            logger.info(f"[SystemSwitcher] 收到切换事件: {event.event_type.value} -> {event.data}")
    
    def subscribe_switch_event(self, handler: Callable):
        """订阅切换事件"""
        self._event_bus.subscribe_all(handler)
    
    def on_switch(self, callback: Callable):
        """注册切换回调"""
        self._on_switch_callbacks.append(callback)
        # 同时注册到数据源切换器
        if self._data_source_switcher:
            self._data_source_switcher.set_on_switch_callback(callback)
    
    # ==================== 生命周期 ====================
    
    def start(self):
        """启动切换控制器"""
        # 启动数据源健康检查
        if self._data_source_switcher:
            self._data_source_switcher.start_health_check()
        
        # 发布启动事件
        self._event_bus.publish_immediate(
            EventType.SYSTEM_STARTUP,
            source='SystemSwitcher',
            data={'mode': self._current_mode.value}
        )
        
        logger.info("[SystemSwitcher] 统一切换控制器已启动")
    
    def shutdown(self):
        """关闭切换控制器"""
        # 停止健康检查
        if self._data_source_switcher:
            self._data_source_switcher.stop_health_check()
        
        # 发布关闭事件
        self._event_bus.publish_immediate(
            EventType.SYSTEM_SHUTDOWN,
            source='SystemSwitcher',
            sync=True
        )
        
        # 关闭事件总线
        self._event_bus.shutdown()
        
        logger.info("[SystemSwitcher] 统一切换控制器已关闭")


# 全局实例
_global_system_switcher: Optional[SystemSwitcher] = None


def get_system_switcher() -> SystemSwitcher:
    """获取全局系统切换器实例（单例）"""
    global _global_system_switcher
    if _global_system_switcher is None:
        _global_system_switcher = SystemSwitcher()
    return _global_system_switcher