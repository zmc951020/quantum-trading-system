"""智能标的轮动策略 — 基于68因子加权评分的信号生成
==================================================
根因修复D4: ShepherdRotationModule是优化器模块，无交易信号生成方法。
本策略类为其添加因子计算和买卖信号生成能力。

核心逻辑:
  1. 从OHLCV数据计算45个技术因子（趋势/动量/波动率/成交量）
  2. 18个价值/质量因子使用中性值（仅价格数据无法计算基本面）
  3. 使用优化后的因子权重进行加权评分
  4. 评分超过入场阈值 → 买入信号，跌破出场阈值 → 卖出信号
  5. 5个轮动控制参数控制持仓管理
"""
import os
import sys
import numpy as np
from typing import Dict, List, Optional, Any, Tuple

current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)


class ShepherdRotationStrategy:
    """智能标的轮动策略 — 交易信号生成器"""

    NAME = "智能标的轮动策略"
    ID = "shepherd_rotation_strategy"

    def __init__(self):
        self._init_factor_weights()
        self._init_rotation_controls()
        self._position = 0
        self._entry_price = 0

    def _init_factor_weights(self):
        """初始化68因子权重（默认值1.0）"""
        self.factor_weights = {}
        groups = {
            'trend_factors': ['ma5_slope', 'ma10_slope', 'ma20_slope', 'ma60_slope',
                'price_to_ma20', 'price_to_ma60', 'adx_14', 'adx_20',
                'plus_di_14', 'minus_di_14', 'trend_strength_20', 'trend_consistency'],
            'momentum_factors': ['rsi_6', 'rsi_12', 'rsi_14', 'rsi_20',
                'macd_line', 'macd_signal', 'macd_histogram', 'roc_5', 'roc_10', 'roc_20',
                'momentum_10d', 'momentum_20d', 'momentum_60d',
                'momentum_acceleration', 'williams_r_14'],
            'volatility_factors': ['atr_10', 'atr_14', 'atr_20',
                'bollinger_width', 'bollinger_position',
                'historical_vol_10d', 'historical_vol_20d', 'historical_vol_60d',
                'volatility_ratio', 'range_volatility'],
            'volume_factors': ['obv', 'obv_ma_slope', 'volume_slope_5', 'volume_slope_10',
                'volume_ratio_20', 'money_flow_index_14',
                'volume_price_correlation', 'accumulation_distribution'],
            'value_factors': ['pe_ratio', 'pb_ratio', 'ps_ratio',
                'roe', 'roa', 'gross_margin', 'net_margin',
                'dividend_yield', 'revenue_growth', 'earnings_growth',
                'book_value_per_share', 'free_cash_flow_yield'],
            'quality_factors': ['operating_margin', 'asset_turnover',
                'debt_to_equity', 'current_ratio',
                'earnings_quality', 'sustainable_growth_rate'],
        }
        for group_factors in groups.values():
            for f in group_factors:
                self.factor_weights[f] = 1.0

    def _init_rotation_controls(self):
        self.rotation_threshold = 0.08
        self.min_hold_period = 10
        self.max_position_pct = 0.15
        self.max_holdings = 5
        self.rebalance_frequency = 7
        self.stop_loss_pct = 0.08  # FIX T4-20261020: 补充显式止损（专家审核指出缺止损）

    # ============================================================
    # 因子计算
    # ============================================================

    def _compute_ma(self, closes, period):
        if len(closes) < period:
            return np.full(len(closes), np.nan)
        result = np.full(len(closes), np.nan)
        cumsum = np.cumsum(np.insert(closes, 0, 0))
        result[period-1:] = (cumsum[period:] - cumsum[:-period]) / period
        return result

    def _compute_ema(self, closes, period):
        if len(closes) < 2:
            return np.full(len(closes), np.nan)
        alpha = 2.0 / (period + 1)
        result = np.full(len(closes), np.nan)
        result[0] = closes[0]
        for i in range(1, len(closes)):
            result[i] = alpha * closes[i] + (1 - alpha) * result[i-1]
        return result

    def _compute_rsi(self, closes, period):
        if len(closes) < period + 1:
            return np.full(len(closes), np.nan)
        deltas = np.diff(closes)
        result = np.full(len(closes), np.nan)
        gains = np.maximum(deltas[:period], 0)
        losses = np.maximum(-deltas[:period], 0)
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        for i in range(period, len(closes)):
            if avg_loss == 0:
                result[i] = 100.0
            else:
                result[i] = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
            delta = deltas[i-1]
            avg_gain = (avg_gain * (period-1) + max(delta, 0)) / period
            avg_loss = (avg_loss * (period-1) + max(-delta, 0)) / period
        return result

    def _compute_macd(self, closes, fast=12, slow=26, signal=9):
        ema_fast = self._compute_ema(closes, fast)
        ema_slow = self._compute_ema(closes, slow)
        macd_line = ema_fast - ema_slow
        macd_signal_line = np.full(len(closes), np.nan)
        valid = ~np.isnan(macd_line)
        if np.sum(valid) > signal:
            sig = self._compute_ema(macd_line[valid], signal)
            macd_signal_line[valid] = np.insert(sig, 0, [np.nan]*(np.sum(valid)-len(sig)))
        return macd_line, macd_signal_line

    def _compute_atr(self, highs, lows, closes, period):
        if len(closes) < 2:
            return np.full(len(closes), np.nan)
        tr = np.maximum(highs[1:] - lows[1:],
                np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1])))
        return self._compute_ma(np.insert(tr, 0, 0), period)

    def compute_all_factors(self, bars: dict) -> Dict[str, np.ndarray]:
        """从OHLCV数据计算45个技术因子"""
        opens = np.array(bars.get("open", []), dtype=float)
        highs = np.array(bars.get("high", []), dtype=float)
        lows = np.array(bars.get("low", []), dtype=float)
        closes = np.array(bars.get("close", []), dtype=float)
        volumes = np.array(bars.get("volume", []), dtype=float)
        n = len(closes)
        if n < 60:
            raise ValueError(f"数据不足: {n}条, 需要≥60条")

        factors = {}
        # 趋势因子
        for p in [5, 10, 20, 60]:
            ma = self._compute_ma(closes, p)
            factors[f'ma{p}_slope'] = np.gradient(np.where(np.isnan(ma), closes, ma))
        factors['price_to_ma20'] = closes / self._compute_ma(closes, 20)
        factors['price_to_ma60'] = closes / self._compute_ma(closes, 60)
        factors['trend_strength_20'] = (closes - self._compute_ma(closes, 20)) / self._compute_ma(closes, 20) * 100
        factors['trend_consistency'] = np.where(
            factors['ma5_slope'] > 0, 1.0,
            np.where(factors['ma5_slope'] < 0, -1.0, 0))
        # ADX简化
        factors['adx_14'] = np.abs(factors['trend_strength_20']) * 10
        factors['adx_20'] = factors['adx_14'] * 0.9
        factors['plus_di_14'] = np.where(factors['ma5_slope'] > 0, factors['trend_strength_20'] * 5, 0)
        factors['minus_di_14'] = np.where(factors['ma5_slope'] < 0, -factors['trend_strength_20'] * 5, 0)

        # 动量因子
        for p in [6, 12, 14, 20]:
            factors[f'rsi_{p}'] = self._compute_rsi(closes, p)
        macd_line, macd_sig = self._compute_macd(closes)
        factors['macd_line'] = macd_line
        factors['macd_signal'] = macd_sig
        factors['macd_histogram'] = (macd_line - macd_sig) * 2
        for p in [5, 10, 20]:
            factors[f'roc_{p}'] = np.insert(np.diff(closes, p) / closes[:-p] * 100, 0, [np.nan]*p)
        for p in [10, 20, 60]:
            factors[f'momentum_{p}d'] = np.insert(closes[p:] / closes[:-p] - 1, 0, [np.nan]*p)
        factors['momentum_acceleration'] = np.full(n, np.nan)
        mom10 = factors['momentum_10d']
        valid = ~np.isnan(mom10)
        if np.sum(valid) > 1:
            diff = np.diff(mom10[valid])
            factors['momentum_acceleration'][valid] = np.insert(diff, 0, np.nan)
        # Williams %R
        wr = np.full(n, np.nan)
        for i in range(14, n):
            hh = np.max(highs[i-13:i+1])
            ll = np.min(lows[i-13:i+1])
            wr[i] = (hh - closes[i]) / (hh - ll + 1e-9) * -100
        factors['williams_r_14'] = wr

        # 波动率因子
        for p in [10, 14, 20]:
            factors[f'atr_{p}'] = self._compute_atr(highs, lows, closes, p)
        ma20 = self._compute_ma(closes, 20)
        std20 = np.array([np.std(closes[max(0,i-19):i+1]) for i in range(n)])
        factors['bollinger_width'] = std20 * 4 / ma20
        factors['bollinger_position'] = (closes - (ma20 - 2*std20)) / (std20 * 4 + 1e-9)
        for p in [10, 20, 60]:
            factors[f'historical_vol_{p}d'] = np.array([np.std(np.diff(closes[max(0,i-p):i+1]) / closes[max(0,i-p):i]) for i in range(n)])
        factors['volatility_ratio'] = factors['historical_vol_10d'] / (factors['historical_vol_60d'] + 1e-9)
        factors['range_volatility'] = (highs - lows) / closes

        # 成交量因子
        factors['obv'] = np.cumsum(np.where(closes > np.insert(closes[:-1], 0, closes[0]), volumes, np.where(closes < np.insert(closes[:-1], 0, closes[0]), -volumes, 0)))
        factors['obv_ma_slope'] = np.gradient(self._compute_ma(factors['obv'], 10))
        for p in [5, 10]:
            factors[f'volume_slope_{p}'] = np.gradient(self._compute_ma(volumes, p))
        factors['volume_ratio_20'] = volumes / (self._compute_ma(volumes, 20) + 1e-9)
        factors['money_flow_index_14'] = self._compute_rsi(volumes * closes, 14)
        factors['volume_price_correlation'] = np.array([np.corrcoef(closes[max(0,i-19):i+1], volumes[max(0,i-19):i+1])[0,1] if i >= 20 else 0 for i in range(n)])
        factors['accumulation_distribution'] = np.cumsum((closes - lows) / (highs - lows + 1e-9) * volumes)

        # 价值/质量因子 — 价格数据不可算，中性值
        for f in ['pe_ratio', 'pb_ratio', 'ps_ratio', 'roe', 'roa', 'gross_margin',
                  'net_margin', 'dividend_yield', 'revenue_growth', 'earnings_growth',
                  'book_value_per_share', 'free_cash_flow_yield',
                  'operating_margin', 'asset_turnover', 'debt_to_equity',
                  'current_ratio', 'earnings_quality', 'sustainable_growth_rate']:
            factors[f] = np.full(n, 1.0)

        return factors

    # ============================================================
    # 评分与信号生成
    # ============================================================

    def compute_score(self, factors: Dict[str, np.ndarray], idx: int) -> float:
        """计算第idx根K线的加权评分"""
        total_weight = 0
        weighted_sum = 0
        for name, series in factors.items():
            w = self.factor_weights.get(name, 1.0)
            val = series[idx]
            if np.isnan(val) or np.isinf(val):
                continue
            total_weight += w
            weighted_sum += w * val
        return weighted_sum / total_weight if total_weight > 0 else 0.5

    def generate(self, bars) -> dict:
        """生成买卖信号列表，兼容DataFrame和dict"""
        import pandas as pd
        if isinstance(bars, pd.DataFrame):
            bars = {
                "open": bars["open"].tolist(), "high": bars["high"].tolist(),
                "low": bars["low"].tolist(), "close": bars["close"].tolist(),
                "volume": bars["volume"].tolist(),
            }
        closes = bars.get("close", [])
        n = len(closes)
        if n < 60:
            return {"signals": [0]*n, "metadata": {"strategy": self.NAME, "error": "数据不足"}}

        factors = self.compute_all_factors(bars)
        scores = []
        for i in range(n):
            scores.append(self.compute_score(factors, i))

        scores = np.array(scores)
        # 归一化到0-1
        score_min, score_max = np.nanmin(scores), np.nanmax(scores)
        if score_max - score_min > 1e-9:
            scores = (scores - score_min) / (score_max - score_min)

        # 使用滚动百分位阈值（自适应）
        lookback = max(20, self.min_hold_period * 2)
        signals = [0] * n
        position = 0
        entry_price = 0
        entry_idx = 0

        entry_threshold = 0.65 + self.rotation_threshold
        exit_threshold = 0.35 - self.rotation_threshold * 0.5

        for i in range(lookback, n):
            if np.isnan(scores[i]):
                continue
            recent = scores[max(0, i-lookback):i]
            pct_rank = np.sum(recent < scores[i]) / len(recent)

            if position == 0:
                if pct_rank > entry_threshold:
                    signals[i] = 1
                    position = 1
                    entry_price = closes[i]
                    entry_idx = i
            else:
                hold_days = i - entry_idx
                exit_ok = hold_days >= self.min_hold_period
                # FIX T4-20261020: 显式止损——价格跌破入场价×(1-stop_loss_pct) 强制退出
                if closes[i] <= entry_price * (1 - self.stop_loss_pct):
                    signals[i] = -1
                    position = 0
                elif pct_rank < exit_threshold and exit_ok:
                    signals[i] = -1
                    position = 0
                elif hold_days >= self.rebalance_frequency * 2:
                    signals[i] = -1
                    position = 0

        return {
            "signals": signals,
            "metadata": {
                "strategy": self.NAME,
                "buy_count": sum(1 for s in signals if s == 1),
                "sell_count": sum(1 for s in signals if s == -1),
                "avg_score": float(np.nanmean(scores)),
                "threshold": self.rotation_threshold,
            }
        }

    # ============================================================
    # 自适应参数接口
    # ============================================================

    def get_param_space(self) -> Dict[str, List[float]]:
        """返回可优化参数空间"""
        return {
            'rotation_threshold': [0.03, 0.05, 0.08, 0.10, 0.12, 0.15],
            'min_hold_period': [3, 5, 10, 15, 20, 30],
            'max_position_pct': [0.05, 0.10, 0.15, 0.20, 0.25, 0.30],
            'max_holdings': [1, 2, 3, 5, 7, 10],
            'rebalance_frequency': [1, 3, 5, 7, 10, 15, 20],
            'stop_loss_pct': [0.03, 0.05, 0.08, 0.12, 0.15],  # FIX T4: 止损参数
        }

    def get_adaptive_params(self, market_regime: str = 'normal') -> Dict[str, float]:
        """根据市场状态动态调整参数"""
        regimes = {
            'trend': {'rotation_threshold': 0.08, 'min_hold_period': 15,
                      'max_position_pct': 0.25, 'max_holdings': 5, 'rebalance_frequency': 10},
            'oscillation': {'rotation_threshold': 0.05, 'min_hold_period': 5,
                            'max_position_pct': 0.12, 'max_holdings': 3, 'rebalance_frequency': 3},
            'bear': {'rotation_threshold': 0.12, 'min_hold_period': 20,
                     'max_position_pct': 0.08, 'max_holdings': 2, 'rebalance_frequency': 15},
            'normal': {'rotation_threshold': 0.08, 'min_hold_period': 10,
                       'max_position_pct': 0.15, 'max_holdings': 5, 'rebalance_frequency': 7},
        }
        return regimes.get(market_regime, regimes['normal'])

    def apply_adaptive_params(self, params: Dict[str, float]):
        """应用自适应参数"""
        for k, v in params.items():
            if hasattr(self, k):
                setattr(self, k, v)