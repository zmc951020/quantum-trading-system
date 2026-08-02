"""同花顺策略测试共享 fixtures"""
from decimal import Decimal
import pytest


@pytest.fixture
def sample_bars():
    """样例K线数据（30天上涨趋势）"""
    return [
        {"date": f"2026-01-{i:02d}", "open": 10 + i * 0.1, "high": 10.5 + i * 0.1,
         "low": 9.8 + i * 0.1, "close": 10.2 + i * 0.1, "volume": 1000000 + i * 10000}
        for i in range(1, 31)
    ]


@pytest.fixture
def sample_capital():
    return Decimal("100000")


@pytest.fixture
def falling_bars():
    """下跌趋势K线数据"""
    return [
        {"date": f"2026-01-{i:02d}", "open": 20 - i * 0.2, "high": 19.5 - i * 0.2,
         "low": 18.8 - i * 0.2, "close": 19.2 - i * 0.2, "volume": 800000}
        for i in range(1, 31)
    ]
