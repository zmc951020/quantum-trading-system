"""战法11：智能画线形态识别（锤子线） — 严格数学建模版

来源：同花顺金融大师·高阶战法
逻辑：下跌趋势末端 + 锤子线（下影线≥2倍实体）+ 放量 + 关键支撑位
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import sma, ema


class KlinePatternRecognitionStrategy(THSBaseStrategy):
    ID = "11_kline_pattern_recognition"
    NAME = "智能画线形态识别"
    CATEGORY = "ths_advanced"
    SOURCE = "同花顺金融大师"
    RISK_LEVEL = "中"
    SHADOW_RATIO_RANGE = (1.5, 3.0)
    RISK_PER_TRADE = Decimal("0.02")
    MAX_POSITION = Decimal("0.15")

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 25:
            self._log_data_short(len(bars), 25)
            return None
        shadow_ratio_min = params.get("shadow_ratio", 2)
        closes = [b["close"] for b in bars]
        last = bars[-1]
        ctx = self._compute_indicators(closes, last, bars, shadow_ratio_min)
        exit_signal = self._check_exit(ctx, closes, last)
        if exit_signal:
            return exit_signal
        return self._check_entry(ctx, last)

    def _compute_indicators(self, closes, last, bars, shadow_ratio_min):
        body = abs(last["close"] - last["open"])
        lower_shadow = min(last["open"], last["close"]) - last["low"]
        upper_shadow = last["high"] - max(last["open"], last["close"])
        is_hammer = body > 0 and lower_shadow >= body * shadow_ratio_min and upper_shadow < body * 0.3
        ma20 = sma(closes, 20)
        downtrend_end = last["close"] < ma20 and all(
            bars[i]["close"] < bars[i - 1]["close"] * 1.02 for i in range(-5, 0))
        vols = [b["volume"] for b in bars]
        vol_surge = last["volume"] > sma(vols, 20) * 1.2
        at_support = last["low"] <= ma20 * 1.02
        dif_series = [fa - sl for fa, sl in zip(ema(closes, 12), ema(closes, 26))]
        dea_series = ema(dif_series, 9) if len(dif_series) >= 9 else dif_series
        dif = dif_series[-1]
        prev_dif = dif_series[-2] if len(dif_series) >= 2 else 0
        dea = dea_series[-1]
        prev_dea = dea_series[-2] if len(dea_series) >= 2 else 0
        return {
            "is_hammer": is_hammer, "downtrend_end": downtrend_end,
            "vol_surge": vol_surge, "at_support": at_support,
            "body": body, "lower_shadow": lower_shadow, "ma20": ma20,
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
        if last["close"] < last["low"] * 1.002:
            result = {"action": "sell", "price": last["close"], "reason": "break_low"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        return None

    def _check_entry(self, ctx, last):
        if not (ctx["is_hammer"] and ctx["downtrend_end"] and ctx["vol_surge"] and ctx["at_support"]):
            conditions = {"is_hammer": ctx["is_hammer"], "downtrend_end": ctx["downtrend_end"],
                          "vol_surge": ctx["vol_surge"], "at_support": ctx["at_support"]}
            self._log_entry_fail(conditions, f"date={last.get('date','')}")
            return None
        result = {
            "action": "buy", "price": last["close"],
            "stop_loss": round(last["low"], 3),
            "take_profit": round(last["close"] * 1.08, 3),
            "body": round(ctx["body"], 3), "lower_shadow": round(ctx["lower_shadow"], 3),
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
        return {"shadow_ratio": self.SHADOW_RATIO_RANGE}

    def validate_params(self, params: dict) -> bool:
        s = params.get("shadow_ratio", 2)
        return self.SHADOW_RATIO_RANGE[0] <= s <= self.SHADOW_RATIO_RANGE[1]