"""战法12：条件预警状态机 — 严格数学建模版

来源：同花顺金融大师·高阶战法
逻辑：价格突破+成交量放大1.5倍+主力净流入为正，三条件同时满足
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import sma, ema


class AlertStateMachineStrategy(THSBaseStrategy):
    ID = "12_alert_state_machine"
    NAME = "条件预警状态机"
    CATEGORY = "ths_advanced"
    SOURCE = "同花顺金融大师"
    RISK_LEVEL = "中"
    VOL_RATIO_RANGE = (1.2, 2.5)
    CONDITIONS_COUNT_RANGE = (2, 5)
    RISK_PER_TRADE = Decimal("0.02")
    MAX_POSITION = Decimal("0.15")

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 25:
            self._log_data_short(len(bars), 25)
            return None
        vol_ratio_min = params.get("vol_ratio", 1.5)
        closes = [b["close"] for b in bars]
        vols = [b["volume"] for b in bars]
        last = bars[-1]
        ctx = self._compute_indicators(closes, vols, last, vol_ratio_min)
        exit_signal = self._check_exit(ctx, closes, last)
        if exit_signal:
            return exit_signal
        return self._check_entry(ctx, last)

    def _compute_indicators(self, closes, vols, last, vol_ratio_min):
        ma20 = sma(closes, 20)
        price_breakout = last["close"] > ma20 * 1.02
        vol_avg = sma(vols, 20)
        vol_surge = last["volume"] > vol_avg * vol_ratio_min if vol_avg > 0 else False
        main_inflow = last.get("main_net_inflow", 0) > 0
        conditions_met = sum([price_breakout, vol_surge, main_inflow])
        dif_series = [fa - sl for fa, sl in zip(ema(closes, 12), ema(closes, 26))]
        dea_series = ema(dif_series, 9) if len(dif_series) >= 9 else dif_series
        dif = dif_series[-1]
        prev_dif = dif_series[-2] if len(dif_series) >= 2 else 0
        dea = dea_series[-1]
        prev_dea = dea_series[-2] if len(dea_series) >= 2 else 0
        return {
            "price_breakout": price_breakout, "vol_surge": vol_surge,
            "main_inflow": main_inflow, "conditions_met": conditions_met,
            "ma20": ma20, "vol_avg": vol_avg,
            "dif": dif, "prev_dif": prev_dif, "dea": dea, "prev_dea": prev_dea,
        }

    def _check_exit(self, ctx, closes, last):
        if last["close"] < ctx["ma20"] * 0.97:
            result = {"action": "sell", "price": last["close"], "reason": "below_ma20"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if ctx["prev_dif"] >= ctx["prev_dea"] and ctx["dif"] < ctx["dea"]:
            result = {"action": "sell", "price": last["close"], "reason": "macd_death"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if last["volume"] > ctx["vol_avg"] * 2.5 and last["close"] < closes[-2]:
            result = {"action": "sell", "price": last["close"], "reason": "heavy_sell"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        return None

    def _check_entry(self, ctx, last):
        if ctx["conditions_met"] < 3:
            conditions = {"price_breakout": ctx["price_breakout"], "vol_surge": ctx["vol_surge"],
                          "main_inflow": ctx["main_inflow"]}
            self._log_entry_fail(conditions, f"date={last.get('date','')}")
            return None
        result = {
            "action": "buy", "price": last["close"],
            "stop_loss": round(ctx["ma20"] * 0.97, 3),
            "take_profit": round(last["close"] * 1.08, 3),
            "conditions_met": ctx["conditions_met"],
            "price_breakout": ctx["price_breakout"],
            "vol_surge": ctx["vol_surge"], "main_inflow": ctx["main_inflow"],
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
        return {"vol_ratio": self.VOL_RATIO_RANGE, "conditions_count": self.CONDITIONS_COUNT_RANGE}

    def validate_params(self, params: dict) -> bool:
        v = params.get("vol_ratio", 1.5)
        c = params.get("conditions_count", 3)
        return self.VOL_RATIO_RANGE[0] <= v <= self.VOL_RATIO_RANGE[1] and 2 <= c <= 5