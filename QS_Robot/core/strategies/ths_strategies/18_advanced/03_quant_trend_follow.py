"""战法03：跟随量化趋势交易

来源：同花顺金融大师·高阶战法
逻辑：北向半小时净流入>10亿 / 龙虎榜量化席位净买 / 量放50%但价涨1-2%
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy


class QuantTrendFollowStrategy(THSBaseStrategy):
    NAME = "跟随量化趋势"
    CATEGORY = "ths_advanced"
    RISK_LEVEL = "高"
    NORTH_INFLOW_RANGE = (5, 50)
    HOLD_DAYS_RANGE = (1, 3)

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 5:
            return None
        inflow_min = params.get("north_inflow_min", 10)
        last = bars[-1]
        north_inflow = last.get("north_inflow", 0)
        dragon_quant = last.get("dragon_list", {}).get("quant_net_buy", 0)
        vols = [b["volume"] for b in bars[-6:-1]]
        avg_vol = sum(vols) / len(vols) if vols else 1
        vol_surge = last["volume"] > avg_vol * 1.5
        prev = bars[-2]
        pct_change = (last["close"] - prev["close"]) / prev["close"] * 100
        sneaky_buy = vol_surge and 1 <= pct_change <= 2
        if north_inflow > inflow_min or dragon_quant > 0 or sneaky_buy:
            return {
                "action": "buy",
                "price": last["close"],
                "stop_loss": round(last["close"] * 0.98, 3),
                "take_profit": round(last["close"] * 1.03, 3),
                "north_inflow": north_inflow,
                "dragon_quant": dragon_quant,
            }
        return None

    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        if signal.get("action") != "buy":
            return Decimal("0")
        return (capital * Decimal("0.06")).quantize(Decimal("0.01"))

    def get_param_space(self) -> dict[str, tuple]:
        return {"north_inflow_min": self.NORTH_INFLOW_RANGE, "hold_days": self.HOLD_DAYS_RANGE}

    def validate_params(self, params: dict) -> bool:
        n = params.get("north_inflow_min", 10)
        h = params.get("hold_days", 1)
        return self.NORTH_INFLOW_RANGE[0] <= n <= self.NORTH_INFLOW_RANGE[1] and h >= 1
