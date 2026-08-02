"""THSBaseStrategy 基类测试"""
from decimal import Decimal
import pytest


def test_base_is_abstract():
    """基类不可直接实例化"""
    from core.strategies.ths_strategies.base import THSBaseStrategy
    with pytest.raises(TypeError):
        THSBaseStrategy()


def test_base_interface_contract():
    """子类必须实现4个接口"""
    from core.strategies.ths_strategies.base import THSBaseStrategy

    class ConcreteStrategy(THSBaseStrategy):
        NAME = "测试策略"
        CATEGORY = "ths_strategies"
        SOURCE = "同花顺"
        RISK_LEVEL = "中"

        def generate_signal(self, bars, params):
            return {"action": "buy", "price": bars[-1]["close"]}

        def calc_position(self, signal, capital):
            return capital * Decimal("0.1")

        def get_param_space(self):
            return {"fast": (5, 30)}

        def validate_params(self, params):
            return 5 <= params.get("fast", 12) <= 30

    s = ConcreteStrategy()
    assert s.NAME == "测试策略"
    assert s.CATEGORY == "ths_strategies"
    sig = s.generate_signal([{"close": 10}], {})
    assert sig["action"] == "buy"
    assert s.calc_position({}, Decimal("100000")) == Decimal("10000")
    assert s.validate_params({"fast": 12}) is True
    assert s.validate_params({"fast": 100}) is False
