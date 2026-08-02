#!/usr/bin/env python3
"""
Alpha因子库（Alpha Factor Engine）

Vibe-Trading 系统的核心因子计算引擎，提供三大类共50个因子：
  - 基础因子（20个）：动量、反转、波动率、成交量、换手率、振幅等
  - 技术因子（15个）：RSI、MACD、布林带、均线、KDJ等
  - 基本面因子（15个）：PE、PB、ROE、ROA、毛利率、净利率等

每个因子返回标准化0-100分，支持因子分析（IC/IR、分位数分层、衰减、相关性）。

依赖：numpy
"""

import logging
import numpy as np
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ============================================================
# 因子元数据
# ============================================================

@dataclass
class FactorMeta:
    """因子元数据"""
    name: str
    category: str          # basic / technical / fundamental
    display_name: str
    description: str
    higher_is_better: bool = True
    normalize: bool = True


# ============================================================
# 因子注册表
# ============================================================

_FACTOR_REGISTRY: Dict[str, FactorMeta] = {}


def register_factor(name: str, category: str, display_name: str, 
                    description: str, higher_is_better: bool = True):
    """因子注册装饰器"""
    def decorator(func: Callable):
        _FACTOR_REGISTRY[name] = FactorMeta(
            name=name, category=category, display_name=display_name,
            description=description, higher_is_better=higher_is_better
        )
        return func
    return decorator


# ============================================================
# 标准化工具函数
# ============================================================

def _min_max_normalize(values: np.ndarray, invert: bool = False) -> np.ndarray:
    """Min-Max归一化到0-100"""
    v = np.asarray(values, dtype=np.float64)
    v_min, v_max = np.nanmin(v), np.nanmax(v)
    if v_max == v_min:
        return np.full_like(v, 50.0)
    result = (v - v_min) / (v_max - v_min) * 100.0
    if invert:
        result = 100.0 - result
    return result


def _zscore_normalize(values: np.ndarray) -> np.ndarray:
    """Z-Score标准化"""
    v = np.asarray(values, dtype=np.float64)
    mean, std = np.nanmean(v), np.nanstd(v)
    if std == 0:
        return np.zeros_like(v)
    return (v - mean) / std


def _rolling_window(arr: np.ndarray, window: int) -> np.ndarray:
    """创建滚动窗口视图"""
    shape = arr.shape[:-1] + (arr.shape[-1] - window + 1, window)
    strides = arr.strides + (arr.strides[-1],)
    return np.lib.stride_tricks.as_strided(arr, shape=shape, strides=strides)


# ============================================================
# Alpha因子引擎
# ============================================================

