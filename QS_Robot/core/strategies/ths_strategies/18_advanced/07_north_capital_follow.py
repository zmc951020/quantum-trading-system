"""战法07：北向资金跟随

来源：同花顺金融大师·高阶战法
逻辑：北向半小时净流入>10亿且集中买某类股，跟买相关ETF
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy


class NorthCapitalFollowStrategy(THSBaseStrategy):
    NAME = "北向资金跟随"
    CATEGORY = "ths_advanced"
    RISK_LEVEL = "低"
    NORTH_INFLOW_RANGE = (5, 50)
    HOLD_DAYS_RANGE = (1, 2)

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 3:
            return None
        inflow_min = params.get("north_inflow_min", 10)
        last = bars[-1]
        north = last.get("north_inflow", 0)
        sector_concentrated = last.get("sector_concentrated", False)
        is_etf = last.get("is_etf", False)
        if north > inflow_min and sector_concentrated:
            return {
                "action": "buy",
                "price": last["close"],
                "stop_loss": round(last["close"] * 0.98, 3),
                "take_profit": round(last["close"] * 1.03, 3),
                "north_inflow": north,
                "is_etf": is_etf,
            }
        return None

    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        if signal.get("action") != "buy":
            return Decimal("0")
        return (capital * Decimal("0.08")).quantize(Decimal("0.01"))

    def get_param_space(self) -> dict[str, tuple]:
        return {"north_inflow_min": self.NORTH_INFLOW_RANGE, "hold_days": self.HOLD_DAYS_RANGE}

    def validate_params(self, params: dict) -> bool:
        n = params.get("north_inflow_min", 10)
        h = params.get("hold_days", 1)
        return self.NORTH_INFLOW_RANGE[0] <= n <= self.NORTH_INFLOW_RANGE[1] and h >= 1
