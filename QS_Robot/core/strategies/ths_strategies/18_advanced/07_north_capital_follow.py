"""战法07：北向资金跟随 — 严格数学建模版

来源：同花顺金融大师·高阶战法
逻辑：北向半小时净流入>10亿且集中买某类股，跟买相关ETF
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import sma


class NorthCapitalFollowStrategy(THSBaseStrategy):
    ID = "07_north_capital_follow"
    NAME = "北向资金跟随"
    CATEGORY = "ths_advanced"
    SOURCE = "同花顺金融大师"
    RISK_LEVEL = "低"
    NORTH_INFLOW_RANGE = (5, 50)
    HOLD_DAYS_RANGE = (1, 2)
    RISK_PER_TRADE = Decimal("0.02")
    MAX_POSITION = Decimal("0.10")

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 3:
            self._log_data_short(len(bars), 3)
            return None
        inflow_min = params.get("north_inflow_min", 10)
        closes = [b["close"] for b in bars]
        last = bars[-1]
        ctx = self._compute_indicators(last, inflow_min)
        exit_signal = self._check_exit(ctx, closes, last)
        if exit_signal:
            return exit_signal
        return self._check_entry(ctx, last)

    def _compute_indicators(self, last, inflow_min):
        north = last.get("north_inflow", 0)
        sector_concentrated = last.get("sector_concentrated", False)
        is_etf = last.get("is_etf", False)
        return {"north": north, "inflow_min": inflow_min,
                "sector_concentrated": sector_concentrated, "is_etf": is_etf,
                "north_ok": north > inflow_min}

    def _check_exit(self, ctx, closes, last):
        if last["close"] < closes[-3] * 0.96:
            result = {"action": "sell", "price": last["close"], "reason": "deep_drawdown"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        return None

    def _check_entry(self, ctx, last):
        if not (ctx["north_ok"] and ctx["sector_concentrated"]):
            conditions = {"north_ok": ctx["north_ok"], "sector_concentrated": ctx["sector_concentrated"]}
            self._log_entry_fail(conditions, f"date={last.get('date','')}")
            return None
        result = {
            "action": "buy", "price": last["close"],
            "stop_loss": round(last["close"] * 0.98, 3),
            "take_profit": round(last["close"] * 1.03, 3),
            "north_inflow": ctx["north"], "is_etf": ctx["is_etf"],
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
        return {"north_inflow_min": self.NORTH_INFLOW_RANGE, "hold_days": self.HOLD_DAYS_RANGE}

    def validate_params(self, params: dict) -> bool:
        n = params.get("north_inflow_min", 10)
        h = params.get("hold_days", 1)
        return self.NORTH_INFLOW_RANGE[0] <= n <= self.NORTH_INFLOW_RANGE[1] and h >= 1