"""战法16：一阳穿三线战法 — 严格数学建模版

来源：同花顺金融大师·高阶战法
逻辑：一根大阳线同时突破5/10/20日均线 + 当日放量
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import sma, ema


class ThreeLineCrossStrategy(THSBaseStrategy):
    ID = "16_three_line_cross"
    NAME = "一阳穿三线"
    CATEGORY = "ths_advanced"
    SOURCE = "同花顺金融大师"
    RISK_LEVEL = "中"
    BIG_CANDLE_RANGE = (0.015, 0.08)
    VOL_RATIO_RANGE = (1.1, 2.5)
    RISK_PER_TRADE = Decimal("0.02")
    MAX_POSITION = Decimal("0.15")

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 25:
            self._log_data_short(len(bars), 25)
            return None
        big_candle_min = params.get("big_candle_pct", 0.025)
        vol_ratio_min = params.get("vol_ratio", 1.2)
        closes = [b["close"] for b in bars]
        vols = [b["volume"] for b in bars]
        last = bars[-1]
        ctx = self._compute_indicators(closes, vols, last, bars, big_candle_min, vol_ratio_min)
        exit_signal = self._check_exit(ctx, closes, last)
        if exit_signal:
            return exit_signal
        entry_signal = self._check_entry(ctx, last)
        return self._apply_meta_filter(entry_signal, bars)

    def _compute_indicators(self, closes, vols, last, bars, big_candle_min, vol_ratio_min):
        prev = bars[-2]
        ma5 = sma(closes, 5)
        ma10 = sma(closes, 10)
        ma20 = sma(closes, 20)
        body_pct = (last["close"] - last["open"]) / last["open"]
        big_candle = body_pct >= big_candle_min
        prev_below = prev["close"] < ma5 or prev["close"] < ma10 or prev["close"] < ma20
        curr_above = last["close"] > ma5 and last["close"] > ma10 and last["close"] > ma20
        cross_three = prev_below and curr_above
        vol_avg = sma(vols, 20)
        vol_surge = last["volume"] > vol_avg * vol_ratio_min if vol_avg > 0 else False
        dif_series = [fa - sl for fa, sl in zip(ema(closes, 12), ema(closes, 26))]
        dea_series = ema(dif_series, 9) if len(dif_series) >= 9 else dif_series
        dif = dif_series[-1]
        prev_dif = dif_series[-2] if len(dif_series) >= 2 else 0
        dea = dea_series[-1]
        prev_dea = dea_series[-2] if len(dea_series) >= 2 else 0
        return {
            "big_candle": big_candle, "cross_three": cross_three, "vol_surge": vol_surge,
            "body_pct": body_pct, "ma5": ma5, "ma10": ma10, "ma20": ma20, "vol_avg": vol_avg,
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
        if not (ctx["big_candle"] and ctx["cross_three"] and ctx["vol_surge"]):
            conditions = {"big_candle": ctx["big_candle"], "cross_three": ctx["cross_three"],
                          "vol_surge": ctx["vol_surge"]}
            self._log_entry_fail(conditions, f"date={last.get('date','')}")
            return None
        result = {
            "action": "buy", "price": last["close"],
            "stop_loss": round(last["close"] * 0.97, 3),
            "take_profit": round(last["close"] * 1.10, 3),
            "body_pct": round(ctx["body_pct"], 4),
            "ma5": round(ctx["ma5"], 3), "ma10": round(ctx["ma10"], 3), "ma20": round(ctx["ma20"], 3),
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
        return {"big_candle_pct": self.BIG_CANDLE_RANGE, "vol_ratio": self.VOL_RATIO_RANGE}

    def validate_params(self, params: dict) -> bool:
        b = params.get("big_candle_pct", 0.05)
        v = params.get("vol_ratio", 1.5)
        return 0 < b < 0.2 and v > 1