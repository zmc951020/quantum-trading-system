"""战法11：智能画线形态识别（锤子线）

来源：同花顺金融大师·高阶战法
逻辑：下跌趋势末端 + 锤子线（下影线≥2倍实体）+ 放量 + 关键支撑位
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import sma


class KlinePatternRecognitionStrategy(THSBaseStrategy):
    NAME = "智能画线形态识别"
    CATEGORY = "ths_advanced"
    RISK_LEVEL = "中"
    SHADOW_RATIO_RANGE = (1.5, 3.0)

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 25:
            return None
        shadow_ratio_min = params.get("shadow_ratio", 2)
        last = bars[-1]
        body = abs(last["close"] - last["open"])
        lower_shadow = min(last["open"], last["close"]) - last["low"]
        upper_shadow = last["high"] - max(last["open"], last["close"])
        is_hammer = body > 0 and lower_shadow >= body * shadow_ratio_min and upper_shadow < body * 0.3
        closes = [b["close"] for b in bars]
        ma20 = sma(closes, 20)
        downtrend_end = last["close"] < ma20 and all(bars[i]["close"] < bars[i - 1]["close"] * 1.02 for i in range(-5, 0))
        vols = [b["volume"] for b in bars]
        vol_surge = last["volume"] > sma(vols, 20) * 1.2
        at_support = last["low"] <= ma20 * 1.02
        if is_hammer and downtrend_end and vol_surge and at_support:
            return {
                "action": "buy",
                "price": last["close"],
                "stop_loss": round(last["low"], 3),
                "take_profit": round(last["close"] * 1.08, 3),
                "body": round(body, 3),
                "lower_shadow": round(lower_shadow, 3),
            }
        return None

    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        if signal.get("action") != "buy":
            return Decimal("0")
        return (capital * Decimal("0.10")).quantize(Decimal("0.01"))

    def get_param_space(self) -> dict[str, tuple]:
        return {"shadow_ratio": self.SHADOW_RATIO_RANGE}

    def validate_params(self, params: dict) -> bool:
        s = params.get("shadow_ratio", 2)
        return self.SHADOW_RATIO_RANGE[0] <= s <= self.SHADOW_RATIO_RANGE[1]
