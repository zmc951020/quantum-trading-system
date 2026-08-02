"""策略01：MACD顺势波段交易战法

来源：同花顺金融大师·策略战法
逻辑：MACD四要素（零轴+DIF+DEA+柱状线），零轴上方金叉顺势做多
数学：DIF = EMA(fast) - EMA(slow); DEA = EMA(DIF, signal); MACD柱 = 2*(DIF-DEA)
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    k = 2 / (period + 1)
    ema = [values[0]]
    for v in values[1:]:
        ema.append(v * k + ema[-1] * (1 - k))
    return ema


class MACDWaveStrategy(THSBaseStrategy):
    """MACD顺势波段：零轴上方金叉做多"""
    NAME = "MACD顺势波段"
    CATEGORY = "ths_strategies"
    SOURCE = "同花顺金融大师"
    RISK_LEVEL = "中"

    FAST_RANGE = (5, 30)
    SLOW_RANGE = (20, 40)
    SIGNAL_RANGE = (5, 15)

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 60:
            return None
        fast = params.get("fast", 12)
        slow = params.get("slow", 26)
        signal = params.get("signal", 9)
        closes = [b["close"] for b in bars]
        ema_fast = _ema(closes, fast)
        ema_slow = _ema(closes, slow)
        dif = ema_fast[-1] - ema_slow[-1]
        prev_dif = ema_fast[-2] - ema_slow[-2]
        dif_series = [ema_fast[i] - ema_slow[i] for i in range(slow, len(closes))]
        if len(dif_series) < signal:
            return None
        dea_series = _ema(dif_series, signal)
        dea = dea_series[-1]
        prev_dea = dea_series[-2]
        macd_hist = 2 * (dif - dea)
        golden_cross = prev_dif < prev_dea and dif > dea
        zero_axis_ok = dif > 0
        if golden_cross and zero_axis_ok and macd_hist > 0:
            price = closes[-1]
            return {
                "action": "buy",
                "price": price,
                "stop_loss": round(price * 0.98, 3),
                "take_profit": round(price * 1.03, 3),
                "dif": round(dif, 4),
                "dea": round(dea, 4),
                "macd_hist": round(macd_hist, 4),
            }
        return None

    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        if signal.get("action") != "buy":
            return Decimal("0")
        return (capital * Decimal("0.1")).quantize(Decimal("0.01"))

    def get_param_space(self) -> dict[str, tuple]:
        return {"fast": self.FAST_RANGE, "slow": self.SLOW_RANGE, "signal": self.SIGNAL_RANGE}

    def validate_params(self, params: dict) -> bool:
        fast = params.get("fast", 12)
        slow = params.get("slow", 26)
        signal = params.get("signal", 9)
        if not (self.FAST_RANGE[0] <= fast <= self.FAST_RANGE[1]):
            return False
        if not (self.SLOW_RANGE[0] <= slow <= self.SLOW_RANGE[1]):
            return False
        if not (self.SIGNAL_RANGE[0] <= signal <= self.SIGNAL_RANGE[1]):
            return False
        return fast < slow
