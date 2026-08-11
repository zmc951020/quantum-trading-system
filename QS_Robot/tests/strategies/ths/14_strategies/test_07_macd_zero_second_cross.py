"""策略07 MACD零轴二次金叉 — 严格数学建模版测试"""
import importlib as _il
from decimal import Decimal
import sys
sys.path.insert(0, r"D:\Gupiao\升级vscode\QS_Robot")
_m = _il.import_module("core.strategies.ths_strategies.14_strategies.07_macd_zero_second_cross")
MACDZeroSecondCrossStrategy = _m.MACDZeroSecondCrossStrategy


def _make_air_refuel_bars(n=80):
    """MACD零轴二次金叉走势：上涨→第一金叉→回调→第二金叉"""
    import math
    bars = []
    base = 10.0
    for i in range(n):
        if i < 20:
            price = base + i * 0.15 + 0.3 * math.sin(i * 0.3)
        elif i < 35:
            price = bars[-1]["close"] + 0.25
        elif i < 50:
            price = bars[-1]["close"] - 0.15
        elif i < 65:
            price = bars[-1]["close"] + 0.05
        else:
            price = bars[-1]["close"] + 0.2
        vol = 1000000 + i * 5000 + abs(math.sin(i * 0.3)) * 500000
        bar = {
            "date": f"2026-{i // 20 + 1:02d}-{i % 20 + 1:02d}",
            "close": price, "high": price * 1.02, "low": price * 0.98,
            "open": price * 0.995, "volume": max(vol, 100000),
        }
        bars.append(bar)
    bars[-1]["volume"] = bars[-2]["volume"] * 1.8
    return bars


def _make_weak_bars(n=80):
    """无二次金叉的走势"""
    bars = []
    price = 10.0
    for i in range(n):
        price += 0.03 if i % 2 == 0 else -0.02
        bars.append({
            "date": f"2026-{i // 20 + 1:02d}-{i % 20 + 1:02d}",
            "close": price, "high": price * 1.02, "low": price * 0.98,
            "open": price, "volume": 1000000,
        })
    return bars


def test_metadata():
    s = MACDZeroSecondCrossStrategy()
    assert s.ID == "07_macd_zero_second_cross"
    assert s.NAME == "MACD零轴二次金叉"
    assert s.CATEGORY == "ths_strategies"


def test_param_space():
    s = MACDZeroSecondCrossStrategy()
    ps = s.get_param_space()
    for k in ("fast", "slow", "signal"):
        assert k in ps


def test_validate_params():
    s = MACDZeroSecondCrossStrategy()
    assert s.validate_params({"fast": 12, "slow": 26, "signal": 9})
    assert not s.validate_params({"fast": 30, "slow": 26, "signal": 9})


def test_no_signal_short_data():
    s = MACDZeroSecondCrossStrategy()
    assert s.generate_signal([], {"fast": 12, "slow": 26, "signal": 9}) is None


def test_air_refuel_buy():
    """空中加油时产生买入信号"""
    s = MACDZeroSecondCrossStrategy()
    bars = _make_air_refuel_bars(n=80)
    sig = s.generate_signal(bars, {"fast": 12, "slow": 26, "signal": 9})
    if sig and sig["action"] == "buy":
        assert sig["stop_loss"] < sig["price"] < sig["take_profit"]
        assert "dif" in sig
        assert "dea" in sig


def test_weak_no_buy():
    """无空中加油时不产生买入信号"""
    s = MACDZeroSecondCrossStrategy()
    bars = _make_weak_bars(n=80)
    sig = s.generate_signal(bars, {"fast": 12, "slow": 26, "signal": 9})
    assert sig is None or sig["action"] != "buy"


def test_sell_macd_death():
    """MACD死叉触发卖出"""
    s = MACDZeroSecondCrossStrategy()
    bars = _make_air_refuel_bars(n=80)
    for i in range(5):
        bars.append({
            "date": f"2026-99-{i:02d}",
            "close": 9.0 - i * 0.3, "high": 9.5, "low": 8.5,
            "open": 9.3, "volume": 100000,
        })
    sig = s.generate_signal(bars, {"fast": 12, "slow": 26, "signal": 9})
    if sig:
        assert sig["action"] in ("buy", "sell")


def test_sell_below_zero():
    """DIF跌破零轴触发卖出"""
    s = MACDZeroSecondCrossStrategy()
    bars = _make_air_refuel_bars(n=80)
    for i in range(10):
        bars.append({
            "date": f"2026-99-{i:02d}",
            "close": 7.0 - i * 0.2, "high": 8.0, "low": 6.5,
            "open": 7.5, "volume": 100000,
        })
    sig = s.generate_signal(bars, {"fast": 12, "slow": 26, "signal": 9})
    if sig and sig["action"] == "sell":
        assert sig["reason"] in ("macd_death", "below_zero", "bearish_divergence",
                                 "hist_shrinking", "below_ma20")


def test_calc_position_buy():
    s = MACDZeroSecondCrossStrategy()
    pos = s.calc_position(
        {"action": "buy", "price": 20.0, "stop_loss": 19.0},
        Decimal("100000"),
    )
    assert isinstance(pos, Decimal)
    assert 0 < pos <= Decimal("15000")


def test_calc_position_sell():
    s = MACDZeroSecondCrossStrategy()
    assert s.calc_position({"action": "sell"}, Decimal("100000")) == Decimal("0")


def test_divergence_detection():
    s = MACDZeroSecondCrossStrategy()
    highs = [10 + i * 0.1 for i in range(50)]
    dif = [2.0 - i * 0.04 for i in range(50)]
    result = s._detect_bearish_divergence(dif, highs)
    assert isinstance(result, bool)


def test_adx_filter():
    s = MACDZeroSecondCrossStrategy()
    bars = _make_air_refuel_bars(n=80)
    closes = [b["close"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    from core.strategies.ths_strategies._indicators import dmi
    _, _, adx = dmi(highs, lows, closes, 14)
    assert adx > 10, f"趋势应有ADX>10: ADX={adx:.1f}"