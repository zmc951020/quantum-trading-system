"""策略08：DMI+ADX强趋势轧空战法 — 严格数学建模版

来源：同花顺金融大师·策略战法

原策略数学模型：
  DMI系统（三线）：
    +DI = 100 × EMA(PLUS_DM, period) / ATR(period)
    -DI = 100 × EMA(MINUS_DM, period) / ATR(period)
    ADX = 100 × EMA(DX, period)  其中 DX = |+DI - -DI| / (+DI + -DI) × 100

  金叉确认：
    golden_cross = +DI(t-1) ≤ -DI(t-1) AND +DI(t) > -DI(t)

  ADX趋势突破（从低位突破阈值）：
    adx_breakout = ADX(t-1) < 20 AND ADX(t) > adx_threshold  # 趋势从弱转强
    adx_rising = ADX(t) > ADX(t-1)                            # ADX上行
    plus_above = +DI > -DI                                    # 多头方向

  成交量确认：
    vol_ok = vol(t) > MA(vol, 5) × 1.5

  均线支撑：
    ma_support = close > MA20 × 0.98

  入场条件（ALL）：
    golden_cross AND adx_breakout AND adx_rising AND plus_above
    AND vol_ok AND ma_support

  出场条件（ANY）：
    - +DI死叉-DI（+DI < -DI）
    - ADX回落（ADX < 20 且 +DI < -DI）
    - 跌破MA20
    - 高位放量滞涨（放量2倍但价格不涨）

  止损：MA20 × 0.97 或 近期低点（取较高者）
  止盈：入场价 × 1.10（短线目标10%）
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import dmi, sma


class DMIADXStrategy(THSBaseStrategy):
    ID = "08_dmi_adx_strong_trend"
    NAME = "DMI+ADX强趋势"
    CATEGORY = "ths_strategies"
    SOURCE = "同花顺金融大师"
    RISK_LEVEL = "中"

    PERIOD_RANGE = (10, 20)
    ADX_THRESHOLD_RANGE = (20, 30)
    RISK_PER_TRADE = Decimal("0.02")
    MAX_POSITION = Decimal("0.15")

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        period = params.get("dmi_period", 14)
        adx_thr = params.get("adx_threshold", 25)
        need = max(period + 5, 60)
        if len(bars) < need:
            self._log_data_short(len(bars), need)
            return None
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]
        closes = [b["close"] for b in bars]
        vols = [b["volume"] for b in bars]
        last = bars[-1]
        ctx = self._compute_indicators(highs, lows, closes, vols, period, adx_thr)
        exit_signal = self._check_exit(ctx, closes, last)
        if exit_signal:
            return exit_signal
        return self._check_entry(ctx, lows, last)

    def _compute_indicators(self, highs, lows, closes, vols, period, adx_thr):
        plus_di, minus_di, adx = dmi(highs, lows, closes, period)
        prev_plus_di, prev_minus_di, prev_adx = dmi(highs[:-1], lows[:-1], closes[:-1], period)
        golden_cross = prev_plus_di <= prev_minus_di and plus_di > minus_di
        plus_above = plus_di > minus_di
        adx_breakout = prev_adx < 20 and adx > adx_thr
        adx_rising = adx > prev_adx
        ma20 = sma(closes, 20)
        ma_support = closes[-1] > ma20 * 0.98
        vol_ma5 = sma(vols, 5)
        vol_ok = vols[-1] > vol_ma5 * 1.5 if vol_ma5 > 0 else False
        prev_adx2 = dmi(highs[:-2], lows[:-2], closes[:-2], period)[2]
        return {
            "plus_di": plus_di, "minus_di": minus_di, "adx": adx,
            "prev_plus_di": prev_plus_di, "prev_minus_di": prev_minus_di,
            "prev_adx": prev_adx, "prev_adx2": prev_adx2,
            "golden_cross": golden_cross, "plus_above": plus_above,
            "adx_breakout": adx_breakout, "adx_rising": adx_rising,
            "ma20": ma20, "ma_support": ma_support, "vol_ok": vol_ok,
            "vol_ma5": vol_ma5,
        }

    def _check_exit(self, ctx, closes, last):
        plus_di, minus_di = ctx["plus_di"], ctx["minus_di"]
        adx = ctx["adx"]
        ma20 = ctx["ma20"]
        if plus_di < minus_di:
            result = {"action": "sell", "price": last["close"], "reason": "di_death"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if adx < 20 and plus_di < minus_di:
            result = {"action": "sell", "price": last["close"], "reason": "adx_weak"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if last["close"] < ma20 * 0.97:
            result = {"action": "sell", "price": last["close"], "reason": "below_ma20"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if last["volume"] > ctx["vol_ma5"] * 2.5 and abs(last["close"] - closes[-2]) / closes[-2] < 0.01:
            result = {"action": "sell", "price": last["close"], "reason": "distribution"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        return None

    def _check_entry(self, ctx, lows, last):
        if not (ctx["golden_cross"] and ctx["adx_breakout"] and ctx["adx_rising"]
                and ctx["plus_above"] and ctx["vol_ok"] and ctx["ma_support"]):
            conditions = {"golden_cross": ctx["golden_cross"], "adx_breakout": ctx["adx_breakout"], "adx_rising": ctx["adx_rising"], "plus_above": ctx["plus_above"], "vol_ok": ctx["vol_ok"], "ma_support": ctx["ma_support"]}
            self._log_entry_fail(conditions, f"date={last.get('date','')}")
            return None
        price = last["close"]
        recent_low = min(lows[-10:])
        stop_loss = max(ctx["ma20"] * 0.97, recent_low * 0.97)
        take_profit = price * 1.10
        result = {
            "action": "buy", "price": price,
            "stop_loss": round(stop_loss, 3), "take_profit": round(take_profit, 3),
            "plus_di": round(ctx["plus_di"], 2), "minus_di": round(ctx["minus_di"], 2),
            "adx": round(ctx["adx"], 2), "ma20": round(ctx["ma20"], 3),
            "vol_ratio": round(last["volume"] / ctx["vol_ma5"], 2) if ctx["vol_ma5"] > 0 else 0,
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
        return {"dmi_period": self.PERIOD_RANGE, "adx_threshold": self.ADX_THRESHOLD_RANGE}

    def validate_params(self, params: dict) -> bool:
        p = params.get("dmi_period", 14)
        a = params.get("adx_threshold", 25)
        return (self.PERIOD_RANGE[0] <= p <= self.PERIOD_RANGE[1]
                and self.ADX_THRESHOLD_RANGE[0] <= a <= self.ADX_THRESHOLD_RANGE[1])