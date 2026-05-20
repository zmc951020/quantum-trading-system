#!/usr/bin/env python3
"""
切换历史记录模块
追踪和记录所有系统切换操作，支持查询、统计和审计

功能：
1. 切换事件记录
2. 切换历史查询
3. 切换统计信息
4. 切换频率监控
5. 持久化存储（数据库 + 文件）
"""

import json
import os
import threading
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


@dataclass
class SwitchRecord:
    """切换记录数据结构"""
    switch_id: str
    switch_type: str               # 切换类型：data_source, strategy, mode, manual
    from_value: str                # 切换前值
    to_value: str                  # 切换后值
    reason: str                    # 切换原因
    triggered_by: str = 'system'   # 触发者：system, manual, auto
    success: bool = True
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    duration_ms: float = 0.0       # 切换耗时（毫秒）
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'switch_id': self.switch_id,
            'switch_type': self.switch_type,
            'from_value': self.from_value,
            'to_value': self.to_value,
            'reason': self.reason,
            'triggered_by': self.triggered_by,
            'success': self.success,
            'details': self.details,
            'timestamp': self.timestamp.isoformat(),
            'duration_ms': self.duration_ms,
        }


class SwitchHistory:
    """切换历史管理器（单例）"""
    
    _instance: Optional['SwitchHistory'] = None
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
        
        self._records: List[SwitchRecord] = []
        self._max_memory_records = 10000
        self._db_manager = None
        self._file_path = 'switch_history.json'
        self._initialized = True
        
        # 从文件加载历史记录
        self._load_from_file()
        logger.info(f"[SwitchHistory] 切换历史管理器已初始化，已加载 {len(self._records)} 条记录")
    
    def set_db_manager(self, db_manager):
        """设置数据库管理器"""
        self._db_manager = db_manager
    
    def record(self, switch_type: str, from_value: str, to_value: str,
               reason: str = '', triggered_by: str = 'system',
               success: bool = True, details: Dict = None,
               duration_ms: float = 0.0) -> Optional[SwitchRecord]:
        """
        记录一次切换
        
        Args:
            switch_type: 切换类型
            from_value: 切换前值
            to_value: 切换后值
            reason: 切换原因
            triggered_by: 触发者
            success: 是否成功
            details: 详细信息
            duration_ms: 耗时
        
        Returns:
            SwitchRecord: 记录对象
        """
        switch_id = f"SW_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(self._records)}"
        
        record = SwitchRecord(
            switch_id=switch_id,
            switch_type=switch_type,
            from_value=str(from_value),
            to_value=str(to_value),
            reason=reason,
            triggered_by=triggered_by,
            success=success,
            details=details or {},
            duration_ms=duration_ms
        )
        
        # 内存记录
        self._records.append(record)
        if len(self._records) > self._max_memory_records:
            self._records = self._records[-self._max_memory_records:]
        
        # 持久化到文件（异步保存最近100条）
        if len(self._records) % 10 == 0:
            self._save_to_file()
        
        # 数据库记录
        if self._db_manager:
            try:
                self._db_manager.insert_system_log(
                    'INFO' if success else 'ERROR',
                    'SwitchHistory',
                    f'{switch_type}_switch',
                    f'{from_value} -> {to_value}: {reason}'
                )
            except Exception as e:
                logger.warning(f"[SwitchHistory] 数据库记录失败: {e}")
        
        logger.info(f"[SwitchHistory] 切换记录: {switch_type} {from_value} -> {to_value} "
                    f"({'成功' if success else '失败'})")
        
        return record
    
    def query(self, switch_type: str = None, from_time: datetime = None,
              to_time: datetime = None, success_only: bool = None,
              limit: int = 100, offset: int = 0) -> List[Dict]:
        """
        查询切换历史
        
        Args:
            switch_type: 按类型过滤
            from_time: 起始时间
            to_time: 结束时间
            success_only: 是否只查成功的
            limit: 返回数量
            offset: 偏移量
        
        Returns:
            切换记录列表
        """
        records = list(self._records)
        
        # 过滤
        if switch_type:
            records = [r for r in records if r.switch_type == switch_type]
        if from_time:
            records = [r for r in records if r.timestamp >= from_time]
        if to_time:
            records = [r for r in records if r.timestamp <= to_time]
        if success_only is not None:
            records = [r for r in records if r.success == success_only]
        
        # 分页
        records = records[offset:offset + limit]
        
        return [r.to_dict() for r in records]
    
    def get_statistics(self, hours: int = 24) -> Dict[str, Any]:
        """
        获取切换统计信息
        
        Args:
            hours: 统计时间范围（小时）
        
        Returns:
            统计信息字典
        """
        since = datetime.now() - timedelta(hours=hours)
        recent = [r for r in self._records if r.timestamp >= since]
        
        # 按类型统计
        type_stats = defaultdict(int)
        for r in recent:
            type_stats[r.switch_type] += 1
        
        # 按触发者统计
        trigger_stats = defaultdict(int)
        for r in recent:
            trigger_stats[r.triggered_by] += 1
        
        # 成功率
        success_count = sum(1 for r in recent if r.success)
        
        return {
            'total_switches': len(recent),
            'time_range_hours': hours,
            'by_type': dict(type_stats),
            'by_trigger': dict(trigger_stats),
            'success_rate': success_count / len(recent) * 100 if recent else 100,
            'last_switch': recent[-1].to_dict() if recent else None,
            'avg_duration_ms': sum(r.duration_ms for r in recent) / len(recent) if recent else 0,
        }
    
    def get_current_state(self) -> Dict[str, str]:
        """
        获取当前各组件状态
        
        基于最近的切换记录推断当前状态
        """
        state = {}
        for switch_type in ['data_source', 'strategy', 'mode']:
            # 找到最近一次成功的切换
            type_records = [r for r in self._records 
                          if r.switch_type == switch_type and r.success]
            if type_records:
                state[switch_type] = type_records[-1].to_value
            else:
                state[switch_type] = 'unknown'
        
        return state
    
    def check_frequency_limits(self, max_per_hour: int = 10) -> Dict[str, Any]:
        """
        检查切换频率是否超过限制
        
        Args:
            max_per_hour: 每小时最大切换次数
        
        Returns:
            频率检查结果
        """
        one_hour_ago = datetime.now() - timedelta(hours=1)
        recent_hour = [r for r in self._records if r.timestamp >= one_hour_ago]
        
        # 按类型统计
        freq_by_type = defaultdict(int)
        for r in recent_hour:
            freq_by_type[r.switch_type] += 1
        
        # 检查告警
        alerts = []
        for stype, count in freq_by_type.items():
            if count > max_per_hour:
                alerts.append(f"{stype}: {count}/{max_per_hour}/小时 (超限)")
        
        return {
            'within_limits': len(alerts) == 0,
            'hourly_counts': dict(freq_by_type),
            'limit': max_per_hour,
            'alerts': alerts,
            'total_hourly': len(recent_hour),
        }
    
    def _save_to_file(self):
        """保存到文件"""
        try:
            # 只保存最近1000条到文件
            records_to_save = self._records[-1000:]
            with open(self._file_path, 'w', encoding='utf-8') as f:
                json.dump([r.to_dict() for r in records_to_save], 
                         f, indent=2, ensure_ascii=False, default=str)
        except Exception as e:
            logger.error(f"[SwitchHistory] 保存文件失败: {e}")
    
    def _load_from_file(self):
        """从文件加载"""
        if os.path.exists(self._file_path):
            try:
                with open(self._file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                for item in data:
                    record = SwitchRecord(
                        switch_id=item.get('switch_id', ''),
                        switch_type=item.get('switch_type', ''),
                        from_value=item.get('from_value', ''),
                        to_value=item.get('to_value', ''),
                        reason=item.get('reason', ''),
                        triggered_by=item.get('triggered_by', 'system'),
                        success=item.get('success', True),
                        details=item.get('details', {}),
                        duration_ms=item.get('duration_ms', 0.0),
                    )
                    if 'timestamp' in item:
                        try:
                            record.timestamp = datetime.fromisoformat(item['timestamp'])
                        except ValueError:
                            pass
                    self._records.append(record)
                    
                logger.info(f"[SwitchHistory] 从文件加载了 {len(data)} 条历史记录")
            except Exception as e:
                logger.warning(f"[SwitchHistory] 加载文件失败: {e}")
    
    def clear(self, before: datetime = None):
        """
        清除历史记录
        
        Args:
            before: 清除此时间之前的记录
        """
        if before:
            self._records = [r for r in self._records if r.timestamp >= before]
        else:
            self._records = []
        
        self._save_to_file()
        logger.info(f"[SwitchHistory] 已清除历史记录，剩余 {len(self._records)} 条")
    
    def __len__(self) -> int:
        return len(self._records)


# 全局实例
_global_switch_history: Optional[SwitchHistory] = None


def get_switch_history() -> SwitchHistory:
    """获取全局切换历史实例（单例）"""
    global _global_switch_history
    if _global_switch_history is None:
        _global_switch_history = SwitchHistory()
    return _global_switch_history