#!/usr/bin/env python3
"""
策略组合管理类
支持多策略协同运行和资金分配
"""

import time
from typing import List, Dict, Any, Optional
from strategies.strategy_base import StrategyBase

class StrategyCombiner:
    """
    策略组合管理类
    """

    def __init__(self, initial_balance: float = 100000.0):
        """
        初始化策略组合

        Args:
            initial_balance: 初始资金
        """
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.strategies = []
        self.strategy_weights = []
        self.strategy_allocations = []
        self.performance_history = []
        self.trades = []

    def add_strategy(self, strategy: StrategyBase, weight: float = 0.33):
        """
        添加策略到组合

        Args:
            strategy: 策略实例
            weight: 策略权重（0-1之间）
        """
        if not 0 <= weight <= 1:
            raise ValueError("权重必须在0-1之间")

        self.strategies.append(strategy)
        self.strategy_weights.append(weight)
        self._update_allocations()

    def remove_strategy(self, strategy_index: int):
        """
        从组合中移除策略

        Args:
            strategy_index: 策略索引
        """
        if 0 <= strategy_index < len(self.strategies):
            self.strategies.pop(strategy_index)
            self.strategy_weights.pop(strategy_index)
            self._update_allocations()

    def update_strategy_weight(self, strategy_index: int, weight: float):
        """
        更新策略权重

        Args:
            strategy_index: 策略索引
            weight: 新权重（0-1之间）
        """
        if not 0 <= weight <= 1:
            raise ValueError("权重必须在0-1之间")

        if 0 <= strategy_index < len(self.strategy_weights):
            self.strategy_weights[strategy_index] = weight
            self._update_allocations()

    def _update_allocations(self):
        """
        更新策略资金分配
        """
        total_weight = sum(self.strategy_weights)
        if total_weight == 0:
            self.strategy_allocations = []
            return

        # 归一化权重
        normalized_weights = [w / total_weight for w in self.strategy_weights]
        self.strategy_allocations = [w * self.current_balance for w in normalized_weights]

        # 更新每个策略的资金
        for i, (strategy, allocation) in enumerate(zip(self.strategies, self.strategy_allocations)):
            strategy.initial_balance = allocation
            strategy.current_balance = allocation

    def update_price(self, price: float):
        """
        更新价格并执行所有策略

        Args:
            price: 当前价格
        """
        total_balance = 0

        for i, (strategy, allocation) in enumerate(zip(self.strategies, self.strategy_allocations)):
            strategy.update_price(price)
            total_balance += strategy.current_balance

        self.current_balance = total_balance
        self._update_allocations()

        # 记录性能历史
        self.performance_history.append({
            'timestamp': time.time(),
            'balance': self.current_balance,
            'total_return': (self.current_balance - self.initial_balance) / self.initial_balance
        })

    def get_performance(self) -> Dict[str, Any]:
        """
        获取组合性能

        Returns:
            性能指标
        """
        total_return = (self.current_balance - self.initial_balance) / self.initial_balance
        strategies_performance = []

        for i, strategy in enumerate(self.strategies):
            perf = strategy.get_performance()
            strategies_performance.append({
                'name': strategy.__class__.__name__,
                'weight': self.strategy_weights[i],
                'allocation': self.strategy_allocations[i],
                'performance': perf
            })

        return {
            'total_balance': self.current_balance,
            'total_return': total_return,
            'initial_balance': self.initial_balance,
            'strategies': strategies_performance,
            'num_strategies': len(self.strategies)
        }

    def get_strategies(self) -> List[Dict[str, Any]]:
        """
        获取策略列表

        Returns:
            策略信息列表
        """
        strategies_info = []
        for i, (strategy, weight, allocation) in enumerate(zip(self.strategies, self.strategy_weights, self.strategy_allocations)):
            strategies_info.append({
                'index': i,
                'name': strategy.__class__.__name__,
                'weight': weight,
                'allocation': allocation,
                'balance': strategy.current_balance
            })
        return strategies_info

    def adjust_allocations(self, market_state: Dict[str, Any]):
        """
        根据市场状态调整策略权重

        Args:
            market_state: 市场状态信息
        """
        # 基于市场状态的权重调整逻辑
        if market_state.get('volatility') == 'high':
            # 高波动市场，增加网格策略权重
            for i, strategy in enumerate(self.strategies):
                if 'Grid' in strategy.__class__.__name__:
                    self.strategy_weights[i] = min(0.6, self.strategy_weights[i] + 0.1)
        elif market_state.get('trend') == 'strong':
            # 强趋势市场，增加趋势策略权重
            for i, strategy in enumerate(self.strategies):
                if 'Trend' in strategy.__class__.__name__ or 'Fourier' in strategy.__class__.__name__:
                    self.strategy_weights[i] = min(0.6, self.strategy_weights[i] + 0.1)

        self._update_allocations()

    def reset(self):
        """
        重置策略组合
        """
        self.current_balance = self.initial_balance
        self.performance_history = []
        self.trades = []
        self._update_allocations()

        for strategy in self.strategies:
            strategy.reset()

    def get_trades(self) -> List[Dict[str, Any]]:
        """
        获取所有策略的交易记录

        Returns:
            交易记录列表
        """
        all_trades = []
        for i, strategy in enumerate(self.strategies):
            strategy_trades = strategy.get_trades()
            for trade in strategy_trades:
                trade['strategy'] = strategy.__class__.__name__
                trade['strategy_index'] = i
                all_trades.append(trade)
        return all_trades