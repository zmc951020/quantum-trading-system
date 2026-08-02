"""战法06：龙虎榜量化专用席位跟庄

来源：同花顺金融大师·高阶战法
逻辑：机构专用席位净买入≥3000万，或知名游资联动，买方前5占比<30%
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy


class DragonTigerQuantSeatStrategy(THSBaseStrategy):
    NAME = "龙虎榜量化席位"
    CATEGORY = "ths_advanced"
    RISK_LEVEL = "高"
    INST_BUY_MIN_RANGE = (10000000, 100000000)
    TOP5_PCT_MAX_RANGE = (0.2, 0.4)

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 3:
            return None
        inst_min = params.get("inst_net_buy_min", 30000000)
        top5_max = params.get("top5_pct_max", 0.3)
        last = bars[-1]
        dl = last.get("dragon_list")
        if not dl:
            return None
        inst_net = dl.get("institutional_net_buy", 0)
        quant_seats = dl.get("quant_seat_net_buy", 0)
        top5_pct = dl.get("top5_buy_pct", 1)
        famous_hot = dl.get("famous_hot_money", False)
        if (inst_net >= inst_min or (quant_seats > 0 and famous_hot)) and top5_pct < top5_max:
            return {
                "action": "buy",
                "price": last["close"],
                "stop_loss": round(last["close"] * 0.98, 3),
                "take_profit": round(last["close"] * 1.05, 3),
                "inst_net_buy": inst_net,
                "quant_seat": quant_seats,
            }
        return None

    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        if signal.get("action") != "buy":
            return Decimal("0")
        return (capital * Decimal("0.06")).quantize(Decimal("0.01"))

    def get_param_space(self) -> dict[str, tuple]:
        return {"inst_net_buy_min": self.INST_BUY_MIN_RANGE, "top5_pct_max": self.TOP5_PCT_MAX_RANGE}

    def validate_params(self, params: dict) -> bool:
        i = params.get("inst_net_buy_min", 30000000)
        t = params.get("top5_pct_max", 0.3)
        return i > 0 and 0 < t < 1
