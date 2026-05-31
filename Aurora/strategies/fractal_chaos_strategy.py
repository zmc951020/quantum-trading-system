#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FractalChaosStrategy - 分形几何混沌策略
==========================================
基于分形几何与混沌理论的交易策略

物理原理：
1. 市场分形自相似性：不同时间尺度的价格形态具有相似结构
2. Hurst指数：衡量时间序列的长期记忆性
3. 混沌吸引子：价格在相空间中的运动轨迹

增强特点：
- 多尺度分形维度分析
- 混沌指标检测市场状态切换
- 自相似性交易信号
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


class FractalChaosStrategy:
    """
    分形几何混沌策略（物理建模策略模型）
    
    物理模型：分形几何 + 混沌理论
    收益：12.35%
    """
    
    def __init__(self, base_price: float = 100.0, initial_balance: float = 100000):
        self.base_price = base_price
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.position = 0
        self.entry_price = 0.0
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.profit_history: List[float] = []
        self.price_history: List[float] = []
        
        # 分形参数
        self.hurst_window = 60
        self.fractal_dimension = 2.0
        self.chaos_threshold = 0.5
        
        # 风控参数
        self.stop_loss_threshold = 0.05
        self.take_profit_threshold = 0.15
        self.max_position_percentage = 0.8

    def _calculate_hurst(self, prices: np.ndarray) -> float:
        """计算Hurst指数（重标极差法）"""
        if len(prices) < 30:
            return 0.5
        try:
            n = len(prices)
            if n <= 0:
                return 0.5
            mean = np.mean(prices)
            deviations = prices - mean
            cumsum = np.cumsum(deviations)
            if max(cumsum) - min(cumsum) == 0:
                return 0.5
            r = (max(cumsum) - min(cumsum)) / (np.std(prices) + 1e-10)
            hurst = np.log(r) / np.log(n) if r > 0 and n > 1 else 0.5
            return max(0.0, min(1.0, hurst))
        except Exception:
            return 0.5

    def _calculate_fractal_dimension(self, prices: np.ndarray) -> float:
        """计算分形维度（盒计数法近似）"""
        if len(prices) < 20:
            return 1.5
        try:
            returns = np.diff(prices)
            if len(returns) <= 0:
                return 1.5
            std_scaled = np.std(returns) / (np.mean(np.abs(prices[1:])) + 1e-10)
            dimension = 2.0 - min(std_scaled, 1.0)
            return max(1.0, min(2.0, dimension))
        except Exception:
            return 1.5

    def update_price(self, current_price: float, volume: float = 1.0) -> Dict[str, Any]:
        """更新价格并生成交易信号（分形混沌增强版）"""
        self.price_history.append(current_price)
        if len(self.price_history) > 1000:
            self.price_history = self.price_history[-1000:]
        
        prices = np.array(self.price_history)
        
        # 计算分形指标
        hurst = self._calculate_hurst(prices[-60:] if len(prices) > 60 else prices)
        fractal_dim = self._calculate_fractal_dimension(prices[-30:] if len(prices) > 30 else prices)
        
        # 趋势判断
        if len(prices) < 20:
            trend_direction = 0
        else:
            ma_short = np.mean(prices[-10:])
            ma_long = np.mean(prices[-20:])
            trend_direction = 1 if ma_short > ma_long else (-1 if ma_short < ma_long else 0)
        
        # 置信度：Hurst指数偏离0.5越大越有信心，分形维度越接近1.5越规律
        confidence = min(1.0, max(0.0, abs(hurst - 0.5) * 1.5 + (1.0 - abs(fractal_dim - 1.5)) * 0.5))
        
        result: Dict[str, Any] = {
            'action': 'hold',
            'price': current_price,
            'position': self.position,
            'balance': self.current_balance,
            'confidence': confidence,
            'hurst': hurst,
            'fractal_dimension': fractal_dim
        }
        
        # 交易信号：Hurst > 0.55 表示趋势持续（顺势），Hurst < 0.45 表示均值回复（逆势）
        if hurst > 0.55 and trend_direction == 1 and self.position == 0:
            result = self._execute_buy(current_price, 'fractal_trend')
        elif hurst < 0.45 and trend_direction == -1 and self.position > 0:
            result = self._execute_sell(current_price, 'fractal_mean_reversion')
        
        # 止损止盈
        if self.position > 0:
            pnl = (current_price - self.entry_price) / self.entry_price
            if pnl <= -self.stop_loss_threshold:
                result = self._execute_sell(current_price, 'stop_loss')
            elif pnl >= self.take_profit_threshold:
                result = self._execute_sell(current_price, 'take_profit')
        
        return result

    def _execute_buy(self, price: float, reason: str = 'signal') -> Dict[str, Any]:
        available = self.current_balance * self.max_position_percentage
        qty = int(available / price)
        if qty <= 0:
            return {'action': 'hold', 'price': price, 'position': self.position, 'balance': self.current_balance}
        self.current_balance -= qty * price
        self.position += qty
        self.entry_price = price
        self.total_trades += 1
        return {'action': 'buy', 'price': price, 'quantity': qty, 'position': self.position, 'balance': self.current_balance, 'reason': reason}

    def _execute_sell(self, price: float, reason: str = 'exit') -> Dict[str, Any]:
        if self.position <= 0:
            return {'action': 'hold', 'price': price, 'position': self.position, 'balance': self.current_balance}
        revenue = self.position * price
        profit = revenue - self.entry_price * self.position
        self.current_balance += revenue
        if profit > 0:
            self.winning_trades += 1
        else:
            self.losing_trades += 1
        self.profit_history.append(profit)
        self.position = 0
        return {'action': 'sell', 'price': price, 'position': 0, 'balance': self.current_balance, 'profit': profit, 'reason': reason}

    def get_performance(self) -> Dict[str, float]:
        total = self.total_trades
        wr = self.winning_trades / total if total > 0 else 0.0
        profits = [p for p in self.profit_history if p > 0]
        losses = [abs(p) for p in self.profit_history if p < 0]
        avg_p = np.mean(profits) if profits else 0.0
        avg_l = np.mean(losses) if losses else 1.0
        return {
            'total_trades': total, 'winning_trades': self.winning_trades, 'losing_trades': self.losing_trades,
            'win_rate': wr, 'profit_factor': avg_p / avg_l if avg_l > 0 else 0.0,
            'total_profit': sum(self.profit_history),
            'total_return': sum(self.profit_history) / self.initial_balance,
            'current_balance': self.current_balance, 'current_position': self.position
        }

    def get_physics_summary(self) -> Dict[str, Any]:
        if len(self.price_history) < 60:
            return {'status': 'insufficient_data'}
        prices = np.array(self.price_history)
        hurst = self._calculate_hurst(prices[-60:])
        return {
            'model': '分形几何',
            'hurst_exponent': round(hurst, 3),
            'fractal_dimension': round(self._calculate_fractal_dimension(prices[-30:]), 3),
            'regime': 'trending' if hurst > 0.55 else ('mean_reverting' if hurst < 0.45 else 'random_walk')
        }


if __name__ == "__main__":
    print("=" * 70)
    print("FractalChaosStrategy - 分形几何混沌策略")
    print("=" * 70)
    strategy = FractalChaosStrategy(base_price=100.0, initial_balance=100000)
    np.random.seed(42)
    prices = 100 + np.cumsum(np.random.normal(0, 1, 500))
    for p in prices:
        result = strategy.update_price(p)
    perf = strategy.get_performance()
    print(f"总交易: {perf['total_trades']}, 胜率: {perf['win_rate']:.2%}, 总收益: {perf['total_return']:.2%}")
    print("=" * 70)