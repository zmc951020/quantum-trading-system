"""战法13：15/30分钟超短战法

来源：同花顺金融大师·高阶战法
逻辑：15分钟MACD金叉 + 30分钟均线支撑 + 5日线上方运行
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import macd, sma


class MinuteKlineShortStrategy(THSBaseStrategy):
    NAME = "15/30分钟超短"
    ID = "13_minute_kline_short"
    CATEGORY = "ths_advanced"
    RISK_LEVEL = "高"
    FAST_RANGE = (5, 15)
    SLOW_RANGE = (15, 30)

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 40:
            return None
        fast = params.get("fast", 12)
        slow = params.get("slow", 26)
        closes = [b["close"] for b in bars]
        dif, dea, hist = macd(closes, fast, slow, 9)
        golden_cross = dif > dea and hist > 0
        ma30 = sma(closes, 30)
        ma5 = sma(closes, 5)
        ma30_support = closes[-1] > ma30 * 0.99
        above_ma5 = closes[-1] > ma5
        last = bars[-1]
        if golden_cross and ma30_support and above_ma5:
            return {
                "action": "buy",
                "price": last["close"],
                "stop_loss": round(ma30 * 0.99, 3),
                "take_profit": round(last["close"] * 1.03, 3),
                "dif": round(dif, 4),
                "dea": round(dea, 4),
            }
        return None

    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        if signal.get("action") != "buy":
            return Decimal("0")
        return (capital * Decimal("0.06")).quantize(Decimal("0.01"))

    def get_param_space(self) -> dict[str, tuple]:
        return {"fast": self.FAST_RANGE, "slow": self.SLOW_RANGE}

    def validate_params(self, params: dict) -> bool:
        f = params.get("fast", 12)
        s = params.get("slow", 26)
        return self.FAST_RANGE[0] <= f <= self.FAST_RANGE[1] and self.SLOW_RANGE[0] <= s <= self.SLOW_RANGE[1] and f < s
