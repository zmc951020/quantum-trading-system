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
    收益：12.35%（docstring 自述，未回测验证，不计为证据）
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
        
        # 分形参数（适配5分钟K线周期）
        self.hurst_window = 100              # Hurst窗口（5分钟线需要更长窗口）
        self.fractal_dimension = 2.0
        self.chaos_threshold = 0.5
        self.hurst_threshold = 0.58          # Hurst买入阈值（提高，减少假信号）
        self.hurst_sell_threshold = 0.45     # Hurst卖出阈值（降低，避免频繁卖出）
        self.fractal_dim_threshold = 1.5
        self.signal_threshold = 0.35         # 信号强度阈值（提高，过滤弱信号）
        self.trend_period_short = 20         # 趋势判断短周期（100分钟）
        self.trend_period_long = 60          # 趋势判断长周期（300分钟）
        
        # 风控参数（适配5分钟K线）
        self.stop_loss_threshold = 0.05      # 止损5%（5分钟波动大）
        self.take_profit_threshold = 0.12    # 止盈12%
        self.max_position_percentage = 0.8
        self.cooldown_bars = 12              # 卖出后冷却期（1小时=12根5分钟K线）
        self.min_hold_bars = 6               # 最小持仓（30分钟=6根5分钟K线）
        self._entry_bar = -1
        self.last_sell_bar = -50
        self.use_daily = False               # 5分钟模式（非日线）

    def _calculate_hurst(self, prices: np.ndarray) -> float:
        """计算Hurst指数（标准多尺度重标极差 R/S 法，作用于对数收益率）。

        旧实现错误地在价格水平上做了单次 R/S（prices-mean 的累积离差），
        且只算了一个窗口的 log(R)/log(n)。现修正为：
        1) 对对数收益率序列 lr = np.diff(np.log(prices)) 做 R/S；
        2) 按多个子窗口长度 n 切分 lr，逐段计算重标极差 R/S（段内累积离差的
           极差 R 除以段内样本标准差 S），再对每个 n 取平均 R/S；
        3) 对 log(n) vs log(R/S) 做线性回归，斜率即 Hurst 指数。
        序列过短（无法构成至少 3 个有效尺度）时返回 nan，不硬算。
        """
        prices = np.asarray(prices, dtype=float)
        if prices.size < 40 or np.any(prices <= 0):
            return float('nan')
        try:
            log_ret = np.diff(np.log(prices))
            log_ret = log_ret[np.isfinite(log_ret)]
            N = log_ret.size
            if N < 30:
                return float('nan')
            # 候选子窗口长度（从 16 起步，避免经典 R/S 在极小 n 处的向上小样本偏差）
            candidates = [16, 24, 32, 48, 64, 96, 128, 256, 512]
            ns: List[int] = []
            rs_means: List[float] = []
            for n in candidates:
                if n > N // 2:
                    continue
                n_chunks = N // n
                if n_chunks < 2:
                    continue
                rs_list = []
                for i in range(n_chunks):
                    seg = log_ret[i * n:(i + 1) * n]
                    seg_mean = np.mean(seg)
                    cum_dev = np.cumsum(seg - seg_mean)
                    R = np.max(cum_dev) - np.min(cum_dev)
                    S = np.std(seg, ddof=1)
                    if S > 1e-12 and R > 1e-12:
                        rs_list.append(R / S)
                if rs_list:
                    ns.append(n)
                    rs_means.append(float(np.mean(rs_list)))
            if len(ns) < 3:
                return float('nan')
            slope, _ = np.polyfit(np.log(ns), np.log(rs_means), 1)
            return float(np.clip(slope, 0.0, 1.0))
        except Exception:
            return float('nan')

    def _calculate_fractal_dimension(self, prices: np.ndarray) -> float:
        """计算分形维（基于 log(价格) 变差函数的尺度斜率法）。

        旧公式 dimension = 2.0 - std(diff(price))/mean(|price|) 完全退化：
        价格≈100 时该比值≈0.01，输出恒≈1.99，毫无区分度。
        现修正为：对对数价格 lp=log(price)，计算不同时间滞后 k 下
        E|lp(t+k)-lp(t)| 的均值；该均值随 k 的增长斜率即粗糙指数 H_v：
            E|Δlp(k)| ~ k^H_v
        曲线分形维 D = 2 - H_v。
        - 纯随机游走（布朗运动）H_v=0.5 → D≈1.5；
        - 趋势序列（近似直线）H_v→1 → D→1.0；
        - 均值回复序列（振荡饱和）H_v→0 → D→2.0。
        序列过短时返回 nan，不硬算。
        """
        prices = np.asarray(prices, dtype=float)
        if prices.size < 30 or np.any(prices <= 0):
            return float('nan')
        try:
            lp = np.log(prices)
            lp = lp[np.isfinite(lp)]
            m = lp.size
            if m < 24:
                return float('nan')
            ks = [k for k in (1, 2, 4, 8, 16) if k <= m // 4]
            if len(ks) < 3:
                return float('nan')
            means = []
            for k in ks:
                means.append(float(np.mean(np.abs(lp[k:] - lp[:-k]))))
            means = np.array(means, dtype=float)
            if np.any(means <= 0):
                return float('nan')
            slope, _ = np.polyfit(np.log(ks), np.log(means), 1)
            dimension = 2.0 - slope
            return float(np.clip(dimension, 1.0, 2.0))
        except Exception:
            return float('nan')

    def update_price(self, current_price: float, volume: float = 1.0) -> Dict[str, Any]:
        """更新价格并生成交易信号（分形混沌增强版）"""
        self.price_history.append(current_price)
        if len(self.price_history) > 1000:
            self.price_history = self.price_history[-1000:]
        
        prices = np.array(self.price_history)
        
        # 计算分形指标（使用可配置窗口）
        hw = min(self.hurst_window, len(prices))
        hurst = self._calculate_hurst(prices[-hw:] if len(prices) > hw else prices)
        fractal_dim = self._calculate_fractal_dimension(prices[-30:] if len(prices) > 30 else prices)
        # FIX T4-20261020: nan 护栏——数据不足时归一为中性值（0.5/1.5），
        # 避免 nan 参与比较（nan > x 恒 False）导致锁死不买/永不触发卖出的静默失效。
        if not np.isfinite(hurst):
            hurst = 0.5
        if not np.isfinite(fractal_dim):
            fractal_dim = 1.5
        
        # 趋势判断（可配置周期）
        if len(prices) < max(self.trend_period_short, self.trend_period_long):
            trend_direction = 0
        else:
            ma_short = np.mean(prices[-self.trend_period_short:])
            ma_long = np.mean(prices[-self.trend_period_long:])
            trend_direction = 1 if ma_short > ma_long else (-1 if ma_short < ma_long else 0)
        
        # 置信度：Hurst指数偏离0.5越大越有信心，分形维度越接近1.5越规律
        confidence = min(1.0, max(0.0, abs(hurst - 0.5) * 1.5 + (1.0 - abs(fractal_dim - 1.5)) * 0.5))
        
        result: Dict[str, Any] = {
            'action': 'hold', 'price': current_price,
            'position': self.position, 'balance': self.current_balance,
            'confidence': confidence, 'hurst': hurst, 'fractal_dimension': fractal_dim
        }
        
        # 信号强度：Hurst偏离0.5的程度 + 趋势方向一致性
        signal_strength = abs(hurst - 0.5) * 2.0
        if trend_direction == 1 and hurst > 0.5:
            signal_strength *= 1.5
        elif trend_direction == -1 and hurst < 0.5:
            signal_strength *= 1.2
        
        # 买入条件：Hurst超过买入阈值 + 趋势向上 + 信号强度足够 + 冷却期
        bars_since_sell = len(self.price_history) - self.last_sell_bar
        buy_signal = (hurst > self.hurst_threshold and trend_direction == 1
                      and signal_strength > self.signal_threshold
                      and bars_since_sell > self.cooldown_bars)
        
        if buy_signal and self.position == 0:
            # 分形维度过滤：维度越接近阈值，趋势越可预测
            if abs(fractal_dim - self.fractal_dim_threshold) < 0.5:
                result = self._execute_buy(current_price, 'fractal_trend')
        
        # 卖出条件：Hurst跌破卖出阈值 或 趋势反转
        if self.position > 0:
            bars_held = len(self.price_history) - self._entry_bar
            sell_signal = (hurst < self.hurst_sell_threshold or trend_direction != 1)
            if sell_signal and bars_held > self.min_hold_bars:
                result = self._execute_sell(current_price, 'fractal_trend_weaken')
        
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
        qty = available / price
        if qty < 0.01:
            return {'action': 'hold', 'price': price, 'position': self.position, 'balance': self.current_balance}
        self.current_balance -= qty * price
        self.position += qty
        self.entry_price = price
        self.total_trades += 1
        self._entry_bar = len(self.price_history)
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
        self.last_sell_bar = len(self.price_history)
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

    def get_param_space(self):
        return {
            'hurst_window': {'type': 'int', 'min': 60, 'max': 200, 'step': 20},
            'hurst_threshold': {'type': 'float', 'min': 0.50, 'max': 0.75, 'step': 0.02},
            'hurst_sell_threshold': {'type': 'float', 'min': 0.35, 'max': 0.55, 'step': 0.02},
            'signal_threshold': {'type': 'float', 'min': 0.20, 'max': 0.60, 'step': 0.05},
            'fractal_dim_threshold': {'type': 'float', 'min': 1.0, 'max': 2.0, 'step': 0.05},
            'stop_loss_threshold': {'type': 'float', 'min': 0.03, 'max': 0.10, 'step': 0.01},
            'take_profit_threshold': {'type': 'float', 'min': 0.06, 'max': 0.25, 'step': 0.02},
            'max_position_percentage': {'type': 'float', 'min': 0.15, 'max': 0.95, 'step': 0.05},
            'cooldown_bars': {'type': 'int', 'min': 6, 'max': 48, 'step': 6},
            'min_hold_bars': {'type': 'int', 'min': 3, 'max': 24, 'step': 3},
            'trend_period_short': {'type': 'int', 'min': 10, 'max': 40, 'step': 5},
            'trend_period_long': {'type': 'int', 'min': 30, 'max': 120, 'step': 10},
        }

    def get_adaptive_params(self):
        if len(self.price_history) < 60:
            return {
                'hurst_threshold': self.hurst_threshold,
                'hurst_sell_threshold': self.hurst_sell_threshold,
                'stop_loss_threshold': self.stop_loss_threshold,
                'take_profit_threshold': self.take_profit_threshold
            }
        prices = np.array(self.price_history[-60:])
        hurst = self._calculate_hurst(prices)
        hurst_factor = abs(hurst - 0.5) * 2.0
        return {
            'hurst_threshold': self.hurst_threshold * (1.0 + hurst_factor * 0.3),
            'hurst_sell_threshold': self.hurst_sell_threshold * (1.0 - hurst_factor * 0.2),
            'stop_loss_threshold': self.stop_loss_threshold * (1.0 + hurst_factor * 0.5),
            'take_profit_threshold': self.take_profit_threshold * (1.0 + hurst_factor * 0.3),
        }

    def apply_adaptive_params(self, params=None):
        if params is None:
            params = self.get_adaptive_params()
        self.hurst_threshold = params.get('hurst_threshold', self.hurst_threshold)
        self.hurst_sell_threshold = params.get('hurst_sell_threshold', self.hurst_sell_threshold)
        self.signal_threshold = params.get('signal_threshold', self.signal_threshold)
        self.fractal_dim_threshold = params.get('fractal_dim_threshold', self.fractal_dim_threshold)
        self.stop_loss_threshold = params.get('stop_loss_threshold', self.stop_loss_threshold)
        self.take_profit_threshold = params.get('take_profit_threshold', self.take_profit_threshold)
        self.max_position_percentage = params.get('max_position_percentage', self.max_position_percentage)
        self.cooldown_bars = int(params.get('cooldown_bars', self.cooldown_bars))
        self.min_hold_bars = int(params.get('min_hold_bars', self.min_hold_bars))
        self.hurst_window = int(params.get('hurst_window', self.hurst_window))
        self.trend_period_short = int(params.get('trend_period_short', self.trend_period_short))
        self.trend_period_long = int(params.get('trend_period_long', self.trend_period_long))


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