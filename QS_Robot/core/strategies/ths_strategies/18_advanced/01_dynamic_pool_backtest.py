"""战法01：动态股池+策略回测闭环

来源：同花顺金融大师·高阶战法
逻辑：多条件动态过滤（风险排雷+基本面+技术），满足全部条件纳入股池
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import sma


class DynamicPoolBacktestStrategy(THSBaseStrategy):
    NAME = "动态股池回测闭环"
    CATEGORY = "ths_advanced"
    RISK_LEVEL = "中"
    FILTER_COUNT_RANGE = (6, 12)

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 60:
            return None
        closes = [b["close"] for b in bars]
        vols = [b["volume"] for b in bars]
        ma20 = sma(closes, 20)
        ma60 = sma(closes, 60)
        last = bars[-1]
        not_st = last.get("is_st", False) is False
        listed_ok = len(bars) >= 250
        ma_bullish = ma20 > ma60 and last["close"] > ma20
        vol_stable = last["volume"] > sma(vols, 20) * 0.8
        profit_ok = last.get("profit_growth", 0) > 0
        cap_ok = 20 <= last.get("market_cap", 30) <= 80
        if not_st and listed_ok and ma_bullish and vol_stable and profit_ok and cap_ok:
            return {
                "action": "buy",
                "price": last["close"],
                "stop_loss": round(ma20 * 0.95, 3),
                "take_profit": round(last["close"] * 1.15, 3),
                "filters_passed": 6,
            }
        return None

    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        if signal.get("action") != "buy":
            return Decimal("0")
        return (capital * Decimal("0.10")).quantize(Decimal("0.01"))

    def get_param_space(self) -> dict[str, tuple]:
        return {"filter_count": self.FILTER_COUNT_RANGE}

    def validate_params(self, params: dict) -> bool:
        f = params.get("filter_count", 8)
        lo, hi = self.FILTER_COUNT_RANGE
        return lo <= f <= hi
