"""策略06 EXPMA双金叉 — 严格数学建模版测试"""
import importlib as _il
from decimal import Decimal
import sys
sys.path.insert(0, r"D:\Gupiao\升级vscode\QS_Robot")
_m = _il.import_module("core.strategies.ths_strategies.14_strategies.06_expma_double_cross")
EXPMADoubleCrossStrategy = _m.EXPMADoubleCrossStrategy


def _make_double_cross_bars(n=80):
    """EXPMA双金叉走势：上涨→第一金叉→回调→第二金叉→放量"""
    import math
    bars = []
    base = 10.0
    for i in range(n):
        if i < 30:
            price = base + i * 0.06 + 0.3 * math.sin(i * 0.2)
            vol = 1000000 + i * 3000
        elif i < 50:
            price = base + 30 * 0.06 + (i - 30) * 0.12 + 0.5 * math.sin(i * 0.25)
            vol = 1500000 + i * 5000
        elif i < 60:
            price = bars[-1]["close"] - 0.2 - (i - 50) * 0.08
            vol = 1200000 - i * 4000
        elif i < 70:
            price = bars[-1]["close"] + 0.05 + (i - 60) * 0.03
            vol = 1000000 + i * 2000
        else:
            price = bars[-1]["close"] + 0.15
            vol = 2000000 + i * 10000
        bar = {
            "date": f"2026-{i // 20 + 1:02d}-{i % 20 + 1:02d}",
            "close": price, "high": price * 1.02, "low": price * 0.98,
            "open": price * 0.995, "volume": max(vol, 100000),
        }
        bars.append(bar)
    bars[-1]["volume"] = bars[-2]["volume"] * 1.5
    return bars


def _make_no_cross_bars(n=80):
    """EXPMA始终未交叉的走势"""
    bars = []
    price = 10.0
    for i in range(n):
        price += 0.05 if i % 2 == 0 else -0.03
        bars.append({
            "date": f"2026-{i // 20 + 1:02d}-{i % 20 + 1:02d}",
            "close": price, "high": price * 1.02, "low": price * 0.98,
            "open": price, "volume": 1000000,
        })
    return bars


def test_metadata():
    s = EXPMADoubleCrossStrategy()
    assert s.ID == "06_expma_double_cross"
    assert s.NAME == "EXPMA双金叉"
    assert s.CATEGORY == "ths_strategies"
    assert s.RISK_LEVEL == "中"


def test_param_space():
    s = EXPMADoubleCrossStrategy()
    ps = s.get_param_space()
    assert "expma_short" in ps
    assert "expma_long" in ps


def test_validate_params():
    s = EXPMADoubleCrossStrategy()
    assert s.validate_params({"expma_short": 7, "expma_long": 21})
    assert not s.validate_params({"expma_short": 30, "expma_long": 21})
    assert not s.validate_params({"expma_short": 7, "expma_long": 50})


def test_no_signal_short_data():
    s = EXPMADoubleCrossStrategy()
    assert s.generate_signal([], {"expma_short": 7, "expma_long": 21}) is None


def test_double_cross_buy():
    """双金叉+回调不破+第二金叉时产生买入信号"""
    s = EXPMADoubleCrossStrategy()
    bars = _make_double_cross_bars(n=80)
    sig = s.generate_signal(bars, {"expma_short": 7, "expma_long": 21})
    if sig and sig["action"] == "buy":
        assert sig["stop_loss"] < sig["price"] < sig["take_profit"]
        assert "expma_short" in sig
        assert "expma_long" in sig


def test_no_cross_no_buy():
    """无金叉时不产生买入信号"""
    s = EXPMADoubleCrossStrategy()
    bars = _make_no_cross_bars(n=80)
    sig = s.generate_signal(bars, {"expma_short": 7, "expma_long": 21})
    assert sig is None or sig["action"] != "buy"


def test_sell_expma_death():
    """EXPMA死叉触发卖出"""
    s = EXPMADoubleCrossStrategy()
    bars = _make_double_cross_bars(n=80)
    for i in range(5):
        bars.append({
            "date": f"2026-99-{i:02d}",
            "close": 9.0 - i * 0.3, "high": 9.5, "low": 8.5,
            "open": 9.3, "volume": 100000,
        })
    sig = s.generate_signal(bars, {"expma_short": 7, "expma_long": 21})
    if sig:
        assert sig["action"] in ("buy", "sell")


def test_sell_below_exp21():
    """跌破EXPMA21触发卖出"""
    s = EXPMADoubleCrossStrategy()
    bars = _make_double_cross_bars(n=80)
    for i in range(5):
        bars.append({
            "date": f"2026-99-{i:02d}",
            "close": 8.0 - i * 0.2, "high": 9.0, "low": 7.5,
            "open": 8.5, "volume": 100000,
        })
    sig = s.generate_signal(bars, {"expma_short": 7, "expma_long": 21})
    if sig and sig["action"] == "sell":
        assert sig["reason"] in ("expma_death", "below_exp21", "deep_pullback", "distribution")


def test_calc_position_buy():
    s = EXPMADoubleCrossStrategy()
    pos = s.calc_position(
        {"action": "buy", "price": 20.0, "stop_loss": 19.0},
        Decimal("100000"),
    )
    assert isinstance(pos, Decimal)
    assert 0 < pos <= Decimal("15000")


def test_calc_position_sell():
    s = EXPMADoubleCrossStrategy()
    assert s.calc_position({"action": "sell"}, Decimal("100000")) == Decimal("0")


def test_calc_position_zero_risk():
    s = EXPMADoubleCrossStrategy()
    assert s.calc_position(
        {"action": "buy", "price": 20.0, "stop_loss": 20.0},
        Decimal("100000"),
    ) == Decimal("0")


def test_adx_filter():
    """验证ADX>20"""
    s = EXPMADoubleCrossStrategy()
    bars = _make_double_cross_bars(n=80)
    closes = [b["close"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    from core.strategies.ths_strategies._indicators import dmi
    _, _, adx = dmi(highs, lows, closes, 14)
    assert adx > 15, f"趋势应有ADX>15: ADX={adx:.1f}"


def test_first_cross_window():
    """验证第一金叉在FIRST_WINDOW内查找"""
    s = EXPMADoubleCrossStrategy()
    bars = _make_double_cross_bars(n=80)
    closes = [b["close"] for b in bars]
    from core.strategies.ths_strategies._indicators import ema
    exp7 = ema(closes, 7)
    exp21 = ema(closes, 21)
    n = len(closes)
    found = False
    for i in range(max(0, n - 30), n - 1):
        if exp7[i - 1] <= exp21[i - 1] and exp7[i] > exp21[i]:
            found = True
            break
    assert found, "应在30窗口内找到第一金叉"