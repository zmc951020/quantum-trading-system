#!/usr/bin/env python3
"""
切换事件总线
实现发布-订阅模式，用于在组件间传递切换事件通知

功能：
1. 事件订阅与取消
2. 事件发布与分发
3. 异步/同步事件处理
4. 事件优先级队列
5. 事件历史记录
"""

import threading
import queue
import time
from typing import Callable, Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class EventType(Enum):
    """事件类型枚举"""
    # 数据源相关
    DATA_SOURCE_SWITCHED = 'data_source_switched'
    DATA_SOURCE_FAILED = 'data_source_failed'
    DATA_SOURCE_RECOVERED = 'data_source_recovered'
    DATA_SOURCE_HEALTH_CHECK = 'data_source_health_check'
    
    # 策略相关
    STRATEGY_SWITCHED = 'strategy_switched'
    STRATEGY_PERFORMANCE_ALERT = 'strategy_performance_alert'
    STRATEGY_WARMUP_STARTED = 'strategy_warmup_started'
    STRATEGY_WARMUP_COMPLETED = 'strategy_warmup_completed'
    
    # 模式相关
    MODE_SWITCHED = 'mode_switched'
    MODE_SWITCH_REQUESTED = 'mode_switch_requested'
    
    # 系统相关
    SYSTEM_STARTUP = 'system_startup'
    SYSTEM_SHUTDOWN = 'system_shutdown'
    SYSTEM_ERROR = 'system_error'
    SYSTEM_WARNING = 'system_warning'
    
    # 配置相关
    CONFIG_CHANGED = 'config_changed'
    CONFIG_RELOADED = 'config_reloaded'
    
    # 安全事件
    SECURITY_ALERT = 'security_alert'
    SECURITY_BLOCKED = 'security_blocked'


@dataclass
class SwitchEvent:
    """切换事件数据结构"""
    event_type: EventType
    source: str                          # 事件来源（组件名）
    data: Dict[str, Any] = field(default_factory=dict)  # 事件数据
    timestamp: datetime = field(default_factory=datetime.now)
    priority: int = 0                    # 优先级（0最低）
    event_id: str = None                 # 事件ID（自动生成）
    
    def __post_init__(self):
        if self.event_id is None:
            self.event_id = f"{self.event_type.value}_{int(time.time() * 1000000)}"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'event_id': self.event_id,
            'event_type': self.event_type.value,
            'source': self.source,
            'data': self.data,
            'timestamp': self.timestamp.isoformat(),
            'priority': self.priority
        }


