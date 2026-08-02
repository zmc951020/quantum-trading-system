"""战法18：主力筹码控盘综合

来源：同花顺金融大师·高阶战法
逻辑：夹板单+大单托底+走势独立+DDY红柱+35-45度匀速上涨+振幅<3%
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import sma


class SmartMoneyTrackingStrategy(THSBaseStrategy):
    NAME = "主力筹码控盘综合"
    CATEGORY = "ths_advanced"
    RISK_LEVEL = "中"
    ANGLE_RANGE = (30, 50)
    AMPLITUDE_MAX_RANGE = (0.02, 0.05)

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 30:
            return None
        angle_min = params.get("angle_min", 35)
        angle_max = params.get("angle_max", 45)
        amp_max = params.get("amplitude_max", 0.03)
        last = bars[-1]
        closes = [b["close"] for b in bars]
        ma10 = sma(closes, 10)
        ma20 = sma(closes, 20)
        recent = closes[-20:]
        if recent[0] <= 0:
            return None
        slope = (recent[-1] - recent[0]) / recent[0] / 20
        angle = slope * 100
        angle_ok = angle_min <= angle * 180 / 3.14159 <= angle_max
        amplitude = (last["high"] - last["low"]) / last["close"]
        amp_ok = amplitude < amp_max
        sandwich = last.get("sandwich_order", False)
        big_support = last.get("big_order_support", False)
        ddy = last.get("ddy", 0)
        ddy_red = ddy > 0
        independent = last.get("independent_trend", False)
        if sandwich and big_support and ddy_red and independent and angle_ok and amp_ok:
            return {
                "action": "buy",
                "price": last["close"],
                "stop_loss": round(ma10 * 0.97, 3),
                "take_profit": round(last["close"] * 1.15, 3),
                "angle": round(angle * 180 / 3.14159, 1),
                "amplitude": round(amplitude, 4),
            }
        return None

    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        if signal.get("action") != "buy":
            return Decimal("0")
        return (capital * Decimal("0.12")).quantize(Decimal("0.01"))

    def get_param_space(self) -> dict[str, tuple]:
        return {"angle_min": self.ANGLE_RANGE, "amplitude_max": self.AMPLITUDE_MAX_RANGE}

    def validate_params(self, params: dict) -> bool:
        a = params.get("angle_min", 35)
        amp = params.get("amplitude_max", 0.03)
        return self.ANGLE_RANGE[0] <= a <= self.ANGLE_RANGE[1] and 0 < amp < 0.1
