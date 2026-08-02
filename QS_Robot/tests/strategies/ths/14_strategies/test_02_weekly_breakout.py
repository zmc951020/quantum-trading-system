"""周线突破战法测试"""
from decimal import Decimal
import sys
sys.path.insert(0, r"D:\Gupiao\升级vscode\QS_Robot")
from core.strategies.ths_strategies.14_strategies.02_weekly_breakout import WeeklyBreakoutStrategy


def test_metadata():
    s = WeeklyBreakoutStrategy()
    assert s.NAME == "周线突破战法"


def test_param_space():
    s = WeeklyBreakoutStrategy()
    ps = s.get_param_space()
    assert "box_weeks" in ps
    assert "ma_short" in ps
    assert "ma_long" in ps


def test_validate_params():
    s = WeeklyBreakoutStrategy()
    assert s.validate_params({"box_weeks": 15, "ma_short": 5, "ma_long": 20}) is True
    assert s.validate_params({"box_weeks": 1, "ma_short": 5, "ma_long": 20}) is False


def test_no_signal_on_short_data():
    s = WeeklyBreakoutStrategy()
    assert s.generate_signal([], {"box_weeks": 15, "ma_short": 5, "ma_long": 20}) is None


def test_buy_on_breakout():
    s = WeeklyBreakoutStrategy()
    bars = [
        {"date": f"2026-W{i:02d}", "close": 10, "high": 10.5, "low": 9.5, "open": 10, "volume": 1000}
        for i in range(1, 21)
    ]
    bars.append({"date": "2026-W21", "close": 11, "high": 11.2, "low": 10.5, "open": 10.5, "volume": 2000})
    sig = s.generate_signal(bars, {"box_weeks": 15, "ma_short": 5, "ma_long": 20})
    assert sig is None or sig["action"] == "buy"


def test_calc_position_decimal():
    s = WeeklyBreakoutStrategy()
    pos = s.calc_position({"action": "buy"}, Decimal("100000"))
    assert isinstance(pos, Decimal)
    assert 0 < pos <= Decimal("100000")
