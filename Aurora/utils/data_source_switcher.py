#!/usr/bin/env python3
"""
数据源切换器
管理多数据源的故障检测、自动切换和健康检查

功能：
1. 数据源健康检查（定时和手动触发）
2. 自动故障转移（按优先级表）
3. 手动切换（API驱动）
4. 数据源性能对比
5. 切换冷却机制
"""

import time
import threading
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime, timedelta
from enum import Enum
import logging

from utils.switch_event_bus import get_event_bus, EventType, SwitchEvent
from utils.switch_config import get_switch_config
from utils.switch_history import get_switch_history

logger = logging.getLogger(__name__)


class SourceStatus(Enum):
    """数据源状态"""
    ONLINE = 'online'
    DEGRADED = 'degraded'      # 性能下降但可用
    UNSTABLE = 'unstable'      # 不稳定
    OFFLINE = 'offline'
    UNKNOWN = 'unknown'


class DataSourceInfo:
    """数据源信息"""
    
    def __init__(self, name: str, fetcher: Callable = None, priority: int = 0):
        self.name = name
        self.fetcher = fetcher
        self.priority = priority
        self.status = SourceStatus.UNKNOWN
        self.consecutive_failures = 0
        self.last_check_time: Optional[datetime] = None
        self.last_success_time: Optional[datetime] = None
        self.response_times: List[float] = []  # 最近响应时间列表
        self.total_requests = 0
        self.successful_requests = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'priority': self.priority,
            'status': self.status.value,
            'consecutive_failures': self.consecutive_failures,
            'last_check': self.last_check_time.isoformat() if self.last_check_time else None,
            'last_success': self.last_success_time.isoformat() if self.last_success_time else None,
            'avg_response_ms': sum(self.response_times) / len(self.response_times) * 1000 if self.response_times else 0,
            'success_rate': self.successful_requests / self.total_requests * 100 if self.total_requests > 0 else 0,
        }


