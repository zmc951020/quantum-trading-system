"""策略08：DMI+ADX强趋势轧空战法

来源：同花顺金融大师·策略战法
逻辑：+DI上穿-DI金叉，ADX从20以下上行突破25，+DI始终在-DI上方
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import dmi, sma


class DMIADXStrategy(THSBaseStrategy):
    NAME = "DMI+ADX强趋势"
    RISK_LEVEL = "中"
    PERIOD_RANGE = (10, 20)
    ADX_THRESHOLD_RANGE = (20, 30)

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        period = params.get("dmi_period", 14)
        adx_thr = params.get("adx_threshold", 25)
        if len(bars) < period + 5:
            return None
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]
        closes = [b["close"] for b in bars]
        plus_di, minus_di, dx = dmi(highs, lows, closes, period)
        plus_di_p, minus_di_p, _ = dmi(highs[:-1], lows[:-1], closes[:-1], period)
        golden_cross = plus_di_p <= minus_di_p and plus_di > minus_di
        plus_above = plus_di > minus_di
        dx_strong = dx > adx_thr
        ma10 = sma(closes, 10)
        last = bars[-1]
        ma_support = last["close"] > ma10 * 0.97
        if golden_cross and plus_above and dx_strong and ma_support:
            return {
                "action": "buy",
                "price": last["close"],
                "stop_loss": round(ma10 * 0.97, 3),
                "take_profit": round(last["close"] * 1.12, 3),
                "plus_di": round(plus_di, 3),
                "minus_di": round(minus_di, 3),
                "adx": round(dx, 3),
            }
        return None

    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        if signal.get("action") != "buy":
            return Decimal("0")
        return (capital * Decimal("0.12")).quantize(Decimal("0.01"))

    def get_param_space(self) -> dict[str, tuple]:
        return {"dmi_period": self.PERIOD_RANGE, "adx_threshold": self.ADX_THRESHOLD_RANGE}

    def validate_params(self, params: dict) -> bool:
        p = params.get("dmi_period", 14)
        a = params.get("adx_threshold", 25)
        if not (self.PERIOD_RANGE[0] <= p <= self.PERIOD_RANGE[1]):
            return False
        if not (self.ADX_THRESHOLD_RANGE[0] <= a <= self.ADX_THRESHOLD_RANGE[1]):
            return False
        return True
