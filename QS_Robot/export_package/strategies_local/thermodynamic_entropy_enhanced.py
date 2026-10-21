#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ThermodynamicEntropyEnhanced - 热力学熵优化增强策略
=====================================================
基于统计力学模型的熵优化版本

物理原理：
1. 熵最大化：系统趋于最大熵状态（不确定性最大的平衡态）
2. 自由能最小化：系统在平衡态时自由能最小
3. 热力学第二定律：熵只增不减

金融映射：
1. 熵 → 市场不确定性/信息熵
2. 自由能 → 风险调整后收益（类似Sharpe比率）
3. 温度 → 波动率
4. 相态 → 市场状态（牛市/熊市/震荡）

增强特点：
- 信息熵计算
- 风险熵优化组合
- 波动率温度模型
- 市场相态识别
- 与原始MLRangeGridTrading完全独立

继承关系：
- 基于ml_range_grid.py的核心逻辑
- 增加热力学/熵优化增强层
- 不修改原始代码
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime
import sys
import os

# 添加Aurora根目录到路径
aurora_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if aurora_root not in sys.path:
    sys.path.insert(0, aurora_root)

try:
    from strategies.aurora_risk_engine import AuroraRiskEngine
except ImportError:
    AuroraRiskEngine = None

class ThermodynamicEntropyCalculator:
    """
    热力学熵计算器
    将市场类比为热力学系统，计算各种"热力学"指标
    """

    def __init__(self):
        self.price_history = []
        self.volume_history = []
        self.return_history = []

    def add_data(self, price: float, volume: float = 1.0):
        """添加价格和成交量数据"""
        self.price_history.append(price)
        self.volume_history.append(volume)

        # 计算收益率
        if len(self.price_history) > 1:
            ret = (price - self.price_history[-2]) / self.price_history[-2]
            self.return_history.append(ret)

        # 保持最近500个数据点
        if len(self.price_history) > 500:
            self.price_history = self.price_history[-500:]
            self.volume_history = self.volume_history[-500:]
            self.return_history = self.return_history[-500:]

    def calculate_information_entropy(self, period: int = 20, bins: int = 10) -> float:
        """
        计算信息熵（Shannon Entropy）
        熵越高，市场越"混乱"，不确定性越大

        H = -Σ p(x) × log(p(x))
        """
        if len(self.return_history) < period:
            return 0.0

        returns = np.array(self.return_history[-period:])

        # 计算收益率分布
        hist, _ = np.histogram(returns, bins=bins, range=(-0.1, 0.1))
        prob = hist / np.sum(hist)

        # 去除零概率（避免log(0)）
        prob = prob[prob > 0]

        # 计算香农熵
        entropy = -np.sum(prob * np.log2(prob))

        return entropy

    def calculate_volatility_temperature(self, period: int = 20) -> float:
        """
        计算波动率温度
        温度越高，波动越剧烈（类比：气体分子运动越剧烈）

        T ∝ σ²（波动率的平方）
        """
        if len(self.return_history) < period:
            return 0.0

        returns = np.array(self.return_history[-period:])

        # 波动率
        volatility = np.std(returns)

        # 温度（波动率的平方，归一化）
        temperature = volatility ** 2 * 100

        return temperature

    def calculate_free_energy(self, period: int = 20, risk_free_rate: float = 0.02) -> float:
        """
        计算自由能（类比Helmholtz自由能）
        自由能越小，系统越"稳定"

        F = E - T × S
        F: 自由能
        E: 期望收益
        T: 温度（波动率）
        S: 熵
        """
        if len(self.return_history) < period:
            return 0.0

        returns = np.array(self.return_history[-period:])

        # 期望收益（年化）
        expected_return = np.mean(returns) * 252

        # 波动率
        volatility = np.std(returns) * np.sqrt(252)

        # 温度
        temperature = volatility

        # 熵
        entropy = self.calculate_information_entropy(period)

        # 自由能 = 收益 - 温度 × 熵
        free_energy = expected_return - temperature * entropy

        return free_energy

    def calculate_phase_state(self, period: int = 20) -> str:
        """
        计算市场相态
        类比：固体（冻结）、液体（横盘）、气体（趋势）

        Returns:
            'solid': 高熵低能，市场冻结
            'liquid': 中等熵，市场横盘
            'gas_up': 低熵高能，趋势上涨
            'gas_down': 低熵高能，趋势下跌
        """
        if len(self.return_history) < period:
            return 'liquid'

        returns = np.array(self.return_history[-period:])

        # 计算指标
        entropy = self.calculate_information_entropy(period)
        temperature = self.calculate_volatility_temperature(period)
        mean_return = np.mean(returns)

        # 判断相态
        if entropy > 4.0 and temperature < 0.5:
            return 'solid'  # 高熵低温，市场冻结
        elif entropy > 3.5 and 0.5 <= temperature < 1.5:
            return 'liquid'  # 中等熵温，市场横盘
        elif entropy < 3.0 and mean_return > 0.001:
            return 'gas_up'  # 低熵高能，趋势上涨
        elif entropy < 3.0 and mean_return < -0.001:
            return 'gas_down'  # 低熵高能，趋势下跌
        else:
            return 'liquid'

