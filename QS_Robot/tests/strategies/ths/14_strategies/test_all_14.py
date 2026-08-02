"""14策略统一接口测试

验证所有 14 个同花顺策略的：
- 类属性完整性（NAME/CATEGORY/SOURCE/RISK_LEVEL）
- 四接口实现（generate_signal/calc_position/get_param_space/validate_params）
- 参数校验（合法通过+非法拒绝）
- 信号生成（dict 或 None）
- 仓位计算（正 Decimal）
"""
import importlib.util
import random
from decimal import Decimal
from pathlib import Path

import pytest

BASE = Path(__file__).parents[4] / "core" / "strategies" / "ths_strategies" / "14_strategies"

STRATEGY_MAP = {
    "01_macd_wave.py": "MACDWaveStrategy",
    "02_weekly_breakout.py": "WeeklyBreakoutStrategy",
    "03_dragon_head.py": "DragonHeadStrategy",
    "04_dragon_list_follow.py": "DragonListFollowStrategy",
    "05_ma_long_arrangement.py": "MALongArrangementStrategy",
    "06_expma_double_cross.py": "EXPMADoubleCrossStrategy",
    "07_macd_zero_second_cross.py": "MACDZeroSecondCrossStrategy",
    "08_dmi_adx_strong_trend.py": "DMIADXStrategy",
    "09_boll_upper_breakout.py": "BollUpperBreakoutStrategy",
    "10_five_day_low_suck.py": "FiveDayLowSuckStrategy",
    "11_ten_day_wave.py": "TenDayWaveStrategy",
    "12_twenty_day_lifeline.py": "TwentyDayLifelineStrategy",
    "13_sixty_day_bull_bear.py": "SixtyDayBullBearStrategy",
    "14_four_ma_resonance.py": "FourMAResonanceStrategy",
}


def _load(file_name: str, class_name: str):
    spec = importlib.util.spec_from_file_location(file_name.replace(".py", ""), BASE / file_name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, class_name)


def _gen_bars(n: int, trend: str = "up") -> list[dict]:
    random.seed(42)
    bars = []
    price = 10.0
    for i in range(n):
        change = random.uniform(-0.01, 0.025) if trend == "up" else random.uniform(-0.025, 0.01)
        open_p = price
        price = max(1.0, price * (1 + change))
        bars.append({
            "date": f"2026-01-{i + 1:02d}",
            "open": round(open_p, 3),
            "high": round(price * 1.01, 3),
            "low": round(open_p * 0.99, 3),
            "close": round(price, 3),
            "volume": random.randint(100000, 500000),
        })
    return bars


@pytest.fixture(params=list(STRATEGY_MAP.items()))
def strategy_class(request):
    fname, cname = request.param
    return _load(fname, cname)


def test_class_attributes(strategy_class):
    for attr in ("NAME", "CATEGORY", "SOURCE", "RISK_LEVEL"):
        assert getattr(strategy_class, attr, ""), f"{attr} 为空"


def test_interface_methods(strategy_class):
    inst = strategy_class()
    for method in ("generate_signal", "calc_position", "get_param_space", "validate_params"):
        assert callable(getattr(inst, method)), f"缺少方法 {method}"


def test_param_space(strategy_class):
    inst = strategy_class()
    ps = inst.get_param_space()
    assert isinstance(ps, dict) and len(ps) > 0, "参数空间必须非空dict"
    for k, v in ps.items():
        assert isinstance(v, tuple) and len(v) == 2, f"参数 {k} 范围必须是2元tuple"


def test_validate_params(strategy_class):
    inst = strategy_class()
    ps = inst.get_param_space()
    default = {k: (v[0] + v[1]) // 2 if isinstance(v[0], int) else v[0] for k, v in ps.items()}
    assert inst.validate_params(default), "默认参数应通过校验"
    bad = {k: 99999 for k in ps}
    assert not inst.validate_params(bad), "非法参数应被拒绝"


def test_signal_generation(strategy_class):
    inst = strategy_class()
    ps = inst.get_param_space()
    default = {k: (v[0] + v[1]) // 2 if isinstance(v[0], int) else v[0] for k, v in ps.items()}
    bars = _gen_bars(80, "up")
    sig = inst.generate_signal(bars, default)
    if sig is not None:
        assert isinstance(sig, dict), "信号必须是dict或None"
        assert "action" in sig, "信号必须包含action"


def test_position_calc(strategy_class):
    inst = strategy_class()
    ps = inst.get_param_space()
    default = {k: (v[0] + v[1]) // 2 if isinstance(v[0], int) else v[0] for k, v in ps.items()}
    bars = _gen_bars(80, "up")
    sig = inst.generate_signal(bars, default)
    if sig is not None and sig.get("action") == "buy":
        pos = inst.calc_position(sig, Decimal("100000"))
        assert isinstance(pos, Decimal) and pos > 0, "买入仓位必须是正Decimal"


def test_empty_bars_no_crash(strategy_class):
    inst = strategy_class()
    ps = inst.get_param_space()
    default = {k: (v[0] + v[1]) // 2 if isinstance(v[0], int) else v[0] for k, v in ps.items()}
    result = inst.generate_signal([], default)
    assert result is None, "空K线不应崩溃且应返回None"
