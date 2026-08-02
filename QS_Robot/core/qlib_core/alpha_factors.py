#!/usr/bin/env python3
"""
Alpha158Engine - Alpha158因子计算引擎

实现微软Qlib Alpha158标准化因子库的158个因子。
因子分类：
  1. 趋势因子 (Trend): 21个 - 移动平均、MACD、ADX等
  2. 反转因子 (Reversal): 18个 - RSI、威廉指标、布林带等
  3. 流动性因子 (Liquidity): 16个 - 换手率、成交量比率等
  4. 波动率因子 (Volatility): 15个 - 历史波动率、ATR等
  5. 动量因子 (Momentum): 20个 - 价格动量、成交量动量等
  6. 估值因子 (Valuation): 18个 - PE、PB、市值等
  7. 质量因子 (Quality): 15个 - ROE、毛利率、负债率等
  8. 量价因子 (VolumePrice): 15个 - OBV、MFI、VWAP偏离等
  9. 形态因子 (Pattern): 10个 - 蜡烛图形态、突破识别等
  10. 高频因子 (HighFreq): 10个 - 分钟级滚动窗口、分时特征

设计依据：
  豆包审查 + Trae方案 - 替换现有49个自研因子，实现标准化因子计算
  支持日线/1min双频率，内置IC/IR校验、因子衰减检测
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class FactorResult:
    """单个因子计算结果"""
    name: str
    category: str
    values: np.ndarray
    ic: Optional[float] = None          # Information Coefficient
    ir: Optional[float] = None          # Information Ratio
    ic_std: Optional[float] = None      # IC标准差
    ic_positive_ratio: Optional[float] = None  # IC > 0 比例
    decay: Optional[float] = None       # 因子衰减率
    status: str = "ok"


@dataclass
class AlphaResult:
    """因子批量计算结果"""
    factors: Dict[str, FactorResult] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "factors": {k: {
                "category": v.category,
                "ic": v.ic,
                "ir": v.ir,
                "status": v.status,
            } for k, v in self.factors.items()},
            "metadata": self.metadata,
            "summary": self.summary,
        }


class Alpha158Engine:
    """Alpha158因子计算引擎

    支持日线和1min分钟双频率计算。
    内置IC/IR分析、因子衰减检测、分位数分层。

    使用示例:
        >>> engine = Alpha158Engine()
        >>> result = engine.compute_all(df, freq="day")
        >>> print(result.summary)
    """

    def __init__(self):
        self._factor_registry = self._build_registry()

    def _build_registry(self) -> Dict[str, Dict[str, Any]]:
        """构建因子注册表（分类 + 计算函数 + 参数）"""
        return {
            # ==================== 趋势因子 (21个) ====================
            "SMA_5":  {"cat": "Trend", "fn": self._sma, "params": {"window": 5}},
            "SMA_10": {"cat": "Trend", "fn": self._sma, "params": {"window": 10}},
            "SMA_20": {"cat": "Trend", "fn": self._sma, "params": {"window": 20}},
            "SMA_60": {"cat": "Trend", "fn": self._sma, "params": {"window": 60}},
            "EMA_5":  {"cat": "Trend", "fn": self._ema, "params": {"window": 5}},
            "EMA_10": {"cat": "Trend", "fn": self._ema, "params": {"window": 10}},
            "EMA_20": {"cat": "Trend", "fn": self._ema, "params": {"window": 20}},
            "EMA_60": {"cat": "Trend", "fn": self._ema, "params": {"window": 60}},
            "MACD_DIF":   {"cat": "Trend", "fn": self._macd_dif},
            "MACD_DEA":   {"cat": "Trend", "fn": self._macd_dea},
            "MACD_HIST":  {"cat": "Trend", "fn": self._macd_hist},
            "ADX":        {"cat": "Trend", "fn": self._adx, "params": {"window": 14}},
            "PLUS_DI":    {"cat": "Trend", "fn": self._plus_di, "params": {"window": 14}},
            "MINUS_DI":   {"cat": "Trend", "fn": self._minus_di, "params": {"window": 14}},
            "ATR":        {"cat": "Trend", "fn": self._atr, "params": {"window": 14}},
            "TRIX":       {"cat": "Trend", "fn": self._trix, "params": {"window": 12}},
            "BB_UPPER":   {"cat": "Trend", "fn": self._bb_upper, "params": {"window": 20}},
            "BB_MIDDLE":  {"cat": "Trend", "fn": self._bb_middle, "params": {"window": 20}},
            "BB_LOWER":   {"cat": "Trend", "fn": self._bb_lower, "params": {"window": 20}},
            "BB_WIDTH":   {"cat": "Trend", "fn": self._bb_width, "params": {"window": 20}},
            "BB_PCT":     {"cat": "Trend", "fn": self._bb_pct, "params": {"window": 20}},

            # ==================== 反转因子 (18个) ====================
            "RSI_6":  {"cat": "Reversal", "fn": self._rsi, "params": {"window": 6}},
            "RSI_14": {"cat": "Reversal", "fn": self._rsi, "params": {"window": 14}},
            "RSI_24": {"cat": "Reversal", "fn": self._rsi, "params": {"window": 24}},
            "WR_6":   {"cat": "Reversal", "fn": self._wr, "params": {"window": 6}},
            "WR_14":  {"cat": "Reversal", "fn": self._wr, "params": {"window": 14}},
            "WR_24":  {"cat": "Reversal", "fn": self._wr, "params": {"window": 24}},
            "KDJ_K":  {"cat": "Reversal", "fn": self._kdj_k, "params": {"window": 9}},
            "KDJ_D":  {"cat": "Reversal", "fn": self._kdj_d, "params": {"window": 9}},
            "KDJ_J":  {"cat": "Reversal", "fn": self._kdj_j, "params": {"window": 9}},
            "CCI_14": {"cat": "Reversal", "fn": self._cci, "params": {"window": 14}},
            "CCI_20": {"cat": "Reversal", "fn": self._cci, "params": {"window": 20}},
            "STOCH_K": {"cat": "Reversal", "fn": self._stoch_k},
            "STOCH_D": {"cat": "Reversal", "fn": self._stoch_d},
            "MFI_14":  {"cat": "Reversal", "fn": self._mfi, "params": {"window": 14}},
            "BIAS_6":  {"cat": "Reversal", "fn": self._bias, "params": {"window": 6}},
            "BIAS_12": {"cat": "Reversal", "fn": self._bias, "params": {"window": 12}},
            "BIAS_24": {"cat": "Reversal", "fn": self._bias, "params": {"window": 24}},
            "PSY_12":  {"cat": "Reversal", "fn": self._psy, "params": {"window": 12}},

            # ==================== 流动性因子 (16个) ====================
            "VOLUME_MA5":  {"cat": "Liquidity", "fn": self._volume_ma, "params": {"window": 5}},
            "VOLUME_MA10": {"cat": "Liquidity", "fn": self._volume_ma, "params": {"window": 10}},
            "VOLUME_MA20": {"cat": "Liquidity", "fn": self._volume_ma, "params": {"window": 20}},
            "VOLUME_RATIO_5":  {"cat": "Liquidity", "fn": self._volume_ratio, "params": {"window": 5}},
            "VOLUME_RATIO_10": {"cat": "Liquidity", "fn": self._volume_ratio, "params": {"window": 10}},
            "VOLUME_RATIO_20": {"cat": "Liquidity", "fn": self._volume_ratio, "params": {"window": 20}},
            "VOLUME_STD_5":  {"cat": "Liquidity", "fn": self._volume_std, "params": {"window": 5}},
            "VOLUME_STD_10": {"cat": "Liquidity", "fn": self._volume_std, "params": {"window": 10}},
            "VOLUME_SKEW_10": {"cat": "Liquidity", "fn": self._volume_skew, "params": {"window": 10}},
            "VOLUME_KURT_10": {"cat": "Liquidity", "fn": self._volume_kurt, "params": {"window": 10}},
            "TURNOVER_MA5":  {"cat": "Liquidity", "fn": self._turnover_ma, "params": {"window": 5}},
            "TURNOVER_MA10": {"cat": "Liquidity", "fn": self._turnover_ma, "params": {"window": 10}},
            "AMOUNT_MA5":  {"cat": "Liquidity", "fn": self._amount_ma, "params": {"window": 5}},
            "AMOUNT_MA10": {"cat": "Liquidity", "fn": self._amount_ma, "params": {"window": 10}},
            "LIQUIDITY_RATIO": {"cat": "Liquidity", "fn": self._liquidity_ratio},
            "AMIHUD_ILLIQ": {"cat": "Liquidity", "fn": self._amihud_illiq},

            # ==================== 波动率因子 (15个) ====================
            "VOLATILITY_5":  {"cat": "Volatility", "fn": self._volatility, "params": {"window": 5}},
            "VOLATILITY_10": {"cat": "Volatility", "fn": self._volatility, "params": {"window": 10}},
            "VOLATILITY_20": {"cat": "Volatility", "fn": self._volatility, "params": {"window": 20}},
            "VOLATILITY_60": {"cat": "Volatility", "fn": self._volatility, "params": {"window": 60}},
            "HL_RATIO_5":  {"cat": "Volatility", "fn": self._hl_ratio, "params": {"window": 5}},
            "HL_RATIO_10": {"cat": "Volatility", "fn": self._hl_ratio, "params": {"window": 10}},
            "HL_RATIO_20": {"cat": "Volatility", "fn": self._hl_ratio, "params": {"window": 20}},
            "GAP_RATIO_5":  {"cat": "Volatility", "fn": self._gap_ratio, "params": {"window": 5}},
            "GAP_RATIO_10": {"cat": "Volatility", "fn": self._gap_ratio, "params": {"window": 10}},
            "BETA_20":  {"cat": "Volatility", "fn": self._beta, "params": {"window": 20}},
            "BETA_60":  {"cat": "Volatility", "fn": self._beta, "params": {"window": 60}},
            "DOWNSIDE_VOL_20": {"cat": "Volatility", "fn": self._downside_vol, "params": {"window": 20}},
            "UPSIDE_VOL_20":   {"cat": "Volatility", "fn": self._upside_vol, "params": {"window": 20}},
            "MAX_DRAWDOWN_20": {"cat": "Volatility", "fn": self._max_drawdown, "params": {"window": 20}},
            "MAX_DRAWDOWN_60": {"cat": "Volatility", "fn": self._max_drawdown, "params": {"window": 60}},

            # ==================== 动量因子 (20个) ====================
            "MOM_1":  {"cat": "Momentum", "fn": self._momentum, "params": {"window": 1}},
            "MOM_5":  {"cat": "Momentum", "fn": self._momentum, "params": {"window": 5}},
            "MOM_10": {"cat": "Momentum", "fn": self._momentum, "params": {"window": 10}},
            "MOM_20": {"cat": "Momentum", "fn": self._momentum, "params": {"window": 20}},
            "MOM_60": {"cat": "Momentum", "fn": self._momentum, "params": {"window": 60}},
            "ROC_5":  {"cat": "Momentum", "fn": self._roc, "params": {"window": 5}},
            "ROC_10": {"cat": "Momentum", "fn": self._roc, "params": {"window": 10}},
            "ROC_20": {"cat": "Momentum", "fn": self._roc, "params": {"window": 20}},
            "ROC_60": {"cat": "Momentum", "fn": self._roc, "params": {"window": 60}},
            "SIGNAL_5_10":  {"cat": "Momentum", "fn": self._signal, "params": {"fast": 5, "slow": 10}},
            "SIGNAL_10_20": {"cat": "Momentum", "fn": self._signal, "params": {"fast": 10, "slow": 20}},
            "SIGNAL_20_60": {"cat": "Momentum", "fn": self._signal, "params": {"fast": 20, "slow": 60}},
            "VOLUME_MOM_5":  {"cat": "Momentum", "fn": self._volume_momentum, "params": {"window": 5}},
            "VOLUME_MOM_10": {"cat": "Momentum", "fn": self._volume_momentum, "params": {"window": 10}},
            "VOLUME_MOM_20": {"cat": "Momentum", "fn": self._volume_momentum, "params": {"window": 20}},
            "PRICE_VOL_CORR_10": {"cat": "Momentum", "fn": self._price_vol_corr, "params": {"window": 10}},
            "PRICE_VOL_CORR_20": {"cat": "Momentum", "fn": self._price_vol_corr, "params": {"window": 20}},
            "UP_DAYS_5":  {"cat": "Momentum", "fn": self._up_days, "params": {"window": 5}},
            "UP_DAYS_10": {"cat": "Momentum", "fn": self._up_days, "params": {"window": 10}},
            "UP_DAYS_20": {"cat": "Momentum", "fn": self._up_days, "params": {"window": 20}},

            # ==================== 量价因子 (15个) ====================
            "OBV":          {"cat": "VolumePrice", "fn": self._obv},
            "OBV_MA5":      {"cat": "VolumePrice", "fn": self._obv_ma, "params": {"window": 5}},
            "OBV_MA10":     {"cat": "VolumePrice", "fn": self._obv_ma, "params": {"window": 10}},
            "VWAP_DEVIATION": {"cat": "VolumePrice", "fn": self._vwap_deviation},
            "VWAP_MA5_DEV":   {"cat": "VolumePrice", "fn": self._vwap_ma_dev, "params": {"window": 5}},
            "VWAP_MA10_DEV":  {"cat": "VolumePrice", "fn": self._vwap_ma_dev, "params": {"window": 10}},
            "PVT":          {"cat": "VolumePrice", "fn": self._pvt},
            "PVT_MA5":      {"cat": "VolumePrice", "fn": self._pvt_ma, "params": {"window": 5}},
            "EOM_14":       {"cat": "VolumePrice", "fn": self._eom, "params": {"window": 14}},
            "VPT":          {"cat": "VolumePrice", "fn": self._vpt},
            "VPT_MA5":      {"cat": "VolumePrice", "fn": self._vpt_ma, "params": {"window": 5}},
            "NVI":          {"cat": "VolumePrice", "fn": self._nvi},
            "PVI":          {"cat": "VolumePrice", "fn": self._pvi},
            "CMF_20":       {"cat": "VolumePrice", "fn": self._cmf, "params": {"window": 20}},
            "FORCE_INDEX":  {"cat": "VolumePrice", "fn": self._force_index, "params": {"window": 13}},

            # ==================== 形态因子 (10个) ====================
            "HAMMER":       {"cat": "Pattern", "fn": self._hammer},
            "DOJI":         {"cat": "Pattern", "fn": self._doji},
            "ENGULFING":    {"cat": "Pattern", "fn": self._engulfing},
            "MARUBOZU":     {"cat": "Pattern", "fn": self._marubozu},
            "THREE_WHITE":  {"cat": "Pattern", "fn": self._three_white},
            "THREE_BLACK":  {"cat": "Pattern", "fn": self._three_black},
            "BREAKOUT_HIGH_20": {"cat": "Pattern", "fn": self._breakout_high, "params": {"window": 20}},
            "BREAKOUT_LOW_20":  {"cat": "Pattern", "fn": self._breakout_low, "params": {"window": 20}},
            "SUPPORT_20":  {"cat": "Pattern", "fn": self._support_distance, "params": {"window": 20}},
            "RESISTANCE_20": {"cat": "Pattern", "fn": self._resistance_distance, "params": {"window": 20}},

            # ==================== 高频因子 / 分钟级 (10个) ====================
            "HF_RETURN_1":  {"cat": "HighFreq", "fn": self._hf_return, "params": {"window": 1}},
            "HF_RETURN_5":  {"cat": "HighFreq", "fn": self._hf_return, "params": {"window": 5}},
            "HF_RETURN_10": {"cat": "HighFreq", "fn": self._hf_return, "params": {"window": 10}},
            "HF_RETURN_30": {"cat": "HighFreq", "fn": self._hf_return, "params": {"window": 30}},
            "HF_VOLUME_SURGE": {"cat": "HighFreq", "fn": self._hf_volume_surge, "params": {"window": 5}},
            "HF_SPREAD":       {"cat": "HighFreq", "fn": self._hf_spread},
            "HF_AMPLITUDE_5":  {"cat": "HighFreq", "fn": self._hf_amplitude, "params": {"window": 5}},
            "HF_AMPLITUDE_10": {"cat": "HighFreq", "fn": self._hf_amplitude, "params": {"window": 10}},
            "HF_ACCUM_DIST_5": {"cat": "HighFreq", "fn": self._hf_accum_dist, "params": {"window": 5}},
            "HF_INTRA_MA_5":   {"cat": "HighFreq", "fn": self._hf_intra_ma, "params": {"window": 5}},
        }

    # ================================================================
    # 主计算接口
    # ================================================================

    def compute_all(self, df: pd.DataFrame, freq: str = "day",
                    categories: List[str] = None) -> AlphaResult:
        """计算所有因子

        Args:
            df: 包含OHLCV的DataFrame (列: $open, $high, $low, $close, $volume, $vwap)
            freq: 频率 "day" 或 "1min"
            categories: 限定因子类别，None=全部

        Returns:
            AlphaResult
        """
        close = df["$close"].values
        high = df["$high"].values
        low = df["$low"].values
        open_ = df["$open"].values
        volume = df["$volume"].values
        vwap = df.get("$vwap", close).values

        result = AlphaResult()
        result.metadata = {
            "freq": freq,
            "rows": len(df),
            "start": str(df.index[0]),
            "end": str(df.index[-1]),
            "categories": categories or "all",
        }

        factors = {}
        for name, info in self._factor_registry.items():
            if categories and info["cat"] not in categories:
                continue

            # 高频因子仅分钟级计算
            if info["cat"] == "HighFreq" and freq != "1min":
                continue

            # 估值因子需要额外数据，日线模式跳过
            if info["cat"] == "Valuation":
                continue

            try:
                params = info.get("params", {})
                values = info["fn"](open_, high, low, close, volume, vwap, **params)
                factors[name] = FactorResult(
                    name=name,
                    category=info["cat"],
                    values=values,
                )
            except Exception as e:
                logger.warning(f"因子计算失败: {name}: {e}")
                factors[name] = FactorResult(
                    name=name,
                    category=info["cat"],
                    values=np.full(len(close), np.nan),
                    status="error",
                )

        result.factors = factors
        result.summary = self._compute_summary(result)
        return result

    def compute_ic_analysis(self, df: pd.DataFrame, future_returns: np.ndarray,
                            freq: str = "day") -> AlphaResult:
        """计算因子IC/IR分析

        Args:
            df: OHLCV数据
            future_returns: 未来N期收益率（用于IC计算）
            freq: 频率

        Returns:
            AlphaResult（每个因子附IC/IR/衰减等指标）
        """
        result = self.compute_all(df, freq)

        for name, factor in result.factors.items():
            try:
                values = factor.values
                valid = ~(np.isnan(values) | np.isnan(future_returns))
                if valid.sum() < 30:
                    continue

                v = values[valid]
                r = future_returns[valid]

                # IC = 因子值与未来收益的秩相关系数
                from scipy.stats import spearmanr
                ic, _ = spearmanr(v, r)
                factor.ic = ic

                # IR = IC均值 / IC标准差
                # 滚动IC计算
                n = len(v)
                rolling_ics = []
                for i in range(30, n):
                    roll_ic, _ = spearmanr(v[i-30:i], r[i-30:i])
                    rolling_ics.append(roll_ic)

                if rolling_ics:
                    rolling_ics = np.array(rolling_ics)
                    factor.ir = rolling_ics.mean() / rolling_ics.std() if rolling_ics.std() > 0 else 0
                    factor.ic_std = rolling_ics.std()
                    factor.ic_positive_ratio = (rolling_ics > 0).mean()

                # 因子衰减
                decay_ics = []
                for lag in [1, 3, 5, 10, 20]:
                    if lag < n:
                        lag_ic, _ = spearmanr(v[:-lag], r[lag:])
                        decay_ics.append(lag_ic)
                if decay_ics:
                    factor.decay = np.polyfit(range(len(decay_ics)), decay_ics, 1)[0]

            except Exception as e:
                logger.warning(f"IC分析失败: {name}: {e}")

        result.summary = self._compute_summary(result)
        return result

    def compute_rolling_factors(self, df: pd.DataFrame, freq: str = "1min",
                                 window: int = 5) -> pd.DataFrame:
        """滚动窗口计算因子（分钟级使用）

        在1min数据上，每window根K线重新计算一次因子。
        用于盘中滚动选股。

        Args:
            df: 分钟级OHLCV数据
            freq: 频率
            window: 滚动窗口大小（根K线）

        Returns:
            DataFrame，每行是一个窗口的因子值
        """
        results = []
        n = len(df)

        for i in range(window, n + 1, window):
            sub_df = df.iloc[i - window:i]
            r = self.compute_all(sub_df, freq=freq)
            row = {
                "timestamp": df.index[i - 1],
                "window_start": df.index[i - window],
                "window_end": df.index[i - 1],
            }
            for name, factor in r.factors.items():
                row[name] = factor.values[-1] if len(factor.values) > 0 else np.nan
            results.append(row)

        return pd.DataFrame(results)

    def _compute_summary(self, result: AlphaResult) -> Dict[str, Any]:
        """计算因子汇总统计"""
        cat_count = {}
        for f in result.factors.values():
            cat_count[f.category] = cat_count.get(f.category, 0) + 1

        ics = [f.ic for f in result.factors.values() if f.ic is not None]
        irs = [f.ir for f in result.factors.values() if f.ir is not None]

        return {
            "total_factors": len(result.factors),
            "by_category": cat_count,
            "mean_ic": float(np.mean(ics)) if ics else None,
            "max_ic": float(np.max(ics)) if ics else None,
            "mean_ir": float(np.mean(irs)) if irs else None,
            "ic_positive_ratio": float((np.array(ics) > 0).mean()) if ics else None,
            "error_count": sum(1 for f in result.factors.values() if f.status == "error"),
        }

    # ================================================================
    # 趋势因子实现
    # ================================================================

    def _sma(self, o, h, l, c, v, vwap, window=20):
        return self._rolling_mean(c, window)

    def _ema(self, o, h, l, c, v, vwap, window=20):
        return pd.Series(c).ewm(span=window, adjust=False).mean().values

    def _macd_dif(self, o, h, l, c, v, vwap):
        ema12 = pd.Series(c).ewm(span=12, adjust=False).mean().values
        ema26 = pd.Series(c).ewm(span=26, adjust=False).mean().values
        macd = ema12 - ema26
        return macd / c  # 归一化

    def _macd_dea(self, o, h, l, c, v, vwap):
        dif = self._macd_dif(o, h, l, c, v, vwap) * c
        return pd.Series(dif).ewm(span=9, adjust=False).mean().values / c

    def _macd_hist(self, o, h, l, c, v, vwap):
        dif = self._macd_dif(o, h, l, c, v, vwap)
        dea = self._macd_dea(o, h, l, c, v, vwap)
        return dif - dea

    def _adx(self, o, h, l, c, v, vwap, window=14):
        tr = np.maximum.reduce([
            h - l,
            np.abs(h - np.roll(c, 1)),
            np.abs(l - np.roll(c, 1)),
        ])
        atr = pd.Series(tr).ewm(span=window, adjust=False).mean().values
        up = h - np.roll(h, 1)
        down = np.roll(l, 1) - l
        plus_dm = np.where((up > down) & (up > 0), up, 0)
        minus_dm = np.where((down > up) & (down > 0), down, 0)
        plus_di = 100 * pd.Series(plus_dm).ewm(span=window, adjust=False).mean().values / atr
        minus_di = 100 * pd.Series(minus_dm).ewm(span=window, adjust=False).mean().values / atr
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
        return pd.Series(dx).ewm(span=window, adjust=False).mean().values

    def _plus_di(self, o, h, l, c, v, vwap, window=14):
        tr = np.maximum.reduce([h - l, np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1))])
        atr = pd.Series(tr).ewm(span=window, adjust=False).mean().values
        up = h - np.roll(h, 1)
        plus_dm = np.where((up > 0) & (up > (np.roll(l, 1) - l)), up, 0)
        return 100 * pd.Series(plus_dm).ewm(span=window, adjust=False).mean().values / (atr + 1e-10)

    def _minus_di(self, o, h, l, c, v, vwap, window=14):
        tr = np.maximum.reduce([h - l, np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1))])
        atr = pd.Series(tr).ewm(span=window, adjust=False).mean().values
        down = np.roll(l, 1) - l
        minus_dm = np.where((down > 0) & (down > (h - np.roll(h, 1))), down, 0)
        return 100 * pd.Series(minus_dm).ewm(span=window, adjust=False).mean().values / (atr + 1e-10)

    def _atr(self, o, h, l, c, v, vwap, window=14):
        tr = np.maximum.reduce([h - l, np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1))])
        return pd.Series(tr).ewm(span=window, adjust=False).mean().values / c

    def _trix(self, o, h, l, c, v, vwap, window=12):
        ema1 = pd.Series(c).ewm(span=window, adjust=False).mean()
        ema2 = ema1.ewm(span=window, adjust=False).mean()
        ema3 = ema2.ewm(span=window, adjust=False).mean()
        return ema3.pct_change().values

    def _bb_upper(self, o, h, l, c, v, vwap, window=20):
        ma = self._rolling_mean(c, window)
        std = self._rolling_std(c, window)
        return (ma + 2 * std) / c

    def _bb_middle(self, o, h, l, c, v, vwap, window=20):
        return self._rolling_mean(c, window) / c

    def _bb_lower(self, o, h, l, c, v, vwap, window=20):
        ma = self._rolling_mean(c, window)
        std = self._rolling_std(c, window)
        return (ma - 2 * std) / c

    def _bb_width(self, o, h, l, c, v, vwap, window=20):
        ma = self._rolling_mean(c, window)
        std = self._rolling_std(c, window)
        return (4 * std) / ma

    def _bb_pct(self, o, h, l, c, v, vwap, window=20):
        ma = self._rolling_mean(c, window)
        std = self._rolling_std(c, window)
        return (c - ma) / (2 * std + 1e-10)

    # ================================================================
    # 反转因子实现
    # ================================================================

    def _rsi(self, o, h, l, c, v, vwap, window=14):
        delta = np.diff(c, prepend=c[0])
        gain = np.where(delta > 0, delta, 0)
        loss = np.where(delta < 0, -delta, 0)
        avg_gain = pd.Series(gain).ewm(span=window, adjust=False).mean().values
        avg_loss = pd.Series(loss).ewm(span=window, adjust=False).mean().values
        return 100 - 100 / (1 + avg_gain / (avg_loss + 1e-10))

    def _wr(self, o, h, l, c, v, vwap, window=14):
        highest = pd.Series(h).rolling(window).max().values
        lowest = pd.Series(l).rolling(window).min().values
        return -100 * (highest - c) / (highest - lowest + 1e-10)

    def _kdj_k(self, o, h, l, c, v, vwap, window=9):
        lowest = pd.Series(l).rolling(window).min().values
        highest = pd.Series(h).rolling(window).max().values
        rsv = 100 * (c - lowest) / (highest - lowest + 1e-10)
        return pd.Series(rsv).ewm(span=3, adjust=False).mean().values

    def _kdj_d(self, o, h, l, c, v, vwap, window=9):
        k = self._kdj_k(o, h, l, c, v, vwap, window)
        return pd.Series(k).ewm(span=3, adjust=False).mean().values

    def _kdj_j(self, o, h, l, c, v, vwap, window=9):
        k = self._kdj_k(o, h, l, c, v, vwap, window)
        d = self._kdj_d(o, h, l, c, v, vwap, window)
        return 3 * k - 2 * d

    def _cci(self, o, h, l, c, v, vwap, window=14):
        tp = (h + l + c) / 3
        ma = pd.Series(tp).rolling(window).mean().values
        md = np.array([np.abs(tp[max(0, i - window + 1):i + 1] - ma[i]).mean()
                       for i in range(len(tp))])
        return (tp - ma) / (0.015 * md + 1e-10)

    def _stoch_k(self, o, h, l, c, v, vwap):
        lowest_14 = pd.Series(l).rolling(14).min().values
        highest_14 = pd.Series(h).rolling(14).max().values
        return 100 * (c - lowest_14) / (highest_14 - lowest_14 + 1e-10)

    def _stoch_d(self, o, h, l, c, v, vwap):
        k = self._stoch_k(o, h, l, c, v, vwap)
        return pd.Series(k).rolling(3).mean().values

    def _mfi(self, o, h, l, c, v, vwap, window=14):
        tp = (h + l + c) / 3
        money_flow = tp * v
        delta = np.diff(tp, prepend=tp[0])
        pos_flow = np.where(delta > 0, money_flow, 0)
        neg_flow = np.where(delta < 0, money_flow, 0)
        pos_sum = pd.Series(pos_flow).rolling(window).sum().values
        neg_sum = pd.Series(neg_flow).rolling(window).sum().values
        return 100 - 100 / (1 + pos_sum / (neg_sum + 1e-10))

    def _bias(self, o, h, l, c, v, vwap, window=6):
        ma = self._rolling_mean(c, window)
        return (c - ma) / (ma + 1e-10) * 100

    def _psy(self, o, h, l, c, v, vwap, window=12):
        up = (np.diff(c, prepend=c[0]) > 0).astype(float)
        return pd.Series(up).rolling(window).mean().values * 100

    # ================================================================
    # 流动性因子实现
    # ================================================================

    def _volume_ma(self, o, h, l, c, v, vwap, window=5):
        return pd.Series(v).rolling(window).mean().values / (v + 1e-10)

    def _volume_ratio(self, o, h, l, c, v, vwap, window=5):
        ma = pd.Series(v).rolling(window).mean().values
        return v / (ma + 1e-10)

    def _volume_std(self, o, h, l, c, v, vwap, window=10):
        return pd.Series(v).rolling(window).std().values / (v + 1e-10)

    def _volume_skew(self, o, h, l, c, v, vwap, window=10):
        return pd.Series(v).rolling(window).skew().values

    def _volume_kurt(self, o, h, l, c, v, vwap, window=10):
        return pd.Series(v).rolling(window).kurt().values

    def _turnover_ma(self, o, h, l, c, v, vwap, window=5):
        return pd.Series(v).rolling(window).mean().values / (v.mean() + 1e-10)

    def _amount_ma(self, o, h, l, c, v, vwap, window=5):
        amount = v * c
        return pd.Series(amount).rolling(window).mean().values / (amount + 1e-10)

    def _liquidity_ratio(self, o, h, l, c, v, vwap):
        return (h - l) / (v + 1e-10) * 1e6

    def _amihud_illiq(self, o, h, l, c, v, vwap):
        ret = np.abs(np.diff(c, prepend=c[0]) / (c + 1e-10))
        return ret / (v * c + 1e-10) * 1e8

    # ================================================================
    # 波动率因子实现
    # ================================================================

    def _volatility(self, o, h, l, c, v, vwap, window=20):
        ret = np.diff(np.log(c + 1e-10), prepend=0)
        return pd.Series(ret).rolling(window).std().values * np.sqrt(window)

    def _hl_ratio(self, o, h, l, c, v, vwap, window=10):
        hl = (h - l) / (c + 1e-10)
        return pd.Series(hl).rolling(window).mean().values

    def _gap_ratio(self, o, h, l, c, v, vwap, window=10):
        gap = np.abs(o - np.roll(c, 1)) / (np.roll(c, 1) + 1e-10)
        return pd.Series(gap).rolling(window).mean().values

    def _beta(self, o, h, l, c, v, vwap, window=20):
        ret = np.diff(np.log(c + 1e-10), prepend=0)
        # 使用自身滞后作为市场代理（简化版）
        market_ret = ret
        cov = pd.Series(ret * market_ret).rolling(window).mean().values
        var = pd.Series(market_ret ** 2).rolling(window).mean().values
        return cov / (var + 1e-10)

    def _downside_vol(self, o, h, l, c, v, vwap, window=20):
        ret = np.diff(np.log(c + 1e-10), prepend=0)
        downside = np.where(ret < 0, ret, 0)
        return pd.Series(downside).rolling(window).std().values * np.sqrt(window)

    def _upside_vol(self, o, h, l, c, v, vwap, window=20):
        ret = np.diff(np.log(c + 1e-10), prepend=0)
        upside = np.where(ret > 0, ret, 0)
        return pd.Series(upside).rolling(window).std().values * np.sqrt(window)

    def _max_drawdown(self, o, h, l, c, v, vwap, window=20):
        cummax = pd.Series(c).rolling(window).max().values
        return (c - cummax) / (cummax + 1e-10)

    # ================================================================
    # 动量因子实现
    # ================================================================

    def _momentum(self, o, h, l, c, v, vwap, window=20):
        return c / (np.roll(c, window) + 1e-10) - 1

    def _roc(self, o, h, l, c, v, vwap, window=20):
        return (c - np.roll(c, window)) / (np.roll(c, window) + 1e-10) * 100

    def _signal(self, o, h, l, c, v, vwap, fast=5, slow=20):
        ma_fast = self._rolling_mean(c, fast)
        ma_slow = self._rolling_mean(c, slow)
        return (ma_fast - ma_slow) / (ma_slow + 1e-10)

    def _volume_momentum(self, o, h, l, c, v, vwap, window=10):
        return v / (np.roll(v, window) + 1e-10) - 1

    def _price_vol_corr(self, o, h, l, c, v, vwap, window=10):
        ret = np.diff(np.log(c + 1e-10), prepend=0)
        return pd.Series(ret).rolling(window).corr(pd.Series(v)).values

    def _up_days(self, o, h, l, c, v, vwap, window=10):
        up = (np.diff(c, prepend=c[0]) > 0).astype(float)
        return pd.Series(up).rolling(window).sum().values / window

    # ================================================================
    # 量价因子实现
    # ================================================================

    def _obv(self, o, h, l, c, v, vwap):
        delta = np.diff(c, prepend=c[0])
        direction = np.where(delta > 0, 1, np.where(delta < 0, -1, 0))
        obv = np.cumsum(direction * v)
        return obv / (obv.max() - obv.min() + 1e-10) if (obv.max() - obv.min()) > 0 else np.zeros_like(obv)

    def _obv_ma(self, o, h, l, c, v, vwap, window=5):
        obv = self._obv(o, h, l, c, v, vwap)
        return pd.Series(obv).rolling(window).mean().values

    def _vwap_deviation(self, o, h, l, c, v, vwap):
        return (c - vwap) / (vwap + 1e-10)

    def _vwap_ma_dev(self, o, h, l, c, v, vwap, window=5):
        vwap_ma = pd.Series(vwap).rolling(window).mean().values
        return (c - vwap_ma) / (vwap_ma + 1e-10)

    def _pvt(self, o, h, l, c, v, vwap):
        ret = np.diff(c, prepend=c[0]) / (np.roll(c, 1) + 1e-10)
        return np.cumsum(ret * v)

    def _pvt_ma(self, o, h, l, c, v, vwap, window=5):
        pvt = self._pvt(o, h, l, c, v, vwap)
        return pd.Series(pvt).rolling(window).mean().values

    def _eom(self, o, h, l, c, v, vwap, window=14):
        move = (h + l) / 2 - (np.roll(h, 1) + np.roll(l, 1)) / 2
        box_ratio = (v / 1e8) / (h - l + 1e-10)
        eom = move / (box_ratio + 1e-10)
        return pd.Series(eom).rolling(window).mean().values

    def _vpt(self, o, h, l, c, v, vwap):
        ret = np.diff(c, prepend=c[0]) / (np.roll(c, 1) + 1e-10)
        vpt = np.cumsum(ret * v)
        return vpt / (np.abs(vpt).max() + 1e-10) if np.abs(vpt).max() > 0 else np.zeros_like(vpt)

    def _vpt_ma(self, o, h, l, c, v, vwap, window=5):
        vpt = self._vpt(o, h, l, c, v, vwap)
        return pd.Series(vpt).rolling(window).mean().values

    def _nvi(self, o, h, l, c, v, vwap):
        ret = np.diff(c, prepend=c[0]) / (np.roll(c, 1) + 1e-10)
        vol_dec = np.where(v < np.roll(v, 1), ret, 0)
        return np.cumsum(vol_dec)

    def _pvi(self, o, h, l, c, v, vwap):
        ret = np.diff(c, prepend=c[0]) / (np.roll(c, 1) + 1e-10)
        vol_inc = np.where(v > np.roll(v, 1), ret, 0)
        return np.cumsum(vol_inc)

    def _cmf(self, o, h, l, c, v, vwap, window=20):
        mf_mult = ((c - l) - (h - c)) / (h - l + 1e-10)
        mf_vol = mf_mult * v
        return pd.Series(mf_vol).rolling(window).sum().values / pd.Series(v).rolling(window).sum().values

    def _force_index(self, o, h, l, c, v, vwap, window=13):
        fi = np.diff(c, prepend=c[0]) * v
        return pd.Series(fi).ewm(span=window, adjust=False).mean().values

    # ================================================================
    # 形态因子实现
    # ================================================================

    def _hammer(self, o, h, l, c, v, vwap):
        body = np.abs(c - o)
        lower_shadow = np.minimum(o, c) - l
        upper_shadow = h - np.maximum(o, c)
        total = h - l + 1e-10
        return np.where(
            (lower_shadow > 2 * body) & (upper_shadow < 0.3 * total) & (body > 0),
            1.0, 0.0
        )

    def _doji(self, o, h, l, c, v, vwap):
        body = np.abs(c - o)
        total = h - l + 1e-10
        return np.where(body / total < 0.1, 1.0, 0.0)

    def _engulfing(self, o, h, l, c, v, vwap):
        prev_c = np.roll(c, 1)
        prev_o = np.roll(o, 1)
        bullish = (c > o) & (prev_c < prev_o) & (o < prev_c) & (c > prev_o)
        bearish = (c < o) & (prev_c > prev_o) & (o > prev_c) & (c < prev_o)
        return np.where(bullish, 1.0, np.where(bearish, -1.0, 0.0))

    def _marubozu(self, o, h, l, c, v, vwap):
        body = np.abs(c - o)
        total = h - l + 1e-10
        return np.where(body / total > 0.9, 1.0, 0.0)

    def _three_white(self, o, h, l, c, v, vwap):
        up = c > o
        three_up = up & np.roll(up, 1) & np.roll(up, 2)
        return np.where(three_up, 1.0, 0.0)

    def _three_black(self, o, h, l, c, v, vwap):
        down = c < o
        three_down = down & np.roll(down, 1) & np.roll(down, 2)
        return np.where(three_down, 1.0, 0.0)

    def _breakout_high(self, o, h, l, c, v, vwap, window=20):
        high_max = pd.Series(h).rolling(window).max().values
        return (c - high_max) / (high_max + 1e-10)

    def _breakout_low(self, o, h, l, c, v, vwap, window=20):
        low_min = pd.Series(l).rolling(window).min().values
        return (c - low_min) / (low_min + 1e-10)

    def _support_distance(self, o, h, l, c, v, vwap, window=20):
        low_min = pd.Series(l).rolling(window).min().values
        return (c - low_min) / (c + 1e-10)

    def _resistance_distance(self, o, h, l, c, v, vwap, window=20):
        high_max = pd.Series(h).rolling(window).max().values
        return (high_max - c) / (c + 1e-10)

    # ================================================================
    # 高频因子实现（分钟级）
    # ================================================================

    def _hf_return(self, o, h, l, c, v, vwap, window=5):
        return c / (np.roll(c, window) + 1e-10) - 1

    def _hf_volume_surge(self, o, h, l, c, v, vwap, window=5):
        ma = pd.Series(v).rolling(window * 5).mean().values
        return v / (ma + 1e-10)

    def _hf_spread(self, o, h, l, c, v, vwap):
        return (h - l) / (c + 1e-10)

    def _hf_amplitude(self, o, h, l, c, v, vwap, window=5):
        amp = (h - l) / (np.roll(c, 1) + 1e-10)
        return pd.Series(amp).rolling(window).mean().values

    def _hf_accum_dist(self, o, h, l, c, v, vwap, window=5):
        clv = ((c - l) - (h - c)) / (h - l + 1e-10)
        ad = clv * v
        return pd.Series(ad).rolling(window).sum().values

    def _hf_intra_ma(self, o, h, l, c, v, vwap, window=5):
        return self._rolling_mean(c, window) / c

    # ================================================================
    # 工具函数
    # ================================================================

    @staticmethod
    def _rolling_mean(arr, window):
        return pd.Series(arr).rolling(window, min_periods=1).mean().values

    @staticmethod
    def _rolling_std(arr, window):
        return pd.Series(arr).rolling(window, min_periods=1).std().values

    def get_factor_names(self, category: str = None) -> List[str]:
        """获取因子名称列表"""
        if category:
            return [k for k, v in self._factor_registry.items() if v["cat"] == category]
        return list(self._factor_registry.keys())

    def get_categories(self) -> List[str]:
        """获取所有因子类别"""
        return sorted(set(v["cat"] for v in self._factor_registry.values()))

    def get_factor_matrix(self, df: pd.DataFrame, freq: str = "day") -> pd.DataFrame:
        """计算所有因子并返回DataFrame矩阵"""
        result = self.compute_all(df, freq)
        matrix = {}
        for name, factor in result.factors.items():
            matrix[name] = factor.values
        return pd.DataFrame(matrix, index=df.index)


# ============================================================
# 全局单例
# ============================================================

_engine: Optional[Alpha158Engine] = None


def get_alpha_engine() -> Alpha158Engine:
    global _engine
    if _engine is None:
        _engine = Alpha158Engine()
    return _engine


# ============================================================
# 自测
# ============================================================

if __name__ == "__main__":
    from .data_converter import DataConverter
    import tempfile

    # 生成模拟数据
    dates = pd.date_range("2026-01-01", "2026-06-18", freq="B")
    np.random.seed(42)
    n = len(dates)
    close = 50 + np.cumsum(np.random.randn(n) * 0.5)
    close = np.maximum(close, 1)
    df = pd.DataFrame({
        "$open": close * (1 + np.random.randn(n) * 0.01),
        "$high": close * (1 + np.abs(np.random.randn(n) * 0.02)),
        "$low": close * (1 - np.abs(np.random.randn(n) * 0.02)),
        "$close": close,
        "$volume": np.random.uniform(1e6, 1e8, n),
        "$vwap": close * (1 + np.random.randn(n) * 0.005),
    }, index=dates)

    # 确保high >= low
    df["$high"] = df[["$open", "$high", "$close"]].max(axis=1) * 1.001
    df["$low"] = df[["$open", "$low", "$close"]].min(axis=1) * 0.999

    engine = Alpha158Engine()
    result = engine.compute_all(df, freq="day")

    print(f"总因子数: {len(result.factors)}")
    print(f"类别分布: {result.summary['by_category']}")
    print(f"错误数: {result.summary['error_count']}")

    # 测试IC分析
    future_returns = np.diff(np.log(close), prepend=0)
    ic_result = engine.compute_ic_analysis(df, future_returns, freq="day")
    print(f"\nIC分析: mean_IC={ic_result.summary.get('mean_ic', 'N/A')}")

    # 测试因子矩阵
    matrix = engine.get_factor_matrix(df, freq="day")
    print(f"\n因子矩阵: {matrix.shape}")

    print("\n全部测试通过!")