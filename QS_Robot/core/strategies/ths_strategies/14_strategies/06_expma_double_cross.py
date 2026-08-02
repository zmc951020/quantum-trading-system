"""策略06：EXPMA7/21双金叉顺势战法

来源：同花顺金融大师·策略战法
逻辑：7日EXPMA首次上穿21日EXPMA（第一金叉）→ 回调不破21日EXPMA → 再次上穿（第二金叉）
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import ema


class EXPMADoubleCrossStrategy(THSBaseStrategy):
    NAME = "EXPMA双金叉"
    ID = "06_expma_double_cross"
    RISK_LEVEL = "中"
    SHORT_RANGE = (3, 15)
    LONG_RANGE = (15, 40)

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        short = params.get("expma_short", 7)
        long = params.get("expma_long", 21)
        if len(bars) < long + 5:
            return None
        closes = [b["close"] for b in bars]
        exp_short = ema(closes, short)
        exp_long = ema(closes, long)
        prev_diff = exp_short[-2] - exp_long[-2]
        curr_diff = exp_short[-1] - exp_long[-1]
        first_cross_done = any(
            exp_short[i] > exp_long[i] and exp_short[i - 1] <= exp_long[i - 1]
            for i in range(3, len(closes) - 1)
        )
        pullback_hold = min(closes[-3:], key=lambda _: 0) or all(
            closes[i] >= exp_long[len(closes) - 3 + (i - (len(closes) - 3)) - (len(closes) - len(exp_long))] * 0.98
            for i in range(len(closes) - 3, len(closes))
        )
        second_cross = prev_diff <= 0 and curr_diff > 0
        last = bars[-1]
        vol_ok = last["volume"] > sum(b["volume"] for b in bars[-5:-1]) / 4
        if first_cross_done and pullback_hold and second_cross and vol_ok:
            return {
                "action": "buy",
                "price": last["close"],
                "stop_loss": round(exp_long[-1] * 0.98, 3),
                "take_profit": round(last["close"] * 1.08, 3),
                "expma_short": round(exp_short[-1], 3),
                "expma_long": round(exp_long[-1], 3),
            }
        return None

    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        if signal.get("action") != "buy":
            return Decimal("0")
        return (capital * Decimal("0.10")).quantize(Decimal("0.01"))

    def get_param_space(self) -> dict[str, tuple]:
        return {"expma_short": self.SHORT_RANGE, "expma_long": self.LONG_RANGE}

    def validate_params(self, params: dict) -> bool:
        s = params.get("expma_short", 7)
        l = params.get("expma_long", 21)
        if not (self.SHORT_RANGE[0] <= s <= self.SHORT_RANGE[1]):
            return False
        if not (self.LONG_RANGE[0] <= l <= self.LONG_RANGE[1]):
            return False
        return s < l
