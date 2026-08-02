"""战法10：板块轮动导出

来源：同花顺金融大师·高阶战法
逻辑：板块强度前5 + 资金大幅流入 + 领涨个股≥3 + 行业逻辑清晰
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy


class SectorRotationStrategy(THSBaseStrategy):
    NAME = "板块轮动导出"
    CATEGORY = "ths_advanced"
    RISK_LEVEL = "中"
    TOP_N_RANGE = (3, 10)

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 5:
            return None
        top_n = params.get("top_n", 5)
        last = bars[-1]
        sector = last.get("sector_data")
        if not sector:
            return None
        rank = sector.get("strength_rank", 999)
        inflow = sector.get("capital_inflow", 0)
        leaders = sector.get("leader_count", 0)
        logic_clear = sector.get("logic_clear", False)
        if rank <= top_n and inflow > 0 and leaders >= 3 and logic_clear:
            return {
                "action": "buy",
                "price": last["close"],
                "stop_loss": round(last["close"] * 0.95, 3),
                "take_profit": round(last["close"] * 1.12, 3),
                "sector_rank": rank,
                "inflow": inflow,
            }
        return None

    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        if signal.get("action") != "buy":
            return Decimal("0")
        return (capital * Decimal("0.12")).quantize(Decimal("0.01"))

    def get_param_space(self) -> dict[str, tuple]:
        return {"top_n": self.TOP_N_RANGE}

    def validate_params(self, params: dict) -> bool:
        t = params.get("top_n", 5)
        return self.TOP_N_RANGE[0] <= t <= self.TOP_N_RANGE[1]
