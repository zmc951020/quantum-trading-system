"""战法03：跟随量化趋势交易 — 严格数学建模版

来源：同花顺金融大师·高阶战法
逻辑：北向半小时净流入>10亿 / 龙虎榜量化席位净买 / 量放50%但价涨1-2%
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import sma, ema


class QuantTrendFollowStrategy(THSBaseStrategy):
    ID = "03_quant_trend_follow"
    NAME = "跟随量化趋势"
    CATEGORY = "ths_advanced"
    SOURCE = "同花顺金融大师"
    RISK_LEVEL = "高"
    NORTH_INFLOW_RANGE = (5, 50)
    HOLD_DAYS_RANGE = (1, 3)
    RISK_PER_TRADE = Decimal("0.015")
    MAX_POSITION = Decimal("0.10")

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 5:
            self._log_data_short(len(bars), 5)
            return None
        inflow_min = params.get("north_inflow_min", 10)
        closes = [b["close"] for b in bars]
        last = bars[-1]
        ctx = self._compute_indicators(closes, last, bars, inflow_min)
        exit_signal = self._check_exit(ctx, closes, last)
        if exit_signal:
            return exit_signal
        return self._check_entry(ctx, last)

    def _compute_indicators(self, closes, last, bars, inflow_min):
        north_inflow = last.get("north_inflow", 0)
        dragon_quant = last.get("dragon_list", {}).get("quant_net_buy", 0)
        vols = [b["volume"] for b in bars[-6:-1]]
        avg_vol = sum(vols) / len(vols) if vols else 1
        vol_surge = last["volume"] > avg_vol * 1.5
        prev = bars[-2]
        pct_change = (last["close"] - prev["close"]) / prev["close"] * 100
        sneaky_buy = vol_surge and 1 <= pct_change <= 2
        ma5 = sma(closes, 5)
        dif_series = [fa - sl for fa, sl in zip(ema(closes, 12), ema(closes, 26))]
        dea_series = ema(dif_series, 9) if len(dif_series) >= 9 else dif_series
        dif = dif_series[-1]
        prev_dif = dif_series[-2] if len(dif_series) >= 2 else 0
        dea = dea_series[-1]
        prev_dea = dea_series[-2] if len(dea_series) >= 2 else 0
        return {
            "north_inflow": north_inflow, "inflow_min": inflow_min,
            "dragon_quant": dragon_quant, "sneaky_buy": sneaky_buy,
            "ma5": ma5, "dif": dif, "prev_dif": prev_dif, "dea": dea, "prev_dea": prev_dea,
            "north_ok": north_inflow > inflow_min,
            "dragon_ok": dragon_quant > 0,
        }

    def _check_exit(self, ctx, closes, last):
        if last["close"] < ctx["ma5"] * 0.97:
            result = {"action": "sell", "price": last["close"], "reason": "below_ma5"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if ctx["prev_dif"] >= ctx["prev_dea"] and ctx["dif"] < ctx["dea"]:
            result = {"action": "sell", "price": last["close"], "reason": "macd_death"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        return None

    def _check_entry(self, ctx, last):
        if not (ctx["north_ok"] or ctx["dragon_ok"] or ctx["sneaky_buy"]):
            conditions = {"north_ok": ctx["north_ok"], "dragon_ok": ctx["dragon_ok"],
                          "sneaky_buy": ctx["sneaky_buy"]}
            self._log_entry_fail(conditions, f"date={last.get('date','')}")
            return None
        result = {
            "action": "buy", "price": last["close"],
            "stop_loss": round(last["close"] * 0.98, 3),
            "take_profit": round(last["close"] * 1.03, 3),
            "north_inflow": ctx["north_inflow"],
            "dragon_quant": ctx["dragon_quant"],
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
        return {"north_inflow_min": self.NORTH_INFLOW_RANGE, "hold_days": self.HOLD_DAYS_RANGE}

    def validate_params(self, params: dict) -> bool:
        n = params.get("north_inflow_min", 10)
        h = params.get("hold_days", 1)
        return self.NORTH_INFLOW_RANGE[0] <= n <= self.NORTH_INFLOW_RANGE[1] and h >= 1