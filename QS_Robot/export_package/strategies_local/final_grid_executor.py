#!/usr/bin/env python3
"""网格执行器：网格层级计算、买卖执行、金字塔式下跌承接"""

import numpy as np
import pandas as pd
from typing import List, Dict, Optional, Tuple


class GridExecutor:
    """网格交易执行器：网格计算 + 买卖执行 + 金字塔承接"""

    def __init__(self, base_price: float, initial_balance: float = 100000):
        self.base_price = base_price
        self.initial_balance = initial_balance
        self.grid_levels = 100
        self.grid_spacing = 0.0015
        self.grids = self.calculate_grid_levels(base_price, 100, 0.0015)
        self.position = 0
        self.entry_price = 0
        self.last_buy_price = base_price
        self.buy_count = 0
        self.max_buy_count = 8
        self.min_buy_amount = 200
        self.max_buy_amount = 5000
        self.accumulation_fund = 0
        self.accumulation_enabled = True
        self.last_accumulation_price = base_price
        self.accumulation_level = 0
        self._trend_hist: List[float] = []  # 趋势闸门用的内部价格序列
        self.constellation_levels = [
            {'threshold': 0.02, 'allocation': 0.1, 'max_position': 0.15},
            {'threshold': 0.04, 'allocation': 0.15, 'max_position': 0.35},
            {'threshold': 0.06, 'allocation': 0.2, 'max_position': 0.55},
            {'threshold': 0.08, 'allocation': 0.25, 'max_position': 0.75},
            {'threshold': 0.10, 'allocation': 0.3, 'max_position': 1.0},
        ]

    def calculate_grid_levels(self, price: float, levels: int, spacing: float) -> List[float]:
        grids = []
        for i in range(-levels, levels + 1):
            grids.append(price * (1 + spacing) ** i)
        return sorted(grids)

    def _calc_rsi(self, data: pd.Series, period: int = 14) -> float:
        if len(data) < period + 1:
            return 50
        delta = data.diff()
        gain = delta.clip(lower=0).rolling(period).mean().iloc[-1]
        loss = (-delta.clip(upper=0)).rolling(period).mean().iloc[-1]
        return 100 - 100 / (1 + gain / loss) if loss != 0 else 100

    def _calc_macd(self, data: pd.Series) -> Tuple[float, float, float]:
        if len(data) < 35:
            return 0, 0, 0
        ema12 = data.ewm(span=12, adjust=False).mean()
        ema26 = data.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        return macd.iloc[-1], signal.iloc[-1], (macd - signal).iloc[-1]

    def _calc_bbands(self, data: pd.Series) -> Tuple[float, float, float]:
        if len(data) < 20:
            p = data.iloc[-1]
            return p * 1.05, p, p * 0.95
        ma = data.rolling(20).mean().iloc[-1]
        std = data.rolling(20).std().iloc[-1] or 0.01
        return ma + 2 * std, ma, ma - 2 * std

    def _check_accumulation(self, current_price: float, data: pd.Series) -> bool:
        if not self.accumulation_enabled or len(data) < 50:
            return False
        rsi_vals = [self._calc_rsi(data, p) for p in [9, 14, 21]]
        _, _, hist = self._calc_macd(data)
        _, _, lower = self._calc_bbands(data)
        momentum = (data.iloc[-1] - data.iloc[-20]) / data.iloc[-20] if len(data) >= 20 else 0
        drawdown = (data.iloc[-30:].max() - current_price) / data.iloc[-30:].max()
        met = 0
        if self.accumulation_level > 0:
            met += 1
        if sum(1 for r in rsi_vals if r < 30) >= 2:
            met += 1
        if hist > 0 or (len(data) >= 60 and hist > self._calc_macd(data.iloc[:-5])[2]):
            met += 1
        if current_price <= lower * 1.01:
            met += 1
        if momentum > 0.005:
            met += 1
        if drawdown > 0.03:
            met += 1
        if self.accumulation_fund > self.min_buy_amount:
            met += 1
        return met >= 5

    def _calc_accumulation_level(self, current_price: float, data: pd.Series) -> int:
        if len(data) < 20:
            return 0
        drawdown = (data.iloc[-20:].max() - current_price) / data.iloc[-20:].max()
        for i, cfg in enumerate(self.constellation_levels):
            if drawdown >= cfg['threshold']:
                return i + 1
        return 0

    def _record_trend_price(self, price: float):
        """内部维护最近价格序列，供日线趋势闸门使用。"""
        try:
            self._trend_hist.append(float(price))
            if len(self._trend_hist) > 60:
                self._trend_hist = self._trend_hist[-60:]
        except Exception:
            pass

    def _downtrend_block(self, seq=None, current_price=None) -> bool:
        """日线趋势闸门：近20根bar累计下跌超过2%则阻止买入（震荡/上涨放行）。
        seq: 可选价格序列(pd.Series/list)；不传则用内部self._trend_hist。
        数据不足21根bar时不拦截，保证初期正常交易。"""
        try:
            if seq is not None:
                data = list(seq.values) if hasattr(seq, 'values') else [float(x) for x in list(seq)]
            else:
                data = list(self._trend_hist)
            if current_price is not None:
                data.append(float(current_price))
            if len(data) < 21:
                return False
            p_old = data[-21]
            p_now = data[-1]
            return p_old > p_now * 1.02
        except Exception:
            return False

    def execute_grid_buy(self, price: float, balance: float, position: float) -> Optional[Dict]:
        self._record_trend_price(price)
        # 日线趋势闸门：单边下跌>2%时不新开网格买入
        if self._downtrend_block():
            return None
        if balance < self.min_buy_amount:
            return None
        buy_amount = min(balance * 0.15, self.max_buy_amount)
        if buy_amount < self.min_buy_amount:
            return None
        qty = buy_amount / price
        if qty < 0.01:
            return None
        self.position += qty
        self.last_buy_price = price
        if self.entry_price == 0:
            self.entry_price = price
        return {"action": "buy", "quantity": qty, "price": price, "reason": "grid_buy"}

    def execute_grid_sell(self, price: float, position: float) -> Optional[Dict]:
        if position <= 0:
            return None
        sell_qty = position * 0.3
        if sell_qty < 0.01:
            return None
        self.position -= sell_qty
        if self.position <= 0.0001:
            self.position = 0
            self.entry_price = 0
        return {"action": "sell", "quantity": sell_qty, "price": price, "reason": "grid_sell"}

    def pyramid_承接(self, bars: pd.Series, balance: float, position: float) -> Optional[Dict]:
        if len(bars) < 50:
            return None
        current_price = bars.iloc[-1]
        # 日线趋势闸门：单边下跌>2%时不做金字塔承接买入
        if self._downtrend_block(seq=bars):
            return None
        if not self._check_accumulation(current_price, bars):
            return None
        level = self._calc_accumulation_level(current_price, bars)
        if level == 0 or level <= self.accumulation_level:
            return None
        target = level - 1
        if target >= len(self.constellation_levels):
            return None
        cfg = self.constellation_levels[target]
        pos_ratio = (position * current_price) / self.initial_balance
        if pos_ratio >= cfg['max_position']:
            return None
        available = min(self.accumulation_fund, self.initial_balance * cfg['allocation'] - position * current_price)
        if available < self.min_buy_amount:
            return None
        qty = available / current_price
        if qty < 0.01:
            return None
        self.position += qty
        self.accumulation_fund -= available
        if self.entry_price == 0:
            self.entry_price = current_price
        else:
            old_pos = self.position - qty
            self.entry_price = (self.entry_price * old_pos + current_price * qty) / self.position
        self.last_accumulation_price = current_price
        self.accumulation_level = level
        return {"action": "buy", "quantity": qty, "price": current_price, "reason": f"accumulation_level_{level}", "accumulation_fund": self.accumulation_fund, "average_cost": self.entry_price}

    def release_accumulation_fund(self, current_price: float):
        if self.position > 0 and self.entry_price > 0:
            if (current_price - self.entry_price) / self.entry_price > 0.02:
                self.accumulation_fund += self.position * (current_price - self.entry_price) * 0.5

    def get_param_space(self):
        return {
            'grid_levels': {'min': 20, 'max': 200, 'step': 10, 'default': self.grid_levels},
            'grid_spacing': {'min': 0.0005, 'max': 0.005, 'step': 0.0002, 'default': self.grid_spacing},
            'max_buy_count': {'min': 3, 'max': 15, 'step': 1, 'default': self.max_buy_count},
            'min_buy_amount': {'min': 50, 'max': 500, 'step': 25, 'default': self.min_buy_amount},
            'max_buy_amount': {'min': 1000, 'max': 10000, 'step': 500, 'default': self.max_buy_amount},
            'constellation_levels': self.constellation_levels
        }

    def get_adaptive_params(self, volatility=None, trend=None):
        base = {
            'grid_levels': self.grid_levels,
            'grid_spacing': self.grid_spacing,
            'max_buy_count': self.max_buy_count,
            'min_buy_amount': self.min_buy_amount,
            'max_buy_amount': self.max_buy_amount
        }
        if volatility is not None:
            if volatility > 0.03:
                base['grid_spacing'] = min(0.005, self.grid_spacing * 1.5)
                base['max_buy_count'] = min(15, self.max_buy_count + 3)
                base['max_buy_amount'] = min(10000, self.max_buy_amount * 0.7)
            elif volatility < 0.01:
                base['grid_spacing'] = max(0.0005, self.grid_spacing * 0.7)
                base['max_buy_count'] = max(3, self.max_buy_count - 2)
                base['max_buy_amount'] = min(10000, self.max_buy_amount * 1.2)
        if trend is not None and trend < -0.02:
            base['min_buy_amount'] = min(500, self.min_buy_amount * 1.5)
            base['max_buy_count'] = min(15, self.max_buy_count + 2)
        return base