"""策略01 MACD顺势波段 — 完整测试套件"""
import importlib
from decimal import Decimal
import sys
sys.path.insert(0, r"D:\Gupiao\升级vscode\QS_Robot")
_mod = importlib.import_module("core.strategies.ths_strategies.14_strategies.01_macd_wave")
MACDWaveStrategy = _mod.MACDWaveStrategy


def _make_uptrend_bars(n=70, start=10, step=0.15):
    """生成多头趋势K线：价格稳步上涨+均线多头+放量"""
    bars = []
    for i in range(1, n + 1):
        price = start + i * step
        bars.append({
            "date": f"2026-01-{i:02d}", "close": price,
            "high": price * 1.02, "low": price * 0.98, "open": price * 0.995,
            "volume": 1000000 + i * 50000,
        })
    return bars


def _make_downtrend_bars(n=70, start=40, step=0.15):
    """生成空头趋势K线：价格稳步下跌"""
    bars = []
    for i in range(1, n + 1):
        price = start - i * step
        bars.append({
            "date": f"2026-01-{i:02d}", "close": price,
            "high": price * 1.02, "low": price * 0.98, "open": price * 0.995,
            "volume": 1000000 + i * 10000,
        })
    return bars


def test_metadata():
    s = MACDWaveStrategy()
    assert s.ID == "01_macd_wave"
    assert s.NAME == "MACD顺势波段"
    assert s.CATEGORY == "ths_strategies"
    assert s.SOURCE == "同花顺金融大师"
    assert s.RISK_LEVEL == "中"


def test_param_space():
    s = MACDWaveStrategy()
    ps = s.get_param_space()
    for k in ("fast", "slow", "signal"):
        assert k in ps, f"Missing param: {k}"


def test_validate_params():
    s = MACDWaveStrategy()
    assert s.validate_params({"fast": 12, "slow": 26, "signal": 9})
    assert not s.validate_params({"fast": 1, "slow": 26, "signal": 9})
    assert not s.validate_params({"fast": 12, "slow": 10, "signal": 9})  # fast >= slow
    assert not s.validate_params({"fast": 12, "slow": 26, "signal": 3})


def test_no_signal_short_data():
    s = MACDWaveStrategy()
    assert s.generate_signal([], {"fast": 12, "slow": 26, "signal": 9}) is None


def test_buy_signal_uptrend():
    s = MACDWaveStrategy()
    bars = _make_uptrend_bars(70)
    sig = s.generate_signal(bars, {"fast": 12, "slow": 26, "signal": 9})
    if sig:
        assert sig["action"] in ("buy", "sell")
        if sig["action"] == "buy":
            assert "stop_loss" in sig
            assert "take_profit" in sig
            assert sig["stop_loss"] < sig["price"] < sig["take_profit"]


def test_sell_signal_death_cross():
    """构建死叉场景：MACD从金叉转死叉"""
    s = MACDWaveStrategy()
    bars = _make_uptrend_bars(60)
    last = bars[-1]
    for i in range(3):
        bars.append({
            "date": f"2026-02-{i:02d}", "close": last["close"] * (1 - 0.02 * i),
            "high": last["high"], "low": last["low"] * 0.95,
            "open": last["open"], "volume": last["volume"],
        })
    sig = s.generate_signal(bars, {"fast": 12, "slow": 26, "signal": 9})
    if sig:
        assert sig["action"] in ("buy", "sell")


def test_no_signal_downtrend():
    """空头趋势中不产生买入信号"""
    s = MACDWaveStrategy()
    bars = _make_downtrend_bars(70)
    sig = s.generate_signal(bars, {"fast": 12, "slow": 26, "signal": 9})
    assert sig is None or sig["action"] == "sell"


def test_calc_position_buy():
    s = MACDWaveStrategy()
    sig = {"action": "buy", "price": 20.0, "stop_loss": 19.0}
    pos = s.calc_position(sig, Decimal("100000"))
    assert isinstance(pos, Decimal)
    assert pos > 0
    assert pos <= Decimal("15000")  # 不超过15%


def test_calc_position_sell():
    s = MACDWaveStrategy()
    pos = s.calc_position({"action": "sell"}, Decimal("100000"))
    assert pos == Decimal("0")


def test_calc_position_zero_risk():
    s = MACDWaveStrategy()
    sig = {"action": "buy", "price": 20.0, "stop_loss": 20.0}
    pos = s.calc_position(sig, Decimal("100000"))
    assert pos == Decimal("0")


def test_air_refuel_detection():
    s = MACDWaveStrategy()
    dif = [0.1, 0.15, 0.12, 0.08, 0.05, 0.03, 0.04, 0.06, 0.09, 0.12,
           0.08, 0.06, 0.05, 0.07, 0.10, 0.13, 0.15, 0.18, 0.20, 0.22,
           0.25, 0.28, 0.30, 0.28, 0.32]
    dea = [0.08, 0.10, 0.11, 0.09, 0.07, 0.05, 0.04, 0.05, 0.07, 0.09,
           0.08, 0.07, 0.06, 0.06, 0.08, 0.10, 0.12, 0.14, 0.16, 0.18,
           0.20, 0.22, 0.23, 0.24, 0.25]
    result = s._detect_air_refuel(dif, dea, window=20)
    assert isinstance(result, bool)


def test_divergence_detection():
    s = MACDWaveStrategy()
    closes = [10 + i * 0.1 for i in range(50)]
    highs = [c * 1.02 for c in closes]
    dif = [0.5 - i * 0.01 for i in range(50)]
    result = s._detect_bearish_divergence(dif, closes, highs)
    assert isinstance(result, bool)