class ThermodynamicEntropyEnhanced:
    """
    热力学熵优化增强策略
    基于统计力学模型的网格交易策略

    策略逻辑：
    1. 计算市场熵和温度
    2. 识别市场相态
    3. 计算自由能优化方向
    4. 自适应网格交易
    """

    def __init__(self, base_price: float, initial_balance: float = 100000,
                 use_daily: bool = False):
        self.base_price = base_price
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.position = 0
        self.price_history = []
        self.is_active = True
        self.last_price = base_price
        self.last_buy_price = base_price
        self.entry_price = 0
        self.consecutive_holds = 0
        self.use_daily = use_daily

        self.entropy_calc = ThermodynamicEntropyCalculator()

        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.profit_history = []

        self.market_type = 'range_bound'
        self.market_types = ['range_bound', 'trending_up', 'trending_down', 'volatile']

        self.grid_levels = 20 if use_daily else 40
        self.grid_spacing = 0.0080 if use_daily else 0.0040
        self.grids = self._create_grids()
        self.last_grid_index = self.grid_levels

        self.stop_loss_threshold = 0.03 if use_daily else 0.010
        self.take_profit_threshold = 0.05 if use_daily else 0.015
        self.max_position_percentage = 0.5

        self.entropy_threshold = 3.5
        self.temperature_threshold = 1.0
        self.free_energy_threshold = 0.0
        self.confidence_threshold = 0.6

        self.rsi_period = 14
        self.bollinger_period = 20
        self.bollinger_std = 2

        self.bb_entry_threshold = -1.5
        self.bb_exit_threshold = 1.5

    def _create_grids(self) -> List[float]:
        grids = []
        price_range = self.base_price * 0.1
        for i in range(self.grid_levels + 1):
            grid_price = self.base_price - price_range / 2 + (price_range * i / self.grid_levels)
            grids.append(grid_price)
        return grids

    def calculate_all_thermodynamic_metrics(self) -> Dict[str, float]:
        metrics = {}
        metrics['entropy'] = self.entropy_calc.calculate_information_entropy(period=20)
        metrics['temperature'] = self.entropy_calc.calculate_volatility_temperature(period=20)
        metrics['free_energy'] = self.entropy_calc.calculate_free_energy(period=20)
        for period in [10, 20, 40]:
            metrics[f'entropy_{period}'] = self.entropy_calc.calculate_information_entropy(period=period)
            metrics[f'temperature_{period}'] = self.entropy_calc.calculate_volatility_temperature(period=period)
            metrics[f'free_energy_{period}'] = self.entropy_calc.calculate_free_energy(period=period)
        metrics['phase_state'] = self.entropy_calc.calculate_phase_state(period=20)
        return metrics

    def determine_trading_signal(self, metrics: Dict[str, float]) -> Tuple[str, float]:
        entropy = metrics.get('entropy_20', 0.0)
        temperature = metrics.get('temperature_20', 0.0)
        phase_state = metrics.get('phase_state', 'liquid')
        confidence = 0.0
        if entropy < self.entropy_threshold:
            confidence += 0.3
        if temperature > self.temperature_threshold:
            confidence += 0.2
        if phase_state in ['gas_up', 'gas_down']:
            confidence += 0.3
        confidence = min(1.0, confidence / 0.8)
        if phase_state == 'gas_up' and confidence >= self.confidence_threshold:
            signal = 'buy'
        elif phase_state == 'gas_down' and confidence >= self.confidence_threshold:
            signal = 'sell'
        elif entropy > 4.0:
            signal = 'hold'
        else:
            signal = 'hold'
        return signal, confidence

    def check_thermodynamic_conditions(self, metrics: Dict[str, float]) -> Dict[str, bool]:
        conditions = {}
        conditions['low_entropy'] = metrics.get('entropy_20', 0.0) < self.entropy_threshold
        conditions['high_temperature'] = metrics.get('temperature_20', 0.0) > self.temperature_threshold
        conditions['low_free_energy'] = metrics.get('free_energy_20', 0.0) < self.free_energy_threshold
        phase_state = metrics.get('phase_state', 'liquid')
        conditions['phase_transition'] = phase_state in ['gas_up', 'gas_down']
        return conditions

    def calculate_rsi(self, period: int = 14) -> float:
        if len(self.price_history) < period + 1:
            return 50.0
        prices = np.array(self.price_history)
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def calculate_bollinger_position(self) -> float:
        if len(self.price_history) < self.bollinger_period:
            return 0.5
        prices = np.array(self.price_history[-self.bollinger_period:])
        current_price = self.price_history[-1]
        mean = np.mean(prices)
        std = np.std(prices)
        if std == 0:
            return 0.5
        return (current_price - mean) / (self.bollinger_std * std)

    @staticmethod
    def detect_market_type(data: np.ndarray, period: int = 20) -> str:
        if len(data) < period:
            return 'range_bound'
        segment = data[-period:]
        x = np.arange(period)
        slope, _ = np.polyfit(x, segment, 1)
        trend = slope / (np.mean(segment) + 1e-10)
        volatility = np.std(segment) / (np.mean(segment) + 1e-10)
        range_ratio = (np.max(segment) - np.min(segment)) / (np.mean(segment) + 1e-10)
        if abs(trend) < 0.0005 and volatility < 0.02 and range_ratio < 0.05:
            return 'range_bound'
        if volatility > 0.04 or range_ratio > 0.10:
            return 'volatile'
        if trend > 0.001:
            return 'trending_up'
        if trend < -0.001:
            return 'trending_down'
        return 'range_bound'

    @staticmethod
    def get_adaptive_params(market_type: str, use_daily: bool = False) -> dict:
        if use_daily:
            params = {
                'trending_up': {'stop_loss': 0.03, 'take_profit': 0.08, 'max_position': 0.6},
                'trending_down': {'stop_loss': 0.02, 'take_profit': 0.06, 'max_position': 0.3},
                'range_bound': {'stop_loss': 0.025, 'take_profit': 0.05, 'max_position': 0.4},
                'volatile': {'stop_loss': 0.02, 'take_profit': 0.06, 'max_position': 0.25},
            }
        else:
            params = {
                'trending_up': {'stop_loss': 0.012, 'take_profit': 0.025, 'max_position': 0.6},
                'trending_down': {'stop_loss': 0.008, 'take_profit': 0.020, 'max_position': 0.3},
                'range_bound': {'stop_loss': 0.010, 'take_profit': 0.015, 'max_position': 0.4},
                'volatile': {'stop_loss': 0.007, 'take_profit': 0.020, 'max_position': 0.25},
            }
        return params.get(market_type, params['range_bound'])

    def update_price(self, current_price: float, volume: float = 1.0) -> Dict[str, Any]:
        self.price_history.append(current_price)
        if len(self.price_history) > 1000:
            self.price_history = self.price_history[-1000:]

        self.entropy_calc.add_data(current_price, volume)

        metrics = self.calculate_all_thermodynamic_metrics()
        signal, confidence = self.determine_trading_signal(metrics)
        self.confidence = confidence
        self.phase_state = metrics.get('phase_state', 'liquid')

        conditions = self.check_thermodynamic_conditions(metrics)
        rsi = self.calculate_rsi()
        bb_position = self.calculate_bollinger_position()

        self.market_type = self.detect_market_type(np.array(self.price_history))
        adaptive = self.get_adaptive_params(self.market_type, self.use_daily)
        self.stop_loss_threshold = adaptive.get('stop_loss', 0.03)
        self.take_profit_threshold = adaptive.get('take_profit', 0.05)
        self.max_position_percentage = adaptive.get('max_position', 0.3)

        result = {
            'action': 'hold',
            'price': current_price,
            'position': self.position,
            'balance': self.current_balance,
            'signal': signal,
            'confidence': confidence,
            'phase_state': self.phase_state,
            'market_type': self.market_type,
            'metrics': metrics,
            'conditions': conditions,
            'rsi': rsi,
            'bb_position': bb_position
        }

        if signal == 'buy' and self.position == 0 and conditions['low_entropy']:
            result = self._execute_buy(current_price)
        elif signal == 'sell' and self.position > 0:
            result = self._execute_sell(current_price, 'entropy_reversal')
        elif conditions['low_entropy'] and bb_position < self.bb_entry_threshold and self.position == 0:
            result = self._execute_buy(current_price)
        elif conditions['low_entropy'] and bb_position > self.bb_exit_threshold and self.position > 0:
            result = self._execute_sell(current_price, 'entropy_reversal')

        if self.position > 0:
            price_change = (current_price - self.entry_price) / self.entry_price
            if price_change <= -self.stop_loss_threshold:
                result = self._execute_sell(current_price, 'stop_loss')
            if price_change >= self.take_profit_threshold:
                result = self._execute_sell(current_price, 'take_profit')

        return result

    def _execute_buy(self, price: float) -> Dict[str, Any]:
        available_balance = self.current_balance * self.max_position_percentage
        position_size = available_balance / price  # 使用浮点而非int取整
        if position_size < 0.01:
            return {
                'action': 'hold', 'price': price,
                'position': self.position, 'balance': self.current_balance,
                'reason': 'insufficient_funds'
            }
        cost = position_size * price
        self.current_balance -= cost
        self.position += position_size
        self.entry_price = price
        self.total_trades += 1
        return {
            'action': 'buy', 'price': price, 'quantity': position_size,
            'position': self.position, 'balance': self.current_balance,
            'reason': 'thermodynamic_signal'
        }

    def _execute_sell(self, price: float, reason: str = 'exit') -> Dict[str, Any]:
        if self.position <= 0:
            return {
                'action': 'hold', 'price': price,
                'position': self.position, 'balance': self.current_balance,
                'reason': 'no_position'
            }
        revenue = self.position * price
        profit = revenue - self.entry_price * self.position
        self.current_balance += revenue
        if profit > 0:
            self.winning_trades += 1
        else:
            self.losing_trades += 1
        self.profit_history.append(profit)
        quantity = self.position  # 暂存
        self.position = 0
        return {
            'action': 'sell', 'price': price, 'quantity': quantity,
            'position': self.position, 'balance': self.current_balance,
            'profit': profit, 'reason': reason
        }

    def get_performance(self) -> Dict[str, float]:
        total_trades = self.total_trades
        win_rate = self.winning_trades / total_trades if total_trades > 0 else 0.0
        profits = [p for p in self.profit_history if p > 0]
        losses = [abs(p) for p in self.profit_history if p < 0]
        avg_profit = np.mean(profits) if profits else 0.0
        avg_loss = np.mean(losses) if losses else 1.0
        profit_factor = avg_profit / avg_loss if avg_loss > 0 else 0.0
        total_profit = sum(self.profit_history)
        total_return = total_profit / self.initial_balance
        return {
            'total_trades': total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'total_profit': total_profit,
            'total_return': total_return,
            'current_balance': self.current_balance,
            'current_position': self.position
        }

    def get_thermodynamic_summary(self) -> Dict[str, Any]:
        if len(self.price_history) < 60:
            return {'status': 'insufficient_data'}
        metrics = self.calculate_all_thermodynamic_metrics()
        conditions = self.check_thermodynamic_conditions(metrics)
        phase_map = {'solid': '冻结', 'liquid': '横盘', 'gas_up': '上涨', 'gas_down': '下跌'}
        return {
            'phase_state': phase_map.get(self.phase_state, '未知'),
            'market_type': self.market_type,
            'entropy': metrics.get('entropy_20', 0.0),
            'temperature': metrics.get('temperature_20', 0.0),
            'free_energy': metrics.get('free_energy_20', 0.0),
            'conditions_met': sum(conditions.values()),
            'total_conditions': len(conditions)
        }

    def get_param_space(self):
        return {
            'entropy_threshold': {'type': 'float', 'min': 1.0, 'max': 5.0, 'step': 0.5},
            'temperature_threshold': {'type': 'float', 'min': 0.1, 'max': 3.0, 'step': 0.1},
            'confidence_threshold': {'type': 'float', 'min': 0.3, 'max': 0.9, 'step': 0.05},
            'stop_loss_threshold': {'type': 'float', 'min': 0.01, 'max': 0.06, 'step': 0.005},
            'take_profit_threshold': {'type': 'float', 'min': 0.02, 'max': 0.10, 'step': 0.005},
            'max_position_percentage': {'type': 'float', 'min': 0.2, 'max': 0.8, 'step': 0.05},
            'grid_levels': {'type': 'int', 'min': 10, 'max': 50, 'step': 5},
            'grid_spacing': {'type': 'float', 'min': 0.003, 'max': 0.015, 'step': 0.001},
            'bb_entry_threshold': {'type': 'float', 'min': -2.5, 'max': -0.5, 'step': 0.25},
            'bb_exit_threshold': {'type': 'float', 'min': 0.5, 'max': 2.5, 'step': 0.25},
            'use_daily': self.use_daily,
        }

    def get_entropy_adaptive_params(self):
        if len(self.price_history) < 20:
            return {'entropy_threshold': self.entropy_threshold, 'temperature_threshold': self.temperature_threshold, 'confidence_threshold': self.confidence_threshold}
        metrics = self.calculate_all_thermodynamic_metrics()
        entropy = metrics.get('entropy_20', 3.5)
        entropy_factor = entropy / 3.5
        return {
            'entropy_threshold': self.entropy_threshold * entropy_factor,
            'temperature_threshold': self.temperature_threshold / max(entropy_factor, 0.3),
            'confidence_threshold': self.confidence_threshold * (2.0 - min(entropy_factor, 1.5)),
        }

    def apply_adaptive_params(self, params=None):
        if params is None:
            params = self.get_entropy_adaptive_params()
        self.entropy_threshold = params.get('entropy_threshold', self.entropy_threshold)
        self.temperature_threshold = params.get('temperature_threshold', self.temperature_threshold)
        self.confidence_threshold = params.get('confidence_threshold', self.confidence_threshold)
        self.stop_loss_threshold = params.get('stop_loss_threshold', self.stop_loss_threshold)
        self.take_profit_threshold = params.get('take_profit_threshold', self.take_profit_threshold)
        self.max_position_percentage = params.get('max_position_percentage', self.max_position_percentage)
        if 'grid_levels' in params:
            self.grid_levels = int(params['grid_levels'])
        self.grid_spacing = params.get('grid_spacing', self.grid_spacing)
        self.bb_entry_threshold = params.get('bb_entry_threshold', self.bb_entry_threshold)
        self.bb_exit_threshold = params.get('bb_exit_threshold', self.bb_exit_threshold)
        self.grids = self._create_grids()
