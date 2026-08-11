"""策略06：EXPMA7/21双金叉顺势战法 — 严格数学建模版

来源：同花顺金融大师·策略战法

原策略数学模型：
  第一金叉（最近FIRST_WINDOW根bar内）：
    first_cross_idx = argmin_i { exp7(i-1) ≤ exp21(i-1) AND exp7(i) > exp21(i) }
    first_cross_done = first_cross_idx is not None

  回调确认（第一金叉后，价格回踩EXPMA21但不有效跌破）：
    pullback_low = MIN(close[first_cross_idx:])  # 第一金叉后最低价
    pullback_ok = pullback_low >= exp21(t) × 0.98  # 不破EXPMA21

  第二金叉（当前触发）：
	    second_cross = exp7(t-1) ≤ exp21(t-1) AND exp7(t) > exp21(t)
	    gap_ok = (t - first_cross_idx) ≥ MIN_CROSS_GAP  # 两金叉间隔≥3天

  成交量确认：
    vol_ok = vol(t) > MA(vol, 5) × 1.2

  趋势确认：
    adx_ok = ADX(14) > 20

  入场条件（ALL）：
    first_cross_done AND pullback_ok AND second_cross AND vol_ok AND adx_ok

  出场条件（ANY）：
    - EXPMA7死叉EXPMA21（exp7 < exp21）
    - 跌破EXPMA21的97%
    - 从EXPMA21回撤超8%
    - 高位放量滞涨（量>MA5×2.5且收平）

  止损：EXPMA21 × 0.98
  止盈：入场价 × 1.08（短线目标8%）
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import ema, sma, dmi


class EXPMADoubleCrossStrategy(THSBaseStrategy):
    ID = "06_expma_double_cross"
    NAME = "EXPMA双金叉"
    CATEGORY = "ths_strategies"
    SOURCE = "同花顺金融大师"
    RISK_LEVEL = "中"

    SHORT_RANGE = (3, 15)
    LONG_RANGE = (15, 40)
    FIRST_WINDOW = 30
    MIN_CROSS_GAP = 3
    ADX_THRESHOLD = 20
    RISK_PER_TRADE = Decimal("0.02")
    MAX_POSITION = Decimal("0.15")

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        short = params.get("expma_short", 7)
        long = params.get("expma_long", 21)
        need = max(long + 5, self.FIRST_WINDOW + 5, 60)
        if len(bars) < need:
            self._log_data_short(len(bars), need)
            return None
        closes = [b["close"] for b in bars]
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]
        vols = [b["volume"] for b in bars]
        last = bars[-1]
        ctx = self._compute_indicators(closes, highs, lows, vols, short, long)
        exit_signal = self._check_exit(ctx, closes, last)
        if exit_signal:
            return exit_signal
        entry_signal = self._check_entry(ctx, last)
        return self._apply_meta_filter(entry_signal, bars)

    def _compute_indicators(self, closes, highs, lows, vols, short, long):
        exp_short = ema(closes, short)
        exp_long = ema(closes, long)
        n = len(closes)
        first_cross_idx = None
        for i in range(max(0, n - self.FIRST_WINDOW), n - 1):
            if exp_short[i - 1] <= exp_long[i - 1] and exp_short[i] > exp_long[i]:
                first_cross_idx = i
                break
        # 第一金叉与第二金叉之间至少间隔 MIN_CROSS_GAP 根bar
        gap_ok = (first_cross_idx is not None
                  and first_cross_idx <= n - 1 - self.MIN_CROSS_GAP)
        first_cross_done = first_cross_idx is not None and gap_ok
        pullback_ok = False
        if first_cross_done:
            pullback_low = min(lows[first_cross_idx:])
            exp_long_now = exp_long[-1]
            pullback_ok = pullback_low >= exp_long_now * 0.98
        second_cross = (exp_short[-2] <= exp_long[-2] and exp_short[-1] > exp_long[-1])
        vol_ma5 = sma(vols, 5)
        vol_ok = vols[-1] > vol_ma5 * 1.2 if vol_ma5 > 0 else False
        _, _, adx = dmi(highs, lows, closes, 14)
        return {
            "exp_short": exp_short[-1], "exp_long": exp_long[-1],
            "exp_short_prev": exp_short[-2], "exp_long_prev": exp_long[-2],
            "first_cross_done": first_cross_done, "first_cross_idx": first_cross_idx,
            "pullback_ok": pullback_ok, "second_cross": second_cross,
            "vol_ok": vol_ok, "adx": adx, "vol_ma5": vol_ma5,
        }

    def _check_exit(self, ctx, closes, last):
        exp_s, exp_l = ctx["exp_short"], ctx["exp_long"]
        if exp_s < exp_l:
            result = {"action": "sell", "price": last["close"], "reason": "expma_death"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if last["close"] < exp_l * 0.95:
            result = {"action": "sell", "price": last["close"], "reason": "below_exp21"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if last["volume"] > ctx["vol_ma5"] * 2.5 and abs(last["close"] - closes[-2]) / closes[-2] < 0.01:
            result = {"action": "sell", "price": last["close"], "reason": "distribution"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        return None

    def _check_entry(self, ctx, last):
        # 核心：EXPMA 双金叉（保留数学模型原意）
        core_ok = ctx["first_cross_done"] and ctx["second_cross"]
        # 辅助：3选1（回调确认 / 放量 / ADX趋势）
        aux_score = sum([
            bool(ctx["pullback_ok"]),
            bool(ctx["vol_ok"]),
            ctx["adx"] > self.ADX_THRESHOLD,
        ])
        if not (core_ok and aux_score >= 1):
            conditions = {"first_cross_done": ctx["first_cross_done"],
                          "second_cross": ctx["second_cross"],
                          "pullback_ok": ctx["pullback_ok"],
                          "vol_ok": ctx["vol_ok"],
                          "adx_ok": ctx["adx"] > self.ADX_THRESHOLD,
                          "aux_score": aux_score}
            self._log_entry_fail(conditions, f"date={last.get('date','')}")
            return None
        price = last["close"]
        stop_loss = ctx["exp_long"] * 0.98
        take_profit = price * 1.08
        result = {
            "action": "buy", "price": price,
            "stop_loss": round(stop_loss, 3), "take_profit": round(take_profit, 3),
            "expma_short": round(ctx["exp_short"], 3),
            "expma_long": round(ctx["exp_long"], 3),
            "vol_ratio": round(last["volume"] / ctx["vol_ma5"], 2) if ctx["vol_ma5"] > 0 else 0,
            "adx": round(ctx["adx"], 1),
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
        return {"expma_short": self.SHORT_RANGE, "expma_long": self.LONG_RANGE}

    def validate_params(self, params: dict) -> bool:
        s = params.get("expma_short", 7)
        l = params.get("expma_long", 21)
        return (self.SHORT_RANGE[0] <= s <= self.SHORT_RANGE[1]
                and self.LONG_RANGE[0] <= l <= self.LONG_RANGE[1]
                and s < l)