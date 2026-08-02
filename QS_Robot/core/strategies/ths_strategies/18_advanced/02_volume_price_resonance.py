"""战法02：主力量价操盘解析

来源：同花顺金融大师·高阶战法
逻辑：吸筹-洗盘-拉升-出货周期，低位倍量突破+量能维持+均线多头+主力净流入
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import sma


class VolumePriceResonanceStrategy(THSBaseStrategy):
    NAME = "主力量价操盘"
    ID = "02_volume_price_resonance"
    CATEGORY = "ths_advanced"
    RISK_LEVEL = "中"
    VOL_RATIO_RANGE = (1.5, 3.0)
    VOL_MAINTAIN_RANGE = (0.5, 0.8)

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 30:
            return None
        vol_ratio_min = params.get("vol_ratio_min", 2)
        vol_maintain = params.get("vol_maintain_pct", 0.6)
        last = bars[-1]
        vols = [b["volume"] for b in bars]
        avg20 = sma(vols, 20)
        if avg20 <= 0:
            return None
        vol_ratio = last["volume"] / avg20
        recent3_vol = sum(b["volume"] for b in bars[-4:-1]) / 3
        vol_hold = recent3_vol > avg20 * vol_maintain
        closes = [b["close"] for b in bars]
        ma5 = sma(closes, 5)
        ma10 = sma(closes, 10)
        ma20 = sma(closes, 20)
        bullish = ma5 > ma10 > ma20
        low_pos = last["close"] < sma(closes, 60) * 1.1 if len(closes) >= 60 else True
        main_inflow = last.get("main_net_inflow", 0) > 0
        if vol_ratio > vol_ratio_min and vol_hold and bullish and low_pos and main_inflow:
            return {
                "action": "buy",
                "price": last["close"],
                "stop_loss": round(min(b["low"] for b in bars[-5:]) * 0.98, 3),
                "take_profit": round(last["close"] * 1.20, 3),
                "vol_ratio": round(vol_ratio, 2),
            }
        return None

    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        if signal.get("action") != "buy":
            return Decimal("0")
        return (capital * Decimal("0.12")).quantize(Decimal("0.01"))

    def get_param_space(self) -> dict[str, tuple]:
        return {"vol_ratio_min": self.VOL_RATIO_RANGE, "vol_maintain_pct": self.VOL_MAINTAIN_RANGE}

    def validate_params(self, params: dict) -> bool:
        v = params.get("vol_ratio_min", 2)
        m = params.get("vol_maintain_pct", 0.6)
        return self.VOL_RATIO_RANGE[0] <= v <= self.VOL_RATIO_RANGE[1] and 0 < m < 1
