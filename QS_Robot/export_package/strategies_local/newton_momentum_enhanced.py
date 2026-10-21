#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NewtonMomentumEnhanced - 牛顿惯性动量增强策略
================================================
基于经典力学模型的动量增强版本

物理原理：
1. 牛顿第一定律（惯性）：物体保持原有运动状态
2. 动量守恒：p = mv，价格动量具有惯性
3. 牛顿第二定律：F = ma，价格变化需要外力驱动

增强特点：
- 多时间尺度惯性分析
- 动量强度计算
- 趋势加速度检测
- 自适应惯性系数
- 与原始FinalMarketAdaptiveGrid完全独立

继承关系：
- 基于final_market_adaptive.py的核心逻辑
- 增加物理模型增强层
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

class NewtonMomentumCalculator:
    """
    牛顿动量计算器
    将价格运动类比为物体运动，应用物理公式
    """

    def __init__(self):
        self.price_history = []
        self.volume_history = []

    def add_data(self, price: float, volume: float = 1.0):
        """添加价格和成交量数据"""
        self.price_history.append(price)
        self.volume_history.append(volume)

        # 保持最近500个数据点
        if len(self.price_history) > 500:
            self.price_history = self.price_history[-500:]
            self.volume_history = self.volume_history[-500:]

    def calculate_momentum(self, period: int = 20) -> float:
        """
        计算价格动量（类比：线动量 p = mv）
        动量 = 质量（成交量）× 速度（价格变化率）
        日线适配：使用周期总收益率而非日收益之和
        """
        if len(self.price_history) < period:
            return 0.0
        prices = np.array(self.price_history[-period:])
        if prices[0] == 0:
            return 0.0
        total_return = (prices[-1] - prices[0]) / prices[0]
        volumes = np.array(self.volume_history[-period:])
        vol_mean = np.mean(volumes) if len(volumes) > 0 else 1.0
        volume_norm = volumes[-1] / vol_mean if vol_mean > 0 else 1.0
        return total_return * volume_norm

    def calculate_acceleration(self, period: int = 20) -> float:
        """
        计算价格加速度（类比：a = F/m）
        价格变化率的二阶导数
        """
        if len(self.price_history) < period:
            return 0.0

        prices = np.array(self.price_history[-period:])

        # 一阶导数（速度）
        velocity = np.diff(prices)

        # 二阶导数（加速度）
        if len(velocity) < 2:
            return 0.0

        acceleration = np.diff(velocity)

        # 归一化
        accel_mean = np.mean(acceleration)
        accel_std = np.std(acceleration) + 1e-6

        normalized_accel = (accel_mean) / accel_std

        return normalized_accel

    def calculate_inertia_coefficient(self, period: int = 20) -> float:
        """
        计算惯性系数
        趋势越强，惯性越大，价格越难改变方向
        """
        if len(self.price_history) < period:
            return 0.0

        momentum = self.calculate_momentum(period)
        acceleration = self.calculate_acceleration(period)

        # 惯性系数 = 动量 × 加速度方向一致性
        # 如果动量和加速度同向，说明趋势在加速，惯性大
        if momentum * acceleration > 0:
            inertia = abs(momentum) * abs(acceleration)
        else:
            inertia = -abs(momentum) * abs(acceleration)

        return inertia

    def calculate_kinetic_energy(self, period: int = 20) -> float:
        """
        计算价格动能（类比：KE = 0.5mv²）
        动能越大，价格运动越剧烈。日线适配：使用总收益率的平方
        """
        if len(self.price_history) < period:
            return 0.0
        prices = np.array(self.price_history[-period:])
        if prices[0] == 0:
            return 0.0
        total_return = (prices[-1] - prices[0]) / prices[0]
        return 0.5 * total_return * total_return


