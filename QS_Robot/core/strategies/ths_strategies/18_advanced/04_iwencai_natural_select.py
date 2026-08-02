"""战法04：问财AI自然语言选股

来源：同花顺金融大师·高阶战法
逻辑：自然语言指令选股，结合资金流和筹码二次验证
简化实现：解析query关键词映射到技术条件
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import macd, sma


class IwencaiNaturalSelectStrategy(THSBaseStrategy):
    NAME = "问财AI选股"
    CATEGORY = "ths_advanced"
    RISK_LEVEL = "中"

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 40:
            return None
        query = params.get("query", "MACD金叉且零轴上方")
        closes = [b["close"] for b in bars]
        last = bars[-1]
        matched = []
        if "MACD金叉" in query or "macd金叉" in query:
            dif, dea, hist = macd(closes, 12, 26, 9)
            golden = dif > dea and hist > 0
            zero_ok = dif > 0 if "零轴" in query else True
            matched.append(golden and zero_ok)
        if "5日均线上穿10日" in query:
            ma5 = sma(closes, 5)
            ma10 = sma(closes, 10)
            matched.append(ma5 > ma10)
        if "涨停" in query:
            prev = bars[-2]
            pct = (last["close"] - prev["close"]) / prev["close"] * 100
            matched.append(pct >= 9.5)
        if not matched:
            matched = [True]
        if all(matched) and last.get("main_net_inflow", 0) >= 0:
            return {
                "action": "buy",
                "price": last["close"],
                "stop_loss": round(sma(closes, 20) * 0.95, 3),
                "take_profit": round(last["close"] * 1.10, 3),
                "query": query,
                "matched_count": len(matched),
            }
        return None

    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        if signal.get("action") != "buy":
            return Decimal("0")
        return (capital * Decimal("0.10")).quantize(Decimal("0.01"))

    def get_param_space(self) -> dict[str, tuple]:
        return {"min_match": (1, 5)}

    def validate_params(self, params: dict) -> bool:
        m = params.get("min_match", 1)
        return 1 <= m <= 5
