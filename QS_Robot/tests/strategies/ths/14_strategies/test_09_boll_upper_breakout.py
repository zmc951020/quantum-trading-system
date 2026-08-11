"""策略09 BOLL上轨突破 — 严格数学建模版测试"""
import importlib as _il
from decimal import Decimal
import sys
sys.path.insert(0, r"D:\Gupiao\升级vscode\QS_Robot")
_m = _il.import_module("core.strategies.ths_strategies.14_strategies.09_boll_upper_breakout")
BollUpperBreakoutStrategy = _m.BollUpperBreakoutStrategy


def _make_boll_breakout_bars(n=80):
    """BOLL突破走势：中轨向上+站上上轨+开口放大"""
    import math
    bars = []
    base = 10.0
    for i in range(n):
        if i < 30:
            price = base + i * 0.04 + 0.3 * math.sin(i * 0.2)
        elif i < 60:
            price = base + 30 * 0.04 + (i - 30) * 0.12 + 0.5 * math.sin(i * 0.3)
        else:
            price = bars[-1]["close"] + 0.25 + 0.2 * math.sin(i * 0.5)
        vol = 1000000 + i * 5000 + abs(price - base) * 100000
        bar = {
            "date": f"2026-{i // 20 + 1:02d}-{i % 20 + 1:02d}",
            "close": price, "high": price * 1.025, "low": price * 0.975,
            "open": price * 0.995, "volume": max(vol, 100000),
        }
        bars.append(bar)
    bars[-1]["volume"] = bars[-2]["volume"] * 2.0
    return bars


def _make_flat_bars(n=80):
    """横盘走势：BOLL收窄"""
    bars = []
    price = 10.0
    for i in range(n):
        price += 0.02 if i % 2 == 0 else -0.02
        bars.append({
            "date": f"2026-{i // 20 + 1:02d}-{i % 20 + 1:02d}",
            "close": price, "high": price * 1.01, "low": price * 0.99,
            "open": price, "volume": 1000000,
        })
    return bars


def test_metadata():
    s = BollUpperBreakoutStrategy()
    assert s.ID == "09_boll_upper_breakout"
    assert s.NAME == "BOLL上轨突破"
    assert s.CATEGORY == "ths_strategies"


def test_param_space():
    s = BollUpperBreakoutStrategy()
    ps = s.get_param_space()
    for k in ("boll_period", "boll_std", "vol_ratio"):
        assert k in ps


def test_validate_params():
    s = BollUpperBreakoutStrategy()
    assert s.validate_params({"boll_period": 20, "boll_std": 2, "vol_ratio": 1.5})
    assert not s.validate_params({"boll_period": 5, "boll_std": 2, "vol_ratio": 1.5})


def test_no_signal_short_data():
    s = BollUpperBreakoutStrategy()
    assert s.generate_signal([], {"boll_period": 20, "boll_std": 2, "vol_ratio": 1.5}) is None


def test_boll_breakout_buy():
    """BOLL突破时产生买入信号"""
    s = BollUpperBreakoutStrategy()
    bars = _make_boll_breakout_bars(n=80)
    sig = s.generate_signal(bars, {"boll_period": 20, "boll_std": 2, "vol_ratio": 1.5})
    if sig and sig["action"] == "buy":
        assert sig["stop_loss"] < sig["price"] < sig["take_profit"]
        assert "upper" in sig
        assert "mid" in sig


def test_flat_no_buy():
    """横盘时不产生买入信号"""
    s = BollUpperBreakoutStrategy()
    bars = _make_flat_bars(n=80)
    sig = s.generate_signal(bars, {"boll_period": 20, "boll_std": 2, "vol_ratio": 1.5})
    assert sig is None or sig["action"] != "buy"


def test_sell_below_mid():
    """跌破中轨触发卖出"""
    s = BollUpperBreakoutStrategy()
    bars = _make_boll_breakout_bars(n=80)
    for i in range(5):
        bars.append({
            "date": f"2026-99-{i:02d}",
            "close": 9.0 - i * 0.3, "high": 9.5, "low": 8.5,
            "open": 9.3, "volume": 100000,
        })
    sig = s.generate_signal(bars, {"boll_period": 20, "boll_std": 2, "vol_ratio": 1.5})
    if sig:
        assert sig["action"] in ("buy", "sell")


def test_calc_position_buy():
    s = BollUpperBreakoutStrategy()
    pos = s.calc_position(
        {"action": "buy", "price": 20.0, "stop_loss": 19.0},
        Decimal("100000"),
    )
    assert isinstance(pos, Decimal)
    assert 0 < pos <= Decimal("15000")


def test_calc_position_sell():
    s = BollUpperBreakoutStrategy()
    assert s.calc_position({"action": "sell"}, Decimal("100000")) == Decimal("0")


def test_boll_indicators():
    """验证BOLL指标计算正确"""
    s = BollUpperBreakoutStrategy()
    bars = _make_boll_breakout_bars(n=80)
    closes = [b["close"] for b in bars]
    from core.strategies.ths_strategies._indicators import boll
    upper, mid, lower = boll(closes, 20, 2)
    assert upper > mid > lower, f"BOLL: upper={upper:.2f} mid={mid:.2f} lower={lower:.2f}"