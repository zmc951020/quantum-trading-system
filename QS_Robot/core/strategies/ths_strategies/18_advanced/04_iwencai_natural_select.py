"""战法04：问财AI自然语言选股 — 严格数学建模版

来源：同花顺金融大师·高阶战法
逻辑：自然语言指令选股，结合资金流和筹码二次验证
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import macd, sma, ema


class IwencaiNaturalSelectStrategy(THSBaseStrategy):
    ID = "04_iwencai_natural_select"
    NAME = "问财AI选股"
    CATEGORY = "ths_advanced"
    SOURCE = "同花顺金融大师"
    RISK_LEVEL = "中"
    RISK_PER_TRADE = Decimal("0.02")
    MAX_POSITION = Decimal("0.15")

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 40:
            self._log_data_short(len(bars), 40)
            return None
        query = params.get("query", "MACD金叉且零轴上方")
        closes = [b["close"] for b in bars]
        last = bars[-1]
        ctx = self._compute_indicators(closes, last, query)
        exit_signal = self._check_exit(ctx, closes, last)
        if exit_signal:
            return exit_signal
        return self._check_entry(ctx, last)

    def _compute_indicators(self, closes, last, query):
        matched = []
        if "MACD金叉" in query or "macd金叉" in query:
            dif, dea, hist, _, _ = macd(closes, 12, 26, 9)
            golden = dif > dea and hist > 0
            zero_ok = dif > 0 if "零轴" in query else True
            matched.append(golden and zero_ok)
        if "5日均线上穿10日" in query:
            matched.append(sma(closes, 5) > sma(closes, 10))
        if "涨停" in query:
            prev = bars[-2] if len(bars) >= 2 else last
            pct = (last["close"] - prev["close"]) / prev["close"] * 100
            matched.append(pct >= 9.5)
        if not matched:
            matched = [True]
        ma20 = sma(closes, 20)
        dif_series = [fa - sl for fa, sl in zip(ema(closes, 12), ema(closes, 26))]
        dea_series = ema(dif_series, 9) if len(dif_series) >= 9 else dif_series
        dif = dif_series[-1]
        prev_dif = dif_series[-2] if len(dif_series) >= 2 else 0
        dea = dea_series[-1]
        prev_dea = dea_series[-2] if len(dea_series) >= 2 else 0
        return {
            "matched": matched, "query": query, "ma20": ma20,
            "main_inflow": last.get("main_net_inflow", 0) >= 0,
            "dif": dif, "prev_dif": prev_dif, "dea": dea, "prev_dea": prev_dea,
            "all_matched": all(matched),
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
        return None

    def _check_entry(self, ctx, last):
        if not (ctx["all_matched"] and ctx["main_inflow"]):
            conditions = {"all_matched": ctx["all_matched"], "main_inflow": ctx["main_inflow"]}
            self._log_entry_fail(conditions, f"date={last.get('date','')}")
            return None
        result = {
            "action": "buy", "price": last["close"],
            "stop_loss": round(ctx["ma20"] * 0.95, 3),
            "take_profit": round(last["close"] * 1.10, 3),
            "query": ctx["query"], "matched_count": len(ctx["matched"]),
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
        return {"min_match": (1, 5)}

    def validate_params(self, params: dict) -> bool:
        m = params.get("min_match", 1)
        return 1 <= m <= 5