"""战法12：条件预警状态机

来源：同花顺金融大师·高阶战法
逻辑：价格突破+成交量放大1.5倍+主力净流入为正，三条件同时满足
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import sma


class AlertStateMachineStrategy(THSBaseStrategy):
    NAME = "条件预警状态机"
    CATEGORY = "ths_advanced"
    RISK_LEVEL = "中"
    VOL_RATIO_RANGE = (1.2, 2.5)
    CONDITIONS_COUNT_RANGE = (2, 5)

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 25:
            return None
        vol_ratio_min = params.get("vol_ratio", 1.5)
        last = bars[-1]
        closes = [b["close"] for b in bars]
        ma20 = sma(closes, 20)
        price_breakout = last["close"] > ma20 * 1.02
        vols = [b["volume"] for b in bars]
        vol_avg = sma(vols, 20)
        vol_surge = last["volume"] > vol_avg * vol_ratio_min if vol_avg > 0 else False
        main_inflow = last.get("main_net_inflow", 0) > 0
        conditions_met = sum([price_breakout, vol_surge, main_inflow])
        if conditions_met >= 3:
            return {
                "action": "buy",
                "price": last["close"],
                "stop_loss": round(ma20 * 0.97, 3),
                "take_profit": round(last["close"] * 1.08, 3),
                "conditions_met": conditions_met,
                "price_breakout": price_breakout,
                "vol_surge": vol_surge,
                "main_inflow": main_inflow,
            }
        return None

    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        if signal.get("action") != "buy":
            return Decimal("0")
        return (capital * Decimal("0.10")).quantize(Decimal("0.01"))

    def get_param_space(self) -> dict[str, tuple]:
        return {"vol_ratio": self.VOL_RATIO_RANGE, "conditions_count": self.CONDITIONS_COUNT_RANGE}

    def validate_params(self, params: dict) -> bool:
        v = params.get("vol_ratio", 1.5)
        c = params.get("conditions_count", 3)
        return self.VOL_RATIO_RANGE[0] <= v <= self.VOL_RATIO_RANGE[1] and 2 <= c <= 5
