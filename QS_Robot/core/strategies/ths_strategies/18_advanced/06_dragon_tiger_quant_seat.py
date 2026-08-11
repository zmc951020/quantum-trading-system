"""战法06：龙虎榜量化专用席位跟庄 — 严格数学建模版

来源：同花顺金融大师·高阶战法
逻辑：机构专用席位净买入≥3000万，或知名游资联动，买方前5占比<30%
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import sma


class DragonTigerQuantSeatStrategy(THSBaseStrategy):
    ID = "06_dragon_tiger_quant_seat"
    NAME = "龙虎榜量化席位"
    CATEGORY = "ths_advanced"
    SOURCE = "同花顺金融大师"
    RISK_LEVEL = "高"
    INST_BUY_MIN_RANGE = (10000000, 100000000)
    TOP5_PCT_MAX_RANGE = (0.2, 0.4)
    RISK_PER_TRADE = Decimal("0.015")
    MAX_POSITION = Decimal("0.10")

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 3:
            self._log_data_short(len(bars), 3)
            return None
        inst_min = params.get("inst_net_buy_min", 30000000)
        top5_max = params.get("top5_pct_max", 0.3)
        closes = [b["close"] for b in bars]
        last = bars[-1]
        ctx = self._compute_indicators(last, inst_min, top5_max)
        if ctx is None:
            return None
        exit_signal = self._check_exit(ctx, closes, last)
        if exit_signal:
            return exit_signal
        return self._check_entry(ctx, last)

    def _compute_indicators(self, last, inst_min, top5_max):
        dl = last.get("dragon_list")
        if not dl:
            return None
        inst_net = dl.get("institutional_net_buy", 0)
        quant_seats = dl.get("quant_seat_net_buy", 0)
        top5_pct = dl.get("top5_buy_pct", 1)
        famous_hot = dl.get("famous_hot_money", False)
        return {
            "inst_net": inst_net, "inst_min": inst_min, "quant_seats": quant_seats,
            "top5_pct": top5_pct, "top5_max": top5_max, "famous_hot": famous_hot,
            "inst_ok": inst_net >= inst_min,
            "quant_famous": quant_seats > 0 and famous_hot,
            "top5_ok": top5_pct < top5_max,
        }

    def _check_exit(self, ctx, closes, last):
        if last["close"] < closes[-3] * 0.95:
            result = {"action": "sell", "price": last["close"], "reason": "deep_drawdown"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if last["close"] < last["open"] * 0.97:
            result = {"action": "sell", "price": last["close"], "reason": "intraday_weak"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        return None

    def _check_entry(self, ctx, last):
        if not ((ctx["inst_ok"] or ctx["quant_famous"])
                and ctx["top5_ok"]):
            conditions = {"inst_ok": ctx["inst_ok"], "quant_famous": ctx["quant_famous"],
                          "top5_ok": ctx["top5_ok"]}
            self._log_entry_fail(conditions, f"date={last.get('date','')}")
            return None
        result = {
            "action": "buy", "price": last["close"],
            "stop_loss": round(last["close"] * 0.98, 3),
            "take_profit": round(last["close"] * 1.05, 3),
            "inst_net_buy": ctx["inst_net"], "quant_seat": ctx["quant_seats"],
        }
        self._log_signal("buy", result, f"date={last.get('date','')}")
        return result

    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        if signal.get("action") != "buy":
            return Decimal("0")
        risk_per_share = Decimal(str(signal["price"])) - Decimal(str(signal["stop_loss"]))
        if risk_per_share <= 0:
            return Decimal("0")
        position = (capital * self.RISK_PER_TRADE / risk_per_share).quantize(Decimal("0.01"))
        return min(position, capital * self.MAX_POSITION)

    def get_param_space(self) -> dict[str, tuple]:
        return {"inst_net_buy_min": self.INST_BUY_MIN_RANGE, "top5_pct_max": self.TOP5_PCT_MAX_RANGE}

    def validate_params(self, params: dict) -> bool:
        i = params.get("inst_net_buy_min", 30000000)
        t = params.get("top5_pct_max", 0.3)
        return i > 0 and 0 < t < 1