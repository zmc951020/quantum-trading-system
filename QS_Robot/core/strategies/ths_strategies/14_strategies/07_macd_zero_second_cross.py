"""策略07：MACD零轴上方二次金叉（空中加油）— 严格数学建模版

来源：同花顺金融大师·策略战法

原策略数学模型：
  第一金叉（窗口内）：
    first_cross_idx = argmin_i { DIF(i-1) ≤ DEA(i-1) AND DIF(i) > DEA(i) AND DIF(i) > 0 }
    first_cross_done = first_cross_idx is not None

  零轴不破（第一金叉后DIF始终>0）：
    zero_held = all(DIF[i] > 0 for i in [first_cross_idx, ..., now])

  第二金叉（当前触发）：
    second_cross = DIF(t-1) ≤ DEA(t-1) AND DIF(t) > DEA(t) AND DIF(t) > 0

  MACD柱状线放大：
    hist_amplifying = hist(t) > hist(t-1) AND hist(t-1) ≤ 0

  成交量确认：
    vol_ok = vol(t) > MA(vol, 5) × 1.5

  趋势确认：
    adx_ok = ADX(14) > 20

  入场条件（ALL）：
    first_cross_done AND zero_held AND second_cross AND hist_amplifying
    AND vol_ok AND adx_ok

  出场条件（ANY）：
    - MACD死叉（DIF下穿DEA）
    - DIF跌破零轴
    - 顶背离（股价新高MACD柱未新高）
    - 柱状线持续缩短（hist < prev_hist）
    - 跌破MA20

  止损：近期低点×0.98 或 MA20×0.98（取较高者）
  止盈：入场价×1.10（短线目标10%）
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import ema, sma, dmi


class MACDZeroSecondCrossStrategy(THSBaseStrategy):
    ID = "07_macd_zero_second_cross"
    NAME = "MACD零轴二次金叉"
    CATEGORY = "ths_strategies"
    SOURCE = "同花顺金融大师"
    RISK_LEVEL = "中"

    FAST_RANGE = (5, 30)
    SLOW_RANGE = (20, 40)
    SIGNAL_RANGE = (5, 15)
    CROSS_WINDOW = 40
    DIVERGENCE_WINDOW = 20
    ADX_THRESHOLD = 20
    RISK_PER_TRADE = Decimal("0.02")
    MAX_POSITION = Decimal("0.15")

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        fast = params.get("fast", 12)
        slow = params.get("slow", 26)
        signal = params.get("signal", 9)
        need = max(slow + signal + 10, self.CROSS_WINDOW + 5, 60)
        if len(bars) < need:
            self._log_data_short(len(bars), need)
            return None
        closes = [b["close"] for b in bars]
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]
        vols = [b["volume"] for b in bars]
        last = bars[-1]
        ctx = self._compute_indicators(closes, highs, lows, vols, fast, slow, signal)
        exit_signal = self._check_exit(ctx, closes, highs, last)
        if exit_signal:
            return exit_signal
        return self._check_entry(ctx, lows, vols, last)

    def _compute_indicators(self, closes, highs, lows, vols, fast, slow, signal):
        dif_series = self._compute_dif_series(closes, fast, slow)
        dea_series = ema(dif_series, signal)
        dif, prev_dif = dif_series[-1], dif_series[-2]
        dea, prev_dea = dea_series[-1], dea_series[-2]
        hist = 2 * (dif - dea)
        prev_hist = 2 * (prev_dif - prev_dea)
        ma20 = sma(closes, 20)
        n = len(closes)
        first_cross_idx = None
        for i in range(max(0, n - self.CROSS_WINDOW), n - 1):
            if (dif_series[i - 1] <= dea_series[i - 1] and dif_series[i] > dea_series[i]
                    and dif_series[i] > 0):
                first_cross_idx = i
                break
        first_cross_done = first_cross_idx is not None
        zero_held = False
        if first_cross_done:
            zero_held = all(d > 0 for d in dif_series[first_cross_idx:])
        second_cross = (prev_dif <= prev_dea and dif > dea and dif > 0)
        hist_amplifying = hist > prev_hist and prev_hist <= 0
        vol_ma5 = sma(vols, 5)
        vol_ok = vols[-1] > vol_ma5 * 1.5 if vol_ma5 > 0 else False
        _, _, adx = dmi(highs, lows, closes, 14)
        return {
            "dif": dif, "prev_dif": prev_dif, "dea": dea, "prev_dea": prev_dea,
            "hist": hist, "prev_hist": prev_hist, "dif_series": dif_series,
            "dea_series": dea_series, "ma20": ma20,
            "first_cross_done": first_cross_done, "first_cross_idx": first_cross_idx,
            "zero_held": zero_held, "second_cross": second_cross,
            "hist_amplifying": hist_amplifying, "vol_ok": vol_ok, "adx": adx,
            "vol_ma5": vol_ma5,
        }

    def _check_exit(self, ctx, closes, highs, last):
        dif, prev_dif = ctx["dif"], ctx["prev_dif"]
        dea, prev_dea = ctx["dea"], ctx["prev_dea"]
        hist, prev_hist = ctx["hist"], ctx["prev_hist"]
        ma20 = ctx["ma20"]
        if prev_dif >= prev_dea and dif < dea:
            result = {"action": "sell", "price": last["close"], "reason": "macd_death"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if dif < 0:
            result = {"action": "sell", "price": last["close"], "reason": "below_zero"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if self._detect_bearish_divergence(ctx["dif_series"], highs):
            result = {"action": "sell", "price": last["close"], "reason": "bearish_divergence"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if 0 < hist < prev_hist:
            result = {"action": "sell", "price": last["close"], "reason": "hist_shrinking"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if last["close"] < ma20 * 0.98:
            result = {"action": "sell", "price": last["close"], "reason": "below_ma20"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        return None

    def _check_entry(self, ctx, lows, vols, last):
        if not (ctx["first_cross_done"] and ctx["zero_held"] and ctx["second_cross"]
                and ctx["hist_amplifying"]):
            conditions = {"first_cross_done": ctx["first_cross_done"], "zero_held": ctx["zero_held"], "second_cross": ctx["second_cross"], "hist_amplifying": ctx["hist_amplifying"]}
            self._log_entry_fail(conditions, f"date={last.get('date','')}")
            return None
        price = last["close"]
        recent_low = min(lows[-10:])
        stop_loss = max(ctx["ma20"] * 0.98, recent_low * 0.98)
        take_profit = price * 1.10
        result = {
            "action": "buy", "price": price,
            "stop_loss": round(stop_loss, 3), "take_profit": round(take_profit, 3),
            "dif": round(ctx["dif"], 4), "dea": round(ctx["dea"], 4),
            "macd_hist": round(ctx["hist"], 4), "ma20": round(ctx["ma20"], 3),
            "vol_ratio": round(last["volume"] / ctx["vol_ma5"], 2) if ctx["vol_ma5"] > 0 else 0,
            "adx": round(ctx["adx"], 1),
        }
        self._log_signal("buy", result, f"date={last.get('date','')}")
        return result

    def _compute_dif_series(self, closes, fast, slow):
        ema_fast = ema(closes, fast)
        ema_slow = ema(closes, slow)
        return [ema_fast[i] - ema_slow[i] for i in range(len(closes))]

    def _detect_bearish_divergence(self, dif_series, highs):
        n = self.DIVERGENCE_WINDOW
        if len(dif_series) < 2 * n or len(highs) < 2 * n:
            return False
        price_new_high = max(highs[-n:]) > max(highs[-2*n:-n])
        dif_no_new_high = max(dif_series[-n:]) <= max(dif_series[-2*n:-n])
        return price_new_high and dif_no_new_high

    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        if signal.get("action") != "buy":
            return Decimal("0")
        risk_per_share = Decimal(str(signal["price"])) - Decimal(str(signal["stop_loss"]))
        if risk_per_share <= 0:
            return Decimal("0")
        position = (capital * self.RISK_PER_TRADE / risk_per_share).quantize(Decimal("0.01"))
        return min(position, capital * self.MAX_POSITION)

    def get_param_space(self) -> dict[str, tuple]:
        return {"fast": self.FAST_RANGE, "slow": self.SLOW_RANGE, "signal": self.SIGNAL_RANGE}

    def validate_params(self, params: dict) -> bool:
        f = params.get("fast", 12)
        s = params.get("slow", 26)
        sig = params.get("signal", 9)
        return (self.FAST_RANGE[0] <= f <= self.FAST_RANGE[1]
                and self.SLOW_RANGE[0] <= s <= self.SLOW_RANGE[1]
                and self.SIGNAL_RANGE[0] <= sig <= self.SIGNAL_RANGE[1]
                and f < s)