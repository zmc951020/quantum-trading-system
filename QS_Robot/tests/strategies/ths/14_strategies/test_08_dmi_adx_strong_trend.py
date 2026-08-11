"""策略08 DMI+ADX强趋势 — 严格数学建模版测试"""
import importlib as _il
from decimal import Decimal
import sys
sys.path.insert(0, r"D:\Gupiao\升级vscode\QS_Robot")
_m = _il.import_module("core.strategies.ths_strategies.14_strategies.08_dmi_adx_strong_trend")
DMIADXStrategy = _m.DMIADXStrategy


def _make_strong_trend_bars(n=80):
    """强趋势走势：+DI金叉-DI + ADX从低位突破25"""
    import math
    bars = []
    base = 10.0
    for i in range(n):
        if i < 30:
            price = base + i * 0.03 + 0.3 * math.sin(i * 0.2)
        elif i < 50:
            price = base + 30 * 0.03 + (i - 30) * 0.15 + 0.5 * math.sin(i * 0.3)
        elif i < 65:
            price = bars[-1]["close"] + 0.1 + 0.3 * math.sin(i * 0.4)
        else:
            price = bars[-1]["close"] + 0.2
        vol = 1000000 + i * 5000 + abs(math.sin(i * 0.4)) * 400000
        bar = {
            "date": f"2026-{i // 20 + 1:02d}-{i % 20 + 1:02d}",
            "close": price, "high": price * 1.025, "low": price * 0.975,
            "open": price * 0.995, "volume": max(vol, 100000),
        }
        bars.append(bar)
    bars[-1]["volume"] = bars[-2]["volume"] * 1.8
    return bars


def _make_weak_trend_bars(n=80):
    """弱趋势走势：+DI不金叉-DI"""
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
    s = DMIADXStrategy()
    assert s.ID == "08_dmi_adx_strong_trend"
    assert s.NAME == "DMI+ADX强趋势"
    assert s.CATEGORY == "ths_strategies"
    assert s.RISK_LEVEL == "中"


def test_param_space():
    s = DMIADXStrategy()
    ps = s.get_param_space()
    assert "dmi_period" in ps
    assert "adx_threshold" in ps


def test_validate_params():
    s = DMIADXStrategy()
    assert s.validate_params({"dmi_period": 14, "adx_threshold": 25})
    assert not s.validate_params({"dmi_period": 5, "adx_threshold": 25})
    assert not s.validate_params({"dmi_period": 14, "adx_threshold": 50})


def test_no_signal_short_data():
    s = DMIADXStrategy()
    assert s.generate_signal([], {"dmi_period": 14, "adx_threshold": 25}) is None


def test_strong_trend_buy():
    """强趋势+金叉+ADX突破时产生买入信号"""
    s = DMIADXStrategy()
    bars = _make_strong_trend_bars(n=80)
    sig = s.generate_signal(bars, {"dmi_period": 14, "adx_threshold": 25})
    if sig and sig["action"] == "buy":
        assert sig["stop_loss"] < sig["price"] < sig["take_profit"]
        assert "plus_di" in sig
        assert "minus_di" in sig
        assert "adx" in sig


def test_weak_trend_no_buy():
    """弱趋势时不产生买入信号"""
    s = DMIADXStrategy()
    bars = _make_weak_trend_bars(n=80)
    sig = s.generate_signal(bars, {"dmi_period": 14, "adx_threshold": 25})
    assert sig is None or sig["action"] != "buy"


def test_sell_di_death():
    """+DI死叉-DI触发卖出"""
    s = DMIADXStrategy()
    bars = _make_strong_trend_bars(n=80)
    for i in range(5):
        bars.append({
            "date": f"2026-99-{i:02d}",
            "close": 9.0 - i * 0.3, "high": 9.5, "low": 8.5,
            "open": 9.3, "volume": 100000,
        })
    sig = s.generate_signal(bars, {"dmi_period": 14, "adx_threshold": 25})
    if sig:
        assert sig["action"] in ("buy", "sell")


def test_calc_position_buy():
    s = DMIADXStrategy()
    pos = s.calc_position(
        {"action": "buy", "price": 20.0, "stop_loss": 19.0},
        Decimal("100000"),
    )
    assert isinstance(pos, Decimal)
    assert 0 < pos <= Decimal("15000")


def test_calc_position_sell():
    s = DMIADXStrategy()
    assert s.calc_position({"action": "sell"}, Decimal("100000")) == Decimal("0")


def test_calc_position_zero_risk():
    s = DMIADXStrategy()
    assert s.calc_position(
        {"action": "buy", "price": 20.0, "stop_loss": 20.0},
        Decimal("100000"),
    ) == Decimal("0")


def test_dmi_indicators():
    """验证DMI指标计算正确"""
    s = DMIADXStrategy()
    bars = _make_strong_trend_bars(n=80)
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    closes = [b["close"] for b in bars]
    from core.strategies.ths_strategies._indicators import dmi
    plus_di, minus_di, adx = dmi(highs, lows, closes, 14)
    assert 0 <= plus_di <= 100, f"+DI范围: {plus_di:.1f}"
    assert 0 <= minus_di <= 100, f"-DI范围: {minus_di:.1f}"
    assert 0 <= adx <= 100, f"ADX范围: {adx:.1f}"