class DataSourceSwitcher:
    """
    数据源切换器（单例）
    """
    
    _instance: Optional['DataSourceSwitcher'] = None
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
        
        self._sources: Dict[str, DataSourceInfo] = {}
        self._current_source: Optional[DataSourceInfo] = None
        self._config = get_switch_config()
        self._event_bus = get_event_bus()
        self._history = get_switch_history()
        self._last_switch_time: Optional[datetime] = None
        self._switch_count_hour = 0
        self._health_thread: Optional[threading.Thread] = None
        self._running = False
        self._switch_lock = threading.Lock()
        self._on_switch_callback: Optional[Callable] = None
        self._initialized = True
        
        logger.info("[DataSourceSwitcher] 数据源切换器已初始化")
    
    def register_source(self, name: str, fetcher: Callable, priority: int = 0):
        """
        注册数据源
        
        Args:
            name: 数据源名称
            fetcher: 数据获取函数
            priority: 优先级（数值越小越优先）
        """
        info = DataSourceInfo(name=name, fetcher=fetcher, priority=priority)
        self._sources[name] = info
        
        # 如果优先级最高，设为当前数据源
        if self._current_source is None or priority == 0:
            self._current_source = info
            info.status = SourceStatus.ONLINE
        
        logger.info(f"[DataSourceSwitcher] 注册数据源: {name} (优先级: {priority})")
    
    def set_on_switch_callback(self, callback: Callable):
        """设置切换回调函数"""
        self._on_switch_callback = callback
    
    @property
    def current_source_name(self) -> str:
        """获取当前数据源名称"""
        return self._current_source.name if self._current_source else 'unknown'
    
    def get_current_source(self) -> Optional[DataSourceInfo]:
        """获取当前数据源"""
        return self._current_source
    
    def get_all_sources(self) -> List[Dict]:
        """获取所有数据源信息"""
        return [s.to_dict() for s in self._sources.values()]
    
    def health_check(self, source_name: str = None) -> Dict[str, Any]:
        """
        执行健康检查
        
        Args:
            source_name: 指定数据源（None则检查全部）
        
        Returns:
            健康检查结果
        """
        results = {}
        sources_to_check = [source_name] if source_name else list(self._sources.keys())
        
        for name in sources_to_check:
            if name not in self._sources:
                continue
            
            info = self._sources[name]
            info.last_check_time = datetime.now()
            
            try:
                start_time = time.time()
                
                # 执行数据获取测试
                if info.fetcher:
                    data = info.fetcher()
                    success = data is not None
                else:
                    # 无获取函数，标记为在线
                    success = True
                
                duration = time.time() - start_time
                info.response_times.append(duration)
                if len(info.response_times) > 100:
                    info.response_times = info.response_times[-100:]
                
                info.total_requests += 1
                
                if success:
                    info.successful_requests += 1
                    info.consecutive_failures = 0
                    info.last_success_time = datetime.now()
                    
                    # 根据响应时间判断健康状态
                    avg_response = sum(info.response_times) / len(info.response_times)
                    if avg_response > 5.0:
                        info.status = SourceStatus.DEGRADED
                    elif info.consecutive_failures > 0:
                        info.status = SourceStatus.UNSTABLE
                    else:
                        info.status = SourceStatus.ONLINE
                    
                    results[name] = {'status': 'healthy', 'response_time': duration}
                else:
                    info.consecutive_failures += 1
                    if info.consecutive_failures >= self._config.get('source_health_threshold', 3):
                        info.status = SourceStatus.OFFLINE
                    elif info.consecutive_failures >= 1:
                        info.status = SourceStatus.UNSTABLE
                    
                    results[name] = {'status': 'unhealthy', 'consecutive_failures': info.consecutive_failures}
                    
                    # 如果当前数据源不健康，触发自动切换
                    if info == self._current_source and self._config.get('auto_failover', True):
                        self._auto_failover()
                
            except Exception as e:
                logger.error(f"[DataSourceSwitcher] 健康检查异常 ({name}): {e}")
                info.consecutive_failures += 1
                if info.consecutive_failures >= 3:
                    info.status = SourceStatus.OFFLINE
                results[name] = {'status': 'error', 'error': str(e)}
        
        return results
    
    def _auto_failover(self):
        """自动故障转移"""
        with self._switch_lock:
            # 检查冷却时间
            if self._last_switch_time:
                cooldown = self._config.get('switch_cooldown', 60)
                elapsed = (datetime.now() - self._last_switch_time).total_seconds()
                if elapsed < cooldown:
                    logger.warning(f"[DataSourceSwitcher] 切换冷却中 (剩余 {cooldown - elapsed:.0f}s)")
                    return
            
            # 查找下一个可用的数据源（按优先级）
            priority_order = self._config.get('source_priority', [])
            for source_name in priority_order:
                source = self._sources.get(source_name)
                if source and source.name != self._current_source.name and \
                   source.status in [SourceStatus.ONLINE, SourceStatus.DEGRADED]:
                    self._perform_switch(source, f"自动故障转移 (当前源故障)")
                    return
            
            # 尝试所有在线源
            for source in self._sources.values():
                if source != self._current_source and \
                   source.status in [SourceStatus.ONLINE, SourceStatus.DEGRADED]:
                    self._perform_switch(source, f"自动故障转移 (当前源故障)")
                    return
            
            logger.error("[DataSourceSwitcher] 无可用备用数据源!")
    
    def manual_switch(self, target_name: str) -> Dict[str, Any]:
        """
        手动切换数据源
        
        Args:
            target_name: 目标数据源名称
        
        Returns:
            切换结果
        """
        with self._switch_lock:
            if target_name not in self._sources:
                return {'success': False, 'error': f'未知数据源: {target_name}'}
            
            target = self._sources[target_name]
            if target == self._current_source:
                return {'success': True, 'message': f'已在使用: {target_name}'}
            
            # 检查目标源状态
            if target.status == SourceStatus.OFFLINE:
                return {'success': False, 'error': f'目标数据源离线: {target_name}'}
            
            self._perform_switch(target, '手动切换')
            
            return {
                'success': True,
                'from': self._current_source.name if self._current_source else 'unknown',
                'to': target_name
            }
    
    def _perform_switch(self, target: DataSourceInfo, reason: str):
        """执行切换"""
        old_source = self._current_source
        old_name = old_source.name if old_source else 'unknown'
        start_time = time.time()
        
        try:
            self._current_source = target
            self._last_switch_time = datetime.now()
            
            # 记录历史
            self._history.record(
                switch_type='data_source',
                from_value=old_name,
                to_value=target.name,
                reason=reason,
                triggered_by='manual' if '手动' in reason else 'auto',
                duration_ms=(time.time() - start_time) * 1000
            )
            
            # 发布事件
            self._event_bus.publish_immediate(
                EventType.DATA_SOURCE_SWITCHED,
                source='DataSourceSwitcher',
                data={
                    'from': old_name,
                    'to': target.name,
                    'reason': reason
                }
            )
            
            # 调用外部回调
            if self._on_switch_callback:
                try:
                    self._on_switch_callback(old_name, target.name, reason)
                except Exception as e:
                    logger.error(f"[DataSourceSwitcher] 切换回调异常: {e}")
            
            logger.info(f"[DataSourceSwitcher] 切换完成: {old_name} -> {target.name} ({reason})")
            
        except Exception as e:
            logger.error(f"[DataSourceSwitcher] 切换失败: {e}")
            # 尝试恢复
            self._current_source = old_source
            raise
    
    def start_health_check(self, interval: int = None):
        """启动定期健康检查"""
        if self._running:
            return
        
        interval = interval or self._config.get('source_health_check_interval', 30)
        self._running = True
        
        self._health_thread = threading.Thread(
            target=self._health_check_worker,
            args=(interval,),
            name='DataSourceHealthChecker',
            daemon=True
        )
        self._health_thread.start()
        logger.info(f"[DataSourceSwitcher] 健康检查已启动 (间隔: {interval}s)")
    
    def stop_health_check(self):
        """停止定期健康检查"""
        self._running = False
        if self._health_thread:
            self._health_thread.join(timeout=5)
        logger.info("[DataSourceSwitcher] 健康检查已停止")
    
    def _health_check_worker(self, interval: int):
        """健康检查工作线程"""
        logger.info("[DataSourceSwitcher] 健康检查线程已启动")
        while self._running:
            try:
                self.health_check()
            except Exception as e:
                logger.error(f"[DataSourceSwitcher] 健康检查线程异常: {e}")
            time.sleep(interval)
        logger.info("[DataSourceSwitcher] 健康检查线程已退出")
    
    def get_status(self) -> Dict[str, Any]:
        """获取切换器状态"""
        return {
            'current_source': self.current_source_name,
            'sources': self.get_all_sources(),
            'last_switch': self._last_switch_time.isoformat() if self._last_switch_time else None,
            'auto_failover_enabled': self._config.get('auto_failover', True),
            'health_check_running': self._running,
        }


# 全局实例
_global_data_source_switcher: Optional[DataSourceSwitcher] = None


def get_data_source_switcher() -> DataSourceSwitcher:
    """获取全局数据源切换器实例（单例）"""
    global _global_data_source_switcher
    if _global_data_source_switcher is None:
        _global_data_source_switcher = DataSourceSwitcher()
    return _global_data_source_switcher