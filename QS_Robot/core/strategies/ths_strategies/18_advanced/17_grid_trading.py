"""战法17：网格交易套利 — 严格数学建模版

来源：同花顺金融大师·高阶战法
逻辑：震荡区间内网格买卖，每档0.5-1元
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import sma, boll, dmi


class GridTradingStrategy(THSBaseStrategy):
    ID = "17_grid_trading"
    NAME = "网格交易套利"
    CATEGORY = "ths_advanced"
    SOURCE = "同花顺金融大师"
    RISK_LEVEL = "低"
    GRID_STEP_RANGE = (0.3, 1.5)
    GRID_RANGE_RANGE = (5, 20)
    TREND_FILTER_THRESHOLD = 25  # ADX > 25 视为趋势行情，禁用网格
    RISK_PER_TRADE = Decimal("0.01")
    MAX_POSITION = Decimal("0.10")

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 25:
            self._log_data_short(len(bars), 25)
            return None
        grid_step = params.get("grid_step", 0.5)
        closes = [b["close"] for b in bars]
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]
        last = bars[-1]
        ctx = self._compute_indicators(closes, last, grid_step)
        if ctx is None:
            return None
        # 趋势过滤：ADX > 25 视为趋势行情，禁用网格策略
        try:
            _, _, adx = dmi(highs, lows, closes, 14)
            ctx["trend_strong"] = adx > self.TREND_FILTER_THRESHOLD
            ctx["adx"] = round(adx, 2)
        except Exception:
            ctx["trend_strong"] = False
            ctx["adx"] = 0.0
        exit_signal = self._check_exit(ctx, closes, last)
        if exit_signal:
            return exit_signal
        entry_signal = self._check_entry(ctx, last)
        return self._apply_meta_filter(entry_signal, bars)

    def _compute_indicators(self, closes, last, grid_step):
        upper, mid, lower = boll(closes, 20, 2)
        if mid <= 0:
            return None
        in_range = lower < last["close"] < upper
        range_width = (upper - lower) / mid
        range_ok = 0.05 < range_width < 0.30
        grid_low = lower
        grid_high = upper
        levels = int((grid_high - grid_low) / grid_step)
        if levels < 3:
            return None
        level_idx = int((last["close"] - grid_low) / grid_step)
        prev_close = closes[-2]
        prev_idx = int((prev_close - grid_low) / grid_step)
        crossed_down = level_idx < prev_idx
        return {
            "in_range": in_range, "range_ok": range_ok, "crossed_down": crossed_down,
            "grid_low": grid_low, "grid_high": grid_high, "grid_step": grid_step,
            "level_idx": level_idx, "levels": levels, "lower": lower, "upper": upper,
        }

    def _check_exit(self, ctx, closes, last):
        if last["close"] > ctx["upper"]:
            result = {"action": "sell", "price": last["close"], "reason": "touch_upper"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if last["close"] < ctx["lower"] * 0.97:
            result = {"action": "sell", "price": last["close"], "reason": "break_lower"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        return None

    def _check_entry(self, ctx, last):
        # 趋势过滤：趋势行情（ADX>25）禁用网格
        if ctx.get("trend_strong", False):
            self._log_entry_fail(
                {"trend_strong": True, "adx": ctx.get("adx", 0)},
                f"date={last.get('date','')} 趋势过强跳过网格"
            )
            return None
        if not (ctx["in_range"] and ctx["range_ok"] and ctx["crossed_down"]):
            conditions = {"in_range": ctx["in_range"], "range_ok": ctx["range_ok"],
                          "crossed_down": ctx["crossed_down"]}
            self._log_entry_fail(conditions, f"date={last.get('date','')}")
            return None
        result = {
            "action": "buy", "price": last["close"],
            "stop_loss": round(ctx["grid_low"] * 0.97, 3),
            "take_profit": round(last["close"] + ctx["grid_step"], 3),
            "grid_level": ctx["level_idx"], "total_levels": ctx["levels"],
            "adx": ctx.get("adx", 0),
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
        return {"grid_step": self.GRID_STEP_RANGE, "grid_range": self.GRID_RANGE_RANGE}

    def validate_params(self, params: dict) -> bool:
        g = params.get("grid_step", 0.5)
        r = params.get("grid_range", 10)
        return g > 0 and r > 0