"""战法17：网格交易套利

来源：同花顺金融大师·高阶战法
逻辑：震荡区间内网格买卖，每档0.5-1元
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import sma, boll


class GridTradingStrategy(THSBaseStrategy):
    NAME = "网格交易套利"
    CATEGORY = "ths_advanced"
    RISK_LEVEL = "低"
    GRID_STEP_RANGE = (0.3, 1.5)
    GRID_RANGE_RANGE = (5, 20)

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 25:
            return None
        grid_step = params.get("grid_step", 0.5)
        last = bars[-1]
        closes = [b["close"] for b in bars]
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
        if in_range and range_ok and crossed_down:
            return {
                "action": "buy",
                "price": last["close"],
                "stop_loss": round(grid_low * 0.97, 3),
                "take_profit": round(last["close"] + grid_step, 3),
                "grid_level": level_idx,
                "total_levels": levels,
            }
        return None

    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        if signal.get("action") != "buy":
            return Decimal("0")
        return (capital * Decimal("0.05")).quantize(Decimal("0.01"))

    def get_param_space(self) -> dict[str, tuple]:
        return {"grid_step": self.GRID_STEP_RANGE, "grid_range": self.GRID_RANGE_RANGE}

    def validate_params(self, params: dict) -> bool:
        g = params.get("grid_step", 0.5)
        r = params.get("grid_range", 10)
        return g > 0 and r > 0
