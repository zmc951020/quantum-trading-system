"""14策略统一验证脚本

验证所有 14 个同花顺策略的：
1. 类属性完整性（NAME/CATEGORY/SOURCE/RISK_LEVEL）
2. 四接口实现（generate_signal/calc_position/get_param_space/validate_params）
3. 参数校验逻辑
4. 信号生成（模拟K线数据）
5. 仓位计算（Decimal精度）
"""
import importlib.util
import sys
import random
from pathlib import Path
from decimal import Decimal

BASE = Path(__file__).parent / "core" / "strategies" / "ths_strategies" / "14_strategies"

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


def load_strategy(file_name: str, class_name: str):
    spec = importlib.util.spec_from_file_location(file_name.replace(".py", ""), BASE / file_name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, class_name)


def gen_bars(n: int, trend: str = "up") -> list[dict]:
    bars = []
    price = 10.0
    for i in range(n):
        if trend == "up":
            change = random.uniform(-0.01, 0.025)
        elif trend == "down":
            change = random.uniform(-0.025, 0.01)
        else:
            change = random.uniform(-0.015, 0.015)
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


def verify_one(file_name: str, class_name: str) -> tuple[bool, str]:
    try:
        cls = load_strategy(file_name, class_name)
    except Exception as e:
        return False, f"导入失败: {e}"

    issues = []
    for attr in ("NAME", "CATEGORY", "SOURCE", "RISK_LEVEL"):
        if not getattr(cls, attr, ""):
            issues.append(f"{attr}为空")

    inst = cls()
    for method in ("generate_signal", "calc_position", "get_param_space", "validate_params"):
        if not callable(getattr(inst, method, None)):
            issues.append(f"缺少方法{method}")

    ps = inst.get_param_space()
    if not isinstance(ps, dict) or not ps:
        issues.append("参数空间无效")

    default_params = {k: (v[0] + v[1]) // 2 if isinstance(v, tuple) and isinstance(v[0], int) else v[0] for k, v in ps.items()}
    if not inst.validate_params(default_params):
        issues.append("默认参数校验失败")

    bad_params = {k: 99999 for k in ps}
    if inst.validate_params(bad_params):
        issues.append("非法参数未拒绝")

    bars = gen_bars(80, "up")
    try:
        sig = inst.generate_signal(bars, default_params)
    except Exception as e:
        issues.append(f"信号生成异常: {e}")
        sig = None

    if sig is not None:
        if not isinstance(sig, dict):
            issues.append("信号非dict")
        elif sig.get("action") != "buy":
            issues.append("信号action非buy")
        else:
            cap = Decimal("100000")
            pos = inst.calc_position(sig, cap)
            if not isinstance(pos, Decimal) or pos <= 0:
                issues.append(f"仓位计算异常: {pos}")

    return len(issues) == 0, "; ".join(issues) if issues else "全部通过"


def main():
    random.seed(42)
    print("=" * 70)
    print("14策略统一验证")
    print("=" * 70)
    ok_count = 0
    for fname, cname in STRATEGY_MAP.items():
        ok, msg = verify_one(fname, cname)
        flag = "✅" if ok else "❌"
        print(f"{flag} [{fname:<40}] {msg}")
        if ok:
            ok_count += 1
    print("=" * 70)
    print(f"通过: {ok_count}/14")
    return 0 if ok_count == 14 else 1


if __name__ == "__main__":
    sys.exit(main())
