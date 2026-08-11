"""策略14：5/10/20/60四线多头共振战法 — 严格数学建模版

来源：同花顺金融大师·策略战法

原策略数学模型：
  四线多头排列：
    aligned = MA5 > MA10 > MA20 > MA60

  四线同时向上发散（4期斜率确认）：
    all_up = MA5(t) > MA5(t-4) AND MA10(t) > MA10(t-4)
         AND MA20(t) > MA20(t-4) AND MA60(t) > MA60(t-4)

  股价站上所有均线：
    above_all = close > max(MA5, MA10, MA20, MA60)

  回踩任一均线不破（精准回踩+反弹确认）：
    pullback_ok = |low - nearest_ma| / nearest_ma < 0.02 AND close > nearest_ma

  成交量确认（缩量回踩+放量反弹）：
    vol_shrink = vol(t) < MA(vol, 10)
    vol_ok = vol(t) > MA(vol, 5)  # 反弹日放量

  趋势确认：
    adx_ok = ADX(14) > 20

  入场条件（ALL）：
    aligned AND all_up AND above_all AND pullback_ok
    AND vol_shrink AND vol_ok AND adx_ok

  出场条件（ANY）：
    - 排列破坏（MA5 < MA10 或 MA10 < MA20）
    - 跌破MA60（趋势破位）
    - MACD死叉
    - 放量下跌（量>MA10×2.5且收跌）

  止损：MA20 × 0.97
  止盈：入场价 × 1.15
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import sma, ema, dmi


class FourMAResonanceStrategy(THSBaseStrategy):
    ID = "14_four_ma_resonance"
    NAME = "四线多头共振"
    CATEGORY = "ths_strategies"
    SOURCE = "同花顺金融大师"
    RISK_LEVEL = "中"

    MA_PERIODS = (5, 10, 20, 60)
    TREND_LOOKBACK = 4
    ADX_THRESHOLD = 20
    RISK_PER_TRADE = Decimal("0.02")
    MAX_POSITION = Decimal("0.15")

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        need = max(65, self.TREND_LOOKBACK + 5, 60)
        if len(bars) < need:
            self._log_data_short(len(bars), need)
            return None
        vol_ratio = params.get("vol_ratio", 1.2)
        closes = [b["close"] for b in bars]
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]
        opens = [b["open"] for b in bars]
        vols = [b["volume"] for b in bars]
        last = bars[-1]
        ctx = self._compute_indicators(closes, highs, lows, opens, vols, vol_ratio)
        exit_signal = self._check_exit(ctx, closes, last)
        if exit_signal:
            return exit_signal
        return self._check_entry(ctx, last)

    def _compute_indicators(self, closes, highs, lows, opens, vols, vol_ratio):
        ma5, ma10, ma20, ma60 = (sma(closes, p) for p in self.MA_PERIODS)
        ma5_p4, ma10_p4, ma20_p4, ma60_p4 = (sma(closes[:-self.TREND_LOOKBACK], p) for p in self.MA_PERIODS)
        all_up = ma5 > ma5_p4 and ma10 > ma10_p4 and ma20 > ma20_p4 and ma60 > ma60_p4
        aligned = ma5 > ma10 > ma20 > ma60
        above_all = closes[-1] > max(ma5, ma10, ma20, ma60)
        mas = [ma5, ma10, ma20, ma60]
        nearest_ma = min(mas, key=lambda m: abs(closes[-1] - m))
        pullback_ok = abs(lows[-1] - nearest_ma) / nearest_ma < 0.02 if nearest_ma > 0 else False
        pullback_ok = pullback_ok and closes[-1] > nearest_ma
        vol_ma10 = sma(vols, 10)
        vol_ma5 = sma(vols, 5)
        vol_shrink = vols[-1] < vol_ma10 if vol_ma10 > 0 else False
        vol_ok = vols[-1] > vol_ma5 * vol_ratio if vol_ma5 > 0 else False
        _, _, adx = dmi(highs, lows, closes, 14)
        dif_series = self._compute_dif_series(closes, 12, 26)
        dea_series = ema(dif_series, 9) if len(dif_series) >= 9 else dif_series
        dif = dif_series[-1]
        prev_dif = dif_series[-2] if len(dif_series) >= 2 else 0
        dea = dea_series[-1]
        prev_dea = dea_series[-2] if len(dea_series) >= 2 else 0
        return {
            "ma5": ma5, "ma10": ma10, "ma20": ma20, "ma60": ma60,
            "all_up": all_up, "aligned": aligned, "above_all": above_all,
            "pullback_ok": pullback_ok, "vol_shrink": vol_shrink, "vol_ok": vol_ok,
            "adx": adx, "vol_ma10": vol_ma10, "vol_ma5": vol_ma5,
            "dif": dif, "prev_dif": prev_dif, "dea": dea, "prev_dea": prev_dea,
        }

    def _check_exit(self, ctx, closes, last):
        dif, prev_dif = ctx["dif"], ctx["prev_dif"]
        dea, prev_dea = ctx["dea"], ctx["prev_dea"]
        if ctx["ma5"] < ctx["ma10"] or ctx["ma10"] < ctx["ma20"]:
            result = {"action": "sell", "price": last["close"], "reason": "alignment_broken"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if last["close"] < ctx["ma60"] * 0.97:
            result = {"action": "sell", "price": last["close"], "reason": "below_ma60"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if prev_dif >= prev_dea and dif < dea:
            result = {"action": "sell", "price": last["close"], "reason": "macd_death"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if last["volume"] > ctx["vol_ma10"] * 2.5 and last["close"] < closes[-2]:
            result = {"action": "sell", "price": last["close"], "reason": "heavy_sell"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        return None

    def _check_entry(self, ctx, last):
        if not (ctx["aligned"] and ctx["all_up"] and ctx["above_all"]
                and ctx["pullback_ok"] and ctx["vol_shrink"] and ctx["vol_ok"]
                and ctx["adx"] > self.ADX_THRESHOLD):
            conditions = {"aligned": ctx["aligned"], "all_up": ctx["all_up"], "above_all": ctx["above_all"], "pullback_ok": ctx["pullback_ok"], "vol_shrink": ctx["vol_shrink"], "vol_ok": ctx["vol_ok"], "adx_ok": ctx["adx"] > self.ADX_THRESHOLD}
            self._log_entry_fail(conditions, f"date={last.get('date','')}")
            return None
        price = last["close"]
        stop_loss = ctx["ma20"] * 0.97
        take_profit = price * 1.15
        result = {
            "action": "buy", "price": price,
            "stop_loss": round(stop_loss, 3), "take_profit": round(take_profit, 3),
            "ma5": round(ctx["ma5"], 3), "ma10": round(ctx["ma10"], 3),
            "ma20": round(ctx["ma20"], 3), "ma60": round(ctx["ma60"], 3),
            "adx": round(ctx["adx"], 1),
            "vol_ratio": round(last["volume"] / ctx["vol_ma5"], 2) if ctx["vol_ma5"] > 0 else 0,
        }
        self._log_signal("buy", result, f"date={last.get('date','')}")
        return result

    def _compute_dif_series(self, closes, fast, slow):
        ema_fast = ema(closes, fast)
        ema_slow = ema(closes, slow)
        return [ema_fast[i] - ema_slow[i] for i in range(len(closes))]

    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        if signal.get("action") != "buy":
            return Decimal("0")
        risk_per_share = Decimal(str(signal["price"])) - Decimal(str(signal["stop_loss"]))
        if risk_per_share <= 0:
            return Decimal("0")
        position = (capital * self.RISK_PER_TRADE / risk_per_share).quantize(Decimal("0.01"))
        return min(position, capital * self.MAX_POSITION)

    VOL_RATIO_RANGE = (1.0, 2.0)

    def get_param_space(self) -> dict[str, tuple]:
        return {"vol_ratio": self.VOL_RATIO_RANGE}

    def validate_params(self, params: dict) -> bool:
        v = params.get("vol_ratio", 1.2)
        return self.VOL_RATIO_RANGE[0] <= v <= self.VOL_RATIO_RANGE[1]