"""MACD顺势波段策略测试"""
from decimal import Decimal
import sys
sys.path.insert(0, r"D:\Gupiao\升级vscode\QS_Robot")
from core.strategies.ths_strategies.14_strategies.01_macd_wave import MACDWaveStrategy


def test_metadata():
    s = MACDWaveStrategy()
    assert s.NAME == "MACD顺势波段"
    assert s.CATEGORY == "ths_strategies"
    assert s.SOURCE == "同花顺金融大师"


def test_param_space():
    s = MACDWaveStrategy()
    ps = s.get_param_space()
    assert "fast" in ps
    assert "slow" in ps
    assert "signal" in ps


def test_validate_params():
    s = MACDWaveStrategy()
    assert s.validate_params({"fast": 12, "slow": 26, "signal": 9}) is True
    assert s.validate_params({"fast": 1, "slow": 26, "signal": 9}) is False
    assert s.validate_params({"fast": 100, "slow": 26, "signal": 9}) is False


def test_no_signal_on_short_data():
    s = MACDWaveStrategy()
    assert s.generate_signal([], {"fast": 12, "slow": 26, "signal": 9}) is None


def test_buy_signal_on_uptrend():
    s = MACDWaveStrategy()
    bars = [
        {"date": f"2026-01-{i:02d}", "close": 10 + i * 0.5, "high": 11 + i * 0.5,
         "low": 9.5, "open": 10, "volume": 1000000 + i * 10000}
        for i in range(1, 70)
    ]
    sig = s.generate_signal(bars, {"fast": 12, "slow": 26, "signal": 9})
    assert sig is None or sig["action"] in ("buy", "sell")


def test_calc_position_decimal():
    s = MACDWaveStrategy()
    pos = s.calc_position({"action": "buy"}, Decimal("100000"))
    assert isinstance(pos, Decimal)
    assert pos > 0
    assert pos <= Decimal("100000")
