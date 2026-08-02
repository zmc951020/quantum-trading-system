"""策略03：5句口诀抓龙头

来源：同花顺金融大师·策略战法
口诀：
  1.主线题材率先涨停，早盘封板干脆无反复开板
  2.业务逻辑纯正贴合热点，绝非蹭热度的概念杂毛
  3.上涨放量回调缩量，量价结构全程健康稳定
  4.流通市值20-80亿，股性活跃具备涨停历史基因
  5.板块调整逆势抗跌，行情反弹率先领涨带动跟风
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy


class DragonHeadStrategy(THSBaseStrategy):
    """5句口诀抓龙头：涨停+板块效应+量价+市值+抗跌"""
    NAME = "5句口诀抓龙头"
    CATEGORY = "ths_strategies"
    SOURCE = "同花顺金融大师"
    RISK_LEVEL = "高"

    LIMIT_UP_RANGE = (9.5, 11.0)
    SECTOR_COUNT_RANGE = (2, 10)

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 5:
            return None
        limit_up_pct = params.get("limit_up_pct", 9.8)
        sector_count = params.get("sector_count", 3)
        last = bars[-1]
        prev = bars[-2]
        pct_change = (last["close"] - prev["close"]) / prev["close"] * 100
        is_limit_up = pct_change >= limit_up_pct
        vol_avg = sum(b["volume"] for b in bars[-5:-1]) / 4
        vol_ok = last["volume"] > vol_avg * 1.5
        closes = [b["close"] for b in bars[-5:]]
        ma5 = sum(closes) / 5
        ma_support = last["close"] > ma5 * 0.98
        sector_ok = sector_count >= 2
        if is_limit_up and vol_ok and ma_support and sector_ok:
            return {
                "action": "buy",
                "price": last["close"],
                "stop_loss": round(ma5 * 0.97, 3),
                "take_profit": round(last["close"] * 1.10, 3),
                "pct_change": round(pct_change, 2),
                "vol_ratio": round(last["volume"] / vol_avg, 2),
                "ma5": round(ma5, 3),
            }
        return None

    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        if signal.get("action") != "buy":
            return Decimal("0")
        return (capital * Decimal("0.08")).quantize(Decimal("0.01"))

    def get_param_space(self) -> dict[str, tuple]:
        return {
            "limit_up_pct": self.LIMIT_UP_RANGE,
            "sector_count": self.SECTOR_COUNT_RANGE,
        }

    def validate_params(self, params: dict) -> bool:
        lu = params.get("limit_up_pct", 9.8)
        sc = params.get("sector_count", 3)
        if not (self.LIMIT_UP_RANGE[0] <= lu <= self.LIMIT_UP_RANGE[1]):
            return False
        if not (self.SECTOR_COUNT_RANGE[0] <= sc <= self.SECTOR_COUNT_RANGE[1]):
            return False
        return True
