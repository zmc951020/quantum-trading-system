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

    def calculate_boltzmann_distribution(self, returns: List[float]) -> Dict[str, float]:
        """
        计算玻尔兹曼分布
        收益率服从某种概率分布，类比粒子能量分布

        P(E) ∝ exp(-E / kT)
        """
        if len(returns) < 10:
            return {}

        returns_arr = np.array(returns)

        # 计算"能量"等级
        energy = -returns_arr  # 收益越高，"能量"越低

        # 计算概率分布
        beta = 1.0 / (np.std(energy) + 1e-6)  # 温度参数
        probabilities = np.exp(-beta * energy)
        probabilities = probabilities / np.sum(probabilities)

        # 计算各状态的玻尔兹曼概率
        result = {
            'high_energy_prob': np.sum(probabilities[energy > np.percentile(energy, 75)]),
            'low_energy_prob': np.sum(probabilities[energy < np.percentile(energy, 25)]),
            'mean_energy': np.mean(energy),
            'entropy': -np.sum(probabilities * np.log2(probabilities + 1e-10))
        }

        return result


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

    def __init__(self, base_price: float, initial_balance: float = 100000):
        """
        初始化热力学熵优化策略

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
        self.last_buy_price = base_price
        self.entry_price = 0
        self.consecutive_holds = 0

        # === 新增：热力学熵计算器 ===
        self.entropy_calc = ThermodynamicEntropyCalculator()

        # === 交易统计 ===
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.profit_history = []

        # === 市场类型 ===
        self.market_type = 'range_bound'
        self.market_types = ['range_bound', 'trending_up', 'trending_down']

        # === 网格交易参数（保留原始逻辑） ===
        self.grid_levels = 40
        self.grid_spacing = 0.0040
        self.grids = self._create_grids()
        self.last_grid_index = self.grid_levels

        # === 风险控制参数 ===
        self.stop_loss_threshold = 0.010    # 1%止损
        self.take_profit_threshold = 0.015   # 1.5%止盈
        self.max_position_percentage = 0.5   # 最大仓位50%

        # === 热力学参数 ===
        self.entropy_threshold = 3.5      # 熵阈值
        self.temperature_threshold = 1.0   # 温度阈值
        self.free_energy_threshold = 0.0  # 自由能阈值
        self.confidence_threshold = 0.6    # 置信度阈值

        # === 技术指标参数 ===
        self.rsi_period = 14
        self.bollinger_period = 20
        self.bollinger_std = 2

        # === 策略状态 ===
        self.phase_state = 'liquid'  # 当前相态
        self.confidence = 0.0        # 信号置信度

    def _create_grids(self) -> List[float]:
        """创建网格"""
        grids = []
        price_range = self.base_price * 0.1

        for i in range(self.grid_levels + 1):
            grid_price = self.base_price - price_range / 2 + (price_range * i / self.grid_levels)
            grids.append(grid_price)

        return grids

    def calculate_all_thermodynamic_metrics(self) -> Dict[str, float]:
        """
        计算所有热力学指标
        """
        metrics = {}

        # 基础热力学指标
        metrics['entropy'] = self.entropy_calc.calculate_information_entropy(period=20)
        metrics['temperature'] = self.entropy_calc.calculate_volatility_temperature(period=20)
        metrics['free_energy'] = self.entropy_calc.calculate_free_energy(period=20)

        # 多周期指标
        for period in [10, 20, 40]:
            metrics[f'entropy_{period}'] = self.entropy_calc.calculate_information_entropy(period=period)
            metrics[f'temperature_{period}'] = self.entropy_calc.calculate_volatility_temperature(period=period)
            metrics[f'free_energy_{period}'] = self.entropy_calc.calculate_free_energy(period=period)

        # 相态
        metrics['phase_state'] = self.entropy_calc.calculate_phase_state(period=20)

        return metrics

    def determine_trading_signal(self, metrics: Dict[str, float]) -> Tuple[str, float]:
        """
        基于热力学指标确定交易信号

        Returns:
            signal: 'buy', 'sell', 'hold'
            confidence: 置信度 [0, 1]
        """
        entropy = metrics.get('entropy_20', 0.0)
        temperature = metrics.get('temperature_20', 0.0)
        free_energy = metrics.get('free_energy_20', 0.0)
        phase_state = metrics.get('phase_state', 'liquid')

        # 计算置信度
        confidence = 0.0

        # 熵条件
        if entropy < self.entropy_threshold:
            confidence += 0.3

        # 温度条件
        if temperature > self.temperature_threshold:
            confidence += 0.2

        # 自由能条件
        if phase_state in ['gas_up', 'gas_down']:
            confidence += 0.3

        # 归一化
        confidence = min(1.0, confidence / 0.8)

        # 生成信号
        if phase_state == 'gas_up' and confidence >= self.confidence_threshold:
            signal = 'buy'
        elif phase_state == 'gas_down' and confidence >= self.confidence_threshold:
            signal = 'sell'
        elif entropy > 4.0:
            signal = 'hold'  # 高熵横盘，减少交易
        else:
            signal = 'hold'

        return signal, confidence

    def check_thermodynamic_conditions(self, metrics: Dict[str, float]) -> Dict[str, bool]:
        """
        检查热力学条件
        """
        conditions = {}

        # 熵条件：低熵有利于趋势
        conditions['low_entropy'] = metrics.get('entropy_20', 0.0) < self.entropy_threshold

        # 温度条件：高温度表示高波动
        conditions['high_temperature'] = metrics.get('temperature_20', 0.0) > self.temperature_threshold

        # 自由能条件：自由能下降趋势
        conditions['low_free_energy'] = metrics.get('free_energy_20', 0.0) < self.free_energy_threshold

        # 相态条件
        phase_state = metrics.get('phase_state', 'liquid')
        conditions['phase_transition'] = phase_state in ['gas_up', 'gas_down']

        return conditions

    def calculate_rsi(self, period: int = 14) -> float:
        """计算RSI"""
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
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def calculate_bollinger_position(self) -> float:
        """计算布林带位置"""
        if len(self.price_history) < self.bollinger_period:
            return 0.5

        prices = np.array(self.price_history[-self.bollinger_period:])
        current_price = self.price_history[-1]

        mean = np.mean(prices)
        std = np.std(prices)

        if std == 0:
            return 0.5

        position = (current_price - mean) / (self.bollinger_std * std)

        return position

    def update_price(self, current_price: float, volume: float = 1.0) -> Dict[str, Any]:
        """
        更新价格并执行交易（热力学熵优化版）

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

        # === 更新熵计算器 ===
        self.entropy_calc.add_data(current_price, volume)

        # === 计算所有热力学指标 ===
        metrics = self.calculate_all_thermodynamic_metrics()

        # === 确定交易信号 ===
        signal, confidence = self.determine_trading_signal(metrics)
        self.confidence = confidence
        self.phase_state = metrics.get('phase_state', 'liquid')

        # === 检查热力学条件 ===
        conditions = self.check_thermodynamic_conditions(metrics)

        # === 技术指标辅助 ===
        rsi = self.calculate_rsi()
        bb_position = self.calculate_bollinger_position()

        # === 生成交易信号 ===
        result = {
            'action': 'hold',
            'price': current_price,
            'position': self.position,
            'balance': self.current_balance,
            'signal': signal,
            'confidence': confidence,
            'phase_state': self.phase_state,
            'metrics': metrics,
            'conditions': conditions,
            'rsi': rsi,
            'bb_position': bb_position
        }

        # === 执行交易 ===
        if signal == 'buy' and self.position == 0 and conditions['low_entropy']:
            result = self._execute_buy(current_price)
        elif signal == 'sell' and self.position > 0:
            result = self._execute_sell(current_price, 'entropy_reversal')
        elif conditions['low_entropy'] and bb_position < -1.5 and self.position == 0:
            # 低熵 + 价格超卖 → 买入
            result = self._execute_buy(current_price)
        elif conditions['low_entropy'] and bb_position > 1.5 and self.position > 0:
            # 低熵 + 价格超买 → 卖出
            result = self._execute_sell(current_price, 'entropy_reversal')

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
            'reason': 'thermodynamic_signal'
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

    def get_thermodynamic_summary(self) -> Dict[str, Any]:
        """获取热力学模型摘要"""
        if len(self.price_history) < 60:
            return {'status': 'insufficient_data'}

        metrics = self.calculate_all_thermodynamic_metrics()
        conditions = self.check_thermodynamic_conditions(metrics)

        return {
            'phase_state': {
                'solid': '冻结',
                'liquid': '横盘',
                'gas_up': '上涨',
                'gas_down': '下跌'
            }.get(self.phase_state, '未知'),
            'entropy': metrics.get('entropy_20', 0.0),
            'temperature': metrics.get('temperature_20', 0.0),
            'free_energy': metrics.get('free_energy_20', 0.0),
            'conditions_met': sum(conditions.values()),
            'total_conditions': len(conditions)
        }


