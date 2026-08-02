"""策略14：5/10/20/60四线多头共振战法

来源：同花顺金融大师·策略战法
逻辑：四条均线同时向上发散多头排列 + 股价站上所有均线 + 回踩任一均线不破
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import sma


class FourMAResonanceStrategy(THSBaseStrategy):
    NAME = "四线多头共振"
    RISK_LEVEL = "中"
    PERIOD_RANGE = (3, 120)

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 65:
            return None
        closes = [b["close"] for b in bars]
        vols = [b["volume"] for b in bars]
        ma5 = sma(closes, 5)
        ma10 = sma(closes, 10)
        ma20 = sma(closes, 20)
        ma60 = sma(closes, 60)
        ma5_p = sma(closes[:-1], 5)
        ma10_p = sma(closes[:-1], 10)
        ma20_p = sma(closes[:-1], 20)
        ma60_p = sma(closes[:-1], 60)
        all_up = ma5 > ma5_p and ma10 > ma10_p and ma20 > ma20_p and ma60 > ma60_p
        aligned = ma5 > ma10 > ma20 > ma60
        last = bars[-1]
        above_all = last["close"] > ma5 and last["close"] > ma10 and last["close"] > ma20 and last["close"] > ma60
        pullback_any = (last["low"] <= ma5 * 1.02 or last["low"] <= ma10 * 1.02
                        or last["low"] <= ma20 * 1.02 or last["low"] <= ma60 * 1.02)
        hold = last["close"] > ma5
        vol_avg = sum(vols[-10:-1]) / 10
        vol_shrink = last["volume"] < vol_avg
        if all_up and aligned and above_all and pullback_any and hold and vol_shrink:
            return {
                "action": "buy",
                "price": last["close"],
                "stop_loss": round(ma20 * 0.97, 3),
                "take_profit": round(last["close"] * 1.15, 3),
                "ma5": round(ma5, 3), "ma10": round(ma10, 3),
                "ma20": round(ma20, 3), "ma60": round(ma60, 3),
            }
        return None

    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        if signal.get("action") != "buy":
            return Decimal("0")
        return (capital * Decimal("0.15")).quantize(Decimal("0.01"))

    def get_param_space(self) -> dict[str, tuple]:
        return {"ma_periods": self.PERIOD_RANGE}

    def validate_params(self, params: dict) -> bool:
        p = params.get("ma_periods", 60)
        lo, hi = self.PERIOD_RANGE
        return lo <= p <= hi
