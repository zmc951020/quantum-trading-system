"""策略09：BOLL轨道上轨顺势突破战法

来源：同花顺金融大师·策略战法
逻辑：中轨向上 + 股价站上上轨 + 开口放大 + 放量突破
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import boll, sma


class BollUpperBreakoutStrategy(THSBaseStrategy):
    NAME = "BOLL上轨突破"
    ID = "09_boll_upper_breakout"
    RISK_LEVEL = "中"
    PERIOD_RANGE = (15, 30)
    STD_RANGE = (1.5, 2.5)
    VOL_RATIO_RANGE = (1.2, 2.0)

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        period = params.get("boll_period", 20)
        std = params.get("boll_std", 2)
        vol_ratio = params.get("vol_ratio", 1.5)
        if len(bars) < period + 5:
            return None
        closes = [b["close"] for b in bars]
        vols = [b["volume"] for b in bars]
        upper, mid, lower = boll(closes, period, std)
        upper_p, mid_p, lower_p = boll(closes[:-1], period, std)
        mid_up = mid > mid_p
        width_now = upper - lower
        width_prev = upper_p - lower_p
        widening = width_now > width_prev
        last = bars[-1]
        above_upper = last["close"] > upper
        vol_avg = sum(vols[-5:-1]) / 4
        vol_ok = last["volume"] > vol_avg * vol_ratio
        if mid_up and above_upper and widening and vol_ok:
            return {
                "action": "buy",
                "price": last["close"],
                "stop_loss": round(mid * 0.98, 3),
                "take_profit": round(last["close"] * 1.10, 3),
                "upper": round(upper, 3),
                "mid": round(mid, 3),
                "lower": round(lower, 3),
            }
        return None

    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        if signal.get("action") != "buy":
            return Decimal("0")
        return (capital * Decimal("0.10")).quantize(Decimal("0.01"))

    def get_param_space(self) -> dict[str, tuple]:
        return {
            "boll_period": self.PERIOD_RANGE,
            "boll_std": self.STD_RANGE,
            "vol_ratio": self.VOL_RATIO_RANGE,
        }

    def validate_params(self, params: dict) -> bool:
        p = params.get("boll_period", 20)
        s = params.get("boll_std", 2)
        v = params.get("vol_ratio", 1.5)
        if not (self.PERIOD_RANGE[0] <= p <= self.PERIOD_RANGE[1]):
            return False
        if not (self.STD_RANGE[0] <= s <= self.STD_RANGE[1]):
            return False
        if not (self.VOL_RATIO_RANGE[0] <= v <= self.VOL_RATIO_RANGE[1]):
            return False
        return True
