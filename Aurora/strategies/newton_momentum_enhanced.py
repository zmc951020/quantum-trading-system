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
        """
        if len(self.price_history) < period:
            return 0.0

        prices = np.array(self.price_history[-period:])
        volumes = np.array(self.volume_history[-period:])

        # 速度（价格变化率）
        returns = np.diff(prices) / prices[:-1]

        # 质量（成交量标准化）
        volume_norm = volumes / np.mean(volumes)

        # 动量 = 质量 × 速度
        momentum = np.sum(volume_norm[1:] * returns)

        return momentum

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
        动能越大，价格运动越剧烈
        """
        if len(self.price_history) < period:
            return 0.0

        prices = np.array(self.price_history[-period:])
        returns = np.diff(prices) / prices[:-1]
        volumes = np.array(self.volume_history[-period:])

        # 动能 = 0.5 × 质量 × 速度²
        kinetic_energy = 0.5 * np.sum(volumes[1:] * (returns ** 2))

        return kinetic_energy


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
        """
        初始化牛顿动量增强策略

        Args:
            base_price: 基准价格
            initial_balance: 初始资金
        """
        # === 继承原始策略的核心变量 ===
        self.base_price = base_price
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.position = 0
        self.price_history = []
        self.is_active = True
        self.last_price = base_price
        self.entry_price = 0
        self.last_buy_price = base_price

        # === 新增：牛顿动量计算器 ===
        self.momentum_calc = NewtonMomentumCalculator()

        # === 交易统计 ===
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.profit_history = []

        # === 市场类型 ===
        self.market_type = 'range_bound'
        self.last_market_type = 'range_bound'
        self.market_types = ['range_bound', 'trending_up', 'trending_down', 'volatile']

        # === 网格交易参数（保留原始逻辑） ===
        self.grid_levels = 100
        self.grid_spacing = 0.0015
        self.grids = self._create_grids()
        self.last_grid_index = self.grid_levels

        # === 风险控制参数 ===
        self.stop_loss_threshold = 0.008
        self.take_profit_threshold = 0.015
        self.max_position_percentage = 0.5

        # === 牛顿力学参数 ===
        self.momentum_threshold = 0.005  # 动量阈值（降低以产生更多信号）
        self.inertia_threshold = 0.005   # 惯性阈值（降低以产生更多信号）
        self.energy_threshold = 0.0001   # 动能阈值（降低以产生更多信号）
        self.acceleration_threshold = 0.1  # 加速度阈值（降低以产生更多信号）

        # === 多时间尺度惯性分析 ===
        self.timeframes = {
            'ultra_short': 5,   # 超短期（5个数据点）
            'short': 20,        # 短期（20个数据点）
            'medium': 60,       # 中期（60个数据点）
            'long': 120         # 长期（120个数据点）
        }

        # === 策略状态 ===
        self.trend_direction = 0  # 0: 横盘, 1: 上涨, -1: 下跌
        self.confidence = 0.0     # 信号置信度

    def _create_grids(self) -> List[float]:
        """创建网格"""
        grids = []
        price_range = self.base_price * 0.1

        for i in range(self.grid_levels + 1):
            grid_price = self.base_price - price_range / 2 + (price_range * i / self.grid_levels)
            grids.append(grid_price)

        return grids

    def calculate_all_momentum_metrics(self) -> Dict[str, float]:
        """
        计算所有动量指标
        返回多时间尺度的惯性分析结果
        """
        metrics = {}

        for timeframe_name, period in self.timeframes.items():
            metrics[f'{timeframe_name}_momentum'] = self.momentum_calc.calculate_momentum(period)
            metrics[f'{timeframe_name}_acceleration'] = self.momentum_calc.calculate_acceleration(period)
            metrics[f'{timeframe_name}_inertia'] = self.momentum_calc.calculate_inertia_coefficient(period)
            metrics[f'{timeframe_name}_energy'] = self.momentum_calc.calculate_kinetic_energy(period)

        return metrics

    def determine_trend_direction(self, metrics: Dict[str, float]) -> Tuple[int, float]:
        """
        确定趋势方向和置信度
        基于多时间尺度惯性分析

        Returns:
            trend_direction: -1 (下跌), 0 (横盘), 1 (上涨)
            confidence: 置信度 [0, 1]
        """
        # 多时间尺度加权
        weights = {
            'ultra_short': 0.15,
            'short': 0.25,
            'medium': 0.35,
            'long': 0.25
        }

        total_score = 0.0
        total_weight = 0.0

        for timeframe, weight in weights.items():
            momentum = metrics.get(f'{timeframe}_momentum', 0.0)
            inertia = metrics.get(f'{timeframe}_inertia', 0.0)

            # 分数 = 动量 × 惯性系数
            score = momentum * (1 + abs(inertia))
            total_score += score * weight
            total_weight += weight

        avg_score = total_score / total_weight if total_weight > 0 else 0.0

        # 确定趋势方向
        if avg_score > self.momentum_threshold:
            direction = 1
        elif avg_score < -self.momentum_threshold:
            direction = -1
        else:
            direction = 0

        # 计算置信度（基于多时间尺度一致性）
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
        """
        检查物理条件
        多个物理指标同时满足才发出信号
        """
        conditions = {}

        # 动量条件
        conditions['momentum_ok'] = abs(metrics.get('medium_momentum', 0.0)) > self.momentum_threshold

        # 惯性条件
        conditions['inertia_ok'] = abs(metrics.get('medium_inertia', 0.0)) > self.inertia_threshold

        # 动能条件
        conditions['energy_ok'] = metrics.get('medium_energy', 0.0) > self.energy_threshold

        # 加速度条件（趋势是否在加速）
        conditions['acceleration_ok'] = abs(metrics.get('medium_acceleration', 0.0)) > self.acceleration_threshold

        return conditions

    def update_price(self, current_price: float, volume: float = 1.0) -> Dict[str, Any]:
        """
        更新价格并执行交易（牛顿动量增强版）

        Args:
            current_price: 当前价格
            volume: 成交量

        Returns:
            交易结果
        """
        # === 记录价格历史 ===
        self.price_history.append(current_price)
        if len(self.price_history) > 1000:
            self.price_history = self.price_history[-1000:]

        # === 更新动量计算器 ===
        self.momentum_calc.add_data(current_price, volume)

        # === 计算所有动量指标 ===
        metrics = self.calculate_all_momentum_metrics()

        # === 确定趋势方向 ===
        trend_direction, confidence = self.determine_trend_direction(metrics)
        self.trend_direction = trend_direction
        self.confidence = confidence

        # === 检查物理条件 ===
        conditions = self.check_physics_conditions(metrics)

        # === 生成交易信号 ===
        result = {
            'action': 'hold',
            'price': current_price,
            'position': self.position,
            'balance': self.current_balance,
            'trend_direction': trend_direction,
            'confidence': confidence,
            'metrics': metrics,
            'conditions': conditions
        }

        # === 执行交易 ===
        if conditions['momentum_ok'] and conditions['inertia_ok'] and conditions['energy_ok']:
            if trend_direction == 1 and self.position == 0:
                # 买入信号
                result = self._execute_buy(current_price)
            elif trend_direction == -1 and self.position > 0:
                # 卖出信号
                result = self._execute_sell(current_price, 'momentum_reversal')

        # === 止损止盈检查 ===
        if self.position > 0:
            price_change = (current_price - self.entry_price) / self.entry_price

            if price_change <= -self.stop_loss_threshold:
                result = self._execute_sell(current_price, 'stop_loss')

            if price_change >= self.take_profit_threshold:
                result = self._execute_sell(current_price, 'take_profit')

        return result

    def _execute_buy(self, price: float) -> Dict[str, Any]:
        """执行买入"""
        available_balance = self.current_balance * self.max_position_percentage
        position_size = int(available_balance / price)

        if position_size <= 0:
            return {
                'action': 'hold',
                'price': price,
                'position': self.position,
                'balance': self.current_balance,
                'reason': 'insufficient_funds'
            }

        cost = position_size * price
        self.current_balance -= cost
        self.position += position_size
        self.entry_price = price
        self.total_trades += 1

        return {
            'action': 'buy',
            'price': price,
            'quantity': position_size,
            'position': self.position,
            'balance': self.current_balance,
            'reason': 'newton_momentum_signal'
        }

    def _execute_sell(self, price: float, reason: str = 'exit') -> Dict[str, Any]:
        """执行卖出"""
        if self.position <= 0:
            return {
                'action': 'hold',
                'price': price,
                'position': self.position,
                'balance': self.current_balance,
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
        self.position = 0

        return {
            'action': 'sell',
            'price': price,
            'quantity': self.position,
            'position': self.position,
            'balance': self.current_balance,
            'profit': profit,
            'reason': reason
        }

    def get_performance(self) -> Dict[str, float]:
        """获取策略性能指标"""
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
        """获取物理模型摘要"""
        if len(self.price_history) < 60:
            return {'status': 'insufficient_data'}

        metrics = self.calculate_all_momentum_metrics()
        direction, confidence = self.determine_trend_direction(metrics)
        conditions = self.check_physics_conditions(metrics)

        return {
            'trend_direction': '上涨' if direction == 1 else ('下跌' if direction == -1 else '横盘'),
            'confidence': confidence,
            'conditions_met': sum(conditions.values()),
            'total_conditions': len(conditions),
            'metrics_summary': {
                'momentum': metrics.get('medium_momentum', 0.0),
                'inertia': metrics.get('medium_inertia', 0.0),
                'energy': metrics.get('medium_energy', 0.0),
                'acceleration': metrics.get('medium_acceleration', 0.0)
            }
        }


# === 策略注册 ===
def register_strategy():
    """注册策略到策略注册表"""
    try:
        from strategies.strategy_registry import StrategyRegistry
        StrategyRegistry.register('newton_momentum_enhanced', NewtonMomentumEnhanced)
        print("[NewtonMomentumEnhanced] 策略注册成功")
    except ImportError:
        print("[NewtonMomentumEnhanced] 策略注册表不可用")


if __name__ == "__main__":
    # === 示例：回测演示 ===
    print("=" * 70)
    print("NewtonMomentumEnhanced - 牛顿惯性动量增强策略")
    print("=" * 70)

    # 创建策略实例
    strategy = NewtonMomentumEnhanced(base_price=100.0, initial_balance=100000)

    # 生成模拟数据（包含趋势和震荡）
    np.random.seed(42)
    prices = []
    base_price = 100.0
    trend = 0.0

    for i in range(500):
        # 添加趋势成分（惯性效果）
        if i < 250:
            trend += np.random.uniform(0.01, 0.03)  # 上涨趋势
        elif i < 300:
            trend += np.random.uniform(-0.02, 0.02)  # 横盘
        else:
            trend -= np.random.uniform(0.01, 0.03)  # 下跌趋势

        trend = max(-0.5, min(0.5, trend))

        # 周期性波动
        cycle = np.sin(i / 30) * 1.5

        # 噪声
        noise = np.random.normal(0, 0.3)

        price = base_price + trend * 10 + cycle + noise
        prices.append(price)

    # 运行回测
    trade_count = 0
    for i, price in enumerate(prices):
        volume = 1000 + np.random.randint(-300, 300)
        result = strategy.update_price(price, volume)

        if result['action'] in ['buy', 'sell']:
            trade_count += 1
            physics = strategy.get_physics_summary()
            print(f"Trade #{trade_count}: {result['action'].upper()} @ {price:.2f} "
                  f"[{physics.get('trend_direction', 'N/A')}] "
                  f"Confidence: {result['confidence']:.2f}")

    # 输出性能报告
    perf = strategy.get_performance()
    print("\n" + "=" * 70)
    print("Performance Report")
    print("=" * 70)
    print(f"Total Trades: {perf['total_trades']}")
    print(f"Win Rate: {perf['win_rate']:.2%}")
    print(f"Profit Factor: {perf['profit_factor']:.2f}")
    print(f"Total Return: {perf['total_return']:.2%}")
    print(f"Final Balance: {perf['current_balance']:.2f}")
    print("=" * 70)
