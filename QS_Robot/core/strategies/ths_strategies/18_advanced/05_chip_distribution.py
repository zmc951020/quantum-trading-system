"""战法05：筹码分布低位单峰密集

来源：同花顺金融大师·高阶战法
逻辑：低位筹码单峰密集，获利盘≥70%，套牢盘≤20%，穿透率高且量小
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import sma


class ChipDistributionStrategy(THSBaseStrategy):
    NAME = "筹码单峰密集"
    CATEGORY = "ths_advanced"
    RISK_LEVEL = "中"
    PROFIT_RATIO_RANGE = (0.6, 0.9)
    TRAP_RATIO_RANGE = (0.1, 0.3)

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 30:
            return None
        profit_min = params.get("profit_ratio_min", 0.7)
        trap_max = params.get("trap_ratio_max", 0.2)
        last = bars[-1]
        chip = last.get("chip_distribution")
        if not chip:
            return None
        profit_ratio = chip.get("profit_ratio", 0)
        trap_ratio = chip.get("trap_ratio", 1)
        concentration = chip.get("concentration", 0)
        closes = [b["close"] for b in bars]
        ma60 = sma(closes, 60) if len(closes) >= 60 else sma(closes, len(closes))
        low_pos = last["close"] < ma60 * 1.05
        penetrate = chip.get("penetration", 0)
        vol_small = last["volume"] < sma([b["volume"] for b in bars], 20) * 0.8
        if profit_ratio >= profit_min and trap_ratio <= trap_max and concentration > 0.7 and low_pos and penetrate > 0 and vol_small:
            return {
                "action": "buy",
                "price": last["close"],
                "stop_loss": round(chip.get("peak_low", last["close"] * 0.95), 3),
                "take_profit": round(last["close"] * 1.20, 3),
                "profit_ratio": round(profit_ratio, 3),
                "trap_ratio": round(trap_ratio, 3),
            }
        return None

    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        if signal.get("action") != "buy":
            return Decimal("0")
        return (capital * Decimal("0.12")).quantize(Decimal("0.01"))

    def get_param_space(self) -> dict[str, tuple]:
        return {"profit_ratio_min": self.PROFIT_RATIO_RANGE, "trap_ratio_max": self.TRAP_RATIO_RANGE}

    def validate_params(self, params: dict) -> bool:
        p = params.get("profit_ratio_min", 0.7)
        t = params.get("trap_ratio_max", 0.2)
        return 0 < p < 1 and 0 < t < 1
