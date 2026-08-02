"""单均线回踩低吸基类

策略 10/11/12/13 共享逻辑：
  - 股价在均线上方运行
  - 均线向上
  - 回调N日至均线附近缩量收阳不破

子类只需覆盖 MA_PERIOD / PULLBACK_DAYS / NAME / RISK_LEVEL / POSITION_RATIO
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import sma


class MAPullbackBase(THSBaseStrategy):
    MA_PERIOD: int = 10
    PULLBACK_DAYS: int = 2
    POSITION_RATIO: Decimal = Decimal("0.10")
    MA_PERIOD_RANGE: tuple[int, int] = (3, 120)

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        period = params.get("ma_period", self.MA_PERIOD)
        need = period + self.PULLBACK_DAYS + 2
        if len(bars) < need:
            return None
        closes = [b["close"] for b in bars]
        vols = [b["volume"] for b in bars]
        ma_now = sma(closes, period)
        ma_prev = sma(closes[:-1], period)
        ma_up = ma_now > ma_prev
        last = bars[-1]
        above_ma = last["close"] > ma_now
        recent_closes = closes[-(self.PULLBACK_DAYS + 1):-1]
        pullback_ok = all(c <= ma_now * 1.02 for c in recent_closes)
        vol_avg = sum(vols[-(period + 5):-1]) / (period + 5)
        vol_shrink = last["volume"] < vol_avg * 0.9
        bullish_candle = last["close"] > last["open"]
        hold_ma = last["low"] > ma_now * 0.98
        if ma_up and above_ma and pullback_ok and vol_shrink and bullish_candle and hold_ma:
            return {
                "action": "buy",
                "price": last["close"],
                "stop_loss": round(ma_now * 0.98, 3),
                "take_profit": round(last["close"] * 1.05, 3),
                "ma": round(ma_now, 3),
                "ma_period": period,
            }
        return None

    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        if signal.get("action") != "buy":
            return Decimal("0")
        return (capital * self.POSITION_RATIO).quantize(Decimal("0.01"))

    def get_param_space(self) -> dict[str, tuple]:
        return {"ma_period": self.MA_PERIOD_RANGE}

    def validate_params(self, params: dict) -> bool:
        p = params.get("ma_period", self.MA_PERIOD)
        lo, hi = self.MA_PERIOD_RANGE
        return lo <= p <= hi
