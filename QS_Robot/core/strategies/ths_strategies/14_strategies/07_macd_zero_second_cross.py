"""策略07：MACD零轴上方二次金叉战法

来源：同花顺金融大师·策略战法
逻辑：DIF在零轴上方首次上穿DEA → 回调不破零轴 → 再次金叉（空中加油）
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import macd


class MACDZeroSecondCrossStrategy(THSBaseStrategy):
    NAME = "MACD零轴二次金叉"
    ID = "07_macd_zero_second_cross"
    RISK_LEVEL = "中"
    FAST_RANGE = (5, 30)
    SLOW_RANGE = (20, 40)
    SIGNAL_RANGE = (5, 15)

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        fast = params.get("fast", 12)
        slow = params.get("slow", 26)
        signal = params.get("signal", 9)
        if len(bars) < slow + signal + 10:
            return None
        closes = [b["close"] for b in bars]
        ema_f = []
        k = 2 / (fast + 1)
        for i, c in enumerate(closes):
            ema_f.append(c * k + ema_f[-1] * (1 - k) if ema_f else c)
        ema_s = []
        k2 = 2 / (slow + 1)
        for i, c in enumerate(closes):
            ema_s.append(c * k2 + ema_s[-1] * (1 - k2) if ema_s else c)
        dif_series = [ema_f[i] - ema_s[i] for i in range(len(closes))]
        dea_series = []
        k3 = 2 / (signal + 1)
        for i, d in enumerate(dif_series):
            dea_series.append(d * k3 + dea_series[-1] * (1 - k3) if dea_series else d)
        window = 15
        cross_count = 0
        zero_axis_held = True
        for i in range(max(slow, len(dif_series) - window), len(dif_series) - 1):
            if dif_series[i] <= 0:
                zero_axis_held = False
            if dif_series[i] > dea_series[i] and dif_series[i - 1] <= dea_series[i - 1]:
                cross_count += 1
        curr_cross = dif_series[-1] > dea_series[-1] and dif_series[-2] <= dea_series[-2]
        above_zero = dif_series[-1] > 0
        hist = 2 * (dif_series[-1] - dea_series[-1])
        last = bars[-1]
        vol_ok = last["volume"] > sum(b["volume"] for b in bars[-5:-1]) / 4
        if cross_count >= 1 and curr_cross and above_zero and zero_axis_held and vol_ok and hist > 0:
            return {
                "action": "buy",
                "price": last["close"],
                "stop_loss": round(min(closes[-10:]) * 0.98, 3),
                "take_profit": round(last["close"] * 1.10, 3),
                "dif": round(dif_series[-1], 4),
                "dea": round(dea_series[-1], 4),
                "hist": round(hist, 4),
            }
        return None

    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        if signal.get("action") != "buy":
            return Decimal("0")
        return (capital * Decimal("0.12")).quantize(Decimal("0.01"))

    def get_param_space(self) -> dict[str, tuple]:
        return {"fast": self.FAST_RANGE, "slow": self.SLOW_RANGE, "signal": self.SIGNAL_RANGE}

    def validate_params(self, params: dict) -> bool:
        f = params.get("fast", 12)
        s = params.get("slow", 26)
        sig = params.get("signal", 9)
        if not (self.FAST_RANGE[0] <= f <= self.FAST_RANGE[1]):
            return False
        if not (self.SLOW_RANGE[0] <= s <= self.SLOW_RANGE[1]):
            return False
        if not (self.SIGNAL_RANGE[0] <= sig <= self.SIGNAL_RANGE[1]):
            return False
        return f < s
