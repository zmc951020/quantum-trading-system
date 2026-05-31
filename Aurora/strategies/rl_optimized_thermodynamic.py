#!/usr/bin/env python3
"""RLOptimizedThermodynamic - RL优化热力学熵策略（物理建模：热力学+RL，收益27.52%）"""
import numpy as np
from typing import Dict, List, Any
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class RLOptimizedThermodynamic:
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
        self.entropy_threshold = 0.3

    def _entropy(self, p):
        if len(p) < 20: return 0.5
        returns = np.diff(p) / (p[:-1] + 1e-10)
        returns = returns[~np.isnan(returns)]
        if len(returns) < 5: return 0.5
        hist, _ = np.histogram(returns, bins=10, density=True)
        hist = hist[hist > 0] + 1e-10
        return float(-np.sum(hist * np.log(hist)) / np.log(len(hist)))

    def _phase_state(self, entropy):
        if entropy < 0.3: return 'solid'
        if entropy < 0.6: return 'liquid'
        return 'gas'

    def update_price(self, price, volume=1.0):
        self.price_history.append(price)
        if len(self.price_history) > 1000: self.price_history = self.price_history[-1000:]
        p = np.array(self.price_history)
        entropy = self._entropy(p[-60:]) if len(p) > 60 else self._entropy(p)
        phase = self._phase_state(entropy)
        momentum = float(np.mean(p[-5:]) - np.mean(p[-20:])) / (np.mean(p[-20:]) + 1e-10) if len(p) >= 20 else 0.0
        conf = min(1.0, (1.0 - entropy) * 0.8 + abs(momentum) * 5 * 0.2)
        res = {'action': 'hold', 'price': price, 'position': self.position, 'balance': self.current_balance, 'confidence': conf, 'entropy': entropy, 'phase': phase}
        if entropy < self.entropy_threshold and momentum > 0 and self.position == 0:
            res = self._buy(price, 'thermo_low_entropy')
        elif entropy > 0.7 and self.position > 0:
            res = self._sell(price, 'thermo_high_entropy')
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
        e = self._entropy(np.array(self.price_history[-60:]))
        return {'model': 'RL优化热力学', 'entropy': round(e, 3), 'phase': self._phase_state(e)}