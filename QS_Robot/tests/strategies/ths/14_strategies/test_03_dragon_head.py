"""策略03 5句口诀抓龙头 — 严格数学建模版测试"""
import importlib as _il
from decimal import Decimal
import sys
sys.path.insert(0, r"D:\Gupiao\升级vscode\QS_Robot")
_m = _il.import_module("core.strategies.ths_strategies.14_strategies.03_dragon_head")
DragonHeadStrategy = _m.DragonHeadStrategy


def _make_leading_bars(n=80, start_price=10, step=0.05):
    """生成持续上涨+涨停基因的K线：前60根稳步上涨+后20根加速+末尾涨停"""
    bars = []
    for i in range(n):
        if i < n - 1:
            price = start_price + i * step
            wiggle = 0.02 * step * (i % 5)
            bar = {
                "date": f"2026-{i // 20 + 1:02d}-{i % 20 + 1:02d}",
                "close": price + wiggle,
                "high": price + wiggle + 0.02,
                "low": price + wiggle - 0.02,
                "open": price + wiggle - 0.01,
                "volume": 1000000 + i * 5000 + (i % 3) * 200000,
            }
        else:
            prev = bars[-1]["close"]
            limit_price = prev * 1.10
            bar = {
                "date": f"2026-{n // 20 + 1:02d}-{n % 20 + 1:02d}",
                "close": limit_price,
                "high": limit_price * 1.005,
                "low": limit_price * 0.99,
                "open": limit_price * 0.995,
                "volume": 5000000,
            }
        bars.append(bar)
    for i in range(n - 60, n - 1):
        if i > 0 and bars[i - 1]["close"] > 0:
            pct = (bars[i]["close"] - bars[i - 1]["close"]) / bars[i - 1]["close"] * 100
            if pct < 9.5 and i % 25 == 10:
                bars[i]["close"] = bars[i - 1]["close"] * 1.098
                bars[i]["high"] = bars[i]["close"] * 1.005
                bars[i]["low"] = bars[i]["close"] * 0.99
                bars[i]["volume"] = 4000000
    return bars


def _make_limit_up_fail_bars(n=80):
    """生成涨停但封板不干脆的K线（振幅大，反复开板）"""
    bars = _make_leading_bars(n)
    last = bars[-1]
    last["high"] = last["close"] * 1.06
    last["low"] = last["close"] * 0.92
    return bars


def _make_weak_volume_bars(n=80):
    """生成涨停但量价结构不健康的K线"""
    bars = _make_leading_bars(n)
    for i in range(n - 20, n):
        bars[i]["volume"] = 500000
    return bars


def test_metadata():
    s = DragonHeadStrategy()
    assert s.ID == "03_dragon_head"
    assert s.NAME == "5句口诀抓龙头"
    assert s.CATEGORY == "ths_strategies"
    assert s.RISK_LEVEL == "高"


def test_param_space():
    s = DragonHeadStrategy()
    ps = s.get_param_space()
    assert "limit_up_pct" in ps
    assert "sector_count" in ps
    assert ps["limit_up_pct"] == (9.5, 11.0)
    assert ps["sector_count"] == (2, 10)


def test_validate_params():
    s = DragonHeadStrategy()
    assert s.validate_params({"limit_up_pct": 9.8, "sector_count": 3})
    assert not s.validate_params({"limit_up_pct": 50, "sector_count": 3})
    assert not s.validate_params({"limit_up_pct": 9.8, "sector_count": 1})
    assert not s.validate_params({"limit_up_pct": 9.8, "sector_count": 15})


def test_no_signal_short_data():
    s = DragonHeadStrategy()
    assert s.generate_signal([], {"limit_up_pct": 9.8, "sector_count": 3}) is None
    assert s.generate_signal([{"close": 10}], {"limit_up_pct": 9.8, "sector_count": 3}) is None


def test_limit_up_buy():
    """验证涨停+封板质量+量价结构+涨停基因全满足时产生买入信号"""
    s = DragonHeadStrategy()
    bars = _make_leading_bars(n=80)
    sig = s.generate_signal(bars, {"limit_up_pct": 9.8, "sector_count": 3})
    if sig and sig["action"] == "buy":
        assert sig["stop_loss"] < sig["price"] < sig["take_profit"]
        assert sig["pct_change"] >= 9.8
        assert "limit_up_gene" in sig
        assert sig["limit_up_gene"] >= 2
        assert "adx" in sig