class NewtonMomentumEnhanced:
    """
    牛顿惯性动量增强策略
    基于经典力学模型的动量交易策略

    策略逻辑：
    1. 计算多时间尺度惯性系数
    2. 趋势加速度确认
    3. 动能强度判断
    4. 自适应网格交易
    """

    def __init__(self, base_price: float, initial_balance: float = 100000):
        self.base_price = base_price
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.position = 0
        self.price_history = []
        self.is_active = True
        self.last_price = base_price
        self.entry_price = 0
        self.last_buy_price = base_price

        self.momentum_calc = NewtonMomentumCalculator()

        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.profit_history = []

        self.market_type = 'range_bound'
        self.last_market_type = 'range_bound'
        self.market_types = ['range_bound', 'trending_up', 'trending_down', 'volatile']

        self.grid_levels = 100
        self.grid_spacing = 0.0015
        self.grids = self._create_grids()
        self.last_grid_index = self.grid_levels

        self.stop_loss_threshold = 0.02      # 2%止损（原0.8%过窄导致过度交易）
        self.take_profit_threshold = 0.04    # 4%止盈（原1.5%过窄导致过度交易）
        self.max_position_percentage = 0.3   # 30%仓位（原50%过重）

        self.momentum_threshold = 0.003
        self.inertia_threshold = 0.00005
        self.energy_threshold = 0.00002
        self.acceleration_threshold = 0.00005

        self.timeframes = {
            'ultra_short': 5,
            'short': 20,
            'medium': 60,
            'long': 120
        }
        self.timeframe_weights = {'ultra_short': 0.15, 'short': 0.25, 'medium': 0.35, 'long': 0.25}

        self.trend_direction = 0
        self.confidence = 0.0
        self.inertia_coefficient = 0.5
        self._entry_bar = -1           # 入场bar索引，-1表示未入场
        self.last_sell_bar = -50
        self.cooldown_bars = 10        # 卖出后冷却10根bar（原1根导致过度交易）
        self.min_hold_bars = 5         # 最少持有5根bar（原1根导致过度交易）

        self.volume_confirm_ratio = 1.0       # 成交量确认倍数
        self.trend_strength_filter = 0.0005   # 趋势强度过滤阈值
        self.market_type_smooth = 3           # 市场类型平滑窗口

    def _create_grids(self) -> List[float]:
        grids = []
        price_range = self.base_price * 0.1
        for i in range(self.grid_levels + 1):
            grid_price = self.base_price - price_range / 2 + (price_range * i / self.grid_levels)
            grids.append(grid_price)
        return grids

    def price_history_len(self) -> int:
        return len(self.price_history)

    def calculate_all_momentum_metrics(self) -> Dict[str, float]:
        metrics = {}
        for timeframe_name, period in self.timeframes.items():
            metrics[f'{timeframe_name}_momentum'] = self.momentum_calc.calculate_momentum(period)
            metrics[f'{timeframe_name}_acceleration'] = self.momentum_calc.calculate_acceleration(period)
            metrics[f'{timeframe_name}_inertia'] = self.momentum_calc.calculate_inertia_coefficient(period)
            metrics[f'{timeframe_name}_energy'] = self.momentum_calc.calculate_kinetic_energy(period)
        return metrics

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
    def get_adaptive_params_by_type(market_type: str) -> dict:
        """按市场类型返回静态参数表（原 get_adaptive_params 静态方法重命名，
        避免与下方实例方法 get_adaptive_params(self) 同名遮蔽）。"""
        params = {
            'trending_up': {'stop_loss': 0.015, 'take_profit': 0.030, 'max_position': 0.6, 'inertia': 0.8},
            'trending_down': {'stop_loss': 0.010, 'take_profit': 0.025, 'max_position': 0.3, 'inertia': 0.4},
            'range_bound': {'stop_loss': 0.008, 'take_profit': 0.015, 'max_position': 0.4, 'inertia': 0.3},
            'volatile': {'stop_loss': 0.006, 'take_profit': 0.020, 'max_position': 0.25, 'inertia': 0.5},
        }
        return params.get(market_type, params['range_bound'])

    @staticmethod
    def calculate_dynamic_force(price_change: float, volume: float, market_type: str) -> float:
        market_factor = {
            'trending_up': 1.5,
            'trending_down': 0.8,
            'range_bound': 0.5,
            'volatile': 0.7,
        }.get(market_type, 0.5)
        volume_factor = min(volume / 1000.0, 3.0)
        return price_change * volume_factor * market_factor

    def determine_trend_direction(self, metrics: Dict[str, float]) -> Tuple[int, float]:
        total_score = 0.0
        total_weight = 0.0
        for timeframe, weight in self.timeframe_weights.items():
            momentum = metrics.get(f'{timeframe}_momentum', 0.0)
            inertia = metrics.get(f'{timeframe}_inertia', 0.0)
            score = momentum * (1 + abs(inertia))
            total_score += score * weight
            total_weight += weight
        avg_score = total_score / total_weight if total_weight > 0 else 0.0
        if avg_score > self.momentum_threshold * 0.25:
            direction = 1
        elif avg_score < -self.momentum_threshold * 0.25:
            direction = -1
        else:
            direction = 0
        confidence_scores = []
        for timeframe in self.timeframes.keys():
            momentum = metrics.get(f'{timeframe}_momentum', 0.0)
            if direction == 1 and momentum > 0:
                confidence_scores.append(1)
            elif direction == -1 and momentum < 0:
                confidence_scores.append(1)
            else:
                confidence_scores.append(0)
        confidence = np.mean(confidence_scores)
        return direction, confidence

    def check_physics_conditions(self, metrics: Dict[str, float]) -> Dict[str, bool]:
        conditions = {}
        conditions['momentum_ok'] = abs(metrics.get('medium_momentum', 0.0)) > self.momentum_threshold
        conditions['inertia_ok'] = abs(metrics.get('medium_inertia', 0.0)) > self.inertia_threshold
        conditions['energy_ok'] = metrics.get('medium_energy', 0.0) > self.energy_threshold
        conditions['acceleration_ok'] = abs(metrics.get('medium_acceleration', 0.0)) > self.acceleration_threshold
        return conditions

    def update_price(self, current_price: float, volume: float = 1.0) -> Dict[str, Any]:
        self.price_history.append(current_price)
        if len(self.price_history) > 1000:
            self.price_history = self.price_history[-1000:]

        self.momentum_calc.add_data(current_price, volume)

        metrics = self.calculate_all_momentum_metrics()
        trend_direction, confidence = self.determine_trend_direction(metrics)
        self.trend_direction = trend_direction
        self.confidence = confidence

        conditions = self.check_physics_conditions(metrics)

        self.market_type = self.detect_market_type(np.array(self.price_history))
        adaptive = self.get_adaptive_params()
        self.inertia_coefficient = adaptive.get('inertia', 0.5)
        self.stop_loss_threshold = adaptive.get('stop_loss', 0.02)
        self.take_profit_threshold = adaptive.get('take_profit', 0.03)
        self.max_position_percentage = adaptive.get('max_position', 0.3)

        if len(self.price_history) >= 2:
            price_change = (current_price - self.price_history[-2]) / (self.price_history[-2] + 1e-10)
            dynamic_force = self.calculate_dynamic_force(price_change, volume, self.market_type)
            # 动态调整已禁用，使用初始化阈值

        result = {
            'action': 'hold',
            'price': current_price,
            'position': self.position,
            'balance': self.current_balance,
            'trend_direction': trend_direction,
            'confidence': confidence,
            'market_type': self.market_type,
            'inertia_coefficient': self.inertia_coefficient,
            'metrics': metrics,
            'conditions': conditions
        }

        # 买入条件：动量+动能必满足，惯性/加速度至少满足一项（3/4即可触发）
        # 冷却期检查：卖出后N根bar内不买入
        bars_since_sell = len(self.price_history) - self.last_sell_bar
        can_buy = (conditions['momentum_ok'] and conditions['energy_ok'] and
                   (conditions['inertia_ok'] or conditions['acceleration_ok']))

        # 成交量确认：当前量需超过均量×确认倍数
        if can_buy and self.volume_confirm_ratio > 1.0:
            vol_history = self.momentum_calc.volume_history
            if len(vol_history) >= 20:
                avg_vol = np.mean(vol_history[-20:])
                if volume < avg_vol * self.volume_confirm_ratio:
                    can_buy = False

        # 趋势强度过滤：趋势太弱不交易
        if can_buy:
            trend_strength = abs(metrics.get('medium_momentum', 0.0))
            if trend_strength < self.trend_strength_filter:
                can_buy = False
        if can_buy and self.position == 0 and bars_since_sell > self.cooldown_bars:
            result = self._execute_buy(current_price)
        elif trend_direction == -1 and self.position > 0:
            bars_held = len(self.price_history) - self._entry_bar
            if bars_held > self.min_hold_bars:
                result = self._execute_sell(current_price, 'trend_reversal')

        if self.position > 0:
            price_change = (current_price - self.entry_price) / self.entry_price
            if price_change <= -self.stop_loss_threshold:
                result = self._execute_sell(current_price, 'stop_loss')
            if price_change >= self.take_profit_threshold:
                result = self._execute_sell(current_price, 'take_profit')

        return result

    def _execute_buy(self, price: float) -> Dict[str, Any]:
        available_balance = self.current_balance * self.max_position_percentage
        position_size = available_balance / price
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
        self._entry_bar = self.price_history_len()
        return {
            'action': 'buy', 'price': price, 'quantity': position_size,
            'position': self.position, 'balance': self.current_balance,
            'reason': 'newton_momentum_signal'
        }

    def _execute_sell(self, price: float, reason: str = 'exit') -> Dict[str, Any]:
        if self.position <= 0:
            return {
                'action': 'hold', 'price': price,
                'position': self.position, 'balance': self.current_balance,
                'reason': 'no_position'
            }
        qty = self.position
        revenue = qty * price
        profit = revenue - self.entry_price * qty
        self.current_balance += revenue
        if profit > 0:
            self.winning_trades += 1
        else:
            self.losing_trades += 1
        self.profit_history.append(profit)
        self.position = 0
        self.last_sell_bar = self.price_history_len()
        return {
            'action': 'sell', 'price': price, 'quantity': qty,
            'position': 0, 'balance': self.current_balance,
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

    def get_physics_summary(self) -> Dict[str, Any]:
        if len(self.price_history) < 60:
            return {'status': 'insufficient_data'}
        metrics = self.calculate_all_momentum_metrics()
        direction, confidence = self.determine_trend_direction(metrics)
        conditions = self.check_physics_conditions(metrics)
        return {
            'trend_direction': '上涨' if direction == 1 else ('下跌' if direction == -1 else '横盘'),
            'confidence': confidence,
            'market_type': self.market_type,
            'inertia_coefficient': self.inertia_coefficient,
            'conditions_met': sum(conditions.values()),
            'total_conditions': len(conditions),
            'metrics_summary': {
                'momentum': metrics.get('medium_momentum', 0.0),
                'inertia': metrics.get('medium_inertia', 0.0),
                'energy': metrics.get('medium_energy', 0.0),
                'acceleration': metrics.get('medium_acceleration', 0.0)
            }
        }

    def get_param_space(self):
        return {
            'momentum_threshold': {'type': 'float', 'min': 0.001, 'max': 0.05, 'step': 0.001},
            'inertia_threshold': {'type': 'float', 'min': 0.00001, 'max': 0.001, 'step': 0.00001},
            'energy_threshold': {'type': 'float', 'min': 0.000005, 'max': 0.0005, 'step': 0.000005},
            'acceleration_threshold': {'type': 'float', 'min': 0.00001, 'max': 0.001, 'step': 0.00001},
            'stop_loss_threshold': {'type': 'float', 'min': 0.005, 'max': 0.06, 'step': 0.002},
            'take_profit_threshold': {'type': 'float', 'min': 0.01, 'max': 0.10, 'step': 0.005},
            'max_position_percentage': {'type': 'float', 'min': 0.15, 'max': 0.75, 'step': 0.05},
            'cooldown_bars': {'type': 'int', 'min': 0, 'max': 5, 'step': 1},
            'min_hold_bars': {'type': 'int', 'min': 1, 'max': 5, 'step': 1},
            'volume_confirm_ratio': {'type': 'float', 'min': 0.5, 'max': 2.0, 'step': 0.1},
            'trend_strength_filter': {'type': 'float', 'min': 0.0001, 'max': 0.003, 'step': 0.0001},
        }

    def get_adaptive_params(self):
        if len(self.price_history) < 20:
            return {'inertia': 0.5, 'stop_loss': 0.02, 'take_profit': 0.03, 'max_position': 0.3}
        metrics = self.calculate_all_momentum_metrics()
        trend_strength = abs(metrics.get('medium_momentum', 0.0))
        strength_factor = 1.0 + trend_strength * 10
        return {
            'inertia': min(0.9, max(0.1, self.inertia_coefficient * (2.0 - strength_factor * 0.5))),
            # 止损下限保护：strength_factor 偏小时止损会被压到极小值，设 0.5% 硬底
            'stop_loss': max(0.005, 0.02 * strength_factor * 0.5),
            'take_profit': 0.03 * strength_factor,
            'max_position': min(0.5, 0.3 * strength_factor * 0.5),
        }

    def get_physics_adaptive_params(self):
        """实例方法：基于物理指标自适应调整参数（重命名避免与静态方法冲突）"""
        return self.get_adaptive_params()

    def apply_adaptive_params(self, params=None):
        if params is None:
            params = self.get_adaptive_params()
        self.momentum_threshold = params.get('momentum_threshold', self.momentum_threshold)
        self.inertia_threshold = params.get('inertia_threshold', self.inertia_threshold)
        self.energy_threshold = params.get('energy_threshold', self.energy_threshold)
        self.acceleration_threshold = params.get('acceleration_threshold', self.acceleration_threshold)
        self.stop_loss_threshold = params.get('stop_loss_threshold', self.stop_loss_threshold)
        self.take_profit_threshold = params.get('take_profit_threshold', self.take_profit_threshold)
        self.max_position_percentage = params.get('max_position_percentage', self.max_position_percentage)
        self.cooldown_bars = int(params.get('cooldown_bars', self.cooldown_bars))
        self.min_hold_bars = int(params.get('min_hold_bars', self.min_hold_bars))
        self.volume_confirm_ratio = params.get('volume_confirm_ratio', self.volume_confirm_ratio)
        self.trend_strength_filter = params.get('trend_strength_filter', self.trend_strength_filter)
