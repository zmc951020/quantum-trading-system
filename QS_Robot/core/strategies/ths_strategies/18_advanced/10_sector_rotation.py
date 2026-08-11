"""战法10：板块轮动导出 — 严格数学建模版

来源：同花顺金融大师·高阶战法
逻辑：板块强度前5 + 资金大幅流入 + 领涨个股≥3 + 行业逻辑清晰
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import sma


class SectorRotationStrategy(THSBaseStrategy):
    ID = "10_sector_rotation"
    NAME = "板块轮动导出"
    CATEGORY = "ths_advanced"
    SOURCE = "同花顺金融大师"
    RISK_LEVEL = "中"
    TOP_N_RANGE = (3, 10)
    RISK_PER_TRADE = Decimal("0.02")
    MAX_POSITION = Decimal("0.15")

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 5:
            self._log_data_short(len(bars), 5)
            return None
        top_n = params.get("top_n", 5)
        closes = [b["close"] for b in bars]
        last = bars[-1]
        ctx = self._compute_indicators(last, top_n)
        if ctx is None:
            return None
        exit_signal = self._check_exit(ctx, closes, last)
        if exit_signal:
            return exit_signal
        return self._check_entry(ctx, last)

    def _compute_indicators(self, last, top_n):
        sector = last.get("sector_data")
        if not sector:
            return None
        rank = sector.get("strength_rank", 999)
        inflow = sector.get("capital_inflow", 0)
        leaders = sector.get("leader_count", 0)
        logic_clear = sector.get("logic_clear", False)
        return {"rank": rank, "top_n": top_n, "inflow": inflow,
                "leaders": leaders, "logic_clear": logic_clear,
                "rank_ok": rank <= top_n,
                "inflow_ok": inflow > 0,
                "leaders_ok": leaders >= 3}

    def _check_exit(self, ctx, closes, last):
        if last["close"] < closes[-3] * 0.95:
            result = {"action": "sell", "price": last["close"], "reason": "deep_drawdown"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        return None

    def _check_entry(self, ctx, last):
        if not (ctx["rank_ok"] and ctx["inflow_ok"]
                and ctx["leaders_ok"] and ctx["logic_clear"]):
            conditions = {"rank_ok": ctx["rank_ok"], "inflow_ok": ctx["inflow_ok"],
                          "leaders_ok": ctx["leaders_ok"], "logic_clear": ctx["logic_clear"]}
            self._log_entry_fail(conditions, f"date={last.get('date','')}")
            return None
        result = {
            "action": "buy", "price": last["close"],
            "stop_loss": round(last["close"] * 0.95, 3),
            "take_profit": round(last["close"] * 1.12, 3),
            "sector_rank": ctx["rank"], "inflow": ctx["inflow"],
        }
        self._log_signal("buy", result, f"date={last.get('date','')}")
        return result

    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        if signal.get("action") != "buy":
            return Decimal("0")
        risk_per_share = Decimal(str(signal["price"])) - Decimal(str(signal["stop_loss"]))
        if risk_per_share <= 0:
            return Decimal("0")
        position = (capital * self.RISK_PER_TRADE / risk_per_share).quantize(Decimal("0.01"))
        return min(position, capital * self.MAX_POSITION)

    def get_param_space(self) -> dict[str, tuple]:
        return {"top_n": self.TOP_N_RANGE}

    def validate_params(self, params: dict) -> bool:
        t = params.get("top_n", 5)
        return self.TOP_N_RANGE[0] <= t <= self.TOP_N_RANGE[1]