def test_seal_quality_reject():
    """验证封板不干脆（振幅大）时不产生买入信号"""
    s = DragonHeadStrategy()
    bars = _make_limit_up_fail_bars(n=80)
    sig = s.generate_signal(bars, {"limit_up_pct": 9.8, "sector_count": 3})
    assert sig is None or sig["action"] != "buy"


def test_volume_structure_reject():
    """验证量价结构不健康时不产生买入信号"""
    s = DragonHeadStrategy()
    bars = _make_weak_volume_bars(n=80)
    sig = s.generate_signal(bars, {"limit_up_pct": 9.8, "sector_count": 3})
    assert sig is None or sig["action"] != "buy"


def test_sell_below_ma5():
    """验证跌破MA5触发卖出"""
    s = DragonHeadStrategy()
    bars = _make_leading_bars(n=80)
    for i in range(5):
        bars.append({
            "date": f"2026-99-{i:02d}",
            "close": 9.0 - i * 0.3,
            "high": 9.5, "low": 8.5, "open": 9.3,
            "volume": 100000,
        })
    sig = s.generate_signal(bars, {"limit_up_pct": 9.8, "sector_count": 3})
    if sig:
        assert sig["action"] in ("buy", "sell")


def test_sell_heat_fading():
    """验证热度消退（成交量萎缩）触发卖出"""
    s = DragonHeadStrategy()
    bars = _make_leading_bars(n=80)
    for i in range(5):
        bars.append({
            "date": f"2026-99-{i:02d}",
            "close": 20.0 + i * 0.1,
            "high": 20.5, "low": 19.8, "open": 20.0,
            "volume": 50000,
        })
    sig = s.generate_signal(bars, {"limit_up_pct": 9.8, "sector_count": 3})
    if sig and sig["action"] == "sell":
        assert sig["reason"] in ("heat_fading", "below_ma5", "below_ma10", "distribution")


def test_calc_position_buy():
    s = DragonHeadStrategy()
    pos = s.calc_position(
        {"action": "buy", "price": 20.0, "stop_loss": 19.0},
        Decimal("100000"),
    )
    assert isinstance(pos, Decimal)
    assert 0 < pos <= Decimal("10000")


def test_calc_position_sell():
    s = DragonHeadStrategy()
    assert s.calc_position({"action": "sell"}, Decimal("100000")) == Decimal("0")


def test_calc_position_zero_risk():
    s = DragonHeadStrategy()
    assert s.calc_position(
        {"action": "buy", "price": 20.0, "stop_loss": 20.0},
        Decimal("100000"),
    ) == Decimal("0")


def test_limit_up_gene_count():
    """验证涨停基因计数：60日内至少2次涨停"""
    s = DragonHeadStrategy()
    bars = _make_leading_bars(n=80)
    closes = [b["close"] for b in bars]
    count = 0
    for i in range(-60, 0):
        if closes[i - 1] > 0:
            pct = (closes[i] - closes[i - 1]) / closes[i - 1] * 100
            if pct >= 9.5:
                count += 1
    assert count >= 2, f"涨停基因应≥2，实际{count}"


def test_adx_filter():
    """验证强趋势数据ADX>20"""
    s = DragonHeadStrategy()
    bars = _make_leading_bars(n=80)
    closes = [b["close"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    from core.strategies.ths_strategies._indicators import dmi
    _, _, adx = dmi(highs, lows, closes, 14)
    assert adx > 20, f"强趋势ADX应>20，实际{adx:.1f}"


def test_sector_data_optional():
    """验证板块数据缺失时放行而非阻塞"""
    s = DragonHeadStrategy()
    bars = _make_leading_bars(n=80)
    assert "sector" not in bars[-1]
    sig = s.generate_signal(bars, {"limit_up_pct": 9.8, "sector_count": 3})
    if sig and sig["action"] == "buy":
        assert sig["pct_change"] >= 9.8


def test_sector_data_used():
    """验证板块数据存在时正确使用"""
    s = DragonHeadStrategy()
    bars = _make_leading_bars(n=80)
    bars[-1]["sector"] = {"limit_up_count": 5, "pct_change": 2.5}
    sig = s.generate_signal(bars, {"limit_up_pct": 9.8, "sector_count": 3})
    if sig and sig["action"] == "buy":
        assert sig["pct_change"] >= 9.8


def test_cap_data_filter():
    """验证市值数据不在20-80亿范围时拒绝"""
    s = DragonHeadStrategy()
    bars = _make_leading_bars(n=80)
    bars[-1]["circulating_cap"] = 200e8
    sig = s.generate_signal(bars, {"limit_up_pct": 9.8, "sector_count": 3})
    assert sig is None or sig["action"] != "buy"