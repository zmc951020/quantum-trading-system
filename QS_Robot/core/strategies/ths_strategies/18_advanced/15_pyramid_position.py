"""战法15：金字塔加码仓位管理

来源：同花顺金融大师·高阶战法
逻辑：首次20%试仓 → 回踩20日均线确认加30% → 趋势延续加50%
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import sma


class PyramidPositionStrategy(THSBaseStrategy):
    NAME = "金字塔加码仓位"
    CATEGORY = "ths_advanced"
    RISK_LEVEL = "中"
    FIRST_PCT_RANGE = (0.1, 0.3)
    MAX_LOSS_RANGE = (0.01, 0.03)

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 30:
            return None
        first_pct = params.get("first_pct", 0.2)
        max_loss = params.get("max_loss_pct", 0.02)
        closes = [b["close"] for b in bars]
        ma20 = sma(closes, 20)
        ma60 = sma(closes, 60) if len(closes) >= 60 else ma20
        last = bars[-1]
        trend_up = ma20 > ma60 and last["close"] > ma20
        pullback_to_ma20 = abs(last["close"] - ma20) / ma20 < 0.02 if ma20 > 0 else False
        if trend_up and pullback_to_ma20:
            max_dd = 0.15
            max_position = Decimal(str(first_pct)) * (Decimal("0.02") / Decimal(str(max_dd)))
            return {
                "action": "buy",
                "price": last["close"],
                "stop_loss": round(ma20 * (1 - max_loss), 3),
                "take_profit": round(last["close"] * 1.15, 3),
                "first_pct": first_pct,
                "max_position_ratio": float(max_position),
                "stage": "first_20%",
            }
        return None

    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        if signal.get("action") != "buy":
            return Decimal("0")
        ratio = Decimal(str(signal.get("first_pct", 0.2)))
        return (capital * ratio).quantize(Decimal("0.01"))

    def get_param_space(self) -> dict[str, tuple]:
        return {"first_pct": self.FIRST_PCT_RANGE, "max_loss_pct": self.MAX_LOSS_RANGE}

    def validate_params(self, params: dict) -> bool:
        f = params.get("first_pct", 0.2)
        m = params.get("max_loss_pct", 0.02)
        return 0 < f < 1 and 0 < m < 0.1
