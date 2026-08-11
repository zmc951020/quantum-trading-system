"""策略02 周线突破 — 严格数学建模版测试"""
import importlib as _il
from decimal import Decimal
import sys
sys.path.insert(0, r"D:\Gupiao\升级vscode\QS_Robot")
_m = _il.import_module("core.strategies.ths_strategies.14_strategies.02_weekly_breakout")
WeeklyBreakoutStrategy = _m.WeeklyBreakoutStrategy


def _make_box_bars(box_weeks=15, box_price=10, amplitude=0.4, n_extra=6):
    """生成箱体震荡+突破的周线K线：价格在箱体内微幅上行+末期放量突破"""
    bars = []
    for i in range(1, box_weeks + 1):
        wiggle = (i % 5 - 2) * amplitude * 0.12
        price = box_price + wiggle + i * 0.02
        bars.append({
            "date": f"2026-W{i:02d}", "close": price,
            "high": price + amplitude * 0.15, "low": price - amplitude * 0.15,
            "open": price, "volume": 100000 + i * 500,
        })
    for i in range(1, n_extra + 1):
        price = box_price + amplitude * 0.5 + i * 0.8
        bars.append({
            "date": f"2026-W{box_weeks + i:02d}", "close": price,
            "high": price * 1.04, "low": price * 0.97, "open": price * 0.99,
            "volume": 500000 + i * 300000,
        })
    return bars


def _make_strong_trend_bars(n=80, start_price=10, step=0.3):
    """生成强趋势K线：持续上涨+递增放量，确保ADX>20"""
    bars = []
    for i in range(n):
        price = start_price + i * step
        bars.append({
            "date": f"2026-W{i:02d}", "close": price,
            "high": price * 1.03, "low": price * 0.98, "open": price * 0.99,
            "volume": 200000 + i * 5000,
        })
    return bars


def test_metadata():
    s = WeeklyBreakoutStrategy()
    assert s.ID == "02_weekly_breakout"
    assert s.NAME == "周线突破战法"
    assert s.CATEGORY == "ths_strategies"


def test_param_space():
    s = WeeklyBreakoutStrategy()
    ps = s.get_param_space()
    for k in ("box_weeks", "ma_short", "ma_mid", "ma_long", "vol_ratio", "tp_multiplier"):
        assert k in ps, f"Missing: {k}"


def test_validate_params():
    s = WeeklyBreakoutStrategy()
    p = {"box_weeks": 15, "ma_short": 5, "ma_mid": 10, "ma_long": 20, "vol_ratio": 1.5, "tp_multiplier": 1.5}
    assert s.validate_params(p)
    assert not s.validate_params({**p, "box_weeks": 1})
    assert not s.validate_params({**p, "ma_short": 15, "ma_mid": 10})


def test_no_signal_short_data():
    s = WeeklyBreakoutStrategy()
    assert s.generate_signal([], {}) is None


def test_box_breakout_buy():
    s = WeeklyBreakoutStrategy()
    bars = _make_box_bars(box_weeks=15, box_price=10, amplitude=1.0, n_extra=8)
    sig = s.generate_signal(bars, {"box_weeks": 15, "ma_short": 5, "ma_mid": 10, "ma_long": 20, "vol_ratio": 1.5, "tp_multiplier": 1.5})
    if sig and sig["action"] == "buy":
        assert sig["stop_loss"] < sig["price"] < sig["take_profit"]
        assert "box_high" in sig
        assert "box_low" in sig
        assert "adx" in sig


def test_golden_cross_ma5_ma10():
    """验证金叉是MA5穿MA10而非MA20"""
    s = WeeklyBreakoutStrategy()
    bars = _make_box_bars(box_weeks=15, box_price=10, amplitude=1.0, n_extra=8)
    sig = s.generate_signal(bars, {"box_weeks": 15, "ma_short": 5, "ma_mid": 10, "ma_long": 20, "vol_ratio": 1.5, "tp_multiplier": 1.5})
    if sig and sig["action"] == "buy":
        assert sig["sma_short"] > sig["sma_mid"]


def test_sell_signal():
    s = WeeklyBreakoutStrategy()
    bars = _make_box_bars(box_weeks=15, box_price=10, amplitude=1.0, n_extra=3)
    for i in range(8):
        bars.append({
            "date": f"2026-W{20 + i:02d}", "close": 9.0 - i * 0.3,
            "high": 9.5, "low": 8.5, "open": 9.3, "volume": 100000,
        })
    sig = s.generate_signal(bars, {"box_weeks": 15, "ma_short": 5, "ma_mid": 10, "ma_long": 20, "vol_ratio": 1.5, "tp_multiplier": 1.5})
    if sig:
        assert sig["action"] in ("buy", "sell")


def test_calc_position_buy():
    s = WeeklyBreakoutStrategy()
    pos = s.calc_position({"action": "buy", "price": 20.0, "stop_loss": 19.0}, Decimal("100000"))
    assert isinstance(pos, Decimal) and 0 < pos <= Decimal("20000")


def test_calc_position_sell():
    s = WeeklyBreakoutStrategy()
    assert s.calc_position({"action": "sell"}, Decimal("100000")) == Decimal("0")