class AlphaFactorEngine:
    """Alpha因子计算引擎

    计算所有注册因子，支持因子分析（IC/IR、分层、衰减、相关性）。
    """

    def __init__(self):
        self._factors: Dict[str, Callable] = {}
        self._factor_meta: Dict[str, FactorMeta] = {}
        self._register_builtin_factors()

    # ---- 因子注册 ----

    def _register_builtin_factors(self):
        """注册所有内置因子"""
        for name in dir(self):
            if name.startswith('_'):
                continue
            attr = getattr(self, name)
            if callable(attr) and name in _FACTOR_REGISTRY:
                self._factors[name] = attr
                self._factor_meta[name] = _FACTOR_REGISTRY[name]
        logger.info(f"已注册 {len(self._factors)} 个Alpha因子")

    @property
    def factor_names(self) -> List[str]:
        """返回所有因子名称"""
        return list(self._factors.keys())

    @property
    def factor_meta(self) -> Dict[str, FactorMeta]:
        """返回所有因子元数据"""
        return dict(self._factor_meta)

    # ============================================================
    # 基础因子（20个）
    # ============================================================

    @staticmethod
    @register_factor("momentum_1m", "basic", "1月动量", "过去21个交易日收益率")
    def momentum_1m(close: np.ndarray) -> np.ndarray:
        """1月动量因子（21日）"""
        c = np.asarray(close, dtype=np.float64)
        result = np.full_like(c, np.nan)
        result[21:] = (c[21:] - c[:-21]) / c[:-21] * 100
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("momentum_3m", "basic", "3月动量", "过去63个交易日收益率")
    def momentum_3m(close: np.ndarray) -> np.ndarray:
        """3月动量因子（63日）"""
        c = np.asarray(close, dtype=np.float64)
        result = np.full_like(c, np.nan)
        result[63:] = (c[63:] - c[:-63]) / c[:-63] * 100
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("momentum_6m", "basic", "6月动量", "过去126个交易日收益率")
    def momentum_6m(close: np.ndarray) -> np.ndarray:
        """6月动量因子（126日）"""
        c = np.asarray(close, dtype=np.float64)
        result = np.full_like(c, np.nan)
        result[126:] = (c[126:] - c[:-126]) / c[:-126] * 100
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("momentum_12m", "basic", "12月动量", "过去252个交易日收益率")
    def momentum_12m(close: np.ndarray) -> np.ndarray:
        """12月动量因子（252日）"""
        c = np.asarray(close, dtype=np.float64)
        result = np.full_like(c, np.nan)
        result[252:] = (c[252:] - c[:-252]) / c[:-252] * 100
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("reversal_1m", "basic", "1月反转", "短期反转效应，越高越可能反转下跌",
                     higher_is_better=False)
    def reversal_1m(close: np.ndarray) -> np.ndarray:
        """1月反转因子（5日反转）"""
        c = np.asarray(close, dtype=np.float64)
        result = np.full_like(c, np.nan)
        result[5:] = (c[5:] - c[:-5]) / c[:-5] * 100
        return _min_max_normalize(result, invert=True)

    @staticmethod
    @register_factor("volatility_1m", "basic", "1月波动率", "21日年化波动率",
                     higher_is_better=False)
    def volatility_1m(close: np.ndarray) -> np.ndarray:
        """1月波动率因子"""
        c = np.asarray(close, dtype=np.float64)
        returns = np.full_like(c, np.nan)
        returns[1:] = (c[1:] - c[:-1]) / c[:-1]
        result = np.full_like(c, np.nan)
        for i in range(21, len(c)):
            result[i] = np.nanstd(returns[i-20:i+1]) * np.sqrt(252)
        return _min_max_normalize(result, invert=True)

    @staticmethod
    @register_factor("volatility_3m", "basic", "3月波动率", "63日年化波动率",
                     higher_is_better=False)
    def volatility_3m(close: np.ndarray) -> np.ndarray:
        """3月波动率因子"""
        c = np.asarray(close, dtype=np.float64)
        returns = np.full_like(c, np.nan)
        returns[1:] = (c[1:] - c[:-1]) / c[:-1]
        result = np.full_like(c, np.nan)
        for i in range(63, len(c)):
            result[i] = np.nanstd(returns[i-62:i+1]) * np.sqrt(252)
        return _min_max_normalize(result, invert=True)

    @staticmethod
    @register_factor("volume_ratio", "basic", "量比", "当日成交量 / 5日均量")
    def volume_ratio(volume: np.ndarray) -> np.ndarray:
        """量比因子"""
        v = np.asarray(volume, dtype=np.float64)
        result = np.full_like(v, np.nan)
        for i in range(5, len(v)):
            ma5 = np.nanmean(v[i-4:i+1])
            result[i] = v[i] / ma5 if ma5 > 0 else np.nan
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("turnover_rate", "basic", "换手率", "日均换手率（需外部传入）")
    def turnover_rate(turnover: np.ndarray) -> np.ndarray:
        """换手率因子"""
        t = np.asarray(turnover, dtype=np.float64)
        return _min_max_normalize(t)

    @staticmethod
    @register_factor("amplitude", "basic", "振幅", "当日振幅 (high-low)/close")
    def amplitude(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
        """振幅因子"""
        h = np.asarray(high, dtype=np.float64)
        l = np.asarray(low, dtype=np.float64)
        c = np.asarray(close, dtype=np.float64)
        result = (h - l) / c * 100
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("price_position", "basic", "价格位置", "收盘价在N日高低区间的相对位置")
    def price_position(close: np.ndarray, window: int = 60) -> np.ndarray:
        """价格位置因子"""
        c = np.asarray(close, dtype=np.float64)
        result = np.full_like(c, np.nan)
        for i in range(window, len(c)):
            h = np.nanmax(c[i-window:i+1])
            l = np.nanmin(c[i-window:i+1])
            result[i] = (c[i] - l) / (h - l) * 100 if h != l else 50
        return result

    @staticmethod
    @register_factor("ma_deviation", "basic", "均线偏离", "收盘价偏离20日均线程度")
    def ma_deviation(close: np.ndarray) -> np.ndarray:
        """均线偏离因子"""
        c = np.asarray(close, dtype=np.float64)
        result = np.full_like(c, np.nan)
        for i in range(20, len(c)):
            ma20 = np.nanmean(c[i-19:i+1])
            result[i] = (c[i] - ma20) / ma20 * 100
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("volume_breakout", "basic", "放量突破", "当日成交量突破N日均量倍数")
    def volume_breakout(volume: np.ndarray) -> np.ndarray:
        """放量突破因子"""
        v = np.asarray(volume, dtype=np.float64)
        result = np.full_like(v, np.nan)
        for i in range(20, len(v)):
            ma20 = np.nanmean(v[i-19:i+1])
            result[i] = v[i] / ma20 if ma20 > 0 else np.nan
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("drawdown", "basic", "回撤幅度", "当前价格相对N日高点的回撤",
                     higher_is_better=False)
    def drawdown(close: np.ndarray, window: int = 60) -> np.ndarray:
        """回撤幅度因子"""
        c = np.asarray(close, dtype=np.float64)
        result = np.full_like(c, np.nan)
        for i in range(window, len(c)):
            peak = np.nanmax(c[i-window:i+1])
            result[i] = (c[i] - peak) / peak * 100
        return _min_max_normalize(result, invert=True)

    @staticmethod
    @register_factor("up_days_ratio", "basic", "上涨天数比", "近N日上涨天数占比")
    def up_days_ratio(close: np.ndarray, window: int = 20) -> np.ndarray:
        """上涨天数比因子"""
        c = np.asarray(close, dtype=np.float64)
        result = np.full_like(c, np.nan)
        for i in range(window, len(c)):
            diff = np.diff(c[i-window:i+1])
            up_count = np.sum(diff > 0)
            result[i] = up_count / window * 100
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("gap_ratio", "basic", "跳空比率", "跳空高开/低开比率")
    def gap_ratio(open_prices: np.ndarray, prev_close: np.ndarray) -> np.ndarray:
        """跳空比率因子"""
        o = np.asarray(open_prices, dtype=np.float64)
        pc = np.asarray(prev_close, dtype=np.float64)
        result = np.full_like(o, np.nan)
        result[1:] = (o[1:] - pc[:-1]) / pc[:-1] * 100
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("volume_trend", "basic", "量价趋势", "量价配合度")
    def volume_trend(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
        """量价趋势因子"""
        c = np.asarray(close, dtype=np.float64)
        v = np.asarray(volume, dtype=np.float64)
        result = np.full_like(c, np.nan)
        for i in range(5, len(c)):
            price_change = (c[i] - c[i-5]) / c[i-5]
            vol_change = (v[i] - v[i-5]) / v[i-5] if v[i-5] > 0 else 0
            result[i] = price_change * 100 + vol_change * 50
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("high_low_ratio", "basic", "高低价比", "N日最高/最低价比")
    def high_low_ratio(high: np.ndarray, low: np.ndarray, window: int = 20) -> np.ndarray:
        """高低价比因子"""
        h = np.asarray(high, dtype=np.float64)
        l = np.asarray(low, dtype=np.float64)
        result = np.full_like(h, np.nan)
        for i in range(window, len(h)):
            h_max = np.nanmax(h[i-window+1:i+1])
            l_min = np.nanmin(l[i-window+1:i+1])
            result[i] = h_max / l_min if l_min > 0 else np.nan
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("continuous_days", "basic", "连涨连跌", "连续上涨天数（正）/连续下跌天数（负）")
    def continuous_days(close: np.ndarray) -> np.ndarray:
        """连涨连跌因子"""
        c = np.asarray(close, dtype=np.float64)
        result = np.zeros_like(c)
        for i in range(1, len(c)):
            if c[i] > c[i-1]:
                result[i] = abs(result[i-1]) + 1 if result[i-1] >= 0 else 1
            elif c[i] < c[i-1]:
                result[i] = -abs(result[i-1]) - 1 if result[i-1] <= 0 else -1
            else:
                result[i] = 0
        return _min_max_normalize(result)

    # ============================================================
    # 技术因子（15个）
    # ============================================================

    @staticmethod
    @register_factor("rsi_factor", "technical", "RSI因子", "14日RSI，超买超卖信号")
    def rsi_factor(close: np.ndarray) -> np.ndarray:
        """RSI因子"""
        c = np.asarray(close, dtype=np.float64)
        diff = np.diff(c)
        result = np.full_like(c, np.nan)
        for i in range(14, len(c)):
            gains = np.sum(diff[i-13:i+1][diff[i-13:i+1] > 0])
            losses = -np.sum(diff[i-13:i+1][diff[i-13:i+1] < 0])
            if losses == 0:
                result[i] = 100.0
            else:
                rs = gains / losses
                result[i] = 100.0 - 100.0 / (1.0 + rs)
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("macd_divergence", "technical", "MACD背离", "MACD与价格背离程度")
    def macd_divergence(close: np.ndarray) -> np.ndarray:
        """MACD背离因子"""
        c = np.asarray(close, dtype=np.float64)
        n = len(c)
        ema12 = np.full(n, np.nan)
        ema26 = np.full(n, np.nan)
        if n >= 12:
            ema12[11] = np.nanmean(c[:12])
            for i in range(12, n):
                ema12[i] = c[i] * 2/13 + ema12[i-1] * 11/13
        if n >= 26:
            ema26[25] = np.nanmean(c[:26])
            for i in range(26, n):
                ema26[i] = c[i] * 2/27 + ema26[i-1] * 25/27
        dif = ema12 - ema26
        dea = np.full(n, np.nan)
        if n >= 35:
            dea[34] = np.nanmean(dif[26:35])
            for i in range(35, n):
                dea[i] = dif[i] * 2/10 + dea[i-1] * 8/10
        macd = (dif - dea) * 2
        return _min_max_normalize(macd)

    @staticmethod
    @register_factor("boll_position", "technical", "布林带位置", "价格在布林带中的位置")
    def boll_position(close: np.ndarray) -> np.ndarray:
        """布林带位置因子"""
        c = np.asarray(close, dtype=np.float64)
        result = np.full_like(c, np.nan)
        for i in range(20, len(c)):
            ma = np.nanmean(c[i-19:i+1])
            std = np.nanstd(c[i-19:i+1])
            upper = ma + 2 * std
            lower = ma - 2 * std
            if upper != lower:
                result[i] = (c[i] - lower) / (upper - lower) * 100
            else:
                result[i] = 50
        return result

    @staticmethod
    @register_factor("ma_alignment", "technical", "均线排列", "5/10/20/60日均线多头排列程度")
    def ma_alignment(close: np.ndarray) -> np.ndarray:
        """均线排列因子"""
        c = np.asarray(close, dtype=np.float64)
        result = np.full_like(c, np.nan)
        for i in range(60, len(c)):
            ma5 = np.nanmean(c[i-4:i+1])
            ma10 = np.nanmean(c[i-9:i+1])
            ma20 = np.nanmean(c[i-19:i+1])
            ma60 = np.nanmean(c[i-59:i+1])
            score = 0
            if ma5 > ma10:
                score += 25
            if ma10 > ma20:
                score += 25
            if ma20 > ma60:
                score += 25
            if c[i] > ma5:
                score += 25
            result[i] = score
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("kdj_golden_cross", "technical", "KDJ金叉", "KDJ指标金叉信号强度")
    def kdj_golden_cross(close: np.ndarray, high: np.ndarray, low: np.ndarray) -> np.ndarray:
        """KDJ金叉因子"""
        c = np.asarray(close, dtype=np.float64)
        h = np.asarray(high, dtype=np.float64)
        l = np.asarray(low, dtype=np.float64)
        n = len(c)
        k = np.full(n, 50.0)
        d = np.full(n, 50.0)
        j = np.full(n, 50.0)
        for i in range(8, n):
            h9 = np.nanmax(h[i-8:i+1])
            l9 = np.nanmin(l[i-8:i+1])
            rsv = (c[i] - l9) / (h9 - l9) * 100 if h9 != l9 else 50
            k[i] = 2/3 * k[i-1] + 1/3 * rsv
            d[i] = 2/3 * d[i-1] + 1/3 * k[i]
            j[i] = 3 * k[i] - 2 * d[i]
        result = np.full_like(c, 50.0)
        for i in range(9, n):
            if k[i] > d[i] and k[i-1] <= d[i-1]:
                result[i] = 80.0
            elif k[i] < d[i] and k[i-1] >= d[i-1]:
                result[i] = 20.0
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("atr_factor", "technical", "ATR波动", "14日平均真实波幅",
                     higher_is_better=False)
    def atr_factor(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
        """ATR波动因子"""
        h = np.asarray(high, dtype=np.float64)
        l = np.asarray(low, dtype=np.float64)
        c = np.asarray(close, dtype=np.float64)
        n = len(c)
        tr = np.zeros(n)
        for i in range(1, n):
            tr[i] = max(h[i] - l[i], abs(h[i] - c[i-1]), abs(l[i] - c[i-1]))
        result = np.full(n, np.nan)
        for i in range(14, n):
            result[i] = np.nanmean(tr[i-13:i+1])
        return _min_max_normalize(result, invert=True)

    @staticmethod
    @register_factor("obv_divergence", "technical", "OBV背离", "能量潮与价格背离")
    def obv_divergence(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
        """OBV背离因子"""
        c = np.asarray(close, dtype=np.float64)
        v = np.asarray(volume, dtype=np.float64)
        obv = np.zeros(len(c))
        obv[0] = v[0]
        for i in range(1, len(c)):
            if c[i] > c[i-1]:
                obv[i] = obv[i-1] + v[i]
            elif c[i] < c[i-1]:
                obv[i] = obv[i-1] - v[i]
            else:
                obv[i] = obv[i-1]
        return _min_max_normalize(obv)

    @staticmethod
    @register_factor("cci_factor", "technical", "CCI因子", "14日商品通道指数")
    def cci_factor(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
        """CCI因子"""
        h = np.asarray(high, dtype=np.float64)
        l = np.asarray(low, dtype=np.float64)
        c = np.asarray(close, dtype=np.float64)
        tp = (h + l + c) / 3
        result = np.full_like(c, np.nan)
        for i in range(14, len(c)):
            ma = np.nanmean(tp[i-13:i+1])
            md = np.nanmean(np.abs(tp[i-13:i+1] - ma))
            result[i] = (tp[i] - ma) / (0.015 * md) if md > 0 else 0
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("williams_r", "technical", "威廉指标", "14日威廉%R",
                     higher_is_better=False)
    def williams_r(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
        """威廉%R因子"""
        h = np.asarray(high, dtype=np.float64)
        l = np.asarray(low, dtype=np.float64)
        c = np.asarray(close, dtype=np.float64)
        result = np.full_like(c, np.nan)
        for i in range(14, len(c)):
            hh = np.nanmax(h[i-13:i+1])
            ll = np.nanmin(l[i-13:i+1])
            result[i] = (hh - c[i]) / (hh - ll) * 100 if hh != ll else 50
        return _min_max_normalize(result, invert=True)

    @staticmethod
    @register_factor("mfi_factor", "technical", "MFI因子", "14日资金流量指标")
    def mfi_factor(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                   volume: np.ndarray) -> np.ndarray:
        """MFI因子"""
        h = np.asarray(high, dtype=np.float64)
        l = np.asarray(low, dtype=np.float64)
        c = np.asarray(close, dtype=np.float64)
        v = np.asarray(volume, dtype=np.float64)
        tp = (h + l + c) / 3
        result = np.full_like(c, np.nan)
        for i in range(14, len(c)):
            pos_flow = neg_flow = 0.0
            for j in range(i-13, i+1):
                mf = tp[j] * v[j]
                if tp[j] > tp[j-1]:
                    pos_flow += mf
                elif tp[j] < tp[j-1]:
                    neg_flow += mf
            if neg_flow > 0:
                mfr = pos_flow / neg_flow
                result[i] = 100.0 - 100.0 / (1.0 + mfr)
            else:
                result[i] = 100.0
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("adx_trend", "technical", "ADX趋势强度", "14日ADX趋势强度")
    def adx_trend(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
        """ADX趋势强度因子"""
        h = np.asarray(high, dtype=np.float64)
        l = np.asarray(low, dtype=np.float64)
        c = np.asarray(close, dtype=np.float64)
        n = len(c)
        tr = np.zeros(n)
        plus_dm = np.zeros(n)
        minus_dm = np.zeros(n)
        for i in range(1, n):
            tr[i] = max(h[i] - l[i], abs(h[i] - c[i-1]), abs(l[i] - c[i-1]))
            up = h[i] - h[i-1]
            dn = l[i-1] - l[i]
            plus_dm[i] = up if up > dn and up > 0 else 0
            minus_dm[i] = dn if dn > up and dn > 0 else 0
        result = np.full(n, np.nan)
        for i in range(28, n):
            tr14 = np.sum(tr[i-13:i+1])
            if tr14 == 0:
                continue
            pdi14 = np.sum(plus_dm[i-13:i+1]) / tr14 * 100
            mdi14 = np.sum(minus_dm[i-13:i+1]) / tr14 * 100
            dx = abs(pdi14 - mdi14) / (pdi14 + mdi14) * 100 if (pdi14 + mdi14) > 0 else 0
            result[i] = dx
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("psar_reversal", "technical", "PSAR反转", "抛物线SAR反转信号")
    def psar_reversal(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
        """PSAR反转因子"""
        h = np.asarray(high, dtype=np.float64)
        l = np.asarray(low, dtype=np.float64)
        c = np.asarray(close, dtype=np.float64)
        n = len(h)
        af = 0.02
        af_max = 0.2
        psar = np.full(n, np.nan)
        psar[0] = l[0]
        trend = 1  # 1=上升, -1=下降
        ep = h[0]
        result = np.full(n, 50.0)
        for i in range(1, n):
            psar[i] = psar[i-1] + af * (ep - psar[i-1])
            if trend == 1:
                if l[i] < psar[i]:
                    trend = -1
                    psar[i] = ep
                    af = 0.02
                    ep = l[i]
                    result[i] = 20.0
                else:
                    if h[i] > ep:
                        ep = h[i]
                        af = min(af + 0.02, af_max)
                    result[i] = 80.0 if c[i] > psar[i] else 50.0
            else:
                if h[i] > psar[i]:
                    trend = 1
                    psar[i] = ep
                    af = 0.02
                    ep = h[i]
                    result[i] = 80.0
                else:
                    if l[i] < ep:
                        ep = l[i]
                        af = min(af + 0.02, af_max)
                    result[i] = 20.0 if c[i] < psar[i] else 50.0
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("ichimoku_cloud", "technical", "一目均衡", "价格相对云层位置")
    def ichimoku_cloud(close: np.ndarray, high: np.ndarray, low: np.ndarray) -> np.ndarray:
        """一目均衡云因子"""
        c = np.asarray(close, dtype=np.float64)
        h = np.asarray(high, dtype=np.float64)
        l = np.asarray(low, dtype=np.float64)
        n = len(c)
        tenkan = np.full(n, np.nan)
        kijun = np.full(n, np.nan)
        for i in range(9, n):
            tenkan[i] = (np.nanmax(h[i-8:i+1]) + np.nanmin(l[i-8:i+1])) / 2
        for i in range(26, n):
            kijun[i] = (np.nanmax(h[i-25:i+1]) + np.nanmin(l[i-25:i+1])) / 2
        result = np.full(n, 50.0)
        for i in range(26, n):
            if c[i] > max(tenkan[i], kijun[i]):
                result[i] = 80.0
            elif c[i] < min(tenkan[i], kijun[i]):
                result[i] = 20.0
            elif tenkan[i] > kijun[i]:
                result[i] = 60.0
            else:
                result[i] = 40.0
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("ema_cross", "technical", "EMA交叉", "EMA12/26交叉信号")
    def ema_cross(close: np.ndarray) -> np.ndarray:
        """EMA交叉因子"""
        c = np.asarray(close, dtype=np.float64)
        n = len(c)
        ema12 = np.full(n, np.nan)
        ema26 = np.full(n, np.nan)
        if n >= 12:
            ema12[11] = np.nanmean(c[:12])
            for i in range(12, n):
                ema12[i] = c[i] * 2/13 + ema12[i-1] * 11/13
        if n >= 26:
            ema26[25] = np.nanmean(c[:26])
            for i in range(26, n):
                ema26[i] = c[i] * 2/27 + ema26[i-1] * 25/27
        result = np.full(n, 50.0)
        for i in range(26, n):
            diff = ema12[i] - ema26[i]
            prev_diff = ema12[i-1] - ema26[i-1]
            if diff > 0 and prev_diff <= 0:
                result[i] = 85.0
            elif diff < 0 and prev_diff >= 0:
                result[i] = 15.0
            elif diff > 0:
                result[i] = 60.0
            else:
                result[i] = 40.0
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("bollinger_bandwidth", "technical", "布林带宽", "布林带宽度/中轨，波动率扩张")
    def bollinger_bandwidth(close: np.ndarray) -> np.ndarray:
        """布林带宽因子"""
        c = np.asarray(close, dtype=np.float64)
        result = np.full_like(c, np.nan)
        for i in range(20, len(c)):
            ma = np.nanmean(c[i-19:i+1])
            std = np.nanstd(c[i-19:i+1])
            result[i] = (2 * std) / ma * 100 if ma > 0 else 0
        return _min_max_normalize(result)

    # ============================================================
    # 基本面因子（15个）
    # ============================================================

    @staticmethod
    @register_factor("pe_factor", "fundamental", "PE因子", "市盈率，越低越好",
                     higher_is_better=False)
    def pe_factor(pe: float) -> np.ndarray:
        """PE因子（单值）"""
        if pe <= 0:
            return np.array([20.0])
        if pe < 10:
            return np.array([90.0])
        elif pe < 20:
            return np.array([70.0])
        elif pe < 30:
            return np.array([50.0])
        elif pe < 50:
            return np.array([30.0])
        else:
            return np.array([10.0])

    @staticmethod
    @register_factor("pb_factor", "fundamental", "PB因子", "市净率，越低越好",
                     higher_is_better=False)
    def pb_factor(pb: float) -> np.ndarray:
        """PB因子（单值）"""
        if pb <= 0:
            return np.array([20.0])
        if pb < 1:
            return np.array([85.0])
        elif pb < 2:
            return np.array([65.0])
        elif pb < 3:
            return np.array([45.0])
        elif pb < 5:
            return np.array([25.0])
        else:
            return np.array([10.0])

    @staticmethod
    @register_factor("roe_factor", "fundamental", "ROE因子", "净资产收益率")
    def roe_factor(roe: float) -> np.ndarray:
        """ROE因子（单值）"""
        if roe > 20:
            return np.array([90.0])
        elif roe > 15:
            return np.array([75.0])
        elif roe > 10:
            return np.array([55.0])
        elif roe > 5:
            return np.array([35.0])
        elif roe > 0:
            return np.array([15.0])
        else:
            return np.array([5.0])

    @staticmethod
    @register_factor("roa_factor", "fundamental", "ROA因子", "总资产收益率")
    def roa_factor(roa: float) -> np.ndarray:
        """ROA因子（单值）"""
        if roa > 10:
            return np.array([90.0])
        elif roa > 5:
            return np.array([70.0])
        elif roa > 2:
            return np.array([50.0])
        elif roa > 0:
            return np.array([30.0])
        else:
            return np.array([10.0])

    @staticmethod
    @register_factor("gross_margin", "fundamental", "毛利率", "销售毛利率")
    def gross_margin(margin: float) -> np.ndarray:
        """毛利率因子（单值）"""
        if margin > 60:
            return np.array([90.0])
        elif margin > 40:
            return np.array([70.0])
        elif margin > 20:
            return np.array([50.0])
        elif margin > 10:
            return np.array([30.0])
        else:
            return np.array([10.0])

    @staticmethod
    @register_factor("net_margin", "fundamental", "净利率", "销售净利率")
    def net_margin(margin: float) -> np.ndarray:
        """净利率因子（单值）"""
        if margin > 20:
            return np.array([90.0])
        elif margin > 10:
            return np.array([70.0])
        elif margin > 5:
            return np.array([50.0])
        elif margin > 0:
            return np.array([30.0])
        else:
            return np.array([10.0])

    @staticmethod
    @register_factor("debt_ratio", "fundamental", "负债率", "资产负债率，越低越好",
                     higher_is_better=False)
    def debt_ratio(ratio: float) -> np.ndarray:
        """负债率因子（单值）"""
        if ratio < 30:
            return np.array([85.0])
        elif ratio < 50:
            return np.array([65.0])
        elif ratio < 70:
            return np.array([40.0])
        elif ratio < 85:
            return np.array([20.0])
        else:
            return np.array([5.0])

    @staticmethod
    @register_factor("cash_flow_ratio", "fundamental", "现金流比率", "经营现金流/营业收入")
    def cash_flow_ratio(ratio: float) -> np.ndarray:
        """现金流比率因子（单值）"""
        if ratio > 30:
            return np.array([90.0])
        elif ratio > 20:
            return np.array([75.0])
        elif ratio > 10:
            return np.array([55.0])
        elif ratio > 5:
            return np.array([35.0])
        elif ratio > 0:
            return np.array([15.0])
        else:
            return np.array([5.0])

    @staticmethod
    @register_factor("eps_growth", "fundamental", "EPS增长率", "每股收益同比增长率")
    def eps_growth(growth: float) -> np.ndarray:
        """EPS增长率因子（单值）"""
        if growth > 50:
            return np.array([90.0])
        elif growth > 30:
            return np.array([75.0])
        elif growth > 10:
            return np.array([55.0])
        elif growth > 0:
            return np.array([35.0])
        else:
            return np.array([10.0])

    @staticmethod
    @register_factor("revenue_growth", "fundamental", "营收增长率", "营业收入同比增长率")
    def revenue_growth(growth: float) -> np.ndarray:
        """营收增长率因子（单值）"""
        if growth > 30:
            return np.array([90.0])
        elif growth > 20:
            return np.array([75.0])
        elif growth > 10:
            return np.array([55.0])
        elif growth > 0:
            return np.array([35.0])
        else:
            return np.array([10.0])

    @staticmethod
    @register_factor("dividend_yield", "fundamental", "股息率", "股息率")
    def dividend_yield(yld: float) -> np.ndarray:
        """股息率因子（单值）"""
        if yld > 5:
            return np.array([90.0])
        elif yld > 3:
            return np.array([70.0])
        elif yld > 2:
            return np.array([50.0])
        elif yld > 1:
            return np.array([30.0])
        else:
            return np.array([10.0])

    @staticmethod
    @register_factor("current_ratio", "fundamental", "流动比率", "流动资产/流动负债")
    def current_ratio(cr: float) -> np.ndarray:
        """流动比率因子（单值）"""
        if cr > 2.5:
            return np.array([85.0])
        elif cr > 2.0:
            return np.array([70.0])
        elif cr > 1.5:
            return np.array([55.0])
        elif cr > 1.0:
            return np.array([40.0])
        else:
            return np.array([15.0])

    @staticmethod
    @register_factor("inventory_turnover", "fundamental", "存货周转率", "存货周转率")
    def inventory_turnover(turnover: float) -> np.ndarray:
        """存货周转率因子（单值）"""
        if turnover > 10:
            return np.array([90.0])
        elif turnover > 5:
            return np.array([70.0])
        elif turnover > 2:
            return np.array([50.0])
        elif turnover > 1:
            return np.array([30.0])
        else:
            return np.array([10.0])

    @staticmethod
    @register_factor("peg_factor", "fundamental", "PEG因子", "市盈率/增长率，越低越好",
                     higher_is_better=False)
    def peg_factor(peg: float) -> np.ndarray:
        """PEG因子（单值）"""
        if peg <= 0:
            return np.array([20.0])
        if peg < 0.5:
            return np.array([90.0])
        elif peg < 1.0:
            return np.array([75.0])
        elif peg < 1.5:
            return np.array([50.0])
        elif peg < 2.0:
            return np.array([30.0])
        else:
            return np.array([10.0])

    @staticmethod
    @register_factor("ev_ebitda", "fundamental", "EV/EBITDA", "企业价值/EBITDA，越低越好",
                     higher_is_better=False)
    def ev_ebitda(ratio: float) -> np.ndarray:
        """EV/EBITDA因子（单值）"""
        if ratio <= 0:
            return np.array([20.0])
        if ratio < 5:
            return np.array([90.0])
        elif ratio < 10:
            return np.array([70.0])
        elif ratio < 15:
            return np.array([50.0])
        elif ratio < 20:
            return np.array([30.0])
        else:
            return np.array([10.0])

    # ============================================================
    # 批量计算
    # ============================================================

    def calculate_all(self, symbol: str, kline_data: Dict[str, np.ndarray],
                      financials: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """计算所有因子

        Args:
            symbol: 股票代码
            kline_data: K线数据，包含 close/high/low/open/volume 等字段
            financials: 基本面数据字典，可选

        Returns:
            dict: {success, factors: {name: score}, metadata: {...}, elapsed_seconds}
        """
        import time
        t0 = time.time()

        if kline_data is None or len(kline_data.get("close", [])) < 60:
            return {
                "success": False,
                "error": "K线数据不足（至少需要60根K线）",
                "factors": {},
                "elapsed_seconds": 0
            }

        close = np.asarray(kline_data["close"], dtype=np.float64)
        high = np.asarray(kline_data.get("high", close), dtype=np.float64)
        low = np.asarray(kline_data.get("low", close), dtype=np.float64)
        open_prices = np.asarray(kline_data.get("open", close), dtype=np.float64)
        volume = np.asarray(kline_data.get("volume", np.ones_like(close)), dtype=np.float64)
        turnover = np.asarray(kline_data.get("turnover", np.ones_like(close)), dtype=np.float64)

        factors = {}
        financials = financials or {}

        # 基础因子：需要序列数据
        basic_sequence_args = {
            "momentum_1m": [close],
            "momentum_3m": [close],
            "momentum_6m": [close],
            "momentum_12m": [close],
            "reversal_1m": [close],
            "volatility_1m": [close],
            "volatility_3m": [close],
            "volume_ratio": [volume],
            "turnover_rate": [turnover],
            "amplitude": [high, low, close],
            "price_position": [close],
            "ma_deviation": [close],
            "volume_breakout": [volume],
            "drawdown": [close],
            "up_days_ratio": [close],
            "gap_ratio": [open_prices, close],
            "volume_trend": [close, volume],
            "high_low_ratio": [high, low],
            "continuous_days": [close],
        }
        for name, args in basic_sequence_args.items():
            try:
                func = self._factors.get(name)
                if func:
                    factors[name] = float(func(*args)[-1])
            except Exception as e:
                logger.warning(f"计算因子 {name} 失败: {e}")
                factors[name] = 50.0

        # 技术因子
        technical_sequence_args = {
            "rsi_factor": [close],
            "macd_divergence": [close],
            "boll_position": [close],
            "ma_alignment": [close],
            "kdj_golden_cross": [close, high, low],
            "atr_factor": [high, low, close],
            "obv_divergence": [close, volume],
            "cci_factor": [high, low, close],
            "williams_r": [high, low, close],
            "mfi_factor": [high, low, close, volume],
            "adx_trend": [high, low, close],
            "psar_reversal": [high, low, close],
            "ichimoku_cloud": [close, high, low],
            "ema_cross": [close],
            "bollinger_bandwidth": [close],
        }
        for name, args in technical_sequence_args.items():
            try:
                func = self._factors.get(name)
                if func:
                    factors[name] = float(func(*args)[-1])
            except Exception as e:
                logger.warning(f"计算因子 {name} 失败: {e}")
                factors[name] = 50.0

        # 基本面因子（单值）
        fundamental_single_args = {
            "pe_factor": financials.get("pe", 0),
            "pb_factor": financials.get("pb", 0),
            "roe_factor": financials.get("roe", 0),
            "roa_factor": financials.get("roa", 0),
            "gross_margin": financials.get("gross_margin", 0),
            "net_margin": financials.get("net_margin", 0),
            "debt_ratio": financials.get("debt_ratio", 0),
            "cash_flow_ratio": financials.get("cash_flow_ratio", 0),
            "eps_growth": financials.get("eps_growth", 0),
            "revenue_growth": financials.get("revenue_growth", 0),
            "dividend_yield": financials.get("dividend_yield", 0),
            "current_ratio": financials.get("current_ratio", 0),
            "inventory_turnover": financials.get("inventory_turnover", 0),
            "peg_factor": financials.get("peg", 0),
            "ev_ebitda": financials.get("ev_ebitda", 0),
        }
        for name, arg in fundamental_single_args.items():
            try:
                func = self._factors.get(name)
                if func:
                    factors[name] = float(func(arg)[0])
            except Exception as e:
                logger.warning(f"计算因子 {name} 失败: {e}")
                factors[name] = 50.0

        # 计算综合评分
        valid_scores = [v for v in factors.values() if not np.isnan(v)]
        composite_score = float(np.nanmean(valid_scores)) if valid_scores else 50.0

        elapsed = round(time.time() - t0, 4)
        logger.info(f"[{symbol}] 因子计算完成: {len(factors)}个因子, 综合评分={composite_score:.1f}, 耗时={elapsed}s")

        return {
            "success": True,
            "symbol": symbol,
            "factors": factors,
            "composite_score": composite_score,
            "factor_count": len(factors),
            "elapsed_seconds": elapsed,
        }

    # ============================================================
    # 因子分析
    # ============================================================

    def calculate_ic_ir(self, factor_name: str,
                        factor_values: np.ndarray,
                        returns: np.ndarray) -> Dict[str, Any]:
        """IC/IR分析

        Args:
            factor_name: 因子名称
            factor_values: 因子值序列
            returns: 未来收益率序列（同长度）

        Returns:
            dict: {success, ic_mean, ic_std, ir, ic_series, ic_positive_rate, ...}
        """
        try:
            fv = np.asarray(factor_values, dtype=np.float64)
            rt = np.asarray(returns, dtype=np.float64)

            valid = ~(np.isnan(fv) | np.isnan(rt))
            fv = fv[valid]
            rt = rt[valid]

            if len(fv) < 10:
                return {"success": False, "error": "数据点不足", "factor_name": factor_name}

            # Rank IC
            from scipy.stats import spearmanr
            ic, _ = spearmanr(fv, rt)
            ic_series = np.array([ic])

            ic_mean = float(np.nanmean(ic_series))
            ic_std = float(np.nanstd(ic_series))
            ir = ic_mean / ic_std if ic_std > 0 else 0.0
            ic_positive_rate = float(np.sum(ic_series > 0) / len(ic_series))

            return {
                "success": True,
                "factor_name": factor_name,
                "ic_mean": round(ic_mean, 6),
                "ic_std": round(ic_std, 6),
                "ir": round(ir, 4),
                "ic_positive_rate": round(ic_positive_rate, 4),
                "sample_count": len(fv),
            }
        except Exception as e:
            logger.error(f"IC/IR分析失败 [{factor_name}]: {e}")
            return {"success": False, "error": str(e), "factor_name": factor_name}

    def factor_quantile_analysis(self, factor_name: str,
                                 factor_values: np.ndarray,
                                 returns: np.ndarray,
                                 n_quantiles: int = 5) -> Dict[str, Any]:
        """分位数分层分析

        Args:
            factor_name: 因子名称
            factor_values: 因子值
            returns: 收益率
            n_quantiles: 分位数数量

        Returns:
            dict: {success, quantiles: [{rank, mean_return, count}], top_minus_bottom, ...}
        """
        try:
            fv = np.asarray(factor_values, dtype=np.float64)
            rt = np.asarray(returns, dtype=np.float64)

            valid = ~(np.isnan(fv) | np.isnan(rt))
            fv = fv[valid]
            rt = rt[valid]

            if len(fv) < n_quantiles * 5:
                return {"success": False, "error": "数据点不足", "factor_name": factor_name}

            quantile_edges = np.percentile(fv, np.linspace(0, 100, n_quantiles + 1))
            quantiles = []
            for i in range(n_quantiles):
                mask = (fv >= quantile_edges[i]) & (fv < quantile_edges[i + 1])
                if i == n_quantiles - 1:
                    mask = (fv >= quantile_edges[i]) & (fv <= quantile_edges[i + 1])
                quantiles.append({
                    "rank": i + 1,
                    "mean_return": round(float(np.nanmean(rt[mask])), 6),
                    "count": int(np.sum(mask)),
                })

            top_minus_bottom = quantiles[-1]["mean_return"] - quantiles[0]["mean_return"]

            return {
                "success": True,
                "factor_name": factor_name,
                "quantiles": quantiles,
                "top_minus_bottom": round(top_minus_bottom, 6),
                "n_quantiles": n_quantiles,
            }
        except Exception as e:
            logger.error(f"分位数分析失败 [{factor_name}]: {e}")
            return {"success": False, "error": str(e), "factor_name": factor_name}

    def factor_decay_analysis(self, factor_name: str,
                              factor_values: np.ndarray,
                              future_returns: Dict[int, np.ndarray]) -> Dict[str, Any]:
        """因子衰减分析

        Args:
            factor_name: 因子名称
            factor_values: 因子值序列
            future_returns: {period_days: returns_array} 不同周期的未来收益

        Returns:
            dict: {success, decay_curve: [{period, ic_mean}], half_life_days, ...}
        """
        try:
            fv = np.asarray(factor_values, dtype=np.float64)
            decay_curve = []

            for period, rt in sorted(future_returns.items()):
                rt_arr = np.asarray(rt, dtype=np.float64)
                valid = ~(np.isnan(fv) | np.isnan(rt_arr))
                if np.sum(valid) < 10:
                    continue
                from scipy.stats import spearmanr
                ic, _ = spearmanr(fv[valid], rt_arr[valid])
                decay_curve.append({
                    "period": period,
                    "ic_mean": round(float(ic), 6),
                })

            # 估计半衰期
            half_life = None
            if len(decay_curve) >= 2 and decay_curve[0]["ic_mean"] != 0:
                for dc in decay_curve:
                    if abs(dc["ic_mean"]) < abs(decay_curve[0]["ic_mean"]) / 2:
                        half_life = dc["period"]
                        break

            return {
                "success": True,
                "factor_name": factor_name,
                "decay_curve": decay_curve,
                "half_life_days": half_life,
            }
        except Exception as e:
            logger.error(f"因子衰减分析失败 [{factor_name}]: {e}")
            return {"success": False, "error": str(e), "factor_name": factor_name}

    def factor_correlation_matrix(self,
                                  factor_data: Dict[str, np.ndarray]) -> Dict[str, Any]:
        """因子相关性矩阵

        Args:
            factor_data: {factor_name: values_array}

        Returns:
            dict: {success, correlation_matrix: [[...]], factor_names: [...], high_correlation_pairs: [...]}
        """
        try:
            factor_names = list(factor_data.keys())
            n = len(factor_names)

            if n < 2:
                return {"success": False, "error": "至少需要2个因子", "factor_names": factor_names}

            # 构建矩阵
            data_matrix = np.column_stack([
                np.asarray(factor_data[name], dtype=np.float64)
                for name in factor_names
            ])

            valid_rows = ~np.any(np.isnan(data_matrix), axis=1)
            data_matrix = data_matrix[valid_rows]

            if len(data_matrix) < 10:
                return {"success": False, "error": "有效数据点不足", "factor_names": factor_names}

            corr_matrix = np.corrcoef(data_matrix.T)
            corr_list = corr_matrix.tolist()

            # 高相关性因子对
            high_corr_pairs = []
            for i in range(n):
                for j in range(i + 1, n):
                    if abs(corr_matrix[i, j]) > 0.7:
                        high_corr_pairs.append({
                            "factor_a": factor_names[i],
                            "factor_b": factor_names[j],
                            "correlation": round(float(corr_matrix[i, j]), 4),
                        })

            return {
                "success": True,
                "factor_names": factor_names,
                "correlation_matrix": corr_list,
                "high_correlation_pairs": high_corr_pairs,
                "sample_count": len(data_matrix),
            }
        except Exception as e:
            logger.error(f"因子相关性分析失败: {e}")
            return {"success": False, "error": str(e), "factor_names": list(factor_data.keys())}


# ============================================================
# 测试
# ============================================================

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    engine = AlphaFactorEngine()
    print(f"已注册因子数量: {len(engine.factor_names)}")
    print(f"因子列表: {engine.factor_names}")

    # 生成模拟K线数据
    np.random.seed(42)
    n = 300
    close = np.cumprod(1 + np.random.randn(n) * 0.02) * 10
    high = close * (1 + np.abs(np.random.randn(n) * 0.02))
    low = close * (1 - np.abs(np.random.randn(n) * 0.02))
    open_prices = close * (1 + np.random.randn(n) * 0.005)
    volume = np.abs(np.random.randn(n) * 1000000 + 5000000)

    kline = {
        "close": close,
        "high": high,
        "low": low,
        "open": open_prices,
        "volume": volume,
        "turnover": volume / 100000000,
    }

    financials = {
        "pe": 15.5, "pb": 2.1, "roe": 18.2, "roa": 8.5,
        "gross_margin": 45.0, "net_margin": 12.0,
        "debt_ratio": 40.0, "cash_flow_ratio": 15.0,
        "eps_growth": 25.0, "revenue_growth": 18.0,
        "dividend_yield": 2.5, "current_ratio": 2.0,
        "inventory_turnover": 5.0, "peg": 0.8, "ev_ebitda": 8.0,
    }

    result = engine.calculate_all("TEST", kline, financials)
    print(f"\n综合评分: {result['composite_score']:.2f}")
    print(f"因子数量: {result['factor_count']}")
    print(f"耗时: {result['elapsed_seconds']}s")

    # 因子相关性矩阵
    factor_values = {}
    for name in list(engine.factor_names)[:10]:
        val = np.array([result["factors"].get(name, 50.0)] * 100)
        factor_values[name] = val
    corr_result = engine.factor_correlation_matrix(factor_values)
    print(f"\n相关性矩阵: {corr_result['success']}")