class SwitchEventBus:
    """
    切换事件总线（单例模式）
    支持同步和异步事件分发
    """
    
    _instance: Optional['SwitchEventBus'] = None
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
        
        self._subscribers: Dict[EventType, List[Callable]] = {}
        self._event_queue: queue.PriorityQueue = queue.PriorityQueue()
        self._event_history: List[SwitchEvent] = []
        self._max_history = 1000
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        self._async_mode = True
        self._initialized = True
        
        # 初始化事件类型订阅列表
        for event_type in EventType:
            self._subscribers[event_type] = []
        
        self._subscribers['*'] = []  # 通配符 - 订阅所有事件
        self._running = True
        
        # 启动异步事件处理线程
        self._worker_thread = threading.Thread(
            target=self._event_worker,
            name='SwitchEventBus-Worker',
            daemon=True
        )
        self._worker_thread.start()
        logger.info("[EventBus] 切换事件总线已初始化")
    
    def subscribe(self, event_type: EventType, handler: Callable[[SwitchEvent], None]) -> bool:
        """
        订阅事件
        
        Args:
            event_type: 事件类型
            handler: 事件处理函数
        
        Returns:
            是否订阅成功
        """
        if event_type not in self._subscribers:
            logger.warning(f"[EventBus] 未知事件类型: {event_type}")
            return False
        
        if handler not in self._subscribers[event_type]:
            self._subscribers[event_type].append(handler)
            logger.debug(f"[EventBus] 订阅事件: {event_type.value} -> {handler.__name__}")
        
        return True
    
    def subscribe_all(self, handler: Callable[[SwitchEvent], None]) -> bool:
        """
        订阅所有事件（通配符）
        
        Args:
            handler: 事件处理函数
        """
        return self.subscribe('*', handler)  # type: ignore
    
    def unsubscribe(self, event_type: EventType, handler: Callable[[SwitchEvent], None]) -> bool:
        """
        取消订阅
        
        Args:
            event_type: 事件类型
            handler: 事件处理函数
        """
        if event_type in self._subscribers and handler in self._subscribers[event_type]:
            self._subscribers[event_type].remove(handler)
            logger.debug(f"[EventBus] 取消订阅: {event_type.value} -> {handler.__name__}")
            return True
        return False
    
    def publish(self, event: SwitchEvent, async_mode: bool = True) -> bool:
        """
        发布事件
        
        Args:
            event: 事件对象
            async_mode: 是否异步分发
        
        Returns:
            是否发布成功
        """
        try:
            if async_mode and self._async_mode:
                # 异步模式：放入队列
                self._event_queue.put((-event.priority, time.time(), event))
            else:
                # 同步模式：直接分发
                self._dispatch_event(event)
            
            # 存入历史记录
            self._event_history.append(event)
            if len(self._event_history) > self._max_history:
                self._event_history = self._event_history[-self._max_history:]
            
            return True
        except Exception as e:
            logger.error(f"[EventBus] 发布事件失败: {e}")
            return False
    
    def publish_immediate(self, event_type: EventType, source: str, 
                          data: Dict[str, Any] = None, priority: int = 0,
                          sync: bool = False) -> SwitchEvent:
        """
        快捷发布事件
        
        Args:
            event_type: 事件类型
            source: 事件来源
            data: 事件数据
            priority: 优先级
            sync: 是否同步分发
        
        Returns:
            SwitchEvent: 已发布的事件对象
        """
        event = SwitchEvent(
            event_type=event_type,
            source=source,
            data=data or {},
            priority=priority
        )
        self.publish(event, async_mode=not sync)
        return event
    
    def _dispatch_event(self, event: SwitchEvent):
        """分发事件给订阅者"""
        handlers = []
        
        # 获取特定类型的订阅者
        if event.event_type in self._subscribers:
            handlers.extend(self._subscribers[event.event_type])
        
        # 获取通配符订阅者
        handlers.extend(self._subscribers.get('*', []))
        
        # 去重
        handlers = list(dict.fromkeys(handlers))
        
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"[EventBus] 事件处理异常 ({handler.__name__}): {e}")
    
    def _event_worker(self):
        """异步事件处理线程"""
        logger.info("[EventBus] 事件处理线程已启动")
        while self._running:
            try:
                # 非阻塞获取事件，1秒超时
                priority, timestamp, event = self._event_queue.get(timeout=1)
                self._dispatch_event(event)
                self._event_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"[EventBus] 事件处理线程异常: {e}")
        
        logger.info("[EventBus] 事件处理线程已退出")
    
    def get_history(self, event_type: EventType = None, 
                    limit: int = 100) -> List[SwitchEvent]:
        """
        获取事件历史
        
        Args:
            event_type: 事件类型（None表示所有类型）
            limit: 最大返回数量
        
        Returns:
            事件列表
        """
        if event_type:
            events = [e for e in self._event_history if e.event_type == event_type]
        else:
            events = list(self._event_history)
        
        return events[-limit:]
    
    def get_events_since(self, since: datetime) -> List[SwitchEvent]:
        """
        获取指定时间后的事件
        
        Args:
            since: 起始时间
        
        Returns:
            事件列表
        """
        return [e for e in self._event_history if e.timestamp >= since]
    
    def get_subscriber_count(self, event_type: EventType = None) -> int:
        """获取订阅者数量"""
        if event_type:
            return len(self._subscribers.get(event_type, []))
        total = 0
        for subscribers in self._subscribers.values():
            total += len(subscribers)
        return total
    
    def shutdown(self):
        """关闭事件总线"""
        logger.info("[EventBus] 正在关闭事件总线...")
        self._running = False
        
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5)
        
        # 清空队列中剩余事件
        while not self._event_queue.empty():
            try:
                self._event_queue.get_nowait()
                self._event_queue.task_done()
            except queue.Empty:
                break
        
        logger.info("[EventBus] 事件总线已关闭")


# 全局事件总线实例
_global_event_bus: Optional[SwitchEventBus] = None


def get_event_bus() -> SwitchEventBus:
    """获取全局事件总线实例（单例）"""
    global _global_event_bus
    if _global_event_bus is None:
        _global_event_bus = SwitchEventBus()
    return _global_event_bus