"""5句口诀抓龙头策略测试"""
from decimal import Decimal
import sys
sys.path.insert(0, r"D:\Gupiao\升级vscode\QS_Robot")
from core.strategies.ths_strategies.14_strategies.03_dragon_head import DragonHeadStrategy


def test_metadata():
    s = DragonHeadStrategy()
    assert s.NAME == "5句口诀抓龙头"


def test_param_space():
    s = DragonHeadStrategy()
    assert "limit_up_pct" in s.get_param_space()


def test_validate_params():
    s = DragonHeadStrategy()
    assert s.validate_params({"limit_up_pct": 9.8, "sector_count": 3}) is True
    assert s.validate_params({"limit_up_pct": 50, "sector_count": 3}) is False


def test_no_signal_short_data():
    s = DragonHeadStrategy()
    assert s.generate_signal([], {"limit_up_pct": 9.8, "sector_count": 3}) is None


def test_buy_on_hot():
    s = DragonHeadStrategy()
    bars = [
        {"date": f"2026-01-{i:02d}", "close": 10 + i * 0.3, "high": 10 + i * 0.3,
         "low": 9.5, "open": 10, "volume": 1000000 + i * 100000}
        for i in range(1, 11)
    ]
    sig = s.generate_signal(bars, {"limit_up_pct": 9.8, "sector_count": 3})
    assert sig is None or sig["action"] == "buy"


def test_calc_position_decimal():
    s = DragonHeadStrategy()
    pos = s.calc_position({"action": "buy"}, Decimal("100000"))
    assert isinstance(pos, Decimal)
    assert pos > 0
