"""战法08：成交量阶梯战法

来源：同花顺金融大师·高阶战法
逻辑：首轮突破量>20日均量2倍 → 回调缩量至50% → 二次放大30%以上
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import sma


class VolumeLadderStrategy(THSBaseStrategy):
    NAME = "成交量阶梯"
    CATEGORY = "ths_advanced"
    RISK_LEVEL = "中"
    FIRST_VOL_RANGE = (1.5, 3.0)
    PULLBACK_VOL_RANGE = (0.3, 0.6)
    SECOND_VOL_RANGE = (1.2, 1.8)

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 30:
            return None
        first_ratio = params.get("first_vol_ratio", 2)
        pullback_pct = params.get("pullback_vol_pct", 0.5)
        second_ratio = params.get("second_vol_ratio", 1.3)
        vols = [b["volume"] for b in bars]
        closes = [b["close"] for b in bars]
        avg20 = sma(vols, 20)
        if avg20 <= 0:
            return None
        last = bars[-1]
        prev = bars[-2]
        first_break_idx = None
        for i in range(len(vols) - 10, len(vols) - 2):
            if vols[i] > avg20 * first_ratio and closes[i] > closes[i - 1]:
                first_break_idx = i
                break
        if first_break_idx is None:
            return None
        pullback_vols = vols[first_break_idx + 1:-1]
        pullback_ok = all(v < avg20 * pullback_pct for v in pullback_vols) if pullback_vols else False
        last_vol_ratio = last["volume"] / avg20
        second_surge = last_vol_ratio > second_ratio
        bullish_candle = last["close"] > prev["close"]
        if pullback_ok and second_surge and bullish_candle:
            return {
                "action": "buy",
                "price": last["close"],
                "stop_loss": round(min(b["low"] for b in bars[first_break_idx:]) * 0.97, 3),
                "take_profit": round(last["close"] * 1.15, 3),
                "first_break_idx": first_break_idx,
                "last_vol_ratio": round(last_vol_ratio, 2),
            }
        return None

    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        if signal.get("action") != "buy":
            return Decimal("0")
        return (capital * Decimal("0.12")).quantize(Decimal("0.01"))

    def get_param_space(self) -> dict[str, tuple]:
        return {
            "first_vol_ratio": self.FIRST_VOL_RANGE,
            "pullback_vol_pct": self.PULLBACK_VOL_RANGE,
            "second_vol_ratio": self.SECOND_VOL_RANGE,
        }

    def validate_params(self, params: dict) -> bool:
        f = params.get("first_vol_ratio", 2)
        p = params.get("pullback_vol_pct", 0.5)
        s = params.get("second_vol_ratio", 1.3)
        return f > 1 and 0 < p < 1 and s > 1
