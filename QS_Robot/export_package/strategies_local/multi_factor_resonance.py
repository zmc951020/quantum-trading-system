#!/usr/bin/env python3
"""
多因子共振趋势策略
融合趋势跟踪 + 动量择时 + 波动率风控 + 资金管理
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Any

try:
    import talib as ta
    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False
    ta = None


def _ema(arr, period):
    """手动EMA: EMA = price * k + prev_ema * (1-k), k=2/(period+1)"""
    k = 2.0 / (period + 1)
    result = np.full_like(arr, np.nan, dtype=float)
    if len(arr) < period:
        return result
    result[period - 1] = np.mean(arr[:period])
    for i in range(period, len(arr)):
        result[i] = arr[i] * k + result[i - 1] * (1 - k)
    return result

def _sma(arr, period):
    result = np.full_like(arr, np.nan, dtype=float)
    if len(arr) < period:
        return result
    for i in range(period - 1, len(arr)):
        result[i] = np.mean(arr[i - period + 1:i + 1])
    return result

def _rsi(arr, period):
    result = np.full_like(arr, np.nan, dtype=float)
    if len(arr) < period + 1:
        return result
    delta = np.diff(arr, prepend=arr[0])
    for i in range(period, len(arr)):
        w = delta[i - period + 1:i + 1]
        gain = np.mean(w[w > 0]) if np.any(w > 0) else 0.0
        loss = abs(np.mean(w[w < 0])) if np.any(w < 0) else 0.0
        result[i] = 100.0 - 100.0 / (1.0 + gain / loss) if loss != 0 else 100.0
    return result

def _macd(arr, fast=12, slow=26, signal=9):
    macd_line = _ema(arr, fast) - _ema(arr, slow)
    sig_line = _ema(macd_line[slow - 1:], signal)
    sig_full = np.full_like(arr, np.nan, dtype=float)
    sig_full[slow + signal - 2:len(arr)] = sig_line[signal - 1:]
    return macd_line, sig_full, macd_line - sig_full

def _atr(high, low, close, period):
    result = np.full_like(high, np.nan, dtype=float)
    if len(high) < period + 1:
        return result
    tr = np.maximum(high - low, np.maximum(np.abs(high - np.roll(close, 1)), np.abs(low - np.roll(close, 1))))
    tr[0] = high[0] - low[0]
    for i in range(period - 1, len(tr)):
        result[i] = np.mean(tr[i - period + 1:i + 1])
    return result

def _bbands(arr, period=20, nbdev=2.0):
    mid = _sma(arr, period)
    upper, lower = np.full_like(arr, np.nan), np.full_like(arr, np.nan)
    for i in range(period - 1, len(arr)):
        std = np.std(arr[i - period + 1:i + 1])
        upper[i], lower[i] = mid[i] + nbdev * std, mid[i] - nbdev * std
    return upper, mid, lower

def _obv(close, volume):
    result = np.empty_like(close)
    result[0] = volume[0]
    for i in range(1, len(close)):
        s = np.sign(close[i] - close[i - 1])
        result[i] = result[i - 1] + s * volume[i]
    return result

class _TW:
    """统一封装 talib/手动计算，离线环境自动回退"""
    @staticmethod
    def SMA(arr, p):
        return ta.SMA(arr, p) if TALIB_AVAILABLE else _sma(arr, p)
    @staticmethod
    def RSI(arr, p):
        return ta.RSI(arr, p) if TALIB_AVAILABLE else _rsi(arr, p)
    @staticmethod
    def MACD(arr, fp=12, sp=26, sig=9):
        return ta.MACD(arr, fp, sp, sig) if TALIB_AVAILABLE else _macd(arr, fp, sp, sig)
    @staticmethod
    def ATR(h, l, c, p):
        return ta.ATR(h, l, c, p) if TALIB_AVAILABLE else _atr(h, l, c, p)
    @staticmethod
    def BBANDS(arr, p, nbu, nbd):
        return ta.BBANDS(arr, p, nbu, nbd) if TALIB_AVAILABLE else _bbands(arr, p, nbu)
    @staticmethod
    def OBV(c, v):
        return ta.OBV(c, v) if TALIB_AVAILABLE else _obv(c, v)


class MultiFactorResonanceStrategy:
    """多因子共振趋势策略：趋势跟踪+动量择时+波动率风控+资金管理"""

    def __init__(self, initial_balance: float = 100000, risk_per_trade: float = 0.02,
                 ma_fast: int = 5, ma_medium: int = 15, ma_slow: int = 30,
                 rsi_period: int = 14, atr_period: int = 14, bb_period: int = 20, bb_std: float = 2):
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.risk_per_trade = risk_per_trade
        self.ma_fast = ma_fast
        self.ma_medium = ma_medium
        self.ma_slow = ma_slow
        self.rsi_period = rsi_period
        self.atr_period = atr_period
        self.bb_period = bb_period
        self.bb_std = bb_std
        self._atr_stop_multiplier = 2.0
        self._resonance_threshold = 2  # 降低阈值：2/4因子共振即可（原4/4太严格）
        self._market_regime = 'normal'
        self.position = 0
        self.entry_price = 0
        self.stop_loss = 0
        self.trades = []
        self.price_history = []
        self.equity_curve = []

    def calculate_indicators(self, df: pd.Series) -> pd.DataFrame:
        if isinstance(df, pd.Series):
            df = pd.DataFrame({'close': df})
        
        # 计算OHLC数据（如果只有收盘价）
        if 'open' not in df.columns:
            df['open'] = df['close']
        if 'high' not in df.columns:
            df['high'] = df['close']
        if 'low' not in df.columns:
            df['low'] = df['close']
        if 'volume' not in df.columns:
            df['volume'] = 1.0
        
        tw = _TW

        # 移动平均线
        df['ma_fast'] = tw.SMA(df['close'].values, self.ma_fast)
        df['ma_medium'] = tw.SMA(df['close'].values, self.ma_medium)
        df['ma_slow'] = tw.SMA(df['close'].values, self.ma_slow)

        # RSI
        df['rsi'] = tw.RSI(df['close'].values, self.rsi_period)

        # ATR
        df['atr'] = tw.ATR(df['high'].values, df['low'].values, df['close'].values, self.atr_period)

        # 布林带
        df['bb_upper'], df['bb_mid'], df['bb_lower'] = tw.BBANDS(
            df['close'].values, self.bb_period, self.bb_std, self.bb_std
        )

        # OBV
        df['obv'] = tw.OBV(df['close'].values, df['volume'].values)
        df['obv_ma'] = tw.SMA(df['obv'], self.ma_fast)

        # MACD
        df['macd'], df['macd_signal'], df['macd_hist'] = tw.MACD(df['close'].values)
        
        return df  # 不dropna，保留NaN供后续处理
    
    def generate_signals(self, df: pd.Series) -> pd.DataFrame:
        df = self.calculate_indicators(df)
        
        # 买入因子
        factor_trend = (df['ma_fast'] > df['ma_medium']) & (df['ma_medium'] > df['ma_slow'])
        factor_momentum = (df['rsi'] > 50) & (df['rsi'] < 70)
        factor_volatility = (df['close'] > df['bb_mid']) & (df['close'] < df['bb_upper'])
        factor_volume = (df['obv'] > df['obv_ma']) & (df['volume'] > 0)

        # 共振买入信号：4选4（全部共振才触发，减少假信号）
        resonance_count = (factor_trend.astype(int) +
                          factor_momentum.astype(int) +
                          factor_volatility.astype(int) +
                          factor_volume.astype(int))
        df['buy_signal'] = resonance_count >= self._resonance_threshold

        # 卖出基础信号
        df['sell_base'] = (
            (df['ma_fast'] < df['ma_medium']) |
            (df['rsi'] > 75) |
            (df['close'] < df['bb_lower'])
        )
        
        df['sell_signal'] = False
        return df
    
    def calculate_position_size(self, atr: float, current_price: float) -> float:
        if atr <= 0 or current_price <= 0:
            return 0
        risk_amount = self.current_balance * self.risk_per_trade
        risk_per_unit = self._atr_stop_multiplier * atr
        position_size = risk_amount / risk_per_unit
        max_units = self.current_balance / current_price * 0.95  # 留5%资金缓冲
        return max(0, min(position_size, max_units))
    
    def update_price(self, current_price: float, data: pd.Series = None) -> Dict[str, any]:
        self.price_history.append(current_price)
        
        # 计算当前权益
        if self.position > 0:
            current_equity = self.current_balance + self.position * (current_price - self.entry_price)
        else:
            current_equity = self.current_balance
        self.equity_curve.append({'price': current_price, 'equity': current_equity})
        
        # 生成交易信号
        if data is not None and len(data) >= max(self.ma_slow, self.rsi_period, self.atr_period, self.bb_period):
            df = self.generate_signals(data)
            latest = df.iloc[-1]
            
            # 空仓：检查买入
            if self.position == 0:
                if latest['buy_signal']:
                    pos_size = self.calculate_position_size(latest['atr'], current_price)
                    if pos_size > 0:
                        self.position = pos_size
                        self.entry_price = current_price
                        self.stop_loss = current_price - self._atr_stop_multiplier * latest['atr']
                        self.current_balance -= pos_size * current_price
                        
                        self.trades.append({
                            'type': 'BUY',
                            'price': current_price,
                            'size': pos_size,
                            'stop_loss': self.stop_loss
                        })
                        
                        return {
                            "action": "buy",
                            "quantity": pos_size,
                            "price": current_price,
                            "balance": self.current_balance,
                            "position": self.position
                        }
            # 持仓：检查卖出/止损
            else:
                stop_triggered = current_price < self.stop_loss
                sell_signal = latest['sell_base']
                if sell_signal or stop_triggered:
                    profit = self.position * (current_price - self.entry_price)
                    self.current_balance += self.position * current_price  # 卖出仓位
                    reason = "止损" if stop_triggered else "信号卖出"
                    
                    self.trades.append({
                        'type': 'SELL',
                        'price': current_price,
                        'profit': profit,
                        'reason': reason
                    })
                    
                    position = self.position
                    self.position = 0
                    self.entry_price = 0
                    self.stop_loss = 0
                    
                    return {
                        "action": "sell",
                        "quantity": position,
                        "price": current_price,
                        "balance": self.current_balance,
                        "position": self.position,
                        "profit": profit,
                        "reason": reason
                    }
        
        return {"action": "hold", "balance": self.current_balance, "position": self.position}
    
    def get_performance(self, current_price: float = None) -> Dict[str, float]:
        if current_price is not None and self.position > 0:
            current_equity = self.current_balance + self.position * (current_price - self.entry_price)
        else:
            current_equity = self.current_balance
        
        # 计算绩效指标
        total_return = (current_equity - self.initial_balance) / self.initial_balance
        
        # 计算最大回撤
        max_drawdown = 0
        if self.equity_curve:
            equity_df = pd.DataFrame(self.equity_curve)
            if len(equity_df) > 1:
                rolling_max = equity_df['equity'].cummax()
                drawdown = (equity_df['equity'] - rolling_max) / rolling_max
                max_drawdown = drawdown.min()
        
        # 计算胜率
        win_rate = 0
        profits = [t['profit'] for t in self.trades if t['type'] == 'SELL']
        if profits:
            win_rate = sum(1 for p in profits if p > 0) / len(profits)
        
        return {
            "initial_balance": self.initial_balance,
            "current_balance": self.current_balance,
            "total_value": current_equity,
            "pnl": current_equity - self.initial_balance,
            "return": total_return,
            "max_drawdown": max_drawdown,
            "win_rate": win_rate,
            "total_trades": len(profits)
        }

    def validate_params(self) -> list[str]:
        """验证参数合法性，返回错误信息列表"""
        errors = []
        if self.ma_fast <= 0 or self.ma_medium <= 0 or self.ma_slow <= 0:
            errors.append("MA周期必须大于0")
        if not (self.ma_fast < self.ma_medium < self.ma_slow):
            errors.append(f"MA周期顺序错误: fast({self.ma_fast}) < medium({self.ma_medium}) < slow({self.ma_slow})")
        if self.rsi_period <= 0:
            errors.append("RSI周期必须大于0")
        if self.atr_period <= 0:
            errors.append("ATR周期必须大于0")
        if self.bb_period <= 0:
            errors.append("布林带周期必须大于0")
        if self.bb_std <= 0:
            errors.append("布林带标准差倍数必须大于0")
        if self.risk_per_trade <= 0 or self.risk_per_trade > 1:
            errors.append("单笔风险比例必须在(0, 1]范围内")
        return errors

    def get_param_space(self) -> Dict[str, list]:
        return {
            'ma_fast': list(range(5, 35, 5)),
            'ma_medium': list(range(20, 90, 10)),
            'ma_slow': list(range(80, 220, 20)),
            'rsi_period': list(range(7, 24, 3)),
            'atr_period': list(range(7, 24, 3)),
            'risk_per_trade': [0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05],
            'bb_period': list(range(10, 35, 5)),
            'bb_std': [1.5, 1.8, 2.0, 2.2, 2.5],
            'atr_stop_multiplier': [1.5, 2.0, 2.5, 3.0],
            'resonance_threshold': [2, 3, 4],
        }

    def _calc_volatility_regime(self, data: pd.Series) -> str:
        df = self.calculate_indicators(data)
        if len(df) < 20:
            return 'normal'
        recent_atr = df['atr'].iloc[-20:].mean()
        recent_close = df['close'].iloc[-20:].mean()
        vol_ratio = recent_atr / recent_close if recent_close > 0 else 0.02
        if vol_ratio > 0.04:
            return 'high'
        if vol_ratio < 0.015:
            return 'low'
        return 'normal'

    def get_adaptive_params(self, data: pd.Series) -> Dict[str, Any]:
        regime = self._calc_volatility_regime(data)
        params: Dict[str, Any] = {
            'ma_fast': self.ma_fast,
            'ma_medium': self.ma_medium,
            'ma_slow': self.ma_slow,
            'rsi_period': self.rsi_period,
            'atr_period': self.atr_period,
            'bb_period': self.bb_period,
            'bb_std': self.bb_std,
            'risk_per_trade': self.risk_per_trade,
            'atr_stop_multiplier': 2.0,
            'resonance_threshold': 4,
            'regime': regime,
        }
        if regime == 'high':
            params['rsi_period'] = min(self.rsi_period + 3, 21)
            params['bb_std'] = self.bb_std + 0.5
            params['risk_per_trade'] = max(self.risk_per_trade * 0.5, 0.005)
            params['atr_stop_multiplier'] = 3.0
            params['resonance_threshold'] = 4
        elif regime == 'low':
            params['rsi_period'] = max(self.rsi_period - 2, 7)
            params['bb_std'] = max(self.bb_std - 0.3, 1.5)
            params['risk_per_trade'] = min(self.risk_per_trade * 1.5, 0.05)
            params['atr_stop_multiplier'] = 1.5
            params['resonance_threshold'] = 3
        return params

    def apply_adaptive_params(self, data_or_params) -> Dict[str, Any]:
        if isinstance(data_or_params, dict):
            params = data_or_params
            for key in ['ma_fast', 'ma_medium', 'ma_slow', 'rsi_period',
                        'atr_period', 'bb_period', 'bb_std', 'risk_per_trade',
                        'atr_stop_multiplier', 'resonance_threshold']:
                if key in params and hasattr(self, key):
                    setattr(self, key, params[key])
            if 'resonance_threshold' in params:
                self._resonance_threshold = params['resonance_threshold']
            if 'atr_stop_multiplier' in params:
                self._atr_stop_multiplier = params['atr_stop_multiplier']
            return {}
        data = data_or_params
        adaptive = self.get_adaptive_params(data)
        self.ma_fast = adaptive['ma_fast']
        self.ma_medium = adaptive['ma_medium']
        self.ma_slow = adaptive['ma_slow']
        self.rsi_period = adaptive['rsi_period']
        self.atr_period = adaptive['atr_period']
        self.bb_period = adaptive['bb_period']
        self.bb_std = adaptive['bb_std']
        self.risk_per_trade = adaptive['risk_per_trade']
        self._atr_stop_multiplier = adaptive['atr_stop_multiplier']
        self._resonance_threshold = adaptive['resonance_threshold']
        self._market_regime = adaptive['regime']
        return adaptive
