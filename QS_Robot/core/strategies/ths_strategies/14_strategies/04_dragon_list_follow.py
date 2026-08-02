"""策略04：龙虎榜跟庄

来源：同花顺金融大师·策略战法
逻辑：
  1.龙虎榜显示游资/机构席位净买入
  2.龙头低吸不破核心均线
  3.回踩3-5天缩量起爆
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy


class DragonListFollowStrategy(THSBaseStrategy):
    """龙虎榜跟庄：机构净买+缩量回踩+均线支撑"""
    NAME = "龙虎榜跟庄"
    CATEGORY = "ths_strategies"
    SOURCE = "同花顺金融大师"
    RISK_LEVEL = "中"

    INST_BUY_RANGE = (10, 100)
    PULLBACK_DAYS_RANGE = (2, 7)

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 8:
            return None
        pullback_days = params.get("pullback_days", 3)
        dragon_day = None
        for b in bars[-7:-1]:
            dl = b.get("dragon_list")
            if dl and dl.get("institutional_net_buy", 0) > 0:
                dragon_day = b
                break
        if not dragon_day:
            return None
        recent = bars[-pullback_days:]
        vol_recent = sum(b["volume"] for b in recent) / len(recent)
        vol_dragon = dragon_day["volume"]
        vol_shrink = vol_recent < vol_dragon * 0.7
        closes = [b["close"] for b in bars[-20:]] if len(bars) >= 20 else [b["close"] for b in bars]
        ma = sum(closes) / len(closes)
        last = bars[-1]
        ma_support = last["close"] > ma * 0.97
        if vol_shrink and ma_support:
            return {
                "action": "buy",
                "price": last["close"],
                "stop_loss": round(ma * 0.95, 3),
                "take_profit": round(last["close"] * 1.08, 3),
                "dragon_day_close": dragon_day["close"],
                "vol_shrink_ratio": round(vol_recent / vol_dragon, 2),
            }
        return None

    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        if signal.get("action") != "buy":
            return Decimal("0")
        return (capital * Decimal("0.12")).quantize(Decimal("0.01"))

    def get_param_space(self) -> dict[str, tuple]:
        return {
            "institutional_buy_pct": self.INST_BUY_RANGE,
            "pullback_days": self.PULLBACK_DAYS_RANGE,
        }

    def validate_params(self, params: dict) -> bool:
        ip = params.get("institutional_buy_pct", 30)
        pd = params.get("pullback_days", 3)
        if not (self.INST_BUY_RANGE[0] <= ip <= self.INST_BUY_RANGE[1]):
            return False
        if not (self.PULLBACK_DAYS_RANGE[0] <= pd <= self.PULLBACK_DAYS_RANGE[1]):
            return False
        return True
