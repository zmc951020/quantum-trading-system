"""基础因子 Mixin（20个）"""
import numpy as np
from ._registry import register_factor
from ._utils import _min_max_normalize


class BasicFactorsMixin:
    """基础因子：动量、反转、波动率、成交量、换手率、振幅等"""

    @staticmethod
    @register_factor("momentum_1m", "basic", "1月动量", "过去21个交易日收益率")
    def momentum_1m(close: np.ndarray) -> np.ndarray:
        c = np.asarray(close, dtype=np.float64)
        result = np.full_like(c, np.nan)
        result[21:] = (c[21:] - c[:-21]) / c[:-21] * 100
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("momentum_3m", "basic", "3月动量", "过去63个交易日收益率")
    def momentum_3m(close: np.ndarray) -> np.ndarray:
        c = np.asarray(close, dtype=np.float64)
        result = np.full_like(c, np.nan)
        result[63:] = (c[63:] - c[:-63]) / c[:-63] * 100
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("momentum_6m", "basic", "6月动量", "过去126个交易日收益率")
    def momentum_6m(close: np.ndarray) -> np.ndarray:
        c = np.asarray(close, dtype=np.float64)
        result = np.full_like(c, np.nan)
        result[126:] = (c[126:] - c[:-126]) / c[:-126] * 100
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("momentum_12m", "basic", "12月动量", "过去252个交易日收益率")
    def momentum_12m(close: np.ndarray) -> np.ndarray:
        c = np.asarray(close, dtype=np.float64)
        result = np.full_like(c, np.nan)
        result[252:] = (c[252:] - c[:-252]) / c[:-252] * 100
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("reversal_1m", "basic", "1月反转", "短期反转效应，越高越可能反转下跌",
                     higher_is_better=False)
    def reversal_1m(close: np.ndarray) -> np.ndarray:
        c = np.asarray(close, dtype=np.float64)
        result = np.full_like(c, np.nan)
        result[5:] = (c[5:] - c[:-5]) / c[:-5] * 100
        return _min_max_normalize(result, invert=True)

    @staticmethod
    @register_factor("volatility_1m", "basic", "1月波动率", "21日年化波动率",
                     higher_is_better=False)
    def volatility_1m(close: np.ndarray) -> np.ndarray:
        c = np.asarray(close, dtype=np.float64)
        returns = np.full_like(c, np.nan)
        returns[1:] = (c[1:] - c[:-1]) / c[:-1]
        result = np.full_like(c, np.nan)
        for i in range(21, len(c)):
            result[i] = np.nanstd(returns[i - 20:i + 1]) * np.sqrt(252)
        return _min_max_normalize(result, invert=True)

    @staticmethod
    @register_factor("volatility_3m", "basic", "3月波动率", "63日年化波动率",
                     higher_is_better=False)
    def volatility_3m(close: np.ndarray) -> np.ndarray:
        c = np.asarray(close, dtype=np.float64)
        returns = np.full_like(c, np.nan)
        returns[1:] = (c[1:] - c[:-1]) / c[:-1]
        result = np.full_like(c, np.nan)
        for i in range(63, len(c)):
            result[i] = np.nanstd(returns[i - 62:i + 1]) * np.sqrt(252)
        return _min_max_normalize(result, invert=True)

    @staticmethod
    @register_factor("volume_ratio", "basic", "量比", "当日成交量 / 5日均量")
    def volume_ratio(volume: np.ndarray) -> np.ndarray:
        v = np.asarray(volume, dtype=np.float64)
        result = np.full_like(v, np.nan)
        for i in range(5, len(v)):
            ma5 = np.nanmean(v[i - 4:i + 1])
            result[i] = v[i] / ma5 if ma5 > 0 else np.nan
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("turnover_rate", "basic", "换手率", "日均换手率（需外部传入）")
    def turnover_rate(turnover: np.ndarray) -> np.ndarray:
        t = np.asarray(turnover, dtype=np.float64)
        return _min_max_normalize(t)

    @staticmethod
    @register_factor("amplitude", "basic", "振幅", "当日振幅 (high-low)/close")
    def amplitude(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
        h = np.asarray(high, dtype=np.float64)
        l = np.asarray(low, dtype=np.float64)
        c = np.asarray(close, dtype=np.float64)
        result = (h - l) / c * 100
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("price_position", "basic", "价格位置", "收盘价在N日高低区间的相对位置")
    def price_position(close: np.ndarray, window: int = 60) -> np.ndarray:
        c = np.asarray(close, dtype=np.float64)
        result = np.full_like(c, np.nan)
        for i in range(window, len(c)):
            h = np.nanmax(c[i - window:i + 1])
            l = np.nanmin(c[i - window:i + 1])
            result[i] = (c[i] - l) / (h - l) * 100 if h != l else 50
        return result

    @staticmethod
    @register_factor("ma_deviation", "basic", "均线偏离", "收盘价偏离20日均线程度")
    def ma_deviation(close: np.ndarray) -> np.ndarray:
        c = np.asarray(close, dtype=np.float64)
        result = np.full_like(c, np.nan)
        for i in range(20, len(c)):
            ma20 = np.nanmean(c[i - 19:i + 1])
            result[i] = (c[i] - ma20) / ma20 * 100
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("volume_breakout", "basic", "放量突破", "当日成交量突破N日均量倍数")
    def volume_breakout(volume: np.ndarray) -> np.ndarray:
        v = np.asarray(volume, dtype=np.float64)
        result = np.full_like(v, np.nan)
        for i in range(20, len(v)):
            ma20 = np.nanmean(v[i - 19:i + 1])
            result[i] = v[i] / ma20 if ma20 > 0 else np.nan
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("drawdown", "basic", "回撤幅度", "当前价格相对N日高点的回撤",
                     higher_is_better=False)
    def drawdown(close: np.ndarray, window: int = 60) -> np.ndarray:
        c = np.asarray(close, dtype=np.float64)
        result = np.full_like(c, np.nan)
        for i in range(window, len(c)):
            peak = np.nanmax(c[i - window:i + 1])
            result[i] = (c[i] - peak) / peak * 100
        return _min_max_normalize(result, invert=True)

    @staticmethod
    @register_factor("up_days_ratio", "basic", "上涨天数比", "近N日上涨天数占比")
    def up_days_ratio(close: np.ndarray, window: int = 20) -> np.ndarray:
        c = np.asarray(close, dtype=np.float64)
        result = np.full_like(c, np.nan)
        for i in range(window, len(c)):
            diff = np.diff(c[i - window:i + 1])
            up_count = np.sum(diff > 0)
            result[i] = up_count / window * 100
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("gap_ratio", "basic", "跳空比率", "跳空高开/低开比率")
    def gap_ratio(open_prices: np.ndarray, prev_close: np.ndarray) -> np.ndarray:
        o = np.asarray(open_prices, dtype=np.float64)
        pc = np.asarray(prev_close, dtype=np.float64)
        result = np.full_like(o, np.nan)
        result[1:] = (o[1:] - pc[:-1]) / pc[:-1] * 100
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("volume_trend", "basic", "量价趋势", "量价配合度")
    def volume_trend(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
        c = np.asarray(close, dtype=np.float64)
        v = np.asarray(volume, dtype=np.float64)
        result = np.full_like(c, np.nan)
        for i in range(5, len(c)):
            price_change = (c[i] - c[i - 5]) / c[i - 5]
            vol_change = (v[i] - v[i - 5]) / v[i - 5] if v[i - 5] > 0 else 0
            result[i] = price_change * 100 + vol_change * 50
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("high_low_ratio", "basic", "高低价比", "N日最高/最低价比")
    def high_low_ratio(high: np.ndarray, low: np.ndarray, window: int = 20) -> np.ndarray:
        h = np.asarray(high, dtype=np.float64)
        l = np.asarray(low, dtype=np.float64)
        result = np.full_like(h, np.nan)
        for i in range(window, len(h)):
            h_max = np.nanmax(h[i - window + 1:i + 1])
            l_min = np.nanmin(l[i - window + 1:i + 1])
            result[i] = h_max / l_min if l_min > 0 else np.nan
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("continuous_days", "basic", "连涨连跌", "连续上涨天数（正）/连续下跌天数（负）")
    def continuous_days(close: np.ndarray) -> np.ndarray:
        c = np.asarray(close, dtype=np.float64)
        result = np.zeros_like(c)
        for i in range(1, len(c)):
            if c[i] > c[i - 1]:
                result[i] = abs(result[i - 1]) + 1 if result[i - 1] >= 0 else 1
            elif c[i] < c[i - 1]:
                result[i] = -abs(result[i - 1]) - 1 if result[i - 1] <= 0 else -1
            else:
                result[i] = 0
        return _min_max_normalize(result)