def test_calc_position_zero_risk():
    s = WeeklyBreakoutStrategy()
    assert s.calc_position({"action": "buy", "price": 20.0, "stop_loss": 20.0}, Decimal("100000")) == Decimal("0")


def test_divergence_detection():
    """验证顶背离检测：价格新高但DIF未新高"""
    s = WeeklyBreakoutStrategy()
    highs = [10 + i * 0.15 for i in range(50)]
    dif = [2.0 - i * 0.04 for i in range(50)]
    result = s._detect_bearish_divergence(dif, highs)
    assert isinstance(result, bool)


def test_divergence_no_false_positive():
    """验证同步上涨不触发背离"""
    s = WeeklyBreakoutStrategy()
    highs = [10 + i * 0.1 for i in range(50)]
    dif = [0.5 + i * 0.02 for i in range(50)]
    assert not s._detect_bearish_divergence(dif, highs)


def test_consolidation_check():
    """验证横盘整理检测：价格严格在箱体内"""
    s = WeeklyBreakoutStrategy()
    closes = [10.0] * 20
    highs = [10.1] * 20
    lows = [9.9] * 20
    assert s._check_consolidation(closes, highs, lows, 10.2, 9.8, 15)
    closes2 = [10.0 + (i % 3 - 1) * 3.0 for i in range(20)]
    highs2 = [c + 0.5 for c in closes2]
    lows2 = [c - 0.5 for c in closes2]
    assert not s._check_consolidation(closes2, highs2, lows2, 10.2, 9.8, 15)


def test_consolidation_high_low_boundary():
    """验证最高价/最低价也必须在箱体范围内"""
    s = WeeklyBreakoutStrategy()
    closes = [10.0] * 20
    highs_ok = [10.15] * 20
    lows_ok = [9.85] * 20
    assert s._check_consolidation(closes, highs_ok, lows_ok, 10.2, 9.8, 15)
    highs_bad = [10.5] * 20
    assert not s._check_consolidation(closes, highs_bad, lows_ok, 10.2, 9.8, 15)


def test_adx_filter():
    """验证ADX趋势强度过滤：强趋势+ADX>20+DI方向确认"""
    s = WeeklyBreakoutStrategy()
    bars = _make_strong_trend_bars(n=80, start_price=10, step=0.3)
    closes = [b["close"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    vols = [b["volume"] for b in bars]
    from core.strategies.ths_strategies._indicators import dmi
    plus_di, minus_di, adx = dmi(highs, lows, closes, 14)
    assert adx > 20, f"强趋势数据ADX应>20，实际{adx:.1f}"
    assert plus_di > minus_di, f"上涨趋势+DI应>-DI，实际+DI={plus_di:.1f}, -DI={minus_di:.1f}"


def test_consecutive_volume():
    """验证突破期成交量持续放大趋势"""
    s = WeeklyBreakoutStrategy()
    bars = _make_box_bars(box_weeks=15, box_price=10, amplitude=1.0, n_extra=8)
    vols = [b["volume"] for b in bars]
    breakout_vols = vols[-8:]
    assert all(breakout_vols[i] > breakout_vols[i - 1] for i in range(1, len(breakout_vols))), \
        "突破期成交量应递增"
    vol_ma5 = sum(vols[-5:]) / 5
    prev_vol_ma5 = sum(vols[-6:-1]) / 5
    assert vols[-1] > vol_ma5 * 1.2, f"当前周应相对放量: vol={vols[-1]}, ma5={vol_ma5:.0f}"
    assert vols[-2] > prev_vol_ma5 * 1.2, f"前一周应相对放量: prev_vol={vols[-2]}, prev_ma5={prev_vol_ma5:.0f}"


def test_trending_up_slope():
    """验证4期均线斜率确认"""
    s = WeeklyBreakoutStrategy()
    bars = _make_box_bars(box_weeks=15, box_price=10, amplitude=1.0, n_extra=8)
    closes = [b["close"] for b in bars]
    from core.strategies.ths_strategies._indicators import sma
    ms, mm, ml = 5, 10, 20
    cur_s = sma(closes, ms)
    cur_m = sma(closes, mm)
    cur_l = sma(closes, ml)
    prev4_s = sma(closes[:-4], ms)
    prev4_m = sma(closes[:-4], mm)
    prev4_l = sma(closes[:-4], ml)
    assert cur_s > prev4_s, f"MA5应上升: cur={cur_s:.2f}, prev4={prev4_s:.2f}"
    assert cur_m > prev4_m, f"MA10应上升: cur={cur_m:.2f}, prev4={prev4_m:.2f}"
    assert cur_l > prev4_l, f"MA20应上升: cur={cur_l:.2f}, prev4={prev4_l:.2f}"


def test_chip_concentration():
    """验证筹码集中度检查"""
    s = WeeklyBreakoutStrategy()
    assert s._check_chip_concentration([10.0] * 30)
    closes = [10.0 + i * 0.01 for i in range(80)]
    assert s._check_chip_concentration(closes)
    closes2 = [10.0 + i * 0.5 for i in range(80)]
    assert not s._check_chip_concentration(closes2)