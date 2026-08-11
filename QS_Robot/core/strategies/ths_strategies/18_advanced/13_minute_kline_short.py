"""战法13：15/30分钟超短战法 — 严格数学建模版

来源：同花顺金融大师·高阶战法
逻辑：15分钟MACD金叉 + 30分钟均线支撑 + 5日线上方运行
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import macd, sma


class MinuteKlineShortStrategy(THSBaseStrategy):
    ID = "13_minute_kline_short"
    NAME = "15/30分钟超短"
    CATEGORY = "ths_advanced"
    SOURCE = "同花顺金融大师"
    RISK_LEVEL = "高"
    FAST_RANGE = (5, 15)
    SLOW_RANGE = (15, 30)
    RISK_PER_TRADE = Decimal("0.01")
    MAX_POSITION = Decimal("0.08")

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 40:
            self._log_data_short(len(bars), 40)
            return None
        fast = params.get("fast", 12)
        slow = params.get("slow", 26)
        closes = [b["close"] for b in bars]
        last = bars[-1]
        ctx = self._compute_indicators(closes, last, fast, slow)
        exit_signal = self._check_exit(ctx, closes, last)
        if exit_signal:
            return exit_signal
        entry_signal = self._check_entry(ctx, last)
        return self._apply_meta_filter(entry_signal, bars)

    def _compute_indicators(self, closes, last, fast, slow):
        dif, dea, hist, _, _ = macd(closes, fast, slow, 9)
        golden_cross = dif > dea and hist > 0
        ma30 = sma(closes, 30)
        ma5 = sma(closes, 5)
        ma30_support = closes[-1] > ma30 * 0.99
        above_ma5 = closes[-1] > ma5
        return {
            "golden_cross": golden_cross, "ma30_support": ma30_support,
            "above_ma5": above_ma5, "dif": dif, "dea": dea, "ma30": ma30, "ma5": ma5,
        }

    def _check_exit(self, ctx, closes, last):
        if last["close"] < ctx["ma5"] * 0.98:
            result = {"action": "sell", "price": last["close"], "reason": "below_ma5"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if last["close"] < ctx["ma30"] * 0.99:
            result = {"action": "sell", "price": last["close"], "reason": "below_ma30"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        return None

    def _check_entry(self, ctx, last):
        if not (ctx["golden_cross"] and ctx["ma30_support"] and ctx["above_ma5"]):
            conditions = {"golden_cross": ctx["golden_cross"], "ma30_support": ctx["ma30_support"],
                          "above_ma5": ctx["above_ma5"]}
            self._log_entry_fail(conditions, f"date={last.get('date','')}")
            return None
        result = {
            "action": "buy", "price": last["close"],
            # 日线节奏适配：3% 止损缓冲（原 0.99=1% 适合分钟级，日线易被洗）
            "stop_loss": round(ctx["ma30"] * 0.97, 3),
            # 日线节奏适配：10% 止盈（原 1.03=3% 适合分钟级，日线需更大空间）
            "take_profit": round(last["close"] * 1.10, 3),
            "dif": round(ctx["dif"], 4), "dea": round(ctx.get("dea", 0), 4),
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
        return {"fast": self.FAST_RANGE, "slow": self.SLOW_RANGE}

    def validate_params(self, params: dict) -> bool:
        f = params.get("fast", 12)
        s = params.get("slow", 26)
        return self.FAST_RANGE[0] <= f <= self.FAST_RANGE[1] and self.SLOW_RANGE[0] <= s <= self.SLOW_RANGE[1] and f < s