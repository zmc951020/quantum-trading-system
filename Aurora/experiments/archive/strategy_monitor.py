#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略模块监控系统 (Strategy Module Monitor)
==============================================
监控策略管理平台的所有关键事件链路：
1. 环境切换（模拟盘/实盘）
2. 策略选择与激活
3. 三种优化器执行（RL Bot / V5 / V6）
4. 回测任务执行
5. 报告生成
6. 前端交互事件
"""

import os
import sys
import json
import sqlite3
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any
from collections import deque, defaultdict
from enum import Enum


class StrategyEventType(Enum):
    """策略事件类型"""
    # 环境相关
    ENVIRONMENT_SWITCH = "environment_switch"
    ENVIRONMENT_CHECK = "environment_check"
    
    # 策略相关
    STRATEGY_SELECT = "strategy_select"
    STRATEGY_ACTIVATE = "strategy_activate"
    STRATEGY_DEACTIVATE = "strategy_deactivate"
    STRATEGY_PENDING = "strategy_pending"
    STRATEGY_LOAD = "strategy_load"
    
    # 优化器相关
    OPTIMIZATION_START = "optimization_start"
    OPTIMIZATION_COMPLETE = "optimization_complete"
    OPTIMIZATION_ERROR = "optimization_error"
    OPTIMIZER_RL_START = "optimizer_rl_start"
    OPTIMIZER_RL_COMPLETE = "optimizer_rl_complete"
    OPTIMIZER_RL_ERROR = "optimizer_rl_error"
    OPTIMIZER_V5_START = "optimizer_v5_start"
    OPTIMIZER_V5_COMPLETE = "optimizer_v5_complete"
    OPTIMIZER_V5_ERROR = "optimizer_v5_error"
    OPTIMIZER_V6_DEEP_START = "optimizer_v6_deep_start"
    OPTIMIZER_V6_DEEP_COMPLETE = "optimizer_v6_deep_complete"
    OPTIMIZER_V6_DEEP_ERROR = "optimizer_v6_deep_error"
    OPTIMIZER_V6_AUTO_START = "optimizer_v6_auto_start"
    OPTIMIZER_V6_AUTO_COMPLETE = "optimizer_v6_auto_complete"
    OPTIMIZER_V6_AUTO_ERROR = "optimizer_v6_auto_error"
    
    # 回测相关
    BACKTEST_START = "backtest_start"
    BACKTEST_COMPLETE = "backtest_complete"
    BACKTEST_ERROR = "backtest_error"
    BACKTEST_REPORT_GENERATE = "backtest_report_generate"
    
    # 系统相关
    SYSTEM_INIT = "system_init"
    API_ERROR = "api_error"
    USER_ACTION = "user_action"
    PERFORMANCE_METRIC = "performance_metric"


class EventStatus(Enum):
    """事件状态"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ERROR = "error"
    PARTIAL = "partial"


class StrategyEvent:
    """策略事件"""
    
    def __init__(self, event_type: StrategyEventType, strategy_id: str = None,
                 environment: str = None, metadata: Dict = None):
        self.event_id = f"evt_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        self.event_type = event_type
        self.timestamp = datetime.now()
        self.strategy_id = strategy_id
        self.environment = environment or "paper"
        self.status = EventStatus.PENDING
        self.duration_ms = 0
        self.metadata = metadata or {}
        self.error = None
        self.error_trace = None
        self.session_id = None
        self.user_id = None
    
    def start(self):
        """标记事件开始"""
        self.status = EventStatus.IN_PROGRESS
        self.timestamp = datetime.now()
    
    def complete(self, metadata: Dict = None):
        """标记事件完成"""
        self.status = EventStatus.COMPLETED
        if metadata:
            self.metadata.update(metadata)
        self.duration_ms = int((datetime.now() - self.timestamp).total_seconds() * 1000)
    
    def fail(self, error: str, error_trace: str = None):
        """标记事件失败"""
        self.status = EventStatus.ERROR
        self.error = error
        self.error_trace = error_trace
        self.duration_ms = int((datetime.now() - self.timestamp).total_seconds() * 1000)
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'event_id': self.event_id,
            'event_type': self.event_type.value,
            'timestamp': self.timestamp.isoformat(),
            'strategy_id': self.strategy_id,
            'environment': self.environment,
            'status': self.status.value,
            'duration_ms': self.duration_ms,
            'metadata': json.dumps(self.metadata, ensure_ascii=False) if isinstance(self.metadata, dict) else self.metadata,
            'error': self.error,
            'error_trace': self.error_trace,
            'session_id': self.session_id,
            'user_id': self.user_id,
        }


