"""战法01：动态股池+策略回测闭环 — 严格数学建模版

来源：同花顺金融大师·高阶战法
逻辑：多条件动态过滤（风险排雷+基本面+技术），满足全部条件纳入股池
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import sma, ema, dmi


class DynamicPoolBacktestStrategy(THSBaseStrategy):
    ID = "01_dynamic_pool_backtest"
    NAME = "动态股池回测闭环"
    CATEGORY = "ths_advanced"
    SOURCE = "同花顺金融大师"
    RISK_LEVEL = "中"
    FILTER_COUNT_RANGE = (6, 12)
    RISK_PER_TRADE = Decimal("0.02")
    MAX_POSITION = Decimal("0.15")

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 60:
            self._log_data_short(len(bars), 60)
            return None
        closes = [b["close"] for b in bars]
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]
        vols = [b["volume"] for b in bars]
        last = bars[-1]
        ctx = self._compute_indicators(closes, highs, lows, vols, last, bars)
        exit_signal = self._check_exit(ctx, closes, last)
        if exit_signal:
            return exit_signal
        return self._check_entry(ctx, last)

    def _compute_indicators(self, closes, highs, lows, vols, last, bars):
        ma20 = sma(closes, 20)
        ma60 = sma(closes, 60)
        not_st = last.get("is_st", False) is False
        listed_ok = len(bars) >= 250
        ma_bullish = ma20 > ma60 and last["close"] > ma20
        vol_stable = last["volume"] > sma(vols, 20) * 0.8
        profit_ok = last.get("profit_growth", 0) > 0
        cap_ok = 20 <= last.get("market_cap", 30) <= 80
        filters_passed = sum([not_st, listed_ok, ma_bullish, vol_stable, profit_ok, cap_ok])
        _, _, adx = dmi(highs, lows, closes, 14)
        dif_series = [fa - sl for fa, sl in zip(ema(closes, 12), ema(closes, 26))]
        dea_series = ema(dif_series, 9) if len(dif_series) >= 9 else dif_series
        dif = dif_series[-1]
        prev_dif = dif_series[-2] if len(dif_series) >= 2 else 0
        dea = dea_series[-1]
        prev_dea = dea_series[-2] if len(dea_series) >= 2 else 0
        return {
            "ma20": ma20, "ma60": ma60, "filters_passed": filters_passed,
            "adx": adx, "dif": dif, "prev_dif": prev_dif, "dea": dea, "prev_dea": prev_dea,
            "vol_ma20": sma(vols, 20),
            "not_st": not_st, "listed_ok": listed_ok, "ma_bullish": ma_bullish,
            "vol_stable": vol_stable, "profit_ok": profit_ok, "cap_ok": cap_ok,
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
        if last["volume"] > ctx["vol_ma20"] * 2.5 and last["close"] < closes[-2]:
            result = {"action": "sell", "price": last["close"], "reason": "heavy_sell"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        return None

    def _check_entry(self, ctx, last):
        if ctx["filters_passed"] < 6:
            conditions = {"not_st": ctx["not_st"], "listed_ok": ctx["listed_ok"],
                          "ma_bullish": ctx["ma_bullish"], "vol_stable": ctx["vol_stable"],
                          "profit_ok": ctx["profit_ok"], "cap_ok": ctx["cap_ok"]}
            self._log_entry_fail(conditions, f"date={last.get('date','')}")
            return None
        result = {
            "action": "buy", "price": last["close"],
            "stop_loss": round(ctx["ma20"] * 0.95, 3),
            "take_profit": round(last["close"] * 1.15, 3),
            "filters_passed": ctx["filters_passed"],
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
        return {"filter_count": self.FILTER_COUNT_RANGE}

    def validate_params(self, params: dict) -> bool:
        f = params.get("filter_count", 8)
        lo, hi = self.FILTER_COUNT_RANGE
        return lo <= f <= hi