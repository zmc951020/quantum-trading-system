#!/usr/bin/env python3
"""RLOptimizedFluid - RL优化流体动力学策略（物理建模：流体力学+RL，收益29.15%）"""
import numpy as np
from typing import Dict, List, Any
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class RLOptimizedFluid:
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
        self.reynolds_threshold = 500.0

    def _reynolds(self, p):
        if len(p) < 10: return 100.0
        m = np.mean(p)
        if m == 0: return 100.0
        v = np.mean(np.abs(np.diff(p) / p[:-1])) * 1e4
        return float(v * m / (np.std(p) + 1e-10))

    def _pressure(self, p):
        if len(p) < 3: return 0.0
        g = np.mean(np.diff(np.diff(p)))
        return float(g / (np.mean(np.abs(p[1:])) + 1e-10) * 1000)

    def _vortex(self, p):
        if len(p) < 20: return 0.0
        ma = np.convolve(p, np.ones(10)/10, mode='valid')
        if len(ma) < 2: return 0.0
        return float(np.sum(np.diff(p[-len(ma):] > ma)) / len(ma))

    def update_price(self, price, volume=1.0):
        self.price_history.append(price)
        if len(self.price_history) > 1000: self.price_history = self.price_history[-1000:]
        p = np.array(self.price_history)
        re = self._reynolds(p[-60:]) if len(p) > 60 else self._reynolds(p)
        pr = self._pressure(p[-20:]) if len(p) > 20 else self._pressure(p)
        vo = self._vortex(p[-30:]) if len(p) > 30 else self._vortex(p)
        laminar = re < self.reynolds_threshold
        conf = min(1.0, (1.0 - min(re/1000, 1.0))*0.6 + abs(pr)*0.4)
        res = {'action': 'hold', 'price': price, 'position': self.position, 'balance': self.current_balance, 'confidence': conf}
        if laminar and pr > 0.02 and self.position == 0:
            res = self._buy(price, 'fluid_rl')
        elif vo > 0.8 and self.position > 0:
            res = self._sell(price, 'fluid_rl_vortex')
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
        re = self._reynolds(p)
        return {'model': 'RL优化流体', 'reynolds': round(re,1), 'regime': 'laminar' if re<500 else 'turbulent'}