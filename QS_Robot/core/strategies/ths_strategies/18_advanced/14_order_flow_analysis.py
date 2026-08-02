"""战法14：逐笔成交Level-2分析

来源：同花顺金融大师·高阶战法
逻辑：程序化单<30% + 委买档口大单支撑 + 内外盘差值正常
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy


class OrderFlowAnalysisStrategy(THSBaseStrategy):
    NAME = "Level-2逐笔分析"
    CATEGORY = "ths_advanced"
    RISK_LEVEL = "中"
    PROGRAM_PCT_RANGE = (0.2, 0.4)
    ABANDON_THRESHOLD_RANGE = (0.4, 0.6)

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 3:
            return None
        prog_max = params.get("program_pct_max", 0.3)
        last = bars[-1]
        level2 = last.get("level2")
        if not level2:
            return None
        program_pct = level2.get("program_pct", 1)
        bid_support = level2.get("bid_big_order", False)
        inner_outer = level2.get("inner_outer_ratio", 1)
        normal_diff = 0.5 < inner_outer < 2.0
        if program_pct < prog_max and bid_support and normal_diff:
            return {
                "action": "buy",
                "price": last["close"],
                "stop_loss": round(min(b["low"] for b in bars[-3:]) * 0.98, 3),
                "take_profit": round(last["close"] * 1.08, 3),
                "program_pct": round(program_pct, 3),
            }
        return None

    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        if signal.get("action") != "buy":
            return Decimal("0")
        return (capital * Decimal("0.10")).quantize(Decimal("0.01"))

    def get_param_space(self) -> dict[str, tuple]:
        return {"program_pct_max": self.PROGRAM_PCT_RANGE, "abandon_threshold": self.ABANDON_THRESHOLD_RANGE}

    def validate_params(self, params: dict) -> bool:
        p = params.get("program_pct_max", 0.3)
        a = params.get("abandon_threshold", 0.5)
        return 0 < p < 1 and 0 < a < 1
