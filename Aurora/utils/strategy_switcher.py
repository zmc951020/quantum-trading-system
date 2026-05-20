#!/usr/bin/env python3
"""
策略切换器
管理多策略的注册、性能跟踪和自动切换

功能：
1. 策略注册与管理
2. 基于性能的自动切换
3. 策略预热机制
4. 市场状态适配
5. 策略表现追踪
"""

import threading
import time
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import logging

from utils.switch_event_bus import get_event_bus, EventType
from utils.switch_config import get_switch_config
from utils.switch_history import get_switch_history

logger = logging.getLogger(__name__)


@dataclass
class StrategyPerformance:
    """策略表现追踪"""
    name: str
    total_signals: int = 0
    successful_signals: int = 0
    total_pnl: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    avg_return: float = 0.0
    last_updated: datetime = field(default_factory=datetime.now)
    evaluation_window: int = 100  # 评估窗口大小


@dataclass
class StrategyInfo:
    """策略信息"""
    name: str
    instance: Any = None
    enabled: bool = True
    market_regimes: List[str] = field(default_factory=list)  # 适配的市场状态
    weight: float = 1.0
    min_warmup_bars: int = 100
    performance: StrategyPerformance = None
    
    def __post_init__(self):
        if self.performance is None:
            self.performance = StrategyPerformance(name=self.name)


