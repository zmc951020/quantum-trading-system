"""龙虎榜跟庄策略测试"""
from decimal import Decimal
import sys
sys.path.insert(0, r"D:\Gupiao\升级vscode\QS_Robot")
from core.strategies.ths_strategies.14_strategies.04_dragon_list_follow import DragonListFollowStrategy


def test_metadata():
    s = DragonListFollowStrategy()
    assert s.NAME == "龙虎榜跟庄"


def test_param_space():
    s = DragonListFollowStrategy()
    assert "institutional_buy_pct" in s.get_param_space()
    assert "pullback_days" in s.get_param_space()


def test_validate_params():
    s = DragonListFollowStrategy()
    assert s.validate_params({"institutional_buy_pct": 30, "pullback_days": 3}) is True
    assert s.validate_params({"institutional_buy_pct": 200, "pullback_days": 3}) is False


def test_buy_on_institutional():
    s = DragonListFollowStrategy()
    bars = [
        {"date": f"2026-01-{i:02d}", "close": 10 + (5 - i) * 0.2 if i > 1 else 11,
         "high": 11, "low": 9.8, "open": 10, "volume": 1000000,
         "dragon_list": {"institutional_net_buy": 50000000} if i == 1 else None}
        for i in range(1, 8)
    ]
    sig = s.generate_signal(bars, {"institutional_buy_pct": 30, "pullback_days": 3})
    assert sig is None or sig["action"] == "buy"


def test_calc_position_decimal():
    s = DragonListFollowStrategy()
    pos = s.calc_position({"action": "buy"}, Decimal("100000"))
    assert isinstance(pos, Decimal)
    assert pos > 0
