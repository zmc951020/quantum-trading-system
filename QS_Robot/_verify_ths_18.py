"""18高阶战法统一验证脚本

为每个战法构造合适的模拟K线数据（含外部数据字段），验证接口契约。
"""
import importlib.util
import sys
import random
from pathlib import Path
from decimal import Decimal

BASE = Path(__file__).parent / "core" / "strategies" / "ths_strategies" / "18_advanced"

STRATEGY_MAP = {
    "01_dynamic_pool_backtest.py": "DynamicPoolBacktestStrategy",
    "02_volume_price_resonance.py": "VolumePriceResonanceStrategy",
    "03_quant_trend_follow.py": "QuantTrendFollowStrategy",
    "04_iwencai_natural_select.py": "IwencaiNaturalSelectStrategy",
    "05_chip_distribution.py": "ChipDistributionStrategy",
    "06_dragon_tiger_quant_seat.py": "DragonTigerQuantSeatStrategy",
    "07_north_capital_follow.py": "NorthCapitalFollowStrategy",
    "08_volume_ladder.py": "VolumeLadderStrategy",
    "09_market_emotion.py": "MarketEmotionStrategy",
    "10_sector_rotation.py": "SectorRotationStrategy",
    "11_kline_pattern_recognition.py": "KlinePatternRecognitionStrategy",
    "12_alert_state_machine.py": "AlertStateMachineStrategy",
    "13_minute_kline_short.py": "MinuteKlineShortStrategy",
    "14_order_flow_analysis.py": "OrderFlowAnalysisStrategy",
    "15_pyramid_position.py": "PyramidPositionStrategy",
    "16_three_line_cross.py": "ThreeLineCrossStrategy",
    "17_grid_trading.py": "GridTradingStrategy",
    "18_smart_money_tracking.py": "SmartMoneyTrackingStrategy",
}


def load_strategy(file_name: str, class_name: str):
    spec = importlib.util.spec_from_file_location(file_name.replace(".py", ""), BASE / file_name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, class_name)


def gen_bars(n: int, extra_fields: dict | None = None, trend: str = "up") -> list[dict]:
    bars = []
    price = 10.0
    for i in range(n):
        change = random.uniform(-0.01, 0.025) if trend == "up" else random.uniform(-0.015, 0.015)
        open_p = price
        price = max(1.0, price * (1 + change))
        bar = {
            "date": f"2026-01-{i + 1:02d}",
            "open": round(open_p, 3),
            "high": round(price * 1.01, 3),
            "low": round(open_p * 0.99, 3),
            "close": round(price, 3),
            "volume": random.randint(100000, 500000),
        }
        if extra_fields:
            bar.update(extra_fields)
        bars.append(bar)
    return bars


EXTRA_DATA = {
    "01_dynamic_pool_backtest.py": {"is_st": False, "profit_growth": 20, "market_cap": 40},
    "02_volume_price_resonance.py": {"main_net_inflow": 5000000},
    "03_quant_trend_follow.py": {"north_inflow": 15, "dragon_list": {"quant_net_buy": 5000000}},
    "04_iwencai_natural_select.py": {"main_net_inflow": 1000000},
    "05_chip_distribution.py": {"chip_distribution": {"profit_ratio": 0.75, "trap_ratio": 0.15, "concentration": 0.8, "penetration": 0.5, "peak_low": 9.5}},
    "06_dragon_tiger_quant_seat.py": {"dragon_list": {"institutional_net_buy": 50000000, "quant_seat_net_buy": 3000000, "top5_buy_pct": 0.25, "famous_hot_money": True}},
    "07_north_capital_follow.py": {"north_inflow": 15, "sector_concentrated": True, "is_etf": True},
    "09_market_emotion.py": {"market_emotion": {"up_ratio": 0.75, "board_success_rate": 0.55, "face_alert_level": 0.4, "consecutive_boards": 5}},
    "10_sector_rotation.py": {"sector_data": {"strength_rank": 3, "capital_inflow": 10000000, "leader_count": 4, "logic_clear": True}},
    "12_alert_state_machine.py": {"main_net_inflow": 5000000},
    "14_order_flow_analysis.py": {"level2": {"program_pct": 0.25, "bid_big_order": True, "inner_outer_ratio": 1.2}},
    "18_smart_money_tracking.py": {"sandwich_order": True, "big_order_support": True, "ddy": 5, "independent_trend": True},
}


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

    default_params = {k: (v[0] + v[1]) / 2 if isinstance(v, tuple) and isinstance(v[0], float) else ((v[0] + v[1]) // 2 if isinstance(v, tuple) and isinstance(v[0], int) else v[0]) for k, v in ps.items()}
    if not inst.validate_params(default_params):
        issues.append("默认参数校验失败")

    extra = EXTRA_DATA.get(file_name)
    bars = gen_bars(80, extra, "up")
    if file_name == "04_iwencai_natural_select.py":
        default_params["query"] = "MACD金叉且零轴上方"

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
    print("18高阶战法统一验证")
    print("=" * 70)
    ok_count = 0
    for fname, cname in STRATEGY_MAP.items():
        ok, msg = verify_one(fname, cname)
        flag = "✅" if ok else "❌"
        print(f"{flag} [{fname:<45}] {msg}")
        if ok:
            ok_count += 1
    print("=" * 70)
    print(f"通过: {ok_count}/18")
    return 0 if ok_count == 18 else 1


if __name__ == "__main__":
    sys.exit(main())