class StrategyMonitor:
    """策略模块监控器"""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'aurora_backtest.db'
        )
        
        # 内存中的事件队列
        self.event_queue: deque = deque(maxlen=10000)
        self.recent_events: deque = deque(maxlen=1000)
        
        # 统计数据
        self.stats = defaultdict(int)
        self.optimization_metrics = defaultdict(lambda: {'count': 0, 'total_time': 0, 'success_count': 0, 'failure_count': 0})
        self.backtest_metrics = defaultdict(lambda: {'count': 0, 'total_time': 0, 'success_count': 0, 'failure_count': 0})
        
        # 链路追踪
        self.active_chains = {}
        self.completed_chains = deque(maxlen=100)
        
        # 告警
        self.alerts = deque(maxlen=100)
        
        # 锁
        self._lock = threading.Lock()
        
        # 初始化数据库
        self._init_db()
        
        print("[StrategyMonitor] 策略模块监控系统初始化完成")
    
    def _init_db(self):
        """初始化数据库表"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 策略事件表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS strategy_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT UNIQUE,
                    event_type TEXT,
                    timestamp DATETIME,
                    strategy_id TEXT,
                    environment TEXT,
                    status TEXT,
                    duration_ms INTEGER,
                    metadata TEXT,
                    error TEXT,
                    error_trace TEXT,
                    session_id TEXT,
                    user_id TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 策略监控统计表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS strategy_monitor_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stat_date DATE UNIQUE,
                    total_events INTEGER DEFAULT 0,
                    successful_events INTEGER DEFAULT 0,
                    failed_events INTEGER DEFAULT 0,
                    paper_trades INTEGER DEFAULT 0,
                    live_trades INTEGER DEFAULT 0,
                    rl_optimizations INTEGER DEFAULT 0,
                    v5_optimizations INTEGER DEFAULT 0,
                    v6_optimizations INTEGER DEFAULT 0,
                    backtests INTEGER DEFAULT 0,
                    avg_optimization_time REAL DEFAULT 0,
                    avg_backtest_time REAL DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 策略链路完整性表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS strategy_chains (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chain_id TEXT UNIQUE,
                    strategy_id TEXT,
                    environment TEXT,
                    start_time DATETIME,
                    end_time DATETIME,
                    status TEXT,
                    events_count INTEGER,
                    events_sequence TEXT,
                    duration_ms INTEGER,
                    metadata TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 创建索引
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_strategy_events_type ON strategy_events(event_type)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_strategy_events_strategy ON strategy_events(strategy_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_strategy_events_timestamp ON strategy_events(timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_strategy_events_env ON strategy_events(environment)')
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"[StrategyMonitor] 数据库初始化警告: {e}")
    
    def record_event(self, event: StrategyEvent) -> str:
        """记录事件"""
        with self._lock:
            # 添加到队列
            self.event_queue.append(event)
            self.recent_events.append(event)
            
            # 更新统计
            self.stats['total_events'] += 1
            if event.status == EventStatus.COMPLETED:
                self.stats['successful_events'] += 1
            elif event.status == EventStatus.ERROR:
                self.stats['failed_events'] += 1
            
            # 更新优化器统计
            if event.event_type.value.startswith('optimizer_') or event.event_type.value.startswith('optimization_'):
                if event.event_type.value.startswith('optimizer_'):
                    optimizer_key = event.event_type.value.replace('optimizer_', '').replace('_start', '').replace('_complete', '').replace('_error', '')
                else:
                    optimizer_key = event.event_type.value.replace('optimization_', '').replace('_start', '').replace('_complete', '').replace('_error', '')
                metrics = self.optimization_metrics[optimizer_key]
                if event.status == EventStatus.COMPLETED:
                    metrics['count'] += 1
                    metrics['total_time'] += event.duration_ms
                    metrics['success_count'] += 1
                elif event.status == EventStatus.ERROR:
                    metrics['count'] += 1
                    metrics['failure_count'] += 1
            
            # 更新回测统计
            if event.event_type.value.startswith('backtest_'):
                backtest_key = 'backtest'
                metrics = self.backtest_metrics[backtest_key]
                if event.status == EventStatus.COMPLETED:
                    metrics['count'] += 1
                    metrics['total_time'] += event.duration_ms
                    metrics['success_count'] += 1
                elif event.status == EventStatus.ERROR:
                    metrics['count'] += 1
                    metrics['failure_count'] += 1
            
            # 更新环境统计
            if event.environment == 'paper':
                self.stats['paper_trades'] += 1
            elif event.environment == 'live':
                self.stats['live_trades'] += 1
            
            # 持久化到数据库
            try:
                self._persist_event(event)
            except Exception as e:
                print(f"[StrategyMonitor] 事件持久化失败: {e}")
            
            return event.event_id
    
    def _persist_event(self, event: StrategyEvent):
        """持久化事件到数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO strategy_events 
                (event_id, event_type, timestamp, strategy_id, environment, status, 
                 duration_ms, metadata, error, error_trace, session_id, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                event.event_id,
                event.event_type.value,
                event.timestamp.isoformat(),
                event.strategy_id,
                event.environment,
                event.status.value,
                event.duration_ms,
                json.dumps(event.metadata, ensure_ascii=False) if isinstance(event.metadata, dict) else event.metadata,
                event.error,
                event.error_trace,
                event.session_id,
                event.user_id,
            ))
            
            # 更新每日统计
            today = datetime.now().strftime('%Y-%m-%d')
            cursor.execute('''
                INSERT OR IGNORE INTO strategy_monitor_stats (stat_date) VALUES (?)
            ''', (today,))
            
            cursor.execute('''
                UPDATE strategy_monitor_stats 
                SET total_events = total_events + 1,
                    successful_events = successful_events + ?,
                    failed_events = failed_events + ?,
                    paper_trades = paper_trades + ?,
                    live_trades = live_trades + ?,
                    rl_optimizations = rl_optimizations + ?,
                    v5_optimizations = v5_optimizations + ?,
                    v6_optimizations = v6_optimizations + ?,
                    backtests = backtests + ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE stat_date = ?
            ''', (
                1 if event.status == EventStatus.COMPLETED else 0,
                1 if event.status == EventStatus.ERROR else 0,
                1 if event.environment == 'paper' else 0,
                1 if event.environment == 'live' else 0,
                1 if event.event_type.value.startswith('optimizer_rl') else 0,
                1 if event.event_type.value.startswith('optimizer_v5') else 0,
                1 if event.event_type.value.startswith('optimizer_v6') else 0,
                1 if event.event_type.value.startswith('backtest') else 0,
                today,
            ))
            
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def get_recent_events(self, limit: int = 100, event_type: str = None, 
                          strategy_id: str = None, environment: str = None) -> List[Dict]:
        """获取最近的事件"""
        events = []
        
        with self._lock:
            for event in reversed(self.recent_events):
                if event_type and event.event_type.value != event_type:
                    continue
                if strategy_id and event.strategy_id != strategy_id:
                    continue
                if environment and event.environment != environment:
                    continue
                
                events.append(event.to_dict())
                if len(events) >= limit:
                    break
        
        return events
    
    def get_stats(self) -> Dict:
        """获取监控统计"""
        with self._lock:
            stats = dict(self.stats)
            
            # 计算平均时间
            for opt_key, opt_metrics in self.optimization_metrics.items():
                if opt_metrics['success_count'] > 0:
                    stats[f'{opt_key}_avg_time'] = opt_metrics['total_time'] / opt_metrics['success_count']
                stats[f'{opt_key}_count'] = opt_metrics['count']
                stats[f'{opt_key}_success'] = opt_metrics['success_count']
                stats[f'{opt_key}_failure'] = opt_metrics['failure_count']
            
            for bt_key, bt_metrics in self.backtest_metrics.items():
                if bt_metrics['success_count'] > 0:
                    stats[f'{bt_key}_avg_time'] = bt_metrics['total_time'] / bt_metrics['success_count']
            
            return stats
    
    def get_dashboard_data(self) -> Dict:
        """获取仪表盘数据"""
        return {
            'overview': self.get_stats(),
            'recent_events': self.get_recent_events(limit=20),
            'alerts': list(self.alerts),
            'timestamp': datetime.now().isoformat(),
        }


# ==================== 全局实例 ====================

_global_strategy_monitor: Optional[StrategyMonitor] = None


def get_strategy_monitor(db_path: str = None) -> StrategyMonitor:
    """获取全局策略监控器实例"""
    global _global_strategy_monitor
    if _global_strategy_monitor is None:
        _global_strategy_monitor = StrategyMonitor(db_path=db_path)
    return _global_strategy_monitor


# ==================== 快捷函数 ====================

def monitor_event(event_type: StrategyEventType, strategy_id: str = None,
                  environment: str = None, metadata: Dict = None,
                  auto_start: bool = True) -> StrategyEvent:
    """创建并记录事件（快捷函数）"""
    monitor = get_strategy_monitor()
    event = StrategyEvent(event_type, strategy_id, environment, metadata)
    if auto_start:
        event.start()
    monitor.record_event(event)
    return event
