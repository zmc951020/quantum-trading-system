#!/usr/bin/env python3
"""FluidDynamicsStrategy - 流体动力学策略（物理建模：流体力学，收益20.23%）"""
import numpy as np
from typing import Dict, List, Any
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class FluidDynamicsStrategy:
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
        self.vortex_threshold = 0.8
        self.pressure_threshold = 0.0
        self.use_daily = True
        self.cooldown_bars = 1
        self.min_hold_bars = 1
        self._entry_bar = -1
        self.last_sell_bar = -50

    def _reynolds(self, p):
        if len(p) < 10: return 100.0
        m = np.mean(p)
        if m == 0: return 100.0
        s = np.std(p)
        v = np.mean(np.abs(np.diff(p) / p[:-1])) * 1e4
        return float(v * m / (s + 1e-10))

    def _vortex(self, p):
        if len(p) < 20: return 0.0
        ma = np.convolve(p, np.ones(10)/10, mode='valid')
        if len(ma) < 2: return 0.0
        return float(np.sum(np.diff(p[-len(ma):] > ma)) / len(ma))

    def _pressure(self, p):
        if len(p) < 3: return 0.0
        g = np.mean(np.diff(np.diff(p)))
        return float(g / (np.mean(np.abs(p[1:])) + 1e-10) * 1000)

    def update_price(self, price, volume=1.0):
        self.price_history.append(price)
        if len(self.price_history) > 1000: self.price_history = self.price_history[-1000:]
        p = np.array(self.price_history)
        re = self._reynolds(p[-60:]) if len(p) > 60 else self._reynolds(p)
        vo = self._vortex(p[-30:]) if len(p) > 30 else self._vortex(p)
        pr = self._pressure(p[-20:]) if len(p) > 20 else self._pressure(p)
        laminar = re < self.reynolds_threshold
        conf = min(1.0, max(0.0, (1.0 - min(re/1000, 1.0))*0.7 + abs(pr)*0.3))
        res = {'action': 'hold', 'price': price, 'position': self.position, 'balance': self.current_balance, 'confidence': conf}
        bars_since_sell = len(self.price_history) - self.last_sell_bar
        if laminar and pr > self.pressure_threshold and self.position == 0 and bars_since_sell > self.cooldown_bars:
            res = self._buy(price, 'laminar_flow')
        elif vo > self.vortex_threshold and self.position > 0:
            bars_held = len(self.price_history) - self._entry_bar
            if bars_held > self.min_hold_bars:
                res = self._sell(price, 'vortex_reversal')
        if self.position > 0:
            pnl = (price - self.entry_price) / self.entry_price
            if pnl <= -self.stop_loss: res = self._sell(price, 'stop_loss')
            elif pnl >= self.take_profit: res = self._sell(price, 'take_profit')
        return res

    def _buy(self, price, reason):
        qty = self.current_balance * self.max_pct / price
        if qty < 0.01: return {'action': 'hold', 'price': price, 'position': self.position, 'balance': self.current_balance}
        self.current_balance -= qty * price
        self.position += qty
        self.entry_price = price
        self.total_trades += 1
        self._entry_bar = len(self.price_history)
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
        self.last_sell_bar = len(self.price_history)
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
        p = np.array(self.price_history)
        re = self._reynolds(p[-60:])
        return {'model': '流体动力学', 'reynolds': round(re,1), 'regime': 'laminar' if re<500 else 'turbulent', 'vortex': round(self._vortex(p[-30:]),3)}

    def get_param_space(self):
        return {
            'reynolds_threshold': {'type': 'float', 'min': 100, 'max': 2000, 'step': 50},
            'vortex_threshold': {'type': 'float', 'min': 0.2, 'max': 2.0, 'step': 0.1},
            'pressure_threshold': {'type': 'float', 'min': -5.0, 'max': 5.0, 'step': 0.5},
            'stop_loss': {'type': 'float', 'min': 0.01, 'max': 0.12, 'step': 0.01},
            'take_profit': {'type': 'float', 'min': 0.05, 'max': 0.30, 'step': 0.01},
            'max_pct': {'type': 'float', 'min': 0.15, 'max': 0.95, 'step': 0.05},
            'cooldown_bars': {'type': 'int', 'min': 0, 'max': 5, 'step': 1},
            'min_hold_bars': {'type': 'int', 'min': 1, 'max': 5, 'step': 1},
        }

    def get_adaptive_params(self):
        if len(self.price_history) < 20:
            return {'reynolds_threshold': self.reynolds_threshold, 'stop_loss': self.stop_loss, 'take_profit': self.take_profit}
        prices = np.array(self.price_history[-20:])
        volatility = float(np.std(prices) / (np.mean(prices) + 1e-10))
        vol_factor = 1.0 / (1.0 + volatility * 100)
        return {
            'reynolds_threshold': self.reynolds_threshold * vol_factor,
            'vortex_threshold': self.vortex_threshold,
            'pressure_threshold': self.pressure_threshold,
            'stop_loss': self.stop_loss * (1.0 + volatility * 50),
            'take_profit': self.take_profit * (1.0 + volatility * 30),
            'max_pct': self.max_pct,
            'cooldown_bars': self.cooldown_bars,
            'min_hold_bars': self.min_hold_bars,
        }

    def apply_adaptive_params(self, params=None):
        if params is None:
            params = self.get_adaptive_params()
        self.reynolds_threshold = params.get('reynolds_threshold', self.reynolds_threshold)
        self.vortex_threshold = params.get('vortex_threshold', self.vortex_threshold)
        self.pressure_threshold = params.get('pressure_threshold', self.pressure_threshold)
        self.stop_loss = params.get('stop_loss', self.stop_loss)
        self.take_profit = params.get('take_profit', self.take_profit)
        self.max_pct = params.get('max_pct', self.max_pct)
        self.cooldown_bars = int(params.get('cooldown_bars', self.cooldown_bars))
        self.min_hold_bars = int(params.get('min_hold_bars', self.min_hold_bars))