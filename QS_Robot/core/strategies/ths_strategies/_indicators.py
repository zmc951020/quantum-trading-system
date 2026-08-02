"""同花顺策略共享技术指标计算

集中实现 SMA/EMA/MACD/BOLL/DMI/EXPMA，避免 14 策略 + 18 战法重复造轮子。
所有函数纯计算无副作用，便于单元测试。
"""
from typing import Sequence


def sma(values: Sequence[float], period: int) -> float:
    if len(values) < period or period <= 0:
        return 0.0
    return sum(values[-period:]) / period


def ema(values: Sequence[float], period: int) -> list[float]:
    if not values or period <= 0:
        return []
    k = 2 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def expma(values: Sequence[float], period: int) -> list[float]:
    return ema(values, period)


def macd(closes: Sequence[float], fast: int, slow: int, signal: int) -> tuple[float, float, float]:
    if len(closes) < slow + signal:
        return 0.0, 0.0, 0.0
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    dif_series = [ema_fast[i] - ema_slow[i] for i in range(slow - 1, len(closes))]
    dea_series = ema(dif_series, signal)
    dif = dif_series[-1]
    dea = dea_series[-1]
    hist = 2 * (dif - dea)
    return dif, dea, hist


def boll(closes: Sequence[float], period: int, std_mult: float) -> tuple[float, float, float]:
    if len(closes) < period:
        return 0.0, 0.0, 0.0
    sample = closes[-period:]
    mid = sum(sample) / period
    var = sum((x - mid) ** 2 for x in sample) / period
    sd = var ** 0.5
    return mid + std_mult * sd, mid, mid - std_mult * sd


def dmi(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int) -> tuple[float, float, float]:
    if len(highs) < period + 1:
        return 0.0, 0.0, 0.0
    plus_dm, minus_dm, tr_list = [], [], []
    for i in range(1, len(highs)):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        tr_list.append(tr)
    if len(tr_list) < period:
        return 0.0, 0.0, 0.0
    atr = sum(tr_list[-period:]) / period
    if atr <= 0:
        return 0.0, 0.0, 0.0
    plus_di = 100 * sum(plus_dm[-period:]) / period / atr
    minus_di = 100 * sum(minus_dm[-period:]) / period / atr
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di) if (plus_di + minus_di) > 0 else 0.0
    return plus_di, minus_di, dx


def rsi(closes: Sequence[float], period: int) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(-period, 0):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)
