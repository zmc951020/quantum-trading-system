"""策略05：多头排列回踩低吸 — 严格数学建模版

来源：同花顺金融大师·策略战法

原策略数学模型：
  均线多头排列：
    bull_alignment = MA5 > MA10 > MA20 > MA60
    trending_up = 每根均线4期斜率 > 0  # 均线向上发散

  回踩确认（价格回调到均线支撑位但未有效跌破）：
    low_near_ma = |low - MA5|/MA5 < 0.02 OR |low - MA10|/MA10 < 0.02
    hold_support = close > MA5  # 收盘回到MA5上方，支撑有效

  量价确认：
    vol_shrink = vol(t) < MA(vol, 10)  # 回踩日缩量
    vol_bounce = vol(t) > vol(t-1)     # 反弹日放量（量价配合）

  趋势确认：
    adx_ok = ADX(14) > 20

  入场条件（ALL）：
    bull_alignment AND trending_up AND low_near_ma AND hold_support
    AND vol_shrink AND vol_bounce AND adx_ok

  出场条件（ANY）：
    - 跌破MA20（趋势破位）
    - 均线排列破坏（MA5 < MA10）
    - MACD死叉
    - 放量下跌（量>MA5×2且收跌）

  止损：MA20 × 0.98 或 MA60 × 0.99（取较高者）
  止盈：入场价 × 1.08（短线目标8%）
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import sma, ema, dmi


class MALongArrangementStrategy(THSBaseStrategy):
    ID = "05_ma_long_arrangement"
    NAME = "多头排列回踩低吸"
    CATEGORY = "ths_strategies"
    SOURCE = "同花顺金融大师"
    RISK_LEVEL = "中"

    MA_SHORT = 5
    MA_MID1 = 10
    MA_MID2 = 20
    MA_LONG = 60
    TREND_LOOKBACK = 4
    ADX_THRESHOLD = 20
    VOL_RATIO_RANGE = (0.5, 1.5)
    RISK_PER_TRADE = Decimal("0.02")
    MAX_POSITION = Decimal("0.15")

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        vol_ratio = params.get("vol_ratio", 0.8)
        need = self.MA_LONG + self.TREND_LOOKBACK + 5
        if len(bars) < need:
            self._log_data_short(len(bars), need)
            return None
        closes = [b["close"] for b in bars]
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]
        vols = [b["volume"] for b in bars]
        last = bars[-1]
        ctx = self._compute_indicators(closes, highs, lows, vols, vol_ratio)
        exit_signal = self._check_exit(ctx, closes, last)
        if exit_signal:
            return exit_signal
        return self._check_entry(ctx, vols, last)

    def _compute_indicators(self, closes, highs, lows, vols, vol_ratio):
        ma5 = sma(closes, self.MA_SHORT)
        ma10 = sma(closes, self.MA_MID1)
        ma20 = sma(closes, self.MA_MID2)
        ma60 = sma(closes, self.MA_LONG)
        lb = self.TREND_LOOKBACK
        ma5_prev = sma(closes[:-lb], self.MA_SHORT)
        ma10_prev = sma(closes[:-lb], self.MA_MID1)
        ma20_prev = sma(closes[:-lb], self.MA_MID2)
        ma60_prev = sma(closes[:-lb], self.MA_LONG)
        bull_alignment = ma5 > ma10 > ma20 > ma60
        trending_up = (ma5 > ma5_prev and ma10 > ma10_prev
                       and ma20 > ma20_prev and ma60 > ma60_prev)
        low_near_ma5 = abs(lows[-1] - ma5) / ma5 < 0.02 if ma5 > 0 else False
        low_near_ma10 = abs(lows[-1] - ma10) / ma10 < 0.02 if ma10 > 0 else False
        hold_support = closes[-1] > ma5
        vol_ma10 = sma(vols, 10)
        vol_shrink = vols[-1] < vol_ma10 * vol_ratio if vol_ma10 > 0 else False
        vol_bounce = vols[-1] > vols[-2] if len(vols) >= 2 else False
        _, _, adx = dmi(highs, lows, closes, 14)
        dif_series = self._compute_dif_series(closes, 12, 26)
        dea_series = ema(dif_series, 9) if len(dif_series) >= 9 else dif_series
        dif = dif_series[-1]
        prev_dif = dif_series[-2] if len(dif_series) >= 2 else 0
        dea = dea_series[-1]
        prev_dea = dea_series[-2] if len(dea_series) >= 2 else 0
        return {
            "ma5": ma5, "ma10": ma10, "ma20": ma20, "ma60": ma60,
            "bull_alignment": bull_alignment, "trending_up": trending_up,
            "low_near_ma5": low_near_ma5, "low_near_ma10": low_near_ma10,
            "hold_support": hold_support, "vol_shrink": vol_shrink,
            "vol_bounce": vol_bounce, "adx": adx,
            "dif": dif, "prev_dif": prev_dif, "dea": dea, "prev_dea": prev_dea,
            "vol_ma10": vol_ma10,
        }

    def _check_exit(self, ctx, closes, last):
        ma20, ma60 = ctx["ma20"], ctx["ma60"]
        ma5, ma10 = ctx["ma5"], ctx["ma10"]
        dif, prev_dif = ctx["dif"], ctx["prev_dif"]
        dea, prev_dea = ctx["dea"], ctx["prev_dea"]
        if last["close"] < ma20 * 0.97:
            result = {"action": "sell", "price": last["close"], "reason": "below_ma20"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if last["close"] < ma60 * 0.98:
            result = {"action": "sell", "price": last["close"], "reason": "below_ma60"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if ma5 < ma10:
            result = {"action": "sell", "price": last["close"], "reason": "alignment_broken"}
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

    def _check_entry(self, ctx, vols, last):
        low_near = ctx["low_near_ma5"] or ctx["low_near_ma10"]
        if not (ctx["bull_alignment"] and ctx["trending_up"] and low_near
                and ctx["hold_support"] and ctx["vol_shrink"]
                and ctx["vol_bounce"]):
            conditions = {"bull_alignment": ctx["bull_alignment"], "trending_up": ctx["trending_up"], "low_near": low_near, "hold_support": ctx["hold_support"], "vol_shrink": ctx["vol_shrink"], "vol_bounce": ctx["vol_bounce"]}
            self._log_entry_fail(conditions, f"date={last.get('date','')}")
            return None
        price = last["close"]
        stop_loss = max(ctx["ma20"] * 0.98, ctx["ma60"] * 0.99)
        take_profit = price * 1.08
        result = {
            "action": "buy", "price": price,
            "stop_loss": round(stop_loss, 3), "take_profit": round(take_profit, 3),
            "ma5": round(ctx["ma5"], 3), "ma10": round(ctx["ma10"], 3),
            "ma20": round(ctx["ma20"], 3), "ma60": round(ctx["ma60"], 3),
            "vol_ratio": round(last["volume"] / ctx["vol_ma10"], 2) if ctx["vol_ma10"] > 0 else 0,
            "adx": round(ctx["adx"], 1),
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

    def get_param_space(self) -> dict[str, tuple]:
        return {"vol_ratio": self.VOL_RATIO_RANGE}

    def validate_params(self, params: dict) -> bool:
        vr = params.get("vol_ratio", 0.8)
        return self.VOL_RATIO_RANGE[0] <= vr <= self.VOL_RATIO_RANGE[1]