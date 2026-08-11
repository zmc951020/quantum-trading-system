"""策略01：MACD顺势波段交易战法

来源：同花顺金融大师·策略战法
逻辑：MACD四要素（零轴+DIF+DEA+柱状线），零轴上方金叉顺势做多
数学：DIF = EMA(fast) - EMA(slow); DEA = EMA(DIF, signal); MACD柱 = 2*(DIF-DEA)

原策略规则：
  入场：DIF零轴上方金叉 + 柱状线由负转正放大 + 放量 + 5/10/20日均线多头排列
  出场：死叉 / 顶背离（股价新高MACD柱未新高） / 跌破20日均线
  止损：20日均线或近期低点-2%（动态）
  止盈：1.5倍风险或柱状线持续缩短
  特色：空中加油（零轴上方二次金叉）是最强多头确认
  胜率：标准周线MACD零轴上方金叉延续上涨概率78%+
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import ema, sma, dmi


class MACDWaveStrategy(THSBaseStrategy):
    ID = "01_macd_wave"
    NAME = "MACD顺势波段"
    CATEGORY = "ths_strategies"
    SOURCE = "同花顺金融大师"
    RISK_LEVEL = "中"

    FAST_RANGE = (5, 30)
    SLOW_RANGE = (20, 40)
    SIGNAL_RANGE = (5, 15)
    DIVERGENCE_WINDOW = 20
    ADX_THRESHOLD = 20
    RISK_PER_TRADE = Decimal("0.02")

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 60:
            self._log_data_short(len(bars), 60)
            return None
        fast = params.get("fast", 12)
        slow = params.get("slow", 26)
        signal = params.get("signal", 9)
        closes = [b["close"] for b in bars]
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]
        vols = [b["volume"] for b in bars]
        last = bars[-1]

        ctx = self._compute_indicators(closes, highs, lows, vols, fast, slow, signal)
        exit_signal = self._check_exit(ctx, closes, highs, last)
        if exit_signal:
            return exit_signal
        return self._check_entry(ctx, closes, lows, vols, last)

    def _compute_indicators(self, closes, highs, lows, vols, fast, slow, signal):
        ema_fast = ema(closes, fast)
        ema_slow = ema(closes, slow)
        dif_series = [ema_fast[i] - ema_slow[i] for i in range(len(closes))]
        dea_series = ema(dif_series, signal)
        dif, prev_dif = dif_series[-1], dif_series[-2]
        dea, prev_dea = dea_series[-1], dea_series[-2]
        hist = 2 * (dif - dea)
        prev_hist = 2 * (prev_dif - prev_dea)
        ma5 = sma(closes, 5)
        ma10 = sma(closes, 10)
        ma20 = sma(closes, 20)
        ma5_prev = sma(closes[:-1], 5)
        ma10_prev = sma(closes[:-1], 10)
        ma20_prev = sma(closes[:-1], 20)
        _, _, adx = dmi(highs, lows, closes, 14)
        return {
            "dif": dif, "prev_dif": prev_dif, "dea": dea, "prev_dea": prev_dea,
            "hist": hist, "prev_hist": prev_hist, "dif_series": dif_series,
            "dea_series": dea_series, "ma5": ma5, "ma10": ma10, "ma20": ma20,
            "ma5_prev": ma5_prev, "ma10_prev": ma10_prev, "ma20_prev": ma20_prev,
            "adx": adx,
        }

    def _check_exit(self, ctx, closes, highs, last):
        dif, prev_dif = ctx["dif"], ctx["prev_dif"]
        dea, prev_dea = ctx["dea"], ctx["prev_dea"]
        hist, prev_hist = ctx["hist"], ctx["prev_hist"]
        ma20 = ctx["ma20"]
        death_cross = prev_dif >= prev_dea and dif < dea
        if death_cross:
            result = {"action": "sell", "price": last["close"], "reason": "death_cross"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if self._detect_bearish_divergence(ctx["dif_series"], closes, highs):
            result = {"action": "sell", "price": last["close"], "reason": "bearish_divergence"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if last["close"] < ma20 * 0.98:
            result = {"action": "sell", "price": last["close"], "reason": "below_ma20"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if 0 < hist < prev_hist:
            result = {"action": "sell", "price": last["close"], "reason": "hist_shrinking"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        return None

    def _check_entry(self, ctx, closes, lows, vols, last):
        dif, prev_dif = ctx["dif"], ctx["prev_dif"]
        dea, prev_dea = ctx["dea"], ctx["prev_dea"]
        hist, prev_hist = ctx["hist"], ctx["prev_hist"]
        ma5, ma10, ma20 = ctx["ma5"], ctx["ma10"], ctx["ma20"]
        ma5_prev, ma10_prev, ma20_prev = ctx["ma5_prev"], ctx["ma10_prev"], ctx["ma20_prev"]
        golden_cross = prev_dif <= prev_dea and dif > dea
        zero_axis_ok = dif > 0
        hist_amplifying = hist > prev_hist and prev_hist <= 0
        ma_aligned = ma5 > ma10 > ma20
        ma_up = ma5 > ma5_prev and ma10 > ma10_prev and ma20 > ma20_prev
        vol_ma5 = sum(vols[-6:-1]) / 5
        vol_surge = last["volume"] > vol_ma5 * 1.5
        trend_ok = ctx["adx"] > self.ADX_THRESHOLD
        if not (golden_cross and zero_axis_ok and hist_amplifying and ma_aligned and vol_surge):
            conditions = {"golden_cross": golden_cross, "zero_axis_ok": zero_axis_ok, "hist_amplifying": hist_amplifying, "ma_aligned": ma_aligned, "vol_surge": vol_surge}
            self._log_entry_fail(conditions, f"date={last.get('date','')}")
            return None
        recent_low = min(lows[-10:])
        stop_loss = min(ma20 * 0.98, recent_low * 0.98)
        risk = last["close"] - stop_loss
        take_profit = last["close"] + risk * 1.5
        air_refuel = self._detect_air_refuel(ctx["dif_series"], ctx["dea_series"])
        result = {
            "action": "buy", "price": last["close"],
            "stop_loss": round(stop_loss, 3), "take_profit": round(take_profit, 3),
            "dif": round(dif, 4), "dea": round(dea, 4), "macd_hist": round(hist, 4),
            "ma5": round(ma5, 3), "ma10": round(ma10, 3), "ma20": round(ma20, 3),
            "air_refuel": air_refuel, "risk_reward": 1.5,
        }
        self._log_signal("buy", result, f"date={last.get('date','')}")
        return result

    def _detect_bearish_divergence(self, dif_series, closes, highs):
        n = self.DIVERGENCE_WINDOW
        if len(closes) < 2 * n:
            return False
        price_new_high = max(highs[-n:]) > max(highs[-2*n:-n])
        dif_no_new_high = max(dif_series[-n:]) <= max(dif_series[-2*n:-n])
        return price_new_high and dif_no_new_high

    def _detect_air_refuel(self, dif_series, dea_series, window=20):
        if len(dif_series) < window + 5:
            return False
        recent = dif_series[-window:]
        recent_dea = dea_series[-window:]
        first_cross = None
        for i in range(1, len(recent)):
            if recent[i - 1] <= recent_dea[i - 1] and recent[i] > recent_dea[i]:
                first_cross = i
                break
        if first_cross is None or first_cross >= len(recent) - 3:
            return False
        return all(d > 0 for d in recent[first_cross + 1:])

    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        if signal.get("action") != "buy":
            return Decimal("0")
        risk_per_share = Decimal(str(signal["price"])) - Decimal(str(signal["stop_loss"]))
        if risk_per_share <= 0:
            return Decimal("0")
        position = (capital * self.RISK_PER_TRADE / risk_per_share).quantize(Decimal("0.01"))
        return min(position, capital * Decimal("0.15"))

    def get_param_space(self) -> dict[str, tuple]:
        return {"fast": self.FAST_RANGE, "slow": self.SLOW_RANGE, "signal": self.SIGNAL_RANGE}

    def validate_params(self, params: dict) -> bool:
        fast = params.get("fast", 12)
        slow = params.get("slow", 26)
        signal = params.get("signal", 9)
        return (self.FAST_RANGE[0] <= fast <= self.FAST_RANGE[1]
                and self.SLOW_RANGE[0] <= slow <= self.SLOW_RANGE[1]
                and self.SIGNAL_RANGE[0] <= signal <= self.SIGNAL_RANGE[1]
                and fast < slow)