class StrategySwitcher:
    """
    策略切换器（单例）
    """
    
    _instance: Optional['StrategySwitcher'] = None
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
        
        self._strategies: Dict[str, StrategyInfo] = {}
        self._current_strategy: Optional[StrategyInfo] = None
        self._config = get_switch_config()
        self._event_bus = get_event_bus()
        self._history = get_switch_history()
        self._last_switch_time: Optional[datetime] = None
        self._switch_lock = threading.Lock()
        self._switch_count_hour = 0
        self._performance_memory: Dict[str, List[float]] = {}  # 策略名 -> 最近表现列表
        self._on_switch_callback: Optional[Callable] = None
        self._market_regime: str = 'unknown'
        self._initialized = True
        
        logger.info("[StrategySwitcher] 策略切换器已初始化")
    
    def register_strategy(self, name: str, strategy_instance: Any,
                          market_regimes: List[str] = None, 
                          weight: float = 1.0,
                          min_warmup_bars: int = 100):
        """
        注册策略
        
        Args:
            name: 策略名称
            strategy_instance: 策略实例
            market_regimes: 适配的市场状态列表
            weight: 策略权重
            min_warmup_bars: 最少预热K线数
        """
        info = StrategyInfo(
            name=name,
            instance=strategy_instance,
            market_regimes=market_regimes or ['all'],
            weight=weight,
            min_warmup_bars=min_warmup_bars,
        )
        self._strategies[name] = info
        
        if self._current_strategy is None:
            self._current_strategy = info
        
        self._performance_memory[name] = []
        logger.info(f"[StrategySwitcher] 已注册策略: {name}")
    
    def set_on_switch_callback(self, callback: Callable):
        """设置切换回调"""
        self._on_switch_callback = callback
    
    def set_market_regime(self, regime: str):
        """设置当前市场状态"""
        self._market_regime = regime
        
        # 如果启用了基于市场状态的自动切换
        if self._config.get('auto_strategy_switch', False):
            self._evaluate_market_switch()
    
    @property
    def current_strategy(self) -> str:
        """获取当前策略名称"""
        return self._current_strategy.name if self._current_strategy else 'none'
    
    def get_current_strategy_info(self) -> Dict[str, Any]:
        """获取当前策略详细信息"""
        if not self._current_strategy:
            return {'name': 'none', 'active': False}
        
        perf = self._current_strategy.performance
        return {
            'name': self._current_strategy.name,
            'active': self._current_strategy.enabled,
            'market_regimes': self._current_strategy.market_regimes,
            'weight': self._current_strategy.weight,
            'performance': {
                'total_signals': perf.total_signals,
                'win_rate': perf.win_rate,
                'sharpe_ratio': perf.sharpe_ratio,
                'max_drawdown': perf.max_drawdown,
                'avg_return': perf.avg_return,
                'total_pnl': perf.total_pnl,
            }
        }
    
    def list_strategies(self) -> List[Dict]:
        """列出所有策略"""
        result = []
        for name, info in self._strategies.items():
            perf = info.performance
            result.append({
                'name': name,
                'enabled': info.enabled,
                'is_current': info == self._current_strategy,
                'market_regimes': info.market_regimes,
                'weight': info.weight,
                'win_rate': perf.win_rate,
                'sharpe_ratio': perf.sharpe_ratio,
                'total_pnl': perf.total_pnl,
            })
        return result
    
    def update_performance(self, strategy_name: str, pnl: float = 0,
                           signal_success: bool = None, drawdown: float = 0):
        """
        更新策略表现
        
        Args:
            strategy_name: 策略名称
            pnl: 盈亏
            signal_success: 信号是否成功
            drawdown: 当前回撤
        """
        if strategy_name not in self._strategies:
            return
        
        perf = self._strategies[strategy_name].performance
        perf.total_pnl += pnl
        
        if signal_success is not None:
            perf.total_signals += 1
            if signal_success:
                perf.successful_signals += 1
            perf.win_rate = (perf.successful_signals / perf.total_signals) * 100
        
        if drawdown > perf.max_drawdown:
            perf.max_drawdown = drawdown
        
        perf.last_updated = datetime.now()
        
        # 更新表现记忆
        if strategy_name in self._performance_memory:
            self._performance_memory[strategy_name].append(pnl)
            if len(self._performance_memory[strategy_name]) > 500:
                self._performance_memory[strategy_name] = \
                    self._performance_memory[strategy_name][-500:]
    
    def switch_to(self, target_name: str, warmup: bool = True,
                  reason: str = '') -> Dict[str, Any]:
        """
        切换到指定策略
        
        Args:
            target_name: 目标策略名称
            warmup: 是否预热
            reason: 切换原因
        
        Returns:
            切换结果
        """
        with self._switch_lock:
            if target_name not in self._strategies:
                return {'success': False, 'error': f'未知策略: {target_name}'}
            
            target = self._strategies[target_name]
            if not target.enabled:
                return {'success': False, 'error': f'策略已禁用: {target_name}'}
            
            if target == self._current_strategy:
                return {'success': True, 'message': f'已在使用: {target_name}'}
            
            old_name = self._current_strategy.name if self._current_strategy else 'none'
            start_time = time.time()
            
            try:
                # 预热
                if warmup and target.instance:
                    if hasattr(target.instance, 'warmup'):
                        target.instance.warmup(target.min_warmup_bars)
                    elif hasattr(target.instance, 'initialize'):
                        target.instance.initialize()
                
                self._current_strategy = target
                self._last_switch_time = datetime.now()
                
                # 记录历史
                self._history.record(
                    switch_type='strategy',
                    from_value=old_name,
                    to_value=target_name,
                    reason=reason or '手动切换',
                    triggered_by='manual',
                    duration_ms=(time.time() - start_time) * 1000
                )
                
                # 发布事件
                self._event_bus.publish_immediate(
                    EventType.STRATEGY_SWITCHED,
                    source='StrategySwitcher',
                    data={
                        'from': old_name,
                        'to': target_name,
                        'reason': reason or '手动切换',
                        'warmup': warmup,
                    }
                )
                
                # 调用回调
                if self._on_switch_callback:
                    try:
                        self._on_switch_callback(old_name, target_name, reason)
                    except Exception as e:
                        logger.error(f"[StrategySwitcher] 切换回调异常: {e}")
                
                logger.info(f"[StrategySwitcher] 策略切换完成: {old_name} -> {target_name}")
                
                return {
                    'success': True,
                    'from': old_name,
                    'to': target_name,
                    'warmup': warmup,
                }
                
            except Exception as e:
                logger.error(f"[StrategySwitcher] 切换失败: {e}")
                return {'success': False, 'error': str(e)}
    
    def _evaluate_market_switch(self):
        """评估是否需要根据市场状态切换策略"""
        best_match = None
        best_score = -1
        
        for name, info in self._strategies.items():
            if not info.enabled or info == self._current_strategy:
                continue
            
            # 检查市场状态匹配
            if self._market_regime in info.market_regimes or 'all' in info.market_regimes:
                # 基于表现评分
                score = self._calculate_strategy_score(info)
                if score > best_score:
                    best_score = score
                    best_match = info
        
        if best_match and best_score > 0:
            logger.info(f"[StrategySwitcher] 市场状态 {self._market_regime} 推荐策略: {best_match.name}")
            
            # 检查切换阈值
            threshold = self._config.get('strategy_switch_threshold', 0.7)
            current_score = self._calculate_strategy_score(self._current_strategy) \
                if self._current_strategy else 0
            
            if best_score > current_score * threshold:
                self._auto_switch(best_match)
    
    def _calculate_strategy_score(self, info: StrategyInfo) -> float:
        """计算策略综合评分"""
        if not info:
            return 0
        
        perf = info.performance
        score = 0
        
        # 胜率贡献
        if perf.total_signals > 10:
            score += perf.win_rate * 0.4
        
        # 夏普比率贡献
        score += min(perf.sharpe_ratio, 3) * 0.3 / 3 * 100
        
        # 回撤惩罚
        score -= min(perf.max_drawdown, 30) * 0.2
        
        # 权重
        score *= info.weight
        
        return max(score, 0)
    
    def _auto_switch(self, target: StrategyInfo):
        """自动切换策略"""
        with self._switch_lock:
            # 检查冷却
            if self._last_switch_time:
                cooldown = self._config.get('switch_cooldown', 60)
                elapsed = (datetime.now() - self._last_switch_time).total_seconds()
                if elapsed < cooldown:
                    logger.warning(f"[StrategySwitcher] 切换冷却中 (剩余 {cooldown - elapsed:.0f}s)")
                    return
            
            self.switch_to(
                target.name,
                warmup=True,
                reason=f'市场状态自动切换 ({self._market_regime})'
            )
    
    def enable_strategy(self, name: str):
        """启用策略"""
        if name in self._strategies:
            self._strategies[name].enabled = True
            logger.info(f"[StrategySwitcher] 已启用策略: {name}")
    
    def disable_strategy(self, name: str):
        """禁用策略"""
        if name in self._strategies:
            if self._strategies[name] == self._current_strategy:
                logger.warning(f"[StrategySwitcher] 不能禁用当前策略: {name}")
                return
            self._strategies[name].enabled = False
            logger.info(f"[StrategySwitcher] 已禁用策略: {name}")
    
    def get_status(self) -> Dict[str, Any]:
        """获取切换器状态"""
        return {
            'current_strategy': self.current_strategy,
            'strategies': self.list_strategies(),
            'last_switch': self._last_switch_time.isoformat() if self._last_switch_time else None,
            'market_regime': self._market_regime,
            'auto_switch_enabled': self._config.get('auto_strategy_switch', False),
        }


# 全局实例
_global_strategy_switcher: Optional[StrategySwitcher] = None


def get_strategy_switcher() -> StrategySwitcher:
    """获取全局策略切换器实例（单例）"""
    global _global_strategy_switcher
    if _global_strategy_switcher is None:
        _global_strategy_switcher = StrategySwitcher()
    return _global_strategy_switcher