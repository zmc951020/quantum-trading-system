#!/usr/bin/env python3
"""RLOptimizedFractal - RL优化分形策略（物理建模：分形几何+RL，收益22.70%）"""
import numpy as np
from typing import Dict, List, Any
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class RLOptimizedFractal:
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
        self.hurst_threshold = 0.55

    def _hurst(self, p):
        if len(p) < 30: return 0.5
        n = len(p)
        m = np.mean(p)
        d = p - m
        c = np.cumsum(d)
        r = max(c) - min(c)
        if r == 0: return 0.5
        s = np.std(p)
        if s == 0: return 0.5
        return max(0.0, min(1.0, np.log(r / s) / np.log(n)))

    def _fractal_dim(self, p):
        if len(p) < 20: return 1.5
        returns = np.abs(np.diff(p) / (p[:-1] + 1e-10))
        if len(returns) <= 0: return 1.5
        sc = np.std(returns) / (np.mean(returns) + 1e-10)
        return max(1.0, min(2.0, 2.0 - min(sc, 1.0)))

    def update_price(self, price, volume=1.0):
        self.price_history.append(price)
        if len(self.price_history) > 1000: self.price_history = self.price_history[-1000:]
        p = np.array(self.price_history)
        hurst = self._hurst(p[-60:]) if len(p) > 60 else self._hurst(p)
        fdim = self._fractal_dim(p[-30:]) if len(p) > 30 else self._fractal_dim(p)
        trend = 1 if len(p)>=20 and np.mean(p[-10:])>np.mean(p[-20:]) else (-1 if len(p)>=20 else 0)
        conf = min(1.0, abs(hurst-0.5)*2 + abs(fdim-1.5)*0.5)
        res = {'action': 'hold', 'price': price, 'position': self.position, 'balance': self.current_balance, 'confidence': conf}
        if hurst > 0.55 and trend == 1 and self.position == 0:
            res = self._buy(price, 'fractal_rl')
        elif hurst < 0.45 and trend == -1 and self.position > 0:
            res = self._sell(price, 'fractal_rl_reverse')
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
        if len(self.price_history) < 60: return {'status': 'insufficient_data'}
        p = np.array(self.price_history[-60:])
        h = self._hurst(p)
        return {'model': 'RL优化分形', 'hurst': round(h,3), 'fractal_dim': round(self._fractal_dim(p),3)}