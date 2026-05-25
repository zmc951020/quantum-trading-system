#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略监控模块 - Aurora策略实时运行监控
监控策略执行状态、性能指标和异常告警
"""

import logging
import time
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from collections import deque
from threading import Lock

logger = logging.getLogger(__name__)


class StrategyMonitor:
    """策略监控器"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.max_history = self.config.get("max_history", 1000)
        self._monitors: Dict[str, Dict[str, Any]] = {}
        self._lock = Lock()
        self._callbacks: Dict[str, List[Callable]] = {}

    def register_strategy(self, name: str) -> Dict[str, Any]:
        """注册策略到监控"""
        with self._lock:
            if name not in self._monitors:
                self._monitors[name] = {
                    "start_time": datetime.now(),
                    "signals_generated": 0,
                    "orders_placed": 0,
                    "errors_count": 0,
                    "last_signal_time": None,
                    "last_error": None,
                    "metrics_history": deque(maxlen=self.max_history),
                    "status": "active",
                }
                logger.info(f"策略 {name} 已注册到监控")
        return {"status": "success", "message": f"策略 {name} 已注册"}

    def record_signal(self, strategy_name: str, signal: Dict[str, Any]) -> None:
        """记录交易信号"""
        if strategy_name not in self._monitors:
            self.register_strategy(strategy_name)
        with self._lock:
            monitor = self._monitors[strategy_name]
            monitor["signals_generated"] += 1
            monitor["last_signal_time"] = datetime.now().isoformat()
            monitor["metrics_history"].append({
                "type": "signal",
                "timestamp": datetime.now().isoformat(),
                "data": signal,
            })
            self._trigger_callbacks("on_signal", strategy_name, signal)

    def record_order(self, strategy_name: str, order: Dict[str, Any]) -> None:
        """记录交易订单"""
        if strategy_name not in self._monitors:
            self.register_strategy(strategy_name)
        with self._lock:
            monitor = self._monitors[strategy_name]
            monitor["orders_placed"] += 1
            monitor["metrics_history"].append({
                "type": "order",
                "timestamp": datetime.now().isoformat(),
                "data": order,
            })
            self._trigger_callbacks("on_order", strategy_name, order)

    def record_error(self, strategy_name: str, error: str) -> None:
        """记录错误"""
        if strategy_name not in self._monitors:
            self.register_strategy(strategy_name)
        with self._lock:
            monitor = self._monitors[strategy_name]
            monitor["errors_count"] += 1
            monitor["last_error"] = {"message": error, "time": datetime.now().isoformat()}
            logger.error(f"[{strategy_name}] 错误: {error}")
            self._trigger_callbacks("on_error", strategy_name, error)

    def get_status(self, strategy_name: str) -> Dict[str, Any]:
        """获取策略状态"""
        monitor = self._monitors.get(strategy_name)
        if not monitor:
            return {"status": "unknown", "message": f"策略 {strategy_name} 未注册"}

        return {
            "name": strategy_name,
            "status": monitor["status"],
            "uptime_seconds": (datetime.now() - monitor["start_time"]).total_seconds(),
            "signals_generated": monitor["signals_generated"],
            "orders_placed": monitor["orders_placed"],
            "errors_count": monitor["errors_count"],
            "last_signal_time": monitor["last_signal_time"],
            "last_error": monitor["last_error"],
        }

    def get_all_status(self) -> List[Dict[str, Any]]:
        """获取所有策略状态"""
        return [self.get_status(name) for name in self._monitors]

    def get_recent_activity(self, strategy_name: str, limit: int = 20) -> List[Dict[str, Any]]:
        """获取最近的活动记录"""
        monitor = self._monitors.get(strategy_name)
        if not monitor:
            return []
        return list(monitor["metrics_history"])[-limit:]

    def set_status(self, strategy_name: str, status: str) -> Dict[str, Any]:
        """设置策略状态"""
        monitor = self._monitors.get(strategy_name)
        if not monitor:
            return {"status": "error", "message": f"策略 {strategy_name} 未注册"}

        valid = ["active", "paused", "stopped", "error"]
        if status not in valid:
            return {"status": "error", "message": f"无效状态。有效值: {valid}"}

        monitor["status"] = status
        logger.info(f"策略 {strategy_name} 状态 -> {status}")
        return {"status": "success", "message": f"状态已更新为 {status}"}

    def on(self, event: str, callback: Callable) -> None:
        """注册事件回调"""
        if event not in self._callbacks:
            self._callbacks[event] = []
        self._callbacks[event].append(callback)

    def _trigger_callbacks(self, event: str, *args, **kwargs) -> None:
        """触发事件回调"""
        for callback in self._callbacks.get(event, []):
            try:
                callback(*args, **kwargs)
            except Exception as e:
                logger.error(f"回调执行失败: {e}")


__all__ = ["StrategyMonitor"]