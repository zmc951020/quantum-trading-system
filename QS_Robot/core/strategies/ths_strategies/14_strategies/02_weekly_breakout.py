"""策略02：周线突破战法 — 严格数学建模版

来源：同花顺金融大师·策略战法
逻辑：周线级别过滤日线杂波与主力骗线。横盘箱体后放量突破平台高点，
      5/10/20周均线多头排列向上发散，突破周成交量≥近5周均量1.5倍。

原策略数学模型：
  box_high  = MAX(high[-box_weeks:-1])
  box_low   = MIN(low[-box_weeks:-1])
  breakout  = close > box_high × 1.03
  vol_ok    = vol > MA(vol, 5) × vol_ratio
  alignment = MA5 > MA10 > MA20
  trending  = MA5(t) > MA5(t-4) AND MA10(t) > MA10(t-4) AND MA20(t) > MA20(t-4)
  cross     = MA5(t-1) ≤ MA10(t-1) AND MA5(t) > MA10(t)   # 5周线上穿10周线
  adx_ok    = ADX(14) > 20 AND +DI > -DI                   # 趋势强度+方向过滤
  vol_cons  = vol(t) > MA(vol,5) × vr AND vol(t-1) > MA(vol[:-1],5) × vr
  take_profit = entry + box_height × tp_multiplier

原策略规则：
  入场：周K收盘突破15周箱体高点3% + 5周均线上穿10周均线 + 放量1.5倍
        + 5/10/20均线多头排列向上发散 + ADX>20趋势确认 + 连续放量
        + 筹码底部单峰密集≥70%
  出场：跌破箱体高点或5周均线 / 周线MACD死叉 / 顶背离
  止损：箱体高点下方3%或5周均线下方（取较高者）
  止盈：箱体高度的1.5-2倍
  胜率：标准周线突破形态后续延续上涨概率78%+
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import sma, ema, dmi


class WeeklyBreakoutStrategy(THSBaseStrategy):
    ID = "02_weekly_breakout"
    NAME = "周线突破战法"
    CATEGORY = "ths_strategies"
    SOURCE = "同花顺金融大师"
    RISK_LEVEL = "中"

    BOX_WEEKS_RANGE = (8, 20)
    MA_SHORT_RANGE = (3, 8)
    MA_MID_RANGE = (8, 15)
    MA_LONG_RANGE = (15, 30)
    VOL_RATIO_RANGE = (1.2, 3.0)
    TP_MULT_RANGE = (1.3, 2.5)
    MA_TREND = 60
    DIVERGENCE_WINDOW = 10
    ADX_THRESHOLD = 20
    TREND_LOOKBACK = 4
    RISK_PER_TRADE = Decimal("0.02")

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        # 类型归一化：所有周期/窗口参数强制 int，防止调用方传 float（如 Aurora 层 (a+b)/2 产生）
        box_weeks = int(params.get("box_weeks", 15))
        ma_short = int(params.get("ma_short", 5))
        ma_mid = int(params.get("ma_mid", 10))
        ma_long = int(params.get("ma_long", 20))
        vol_ratio = float(params.get("vol_ratio", 1.5))
        tp_mult = float(params.get("tp_multiplier", 1.5))
        need = max(box_weeks + 2, self.MA_TREND + 2, ma_long + 5,
                   2 * self.DIVERGENCE_WINDOW)
        if len(bars) < need:
            self._log_data_short(len(bars), need)
            return None
        closes = [b["close"] for b in bars]
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]
        vols = [b["volume"] for b in bars]
        last = bars[-1]
        ctx = self._compute_indicators(closes, highs, lows, vols, box_weeks,
                                       ma_short, ma_mid, ma_long, vol_ratio)
        exit_signal = self._check_exit(ctx, closes, highs, last, ma_short)
        if exit_signal:
            return exit_signal
        entry_signal = self._check_entry(ctx, last, tp_mult)
        return self._apply_meta_filter(entry_signal, bars)

    def _compute_indicators(self, closes, highs, lows, vols, bw, ms, mm, ml, vr):
        box_slice = slice(-(bw + 1), -1)
        box_high = max(highs[box_slice])
        box_low = min(lows[box_slice])
        box_height = box_high - box_low
        box_range_ratio = box_height / box_high if box_high > 0 else 0
        box_consolidation = self._check_consolidation(
            closes, highs, lows, box_high, box_low, bw)
        sma_s = sma(closes, ms)
        sma_m = sma(closes, mm)
        sma_l = sma(closes, ml)
        sma_trend = sma(closes, self.MA_TREND)
        prev_sma_s = sma(closes[:-1], ms)
        prev_sma_m = sma(closes[:-1], mm)
        prev4_sma_s = sma(closes[:-self.TREND_LOOKBACK], ms)
        prev4_sma_m = sma(closes[:-self.TREND_LOOKBACK], mm)
        prev4_sma_l = sma(closes[:-self.TREND_LOOKBACK], ml)
        vol_ma5 = sma(vols, 5)
        prev_vol_ma5 = sma(vols[:-1], 5)
        prev_vol = vols[-2] if len(vols) >= 2 else 0
        dif_series = self._compute_dif_series(closes, 12, 26)
        dea_series = ema(dif_series, 9) if len(dif_series) >= 9 else dif_series
        dif = dif_series[-1]
        prev_dif = dif_series[-2] if len(dif_series) >= 2 else 0
        dea = dea_series[-1]
        prev_dea = dea_series[-2] if len(dea_series) >= 2 else 0
        hist = 2 * (dif - dea)
        plus_di, minus_di, adx = dmi(highs, lows, closes, 14)
        chip_ok = self._check_chip_concentration(closes)
        return {
            "box_high": box_high, "box_low": box_low, "box_height": box_height,
            "box_range_ratio": box_range_ratio, "box_consolidation": box_consolidation,
            "sma_s": sma_s, "sma_m": sma_m, "sma_l": sma_l, "sma_trend": sma_trend,
            "prev_sma_s": prev_sma_s, "prev_sma_m": prev_sma_m,
            "prev4_sma_s": prev4_sma_s, "prev4_sma_m": prev4_sma_m,
            "prev4_sma_l": prev4_sma_l,
            "vol_ma5": vol_ma5, "prev_vol_ma5": prev_vol_ma5, "prev_vol": prev_vol, "vr": vr,
            "dif": dif, "dea": dea, "hist": hist,
            "prev_dif": prev_dif, "prev_dea": prev_dea, "dif_series": dif_series,
            "plus_di": plus_di, "minus_di": minus_di, "adx": adx,
            "chip_ok": chip_ok,
        }

    def _check_exit(self, ctx, closes, highs, last, ma_s):
        dif, dea = ctx["dif"], ctx["dea"]
        prev_dif, prev_dea = ctx["prev_dif"], ctx["prev_dea"]
        box_high = ctx["box_high"]
        if prev_dif >= prev_dea and dif < dea:
            result = {"action": "sell", "price": last["close"], "reason": "macd_death_cross"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if last["close"] < box_high * 0.97:
            result = {"action": "sell", "price": last["close"], "reason": "below_box_high"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        sma_s_cur = sma(closes, ma_s)
        if last["close"] < sma_s_cur:
            result = {"action": "sell", "price": last["close"], "reason": "below_ma5"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if self._detect_bearish_divergence(ctx["dif_series"], highs):
            result = {"action": "sell", "price": last["close"], "reason": "bearish_divergence"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        return None

    def _check_entry(self, ctx, last, tp_mult):
        sma_s, sma_m, sma_l = ctx["sma_s"], ctx["sma_m"], ctx["sma_l"]
        prev_sma_s, prev_sma_m = ctx["prev_sma_s"], ctx["prev_sma_m"]
        prev4_s = ctx["prev4_sma_s"]
        prev4_m = ctx["prev4_sma_m"]
        prev4_l = ctx["prev4_sma_l"]
        golden_cross = prev_sma_s <= prev_sma_m and sma_s > sma_m
        bull_alignment = sma_s > sma_m > sma_l
        trending_up = (sma_s > prev4_s and sma_m > prev4_m and sma_l > prev4_l)
        breakout = last["close"] > ctx["box_high"] * 1.03
        vol_cur = last["volume"] > ctx["vol_ma5"] * ctx["vr"] if ctx["vol_ma5"] > 0 else False
        vol_prev = ctx["prev_vol"] > ctx["prev_vol_ma5"] * ctx["vr"] if ctx["prev_vol_ma5"] > 0 else False
        vol_ok = vol_cur and vol_prev
        trend_ok = last["close"] > ctx["sma_trend"]
        adx_ok = ctx["adx"] > self.ADX_THRESHOLD and ctx["plus_di"] > ctx["minus_di"]
        box_ok = 0.03 < ctx["box_range_ratio"] < 0.25 and ctx["box_consolidation"]
        if not (golden_cross and bull_alignment and trending_up and breakout
                and vol_ok and trend_ok and adx_ok and box_ok and ctx["chip_ok"]):
            conditions = {"golden_cross": golden_cross, "bull_alignment": bull_alignment, "trending_up": trending_up, "breakout": breakout, "vol_ok": vol_ok, "trend_ok": trend_ok, "adx_ok": adx_ok, "box_ok": box_ok, "chip_ok": ctx["chip_ok"]}
            self._log_entry_fail(conditions, f"date={last.get('date','')}")
            return None
        price = last["close"]
        stop_loss = max(ctx["box_high"] * 0.97, sma_s * 0.98)
        take_profit = price + ctx["box_height"] * tp_mult
        result = {
            "action": "buy", "price": price,
            "stop_loss": round(stop_loss, 2), "take_profit": round(take_profit, 2),
            "box_high": round(ctx["box_high"], 2), "box_low": round(ctx["box_low"], 2),
            "box_height": round(ctx["box_height"], 2),
            "sma_short": round(sma_s, 2), "sma_mid": round(sma_m, 2),
            "sma_long": round(sma_l, 2), "sma_trend": round(ctx["sma_trend"], 2),
            "vol_ratio_actual": round(last["volume"] / ctx["vol_ma5"], 2) if ctx["vol_ma5"] > 0 else 0,
            "adx": round(ctx["adx"], 1), "tp_multiplier": tp_mult,
        }
        self._log_signal("buy", result, f"date={last.get('date','')}")
        return result

    def _compute_dif_series(self, closes, fast, slow):
        ema_fast = ema(closes, fast)
        ema_slow = ema(closes, slow)
        return [ema_fast[i] - ema_slow[i] for i in range(len(closes))]

    def _check_consolidation(self, closes, highs, lows, box_high, box_low, bw):
        """验证箱体期内价格在箱体内的时间占比≥70%（收盘价+最高价+最低价）"""
        c_slice = closes[-(bw + 1):-1]
        h_slice = highs[-(bw + 1):-1]
        l_slice = lows[-(bw + 1):-1]
        if not c_slice:
            return False
        high_bound = box_high * 1.02
        low_bound = box_low * 0.98
        in_box = sum(1 for i in range(len(c_slice))
                     if low_bound <= c_slice[i] <= high_bound
                     and h_slice[i] <= high_bound
                     and l_slice[i] >= low_bound)
        return in_box / len(c_slice) >= 0.70

    def _check_chip_concentration(self, closes):
        """筹码底部单峰密集检查：数据可用时验证，不可用时放行"""
        if len(closes) < 60:
            return True
        ma60 = sma(closes, 60)
        if ma60 <= 0:
            return True
        recent_avg = sum(closes[-20:]) / 20
        return recent_avg < ma60 * 1.15

    def _detect_bearish_divergence(self, dif_series, highs):
        n = self.DIVERGENCE_WINDOW
        if len(highs) < 2 * n or len(dif_series) < 2 * n:
            return False
        price_new_high = max(highs[-n:]) > max(highs[-2*n:-n])
        dif_new_high = max(dif_series[-n:]) <= max(dif_series[-2*n:-n])
        return price_new_high and dif_new_high

    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        if signal.get("action") != "buy":
            return Decimal("0")
        risk_per_share = Decimal(str(signal["price"])) - Decimal(str(signal["stop_loss"]))
        if risk_per_share <= 0:
            return Decimal("0")
        position = (capital * self.RISK_PER_TRADE / risk_per_share).quantize(Decimal("0.01"))
        return min(position, capital * Decimal("0.20"))

    def get_param_space(self) -> dict[str, tuple]:
        return {
            "box_weeks": self.BOX_WEEKS_RANGE,
            "ma_short": self.MA_SHORT_RANGE,
            "ma_mid": self.MA_MID_RANGE,
            "ma_long": self.MA_LONG_RANGE,
            "vol_ratio": self.VOL_RATIO_RANGE,
            "tp_multiplier": self.TP_MULT_RANGE,
        }

    def validate_params(self, params: dict) -> bool:
        bw = int(params.get("box_weeks", 15))
        ms = int(params.get("ma_short", 5))
        mm = int(params.get("ma_mid", 10))
        ml = int(params.get("ma_long", 20))
        vr = float(params.get("vol_ratio", 1.5))
        tp = float(params.get("tp_multiplier", 1.5))
        return (self.BOX_WEEKS_RANGE[0] <= bw <= self.BOX_WEEKS_RANGE[1]
                and self.MA_SHORT_RANGE[0] <= ms <= self.MA_SHORT_RANGE[1]
                and self.MA_MID_RANGE[0] <= mm <= self.MA_MID_RANGE[1]
                and self.MA_LONG_RANGE[0] <= ml <= self.MA_LONG_RANGE[1]
                and self.VOL_RATIO_RANGE[0] <= vr <= self.VOL_RATIO_RANGE[1]
                and self.TP_MULT_RANGE[0] <= tp <= self.TP_MULT_RANGE[1]
                and ms < mm < ml)