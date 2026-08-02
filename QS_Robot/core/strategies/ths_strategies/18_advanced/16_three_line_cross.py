"""战法16：一阳穿三线战法

来源：同花顺金融大师·高阶战法
逻辑：一根大阳线同时突破5/10/20日均线 + 当日放量
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import sma


class ThreeLineCrossStrategy(THSBaseStrategy):
    NAME = "一阳穿三线"
    CATEGORY = "ths_advanced"
    RISK_LEVEL = "中"
    BIG_CANDLE_RANGE = (0.03, 0.08)
    VOL_RATIO_RANGE = (1.2, 2.5)

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 25:
            return None
        big_candle_min = params.get("big_candle_pct", 0.05)
        vol_ratio_min = params.get("vol_ratio", 1.5)
        last = bars[-1]
        prev = bars[-2]
        closes = [b["close"] for b in bars]
        ma5 = sma(closes, 5)
        ma10 = sma(closes, 10)
        ma20 = sma(closes, 20)
        body_pct = (last["close"] - last["open"]) / last["open"]
        big_candle = body_pct >= big_candle_min
        prev_below = prev["close"] < ma5 or prev["close"] < ma10 or prev["close"] < ma20
        curr_above = last["close"] > ma5 and last["close"] > ma10 and last["close"] > ma20
        cross_three = prev_below and curr_above
        vols = [b["volume"] for b in bars]
        vol_avg = sma(vols, 20)
        vol_surge = last["volume"] > vol_avg * vol_ratio_min if vol_avg > 0 else False
        if big_candle and cross_three and vol_surge:
            return {
                "action": "buy",
                "price": last["close"],
                "stop_loss": round(last["open"], 3),
                "take_profit": round(last["close"] * 1.10, 3),
                "body_pct": round(body_pct, 4),
                "ma5": round(ma5, 3), "ma10": round(ma10, 3), "ma20": round(ma20, 3),
            }
        return None

    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        if signal.get("action") != "buy":
            return Decimal("0")
        return (capital * Decimal("0.12")).quantize(Decimal("0.01"))

    def get_param_space(self) -> dict[str, tuple]:
        return {"big_candle_pct": self.BIG_CANDLE_RANGE, "vol_ratio": self.VOL_RATIO_RANGE}

    def validate_params(self, params: dict) -> bool:
        b = params.get("big_candle_pct", 0.05)
        v = params.get("vol_ratio", 1.5)
        return 0 < b < 0.2 and v > 1
