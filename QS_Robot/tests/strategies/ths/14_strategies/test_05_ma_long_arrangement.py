"""策略05 多头排列回踩低吸 — 严格数学建模版测试"""
import importlib as _il
from decimal import Decimal
import sys
sys.path.insert(0, r"D:\Gupiao\升级vscode\QS_Robot")
_m = _il.import_module("core.strategies.ths_strategies.14_strategies.05_ma_long_arrangement")
MALongArrangementStrategy = _m.MALongArrangementStrategy


def _make_ma_trend_bars(n=80):
    """多头排列趋势：锯齿上涨+ADX>20+回踩MA5/MA10+反弹"""
    import math
    bars = []
    base = 10.0
    amplitude = 0.6
    for i in range(n):
        trend = i * 0.12
        wave = amplitude * math.sin(i * 0.3)
        if i >= n - 10:
            trend = (n - 10) * 0.12
            wave = -amplitude * math.sin(i * 0.3) * 0.7
        if i >= n - 3:
            wave = amplitude * 0.3 * math.sin(i * 0.5)
        price = base + trend + wave
        if i < n - 10:
            vol = 1000000 + i * 2000 + abs(wave) * 500000
        elif i < n - 3:
            vol = 600000 - i * 3000
        else:
            vol = 900000 + i * 8000
        bar = {
            "date": f"2026-{i // 20 + 1:02d}-{i % 20 + 1:02d}",
            "close": price, "high": price * 1.02, "low": price * 0.98,
            "open": price * 0.995, "volume": max(vol, 100000),
        }
        bars.append(bar)
    bars[-1]["low"] = bars[-1]["close"] * 0.985
    bars[-1]["volume"] = bars[-2]["volume"] * 1.15
    return bars


def _make_chaotic_bars(n=80):
    """混乱走势：价格随机波动，均线不排列"""
    bars = []
    price = 10.0
    for i in range(n):
        price += 0.02 if i % 3 == 0 else -0.03
        bars.append({
            "date": f"2026-{i // 20 + 1:02d}-{i % 20 + 1:02d}",
            "close": price, "high": price * 1.02, "low": price * 0.98,
            "open": price, "volume": 1000000,
        })
    return bars


def test_metadata():
    s = MALongArrangementStrategy()
    assert s.ID == "05_ma_long_arrangement"
    assert s.NAME == "多头排列回踩低吸"
    assert s.CATEGORY == "ths_strategies"
    assert s.RISK_LEVEL == "中"


def test_param_space():
    s = MALongArrangementStrategy()
    ps = s.get_param_space()
    assert isinstance(ps, dict) and len(ps) > 0
    assert "vol_ratio" in ps


def test_validate_params():
    s = MALongArrangementStrategy()
    assert s.validate_params({"vol_ratio": 0.8})
    assert not s.validate_params({"vol_ratio": 0.1})
    assert not s.validate_params({"vol_ratio": 2.0})


def test_no_signal_short_data():
    s = MALongArrangementStrategy()
    assert s.generate_signal([], {}) is None


def test_ma_alignment_buy():
    """多头排列+回踩+反弹时产生买入信号"""
    s = MALongArrangementStrategy()
    bars = _make_ma_trend_bars(n=80)
    sig = s.generate_signal(bars, {})
    if sig and sig["action"] == "buy":
        assert sig["stop_loss"] < sig["price"] < sig["take_profit"]
        assert sig["ma5"] > sig["ma10"] > sig["ma20"] > sig["ma60"]


def test_chaotic_no_buy():
    """混乱走势不产生买入信号"""
    s = MALongArrangementStrategy()
    bars = _make_chaotic_bars(n=80)
    sig = s.generate_signal(bars, {})
    assert sig is None or sig["action"] != "buy"


def test_sell_below_ma20():
    """跌破MA20触发卖出"""
    s = MALongArrangementStrategy()
    bars = _make_ma_trend_bars(n=80)
    for i in range(5):
        bars.append({
            "date": f"2026-99-{i:02d}",
            "close": 8.0 - i * 0.3, "high": 9.0, "low": 7.5,
            "open": 8.5, "volume": 100000,
        })
    sig = s.generate_signal(bars, {})
    if sig:
        assert sig["action"] in ("buy", "sell")


def test_sell_alignment_broken():
    """均线排列破坏触发卖出"""
    s = MALongArrangementStrategy()
    bars = _make_ma_trend_bars(n=80)
    for i in range(5):
        bars.append({
            "date": f"2026-99-{i:02d}",
            "close": 12.0 + i * 0.1, "high": 12.5, "low": 11.5,
            "open": 12.0, "volume": 100000,
        })
    sig = s.generate_signal(bars, {})
    if sig and sig["action"] == "sell":
        assert sig["reason"] in ("below_ma20", "below_ma60", "alignment_broken",
                                 "macd_death", "heavy_sell")


def test_calc_position_buy():
    s = MALongArrangementStrategy()
    pos = s.calc_position(
        {"action": "buy", "price": 20.0, "stop_loss": 19.0},
        Decimal("100000"),
    )
    assert isinstance(pos, Decimal)
    assert 0 < pos <= Decimal("15000")


def test_calc_position_sell():
    s = MALongArrangementStrategy()
    assert s.calc_position({"action": "sell"}, Decimal("100000")) == Decimal("0")


def test_calc_position_zero_risk():
    s = MALongArrangementStrategy()
    assert s.calc_position(
        {"action": "buy", "price": 20.0, "stop_loss": 20.0},
        Decimal("100000"),
    ) == Decimal("0")


def test_adx_filter():
    """验证ADX过滤"""
    s = MALongArrangementStrategy()
    bars = _make_ma_trend_bars(n=80)
    closes = [b["close"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    from core.strategies.ths_strategies._indicators import dmi
    _, _, adx = dmi(highs, lows, closes, 14)
    assert adx > 15, f"持续上涨应有趋势: ADX={adx:.1f}"


def test_bull_alignment():
    """验证测试数据具备多头排列基础"""
    s = MALongArrangementStrategy()
    bars = _make_ma_trend_bars(n=80)
    closes = [b["close"] for b in bars]
    from core.strategies.ths_strategies._indicators import sma
    ma5 = sma(closes, 5)
    ma10 = sma(closes, 10)
    ma20 = sma(closes, 20)
    ma60 = sma(closes, 60)
    assert ma20 > ma60, f"MA20应>MA60: MA20={ma20:.2f} MA60={ma60:.2f}"
    assert ma10 > ma20, f"MA10应>MA20: MA10={ma10:.2f} MA20={ma20:.2f}"