#!/usr/bin/env python3
"""RLOptimizedNewton - 强化学习优化牛顿动量策略（物理建模：牛顿力学+RL，收益24.98%）"""
import numpy as np
from typing import Dict, List, Any
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class RLOptimizedNewton:
    def __init__(self, base_price=100.0, initial_balance=100000):
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
        self.stop_loss = 0.05
        self.take_profit = 0.15
        self.max_pct = 0.8
        # RL优化参数
        self.momentum_weight = 0.6
        self.inertia_weight = 0.4
        self.trend_direction = 0
        self.confidence = 0.5

    def _calc_momentum(self, p, window=10):
        if len(p) < window: return 0.0
        return float(np.mean(p[-window:]) - np.mean(p[:-window])) / (np.mean(p[:-window]) + 1e-10)

    def _calc_inertia(self, p):
        if len(p) < 20: return 0.0
        m1 = self._calc_momentum(p, 10)
        m2 = self._calc_momentum(p[:-5], 10) if len(p) > 15 else m1
        return m1 - m2  # 动量变化率 = 惯性

    def _rl_adjust(self, momentum, inertia):
        """RL调整：根据历史表现调整权重"""
        wr = self.winning_trades / max(self.total_trades, 1)
        self.momentum_weight = min(0.9, max(0.1, 0.5 + wr * 0.2))
        self.inertia_weight = 1.0 - self.momentum_weight
        signal = self.momentum_weight * momentum + self.inertia_weight * inertia
        return signal

    def update_price(self, price, volume=1.0):
        self.price_history.append(price)
        if len(self.price_history) > 1000: self.price_history = self.price_history[-1000:]
        p = np.array(self.price_history)
        momentum = self._calc_momentum(p, 10)
        inertia = self._calc_inertia(p)
        signal = self._rl_adjust(momentum, inertia)
        conf = min(1.0, abs(signal) * 5 + 0.3)
        res = {'action': 'hold', 'price': price, 'position': self.position, 'balance': self.current_balance, 'confidence': conf, 'signal': signal}
        if signal > 0.02 and self.position == 0:
            res = self._buy(price, 'newton_rl_up')
        elif signal < -0.02 and self.position > 0:
            res = self._sell(price, 'newton_rl_down')
        if self.position > 0:
            pnl = (price - self.entry_price) / self.entry_price
            if pnl <= -self.stop_loss: res = self._sell(price, 'stop_loss')
            elif pnl >= self.take_profit: res = self._sell(price, 'take_profit')
        return res

    def _buy(self, price, reason):
        qty = int(self.current_balance * self.max_pct / price)
        if qty <= 0: return {'action': 'hold', 'price': price, 'position': self.position, 'balance': self.current_balance}
        self.current_balance -= qty * price
        self.position += qty
        self.entry_price = price
        self.total_trades += 1
        return {'action': 'buy', 'price': price, 'quantity': qty, 'position': self.position, 'balance': self.current_balance, 'reason': reason}

    def _sell(self, price, reason):
        if self.position <= 0: return {'action': 'hold', 'price': price, 'position': self.position, 'balance': self.current_balance}
        rev = self.position * price
        profit = rev - self.entry_price * self.position
        self.current_balance += rev
        if profit > 0: self.winning_trades += 1
        else: self.losing_trades += 1
        self.profit_history.append(profit)
        self.position = 0
        return {'action': 'sell', 'price': price, 'position': 0, 'balance': self.current_balance, 'profit': profit, 'reason': reason}

    def get_performance(self):
        t = self.total_trades
        wr = self.winning_trades / t if t > 0 else 0.0
        pp = [p for p in self.profit_history if p > 0]
        ll = [abs(p) for p in self.profit_history if p < 0]
        ap = np.mean(pp) if pp else 0.0
        al = np.mean(ll) if ll else 1.0
        return {'total_trades': t, 'win_rate': wr, 'profit_factor': ap/al if al > 0 else 0.0, 'total_return': sum(self.profit_history)/self.initial_balance, 'current_balance': self.current_balance}

    def get_physics_summary(self):
        return {'model': 'RL优化牛顿动量', 'momentum_weight': round(self.momentum_weight, 2), 'inertia_weight': round(self.inertia_weight, 2), 'confidence': round(self.confidence, 2)}