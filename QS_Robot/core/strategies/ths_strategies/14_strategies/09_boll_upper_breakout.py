"""策略09：BOLL上轨顺势突破 — 严格数学建模版

来源：同花顺金融大师·策略战法

原策略数学模型：
  BOLL系统：
    MID = SMA(close, period)
    UPPER = MID + std × σ
    LOWER = MID - std × σ
    bandwidth = UPPER - LOWER

  中轨向上：
    mid_up = MID(t) > MID(t-1)

  站上上轨：
    above_upper = close > UPPER

  开口放大（带宽持续扩张）：
    widening = bandwidth(t) > bandwidth(t-1) > bandwidth(t-2)

  成交量确认：
    vol_ok = vol(t) > MA(vol, 5) × 1.5

  趋势确认：
    adx_ok = ADX(14) > 20

  入场条件（ALL）：
    mid_up AND above_upper AND widening AND vol_ok AND adx_ok

  出场条件（ANY）：
    - 跌破中轨（close < MID）
    - 开口缩小（带宽连续缩小）
    - 跌破MA20
    - 高位放量滞涨

  止损：MID × 0.98
  止盈：入场价 × 1.12（波段目标12%）
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import boll, sma, dmi


class BollUpperBreakoutStrategy(THSBaseStrategy):
    ID = "09_boll_upper_breakout"
    NAME = "BOLL上轨突破"
    CATEGORY = "ths_strategies"
    SOURCE = "同花顺金融大师"
    RISK_LEVEL = "中"

    PERIOD_RANGE = (15, 30)
    STD_RANGE = (1.5, 2.5)
    VOL_RATIO_RANGE = (1.2, 2.0)
    ADX_THRESHOLD = 20
    RISK_PER_TRADE = Decimal("0.02")
    MAX_POSITION = Decimal("0.15")

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        period = params.get("boll_period", 20)
        std = params.get("boll_std", 2)
        vol_ratio = params.get("vol_ratio", 1.5)
        need = max(period + 5, 60)
        if len(bars) < need:
            self._log_data_short(len(bars), need)
            return None
        closes = [b["close"] for b in bars]
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]
        vols = [b["volume"] for b in bars]
        last = bars[-1]
        ctx = self._compute_indicators(closes, highs, lows, vols, period, std, vol_ratio)
        exit_signal = self._check_exit(ctx, closes, last)
        if exit_signal:
            return exit_signal
        return self._check_entry(ctx, last)

    def _compute_indicators(self, closes, highs, lows, vols, period, std, vol_ratio):
        upper, mid, lower = boll(closes, period, std)
        upper_p, mid_p, lower_p = boll(closes[:-1], period, std)
        upper_p2, _, lower_p2 = boll(closes[:-2], period, std)
        mid_up = mid > mid_p
        above_upper = closes[-1] > upper
        bw = upper - lower
        bw_p = upper_p - lower_p
        bw_p2 = upper_p2 - lower_p2
        widening = bw > bw_p and bw_p > bw_p2
        vol_ma5 = sma(vols, 5)
        vol_ok = vols[-1] > vol_ma5 * vol_ratio if vol_ma5 > 0 else False
        _, _, adx = dmi(highs, lows, closes, 14)
        ma20 = sma(closes, 20)
        return {
            "upper": upper, "mid": mid, "lower": lower,
            "mid_up": mid_up, "above_upper": above_upper,
            "bw": bw, "widening": widening, "vol_ok": vol_ok,
            "adx": adx, "ma20": ma20, "vol_ma5": vol_ma5,
        }

    def _check_exit(self, ctx, closes, last):
        mid = ctx["mid"]
        ma20 = ctx["ma20"]
        if last["close"] < mid:
            result = {"action": "sell", "price": last["close"], "reason": "below_mid"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if last["close"] < ma20 * 0.97:
            result = {"action": "sell", "price": last["close"], "reason": "below_ma20"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if last["volume"] > ctx["vol_ma5"] * 2.5 and last["close"] < closes[-2]:
            result = {"action": "sell", "price": last["close"], "reason": "heavy_sell"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        return None

    def _check_entry(self, ctx, last):
        if not (ctx["mid_up"] and ctx["above_upper"] and ctx["widening"]
                and ctx["vol_ok"] and ctx["adx"] > self.ADX_THRESHOLD):
            conditions = {"mid_up": ctx["mid_up"], "above_upper": ctx["above_upper"], "widening": ctx["widening"], "vol_ok": ctx["vol_ok"], "adx_ok": ctx["adx"] > self.ADX_THRESHOLD}
            self._log_entry_fail(conditions, f"date={last.get('date','')}")
            return None
        price = last["close"]
        stop_loss = ctx["mid"] * 0.98
        take_profit = price * 1.12
        result = {
            "action": "buy", "price": price,
            "stop_loss": round(stop_loss, 3), "take_profit": round(take_profit, 3),
            "upper": round(ctx["upper"], 3), "mid": round(ctx["mid"], 3),
            "lower": round(ctx["lower"], 3), "adx": round(ctx["adx"], 1),
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
        return {
            "boll_period": self.PERIOD_RANGE,
            "boll_std": self.STD_RANGE,
            "vol_ratio": self.VOL_RATIO_RANGE,
        }

    def validate_params(self, params: dict) -> bool:
        p = params.get("boll_period", 20)
        s = params.get("boll_std", 2)
        v = params.get("vol_ratio", 1.5)
        return (self.PERIOD_RANGE[0] <= p <= self.PERIOD_RANGE[1]
                and self.STD_RANGE[0] <= s <= self.STD_RANGE[1]
                and self.VOL_RATIO_RANGE[0] <= v <= self.VOL_RATIO_RANGE[1])