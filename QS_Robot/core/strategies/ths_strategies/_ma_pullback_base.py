"""单均线回踩低吸基类 — 严格数学建模版

策略 10/11/12/13 共享逻辑：
  - 股价在均线上方运行
  - 均线向上（4期斜率>0）
  - 回调N日至均线附近（最低价触及均线±2%）
  - 缩量（回踩日量<MA10）
  - 收阳（反弹确认）
  - ADX>20（趋势确认）

子类覆盖: MA_PERIOD / PULLBACK_DAYS / NAME / ID / RISK_LEVEL / CATEGORY / SOURCE

原策略数学模型：
  均线向上:
    ma_up = MA(t) > MA(t-4)  # 4期斜率确认

  回踩确认（回调N日内最低价触及均线但未有效跌破）:
    pullback_low = MIN(low[-(N+1):-1])
    pullback_ok = |pullback_low - MA| / MA < 0.02  # 精准回踩均线

  缩量确认:
    vol_shrink = vol(t) < MA(vol, 10) × 0.9

  收阳确认:
    bullish_candle = close > open

  趋势确认:
    adx_ok = ADX(14) > 20

  入场条件（ALL）：
    ma_up AND close > MA AND pullback_ok AND vol_shrink
    AND bullish_candle AND close > MA20 AND adx_ok

  出场条件（ANY）：
    - 跌破MA（close < MA × 0.98）
    - 跌破MA20（趋势破位）
    - MACD死叉
    - 放量下跌（量>MA10×2.5且收跌）
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import sma, ema, dmi


class MAPullbackBase(THSBaseStrategy):
    MA_PERIOD: int = 10
    PULLBACK_DAYS: int = 2
    POSITION_RATIO: Decimal = Decimal("0.10")
    MA_PERIOD_RANGE: tuple[int, int] = (3, 120)
    TREND_LOOKBACK = 4
    ADX_THRESHOLD = 20
    RISK_PER_TRADE = Decimal("0.02")
    MAX_POSITION = Decimal("0.15")

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        period = params.get("ma_period", self.MA_PERIOD)
        need = max(period + self.PULLBACK_DAYS + 5, self.TREND_LOOKBACK + 5, 60)
        if len(bars) < need:
            self._log_data_short(len(bars), need)
            return None
        closes = [b["close"] for b in bars]
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]
        opens = [b["open"] for b in bars]
        vols = [b["volume"] for b in bars]
        last = bars[-1]
        ctx = self._compute_indicators(closes, highs, lows, opens, vols, period)
        exit_signal = self._check_exit(ctx, closes, last)
        if exit_signal:
            return exit_signal
        entry_signal = self._check_entry(ctx, last)
        return self._apply_meta_filter(entry_signal, bars)

    def _compute_indicators(self, closes, highs, lows, opens, vols, period):
        ma = sma(closes, period)
        ma_prev = sma(closes[:-self.TREND_LOOKBACK], period)
        ma_up = ma > ma_prev
        above_ma = closes[-1] > ma
        pullback_start = -(self.PULLBACK_DAYS + 1)
        pullback_low = min(lows[pullback_start:-1]) if len(lows) > self.PULLBACK_DAYS else closes[-1]
        pullback_ok = abs(pullback_low - ma) / ma < 0.02 if ma > 0 else False
        vol_ma10 = sma(vols, 10)
        vol_shrink = vols[-1] < vol_ma10 * 0.9 if vol_ma10 > 0 else False
        bullish_candle = closes[-1] > opens[-1]
        ma20 = sma(closes, 20)
        above_ma20 = closes[-1] > ma20 * 0.98
        _, _, adx = dmi(highs, lows, closes, 14)
        dif_series = self._compute_dif_series(closes, 12, 26)
        dea_series = ema(dif_series, 9) if len(dif_series) >= 9 else dif_series
        dif = dif_series[-1]
        prev_dif = dif_series[-2] if len(dif_series) >= 2 else 0
        dea = dea_series[-1]
        prev_dea = dea_series[-2] if len(dea_series) >= 2 else 0
        return {
            "ma": ma, "ma_up": ma_up, "above_ma": above_ma,
            "pullback_ok": pullback_ok, "vol_shrink": vol_shrink,
            "bullish_candle": bullish_candle, "above_ma20": above_ma20,
            "adx": adx, "ma20": ma20, "vol_ma10": vol_ma10,
            "dif": dif, "prev_dif": prev_dif, "dea": dea, "prev_dea": prev_dea,
        }

    def _check_exit(self, ctx, closes, last):
        ma, ma20 = ctx["ma"], ctx["ma20"]
        dif, prev_dif = ctx["dif"], ctx["prev_dif"]
        dea, prev_dea = ctx["dea"], ctx["prev_dea"]
        if last["close"] < ma * 0.98:
            result = {"action": "sell", "price": last["close"], "reason": "below_ma"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if last["close"] < ma20 * 0.97:
            result = {"action": "sell", "price": last["close"], "reason": "below_ma20"}
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
        # 入场条件：核心 3 AND（趋势+均线+回踩） + 辅助 4 选 2（缩量/收阳/上MA20/ADX强趋势）
        # 原战法为 7 AND 过严（3年日线信号稀少），保留核心放宽辅助
        core_ok = ctx["ma_up"] and ctx["above_ma"] and ctx["pullback_ok"]
        soft_score = sum([
            bool(ctx["vol_shrink"]),
            bool(ctx["bullish_candle"]),
            bool(ctx["above_ma20"]),
            ctx["adx"] > self.ADX_THRESHOLD,
        ])
        if not (core_ok and soft_score >= 2):
            conditions = {
                "ma_up": ctx["ma_up"], "above_ma": ctx["above_ma"],
                "pullback_ok": ctx["pullback_ok"], "vol_shrink": ctx["vol_shrink"],
                "bullish_candle": ctx["bullish_candle"], "above_ma20": ctx["above_ma20"],
                "adx_ok": ctx["adx"] > self.ADX_THRESHOLD, "soft_score": soft_score,
            }
            self._log_entry_fail(conditions, f"date={last.get('date','')}")
            return None
        price = last["close"]
        stop_loss = ctx["ma"] * 0.98
        take_profit = price * 1.05
        result = {
            "action": "buy", "price": price,
            "stop_loss": round(stop_loss, 3), "take_profit": round(take_profit, 3),
            "ma": round(ctx["ma"], 3), "ma_period": self.MA_PERIOD,
            "vol_ratio": round(last["volume"] / ctx["vol_ma10"], 2) if ctx["vol_ma10"] > 0 else 0,
            "adx": round(ctx["adx"], 1),
            "soft_score": soft_score,
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
        return {"ma_period": self.MA_PERIOD_RANGE}

    def validate_params(self, params: dict) -> bool:
        p = params.get("ma_period", self.MA_PERIOD)
        lo, hi = self.MA_PERIOD_RANGE
        return lo <= p <= hi