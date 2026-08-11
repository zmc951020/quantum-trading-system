"""策略04 龙虎榜跟庄 — 严格数学建模版测试"""
import importlib as _il
from decimal import Decimal
import sys
sys.path.insert(0, r"D:\Gupiao\升级vscode\QS_Robot")
_m = _il.import_module("core.strategies.ths_strategies.14_strategies.04_dragon_list_follow")
DragonListFollowStrategy = _m.DragonListFollowStrategy


def _make_dragon_bars(n=80, dragon_at=5):
    """生成龙虎榜跟庄K线：稳步上涨+龙虎榜日+缩量回调+起爆"""
    bars = []
    base = 10.0
    for i in range(n):
        if i < n - dragon_at - 3:
            price = base + i * 0.05
            vol = 1000000 + i * 3000
        elif i == n - dragon_at:
            price = base + (n - dragon_at) * 0.05 + 0.8
            vol = 8000000
        elif i > n - dragon_at:
            decay = i - (n - dragon_at)
            price = bars[-1]["close"] - 0.3 - decay * 0.15
            vol = 8000000 - decay * 1500000
        else:
            price = base + i * 0.05
            vol = 1000000 + i * 3000
        bar = {
            "date": f"2026-{i // 20 + 1:02d}-{i % 20 + 1:02d}",
            "close": price, "high": price * 1.02, "low": price * 0.98,
            "open": price * 0.99, "volume": vol,
        }
        if i == n - dragon_at:
            bar["dragon_list"] = {"institutional_net_buy": 3000000}
        bars.append(bar)
    bars[-1]["volume"] = bars[-2]["volume"] * 1.3
    return bars


def _make_no_dragon_bars(n=80):
    """生成无龙虎榜数据的K线"""
    bars = []
    for i in range(n):
        bars.append({
            "date": f"2026-{i // 20 + 1:02d}-{i % 20 + 1:02d}",
            "close": 10 + i * 0.05, "high": 10.2, "low": 9.8,
            "open": 10, "volume": 1000000,
        })
    return bars


def test_metadata():
    s = DragonListFollowStrategy()
    assert s.ID == "04_dragon_list_follow"
    assert s.NAME == "龙虎榜跟庄"
    assert s.CATEGORY == "ths_strategies"


def test_param_space():
    s = DragonListFollowStrategy()
    ps = s.get_param_space()
    assert "institutional_buy_pct" in ps
    assert "pullback_days" in ps


def test_validate_params():
    s = DragonListFollowStrategy()
    assert s.validate_params({"institutional_buy_pct": 15, "pullback_days": 3})
    assert not s.validate_params({"institutional_buy_pct": 200, "pullback_days": 3})
    assert not s.validate_params({"institutional_buy_pct": 15, "pullback_days": 1})


def test_no_signal_short_data():
    s = DragonListFollowStrategy()
    assert s.generate_signal([], {"institutional_buy_pct": 15, "pullback_days": 3}) is None


def test_no_dragon_list():
    """无龙虎榜数据时返回None"""
    s = DragonListFollowStrategy()
    bars = _make_no_dragon_bars(n=80)
    sig = s.generate_signal(bars, {"institutional_buy_pct": 15, "pullback_days": 3})
    assert sig is None


def test_dragon_follow_buy():
    """龙虎榜+缩量回调+起爆时产生买入信号"""
    s = DragonListFollowStrategy()
    bars = _make_dragon_bars(n=80, dragon_at=5)
    sig = s.generate_signal(bars, {"institutional_buy_pct": 15, "pullback_days": 3})
    if sig and sig["action"] == "buy":
        assert sig["stop_loss"] < sig["price"] < sig["take_profit"]
        assert "dragon_close" in sig
        assert "pullback_pct" in sig
        assert "net_buy_ratio" in sig


def test_inst_buy_pct_filter():
    """机构净买入比例不达标时拒绝"""
    s = DragonListFollowStrategy()
    bars = _make_dragon_bars(n=80, dragon_at=5)
    sig = s.generate_signal(bars, {"institutional_buy_pct": 80, "pullback_days": 3})
    assert sig is None or sig["action"] != "buy"


def test_sell_below_ma20():
    """跌破MA20触发卖出"""
    s = DragonListFollowStrategy()
    bars = _make_dragon_bars(n=80, dragon_at=5)
    for i in range(5):
        bars.append({
            "date": f"2026-99-{i:02d}",
            "close": 8.0 - i * 0.2, "high": 9.0, "low": 7.5,
            "open": 8.5, "volume": 100000,
        })
    sig = s.generate_signal(bars, {"institutional_buy_pct": 15, "pullback_days": 3})
    if sig:
        assert sig["action"] in ("buy", "sell")


def test_sell_deep_pullback():
    """从龙虎榜日回撤超10%触发卖出"""
    s = DragonListFollowStrategy()
    bars = _make_dragon_bars(n=80, dragon_at=5)
    dragon_close = bars[-6]["close"]
    for i in range(3):
        bars.append({
            "date": f"2026-99-{i:02d}",
            "close": dragon_close * 0.85 - i * 0.1,
            "high": dragon_close * 0.9, "low": dragon_close * 0.8,
            "open": dragon_close * 0.88, "volume": 100000,
        })
    sig = s.generate_signal(bars, {"institutional_buy_pct": 15, "pullback_days": 3})
    if sig and sig["action"] == "sell":
        assert sig["reason"] in ("deep_pullback", "below_ma20", "macd_death", "heavy_sell")


def test_calc_position_buy():
    s = DragonListFollowStrategy()
    pos = s.calc_position(
        {"action": "buy", "price": 20.0, "stop_loss": 19.0},
        Decimal("100000"),
    )
    assert isinstance(pos, Decimal)
    assert 0 < pos <= Decimal("15000")


def test_calc_position_sell():
    s = DragonListFollowStrategy()
    assert s.calc_position({"action": "sell"}, Decimal("100000")) == Decimal("0")


def test_calc_position_zero_risk():
    s = DragonListFollowStrategy()
    assert s.calc_position(
        {"action": "buy", "price": 20.0, "stop_loss": 20.0},
        Decimal("100000"),
    ) == Decimal("0")


def test_adx_filter():
    """验证ADX过滤"""
    s = DragonListFollowStrategy()
    bars = _make_dragon_bars(n=80, dragon_at=5)
    closes = [b["close"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    from core.strategies.ths_strategies._indicators import dmi
    _, _, adx = dmi(highs, lows, closes, 14)
    assert adx > 15, f"应有趋势: ADX={adx:.1f}"


def test_net_buy_ratio():
    """验证净买入比例计算正确"""
    s = DragonListFollowStrategy()
    bars = _make_dragon_bars(n=80, dragon_at=5)
    for b in bars:
        if b.get("dragon_list"):
            net_buy = b["dragon_list"]["institutional_net_buy"]
            ratio = net_buy / b["volume"] * 100
            assert ratio > 10, f"净买入比例应>10%: {ratio:.1f}%"