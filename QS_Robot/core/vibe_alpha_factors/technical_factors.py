"""技术因子 Mixin（15个）"""
import numpy as np
from ._registry import register_factor
from ._utils import _min_max_normalize


class TechnicalFactorsMixin:
    """技术因子：RSI、MACD、布林带、均线、KDJ、ATR、OBV、CCI等"""

    @staticmethod
    @register_factor("rsi_factor", "technical", "RSI因子", "14日RSI，超买超卖信号")
    def rsi_factor(close: np.ndarray) -> np.ndarray:
        c = np.asarray(close, dtype=np.float64)
        diff = np.diff(c)
        result = np.full_like(c, np.nan)
        for i in range(14, len(c)):
            gains = np.sum(diff[i - 13:i + 1][diff[i - 13:i + 1] > 0])
            losses = -np.sum(diff[i - 13:i + 1][diff[i - 13:i + 1] < 0])
            if losses == 0:
                result[i] = 100.0
            else:
                rs = gains / losses
                result[i] = 100.0 - 100.0 / (1.0 + rs)
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("macd_divergence", "technical", "MACD背离", "MACD与价格背离程度")
    def macd_divergence(close: np.ndarray) -> np.ndarray:
        c = np.asarray(close, dtype=np.float64)
        n = len(c)
        ema12 = np.full(n, np.nan)
        ema26 = np.full(n, np.nan)
        if n >= 12:
            ema12[11] = np.nanmean(c[:12])
            for i in range(12, n):
                ema12[i] = c[i] * 2 / 13 + ema12[i - 1] * 11 / 13
        if n >= 26:
            ema26[25] = np.nanmean(c[:26])
            for i in range(26, n):
                ema26[i] = c[i] * 2 / 27 + ema26[i - 1] * 25 / 27
        dif = ema12 - ema26
        dea = np.full(n, np.nan)
        if n >= 35:
            dea[34] = np.nanmean(dif[26:35])
            for i in range(35, n):
                dea[i] = dif[i] * 2 / 10 + dea[i - 1] * 8 / 10
        macd = (dif - dea) * 2
        return _min_max_normalize(macd)

    @staticmethod
    @register_factor("boll_position", "technical", "布林带位置", "价格在布林带中的位置")
    def boll_position(close: np.ndarray) -> np.ndarray:
        c = np.asarray(close, dtype=np.float64)
        result = np.full_like(c, np.nan)
        for i in range(20, len(c)):
            ma = np.nanmean(c[i - 19:i + 1])
            std = np.nanstd(c[i - 19:i + 1])
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
        c = np.asarray(close, dtype=np.float64)
        result = np.full_like(c, np.nan)
        for i in range(60, len(c)):
            ma5 = np.nanmean(c[i - 4:i + 1])
            ma10 = np.nanmean(c[i - 9:i + 1])
            ma20 = np.nanmean(c[i - 19:i + 1])
            ma60 = np.nanmean(c[i - 59:i + 1])
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
        c = np.asarray(close, dtype=np.float64)
        h = np.asarray(high, dtype=np.float64)
        l = np.asarray(low, dtype=np.float64)
        n = len(c)
        k = np.full(n, 50.0)
        d = np.full(n, 50.0)
        j = np.full(n, 50.0)
        for i in range(8, n):
            h9 = np.nanmax(h[i - 8:i + 1])
            l9 = np.nanmin(l[i - 8:i + 1])
            rsv = (c[i] - l9) / (h9 - l9) * 100 if h9 != l9 else 50
            k[i] = 2 / 3 * k[i - 1] + 1 / 3 * rsv
            d[i] = 2 / 3 * d[i - 1] + 1 / 3 * k[i]
            j[i] = 3 * k[i] - 2 * d[i]
        result = np.full_like(c, 50.0)
        for i in range(9, n):
            if k[i] > d[i] and k[i - 1] <= d[i - 1]:
                result[i] = 80.0
            elif k[i] < d[i] and k[i - 1] >= d[i - 1]:
                result[i] = 20.0
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("atr_factor", "technical", "ATR波动", "14日平均真实波幅",
                     higher_is_better=False)
    def atr_factor(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
        h = np.asarray(high, dtype=np.float64)
        l = np.asarray(low, dtype=np.float64)
        c = np.asarray(close, dtype=np.float64)
        n = len(c)
        tr = np.zeros(n)
        for i in range(1, n):
            tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
        result = np.full(n, np.nan)
        for i in range(14, n):
            result[i] = np.nanmean(tr[i - 13:i + 1])
        return _min_max_normalize(result, invert=True)

    @staticmethod
    @register_factor("obv_divergence", "technical", "OBV背离", "能量潮与价格背离")
    def obv_divergence(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
        c = np.asarray(close, dtype=np.float64)
        v = np.asarray(volume, dtype=np.float64)
        obv = np.zeros(len(c))
        obv[0] = v[0]
        for i in range(1, len(c)):
            if c[i] > c[i - 1]:
                obv[i] = obv[i - 1] + v[i]
            elif c[i] < c[i - 1]:
                obv[i] = obv[i - 1] - v[i]
            else:
                obv[i] = obv[i - 1]
        return _min_max_normalize(obv)

    @staticmethod
    @register_factor("cci_factor", "technical", "CCI因子", "14日商品通道指数")
    def cci_factor(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
        h = np.asarray(high, dtype=np.float64)
        l = np.asarray(low, dtype=np.float64)
        c = np.asarray(close, dtype=np.float64)
        tp = (h + l + c) / 3
        result = np.full_like(c, np.nan)
        for i in range(14, len(c)):
            ma = np.nanmean(tp[i - 13:i + 1])
            md = np.nanmean(np.abs(tp[i - 13:i + 1] - ma))
            result[i] = (tp[i] - ma) / (0.015 * md) if md > 0 else 0
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("williams_r", "technical", "威廉指标", "14日威廉%R",
                     higher_is_better=False)
    def williams_r(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
        h = np.asarray(high, dtype=np.float64)
        l = np.asarray(low, dtype=np.float64)
        c = np.asarray(close, dtype=np.float64)
        result = np.full_like(c, np.nan)
        for i in range(14, len(c)):
            hh = np.nanmax(h[i - 13:i + 1])
            ll = np.nanmin(l[i - 13:i + 1])
            result[i] = (hh - c[i]) / (hh - ll) * 100 if hh != ll else 50
        return _min_max_normalize(result, invert=True)

    @staticmethod
    @register_factor("mfi_factor", "technical", "MFI因子", "14日资金流量指标")
    def mfi_factor(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                   volume: np.ndarray) -> np.ndarray:
        h = np.asarray(high, dtype=np.float64)
        l = np.asarray(low, dtype=np.float64)
        c = np.asarray(close, dtype=np.float64)
        v = np.asarray(volume, dtype=np.float64)
        tp = (h + l + c) / 3
        result = np.full_like(c, np.nan)
        for i in range(14, len(c)):
            pos_flow = neg_flow = 0.0
            for j in range(i - 13, i + 1):
                mf = tp[j] * v[j]
                if tp[j] > tp[j - 1]:
                    pos_flow += mf
                elif tp[j] < tp[j - 1]:
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
        h = np.asarray(high, dtype=np.float64)
        l = np.asarray(low, dtype=np.float64)
        c = np.asarray(close, dtype=np.float64)
        n = len(c)
        tr = np.zeros(n)
        plus_dm = np.zeros(n)
        minus_dm = np.zeros(n)
        for i in range(1, n):
            tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
            up = h[i] - h[i - 1]
            dn = l[i - 1] - l[i]
            plus_dm[i] = up if up > dn and up > 0 else 0
            minus_dm[i] = dn if dn > up and dn > 0 else 0
        result = np.full(n, np.nan)
        for i in range(28, n):
            tr14 = np.sum(tr[i - 13:i + 1])
            if tr14 == 0:
                continue
            pdi14 = np.sum(plus_dm[i - 13:i + 1]) / tr14 * 100
            mdi14 = np.sum(minus_dm[i - 13:i + 1]) / tr14 * 100
            dx = abs(pdi14 - mdi14) / (pdi14 + mdi14) * 100 if (pdi14 + mdi14) > 0 else 0
            result[i] = dx
        return _min_max_normalize(result)

    @staticmethod
    @register_factor("psar_reversal", "technical", "PSAR反转", "抛物线SAR反转信号")
    def psar_reversal(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
        h = np.asarray(high, dtype=np.float64)
        l = np.asarray(low, dtype=np.float64)
        c = np.asarray(close, dtype=np.float64)
        n = len(h)
        af = 0.02
        af_max = 0.2
        psar = np.full(n, np.nan)
        psar[0] = l[0]
        trend = 1
        ep = h[0]
        result = np.full(n, 50.0)
        for i in range(1, n):
            psar[i] = psar[i - 1] + af * (ep - psar[i - 1])
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
        c = np.asarray(close, dtype=np.float64)
        h = np.asarray(high, dtype=np.float64)
        l = np.asarray(low, dtype=np.float64)
        n = len(c)
        tenkan = np.full(n, np.nan)
        kijun = np.full(n, np.nan)
        for i in range(9, n):
            tenkan[i] = (np.nanmax(h[i - 8:i + 1]) + np.nanmin(l[i - 8:i + 1])) / 2
        for i in range(26, n):
            kijun[i] = (np.nanmax(h[i - 25:i + 1]) + np.nanmin(l[i - 25:i + 1])) / 2
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
        c = np.asarray(close, dtype=np.float64)
        n = len(c)
        ema12 = np.full(n, np.nan)
        ema26 = np.full(n, np.nan)
        if n >= 12:
            ema12[11] = np.nanmean(c[:12])
            for i in range(12, n):
                ema12[i] = c[i] * 2 / 13 + ema12[i - 1] * 11 / 13
        if n >= 26:
            ema26[25] = np.nanmean(c[:26])
            for i in range(26, n):
                ema26[i] = c[i] * 2 / 27 + ema26[i - 1] * 25 / 27
        result = np.full(n, 50.0)
        for i in range(26, n):
            diff = ema12[i] - ema26[i]
            prev_diff = ema12[i - 1] - ema26[i - 1]
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
        c = np.asarray(close, dtype=np.float64)
        result = np.full_like(c, np.nan)
        for i in range(20, len(c)):
            ma = np.nanmean(c[i - 19:i + 1])
            std = np.nanstd(c[i - 19:i + 1])
            result[i] = (2 * std) / ma * 100 if ma > 0 else 0
        return _min_max_normalize(result)