"""策略02：周线突破战法

来源：同花顺金融大师·策略战法
逻辑：周线突破15周箱体高点 + 5周均线上穿20周均线 + 量能配合
胜率：据课程数据，标准周线突破形态后续延续上涨概率78%+
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy


def _sma(values: list[float], period: int) -> float:
    if len(values) < period:
        return 0.0
    return sum(values[-period:]) / period


class WeeklyBreakoutStrategy(THSBaseStrategy):
    """周线突破：箱体突破+均线多头+量能配合"""
    NAME = "周线突破战法"
    CATEGORY = "ths_strategies"
    SOURCE = "同花顺金融大师"
    RISK_LEVEL = "中"

    BOX_WEEKS_RANGE = (10, 20)
    MA_SHORT_RANGE = (3, 10)
    MA_LONG_RANGE = (15, 30)

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        box_weeks = params.get("box_weeks", 15)
        ma_short = params.get("ma_short", 5)
        ma_long = params.get("ma_long", 20)
        if len(bars) < box_weeks + 1:
            return None
        box_high = max(b["high"] for b in bars[-(box_weeks + 1):-1])
        last_bar = bars[-1]
        closes = [b["close"] for b in bars]
        sma_s = _sma(closes, ma_short)
        sma_l = _sma(closes, ma_long)
        golden_cross = sma_s > sma_l and sma_s > 0
        breakout = last_bar["close"] > box_high
        vol_avg = sum(b["volume"] for b in bars[-box_weeks:]) / box_weeks
        vol_ok = last_bar["volume"] > vol_avg
        if breakout and golden_cross and vol_ok:
            price = last_bar["close"]
            return {
                "action": "buy",
                "price": price,
                "stop_loss": round(box_high * 0.97, 3),
                "take_profit": round(price * 1.15, 3),
                "box_high": box_high,
                "sma_short": round(sma_s, 3),
                "sma_long": round(sma_l, 3),
            }
        return None

    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        if signal.get("action") != "buy":
            return Decimal("0")
        return (capital * Decimal("0.15")).quantize(Decimal("0.01"))

    def get_param_space(self) -> dict[str, tuple]:
        return {
            "box_weeks": self.BOX_WEEKS_RANGE,
            "ma_short": self.MA_SHORT_RANGE,
            "ma_long": self.MA_LONG_RANGE,
        }

    def validate_params(self, params: dict) -> bool:
        bw = params.get("box_weeks", 15)
        ms = params.get("ma_short", 5)
        ml = params.get("ma_long", 20)
        if not (self.BOX_WEEKS_RANGE[0] <= bw <= self.BOX_WEEKS_RANGE[1]):
            return False
        if not (self.MA_SHORT_RANGE[0] <= ms <= self.MA_SHORT_RANGE[1]):
            return False
        if not (self.MA_LONG_RANGE[0] <= ml <= self.MA_LONG_RANGE[1]):
            return False
        return ms < ml
