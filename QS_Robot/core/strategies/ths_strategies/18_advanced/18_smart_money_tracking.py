"""战法18：主力筹码控盘综合 — 严格数学建模版

来源：同花顺金融大师·高阶战法
逻辑：夹板单+大单托底+走势独立+DDY红柱+35-45度匀速上涨+振幅<3%
"""
import math
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import sma, ema


class SmartMoneyTrackingStrategy(THSBaseStrategy):
    ID = "18_smart_money_tracking"
    NAME = "主力筹码控盘综合"
    CATEGORY = "ths_advanced"
    SOURCE = "同花顺金融大师"
    RISK_LEVEL = "中"
    ANGLE_RANGE = (30, 50)
    AMPLITUDE_MAX_RANGE = (0.02, 0.05)
    RISK_PER_TRADE = Decimal("0.02")
    MAX_POSITION = Decimal("0.15")

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 30:
            self._log_data_short(len(bars), 30)
            return None
        angle_min = params.get("angle_min", 35)
        angle_max = params.get("angle_max", 45)
        amp_max = params.get("amplitude_max", 0.03)
        closes = [b["close"] for b in bars]
        last = bars[-1]
        ctx = self._compute_indicators(closes, last, angle_min, angle_max, amp_max)
        exit_signal = self._check_exit(ctx, closes, last)
        if exit_signal:
            return exit_signal
        return self._check_entry(ctx, last)

    def _compute_indicators(self, closes, last, angle_min, angle_max, amp_max):
        ma10 = sma(closes, 10)
        ma20 = sma(closes, 20)
        recent = closes[-20:]
        if recent[0] <= 0:
            return None
        slope = (recent[-1] - recent[0]) / recent[0] / 20
        angle_degrees = math.degrees(math.atan(slope * 100))
        angle_ok = angle_min <= angle_degrees <= angle_max
        amplitude = (last["high"] - last["low"]) / last["close"]
        amp_ok = amplitude < amp_max
        sandwich = last.get("sandwich_order", False)
        big_support = last.get("big_order_support", False)
        ddy = last.get("ddy", 0)
        ddy_red = ddy > 0
        independent = last.get("independent_trend", False)
        dif_series = [fa - sl for fa, sl in zip(ema(closes, 12), ema(closes, 26))]
        dea_series = ema(dif_series, 9) if len(dif_series) >= 9 else dif_series
        dif = dif_series[-1]
        prev_dif = dif_series[-2] if len(dif_series) >= 2 else 0
        dea = dea_series[-1]
        prev_dea = dea_series[-2] if len(dea_series) >= 2 else 0
        return {
            "angle_ok": angle_ok, "amp_ok": amp_ok, "sandwich": sandwich,
            "big_support": big_support, "ddy_red": ddy_red, "independent": independent,
            "angle_degrees": angle_degrees, "amplitude": amplitude,
            "ma10": ma10, "ma20": ma20,
            "dif": dif, "prev_dif": prev_dif, "dea": dea, "prev_dea": prev_dea,
        }

    def _check_exit(self, ctx, closes, last):
        if last["close"] < ctx["ma10"] * 0.97:
            result = {"action": "sell", "price": last["close"], "reason": "below_ma10"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if ctx["prev_dif"] >= ctx["prev_dea"] and ctx["dif"] < ctx["dea"]:
            result = {"action": "sell", "price": last["close"], "reason": "macd_death"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        return None

    def _check_entry(self, ctx, last):
        if not (ctx["sandwich"] and ctx["big_support"] and ctx["ddy_red"]
                and ctx["independent"] and ctx["angle_ok"] and ctx["amp_ok"]):
            conditions = {"sandwich": ctx["sandwich"], "big_support": ctx["big_support"],
                          "ddy_red": ctx["ddy_red"], "independent": ctx["independent"],
                          "angle_ok": ctx["angle_ok"], "amp_ok": ctx["amp_ok"]}
            self._log_entry_fail(conditions, f"date={last.get('date','')}")
            return None
        result = {
            "action": "buy", "price": last["close"],
            "stop_loss": round(ctx["ma10"] * 0.97, 3),
            "take_profit": round(last["close"] * 1.15, 3),
            "angle": round(ctx["angle_degrees"], 1), "amplitude": round(ctx["amplitude"], 4),
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
        return {"angle_min": self.ANGLE_RANGE, "amplitude_max": self.AMPLITUDE_MAX_RANGE}

    def validate_params(self, params: dict) -> bool:
        a = params.get("angle_min", 35)
        amp = params.get("amplitude_max", 0.03)
        return self.ANGLE_RANGE[0] <= a <= self.ANGLE_RANGE[1] and 0 < amp < 0.1