# === 策略注册 ===
def register_strategy():
    """注册策略到策略注册表"""
    try:
        from strategies.strategy_registry import StrategyRegistry
        StrategyRegistry.register('thermodynamic_entropy_enhanced', ThermodynamicEntropyEnhanced)
        print("[ThermodynamicEntropyEnhanced] 策略注册成功")
    except ImportError:
        print("[ThermodynamicEntropyEnhanced] 策略注册表不可用")


if __name__ == "__main__":
    # === 示例：回测演示 ===
    print("=" * 70)
    print("ThermodynamicEntropyEnhanced - 热力学熵优化增强策略")
    print("=" * 70)

    # 创建策略实例
    strategy = ThermodynamicEntropyEnhanced(base_price=100.0, initial_balance=100000)

    # 生成模拟数据（包含不同相态）
    np.random.seed(42)
    prices = []
    base_price = 100.0

    for i in range(500):
        # 模拟不同相态
        if i < 100:
            # 固体相：低波动，高熵
            price = base_price + np.random.normal(0, 0.2)
        elif i < 200:
            # 液体相：中等波动
            price = base_price + np.sin(i / 20) * 2 + np.random.normal(0, 0.5)
        elif i < 350:
            # 气体上涨相：低熵高能
            trend = (i - 200) * 0.02
            price = base_price + trend + np.random.normal(0, 0.8)
        else:
            # 气体下跌相
            trend = (500 - i) * 0.02
            price = base_price + trend + np.random.normal(0, 0.8)

        prices.append(price)

    # 运行回测
    trade_count = 0
    for i, price in enumerate(prices):
        volume = 1000 + np.random.randint(-200, 200)
        result = strategy.update_price(price, volume)

        if result['action'] in ['buy', 'sell']:
            trade_count += 1
            thermo = strategy.get_thermodynamic_summary()
            print(f"Trade #{trade_count}: {result['action'].upper()} @ {price:.2f} "
                  f"[{thermo.get('phase_state', 'N/A')}] "
                  f"Entropy: {thermo.get('entropy', 0):.2f} "
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
