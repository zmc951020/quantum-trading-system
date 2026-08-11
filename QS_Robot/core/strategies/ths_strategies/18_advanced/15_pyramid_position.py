"""战法15：金字塔加码仓位管理 — 严格数学建模版

来源：同花顺金融大师·高阶战法
逻辑：首次20%试仓 → 回踩20日均线确认加30% → 趋势延续加50%
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import sma, ema


class PyramidPositionStrategy(THSBaseStrategy):
    ID = "15_pyramid_position"
    NAME = "金字塔加码仓位"
    CATEGORY = "ths_advanced"
    SOURCE = "同花顺金融大师"
    RISK_LEVEL = "中"
    FIRST_PCT_RANGE = (0.1, 0.3)
    MAX_LOSS_RANGE = (0.01, 0.03)
    RISK_PER_TRADE = Decimal("0.02")
    MAX_POSITION = Decimal("0.15")

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 30:
            self._log_data_short(len(bars), 30)
            return None
        first_pct = params.get("first_pct", 0.2)
        max_loss = params.get("max_loss_pct", 0.02)
        closes = [b["close"] for b in bars]
        last = bars[-1]
        ctx = self._compute_indicators(closes, last, first_pct, max_loss)
        exit_signal = self._check_exit(ctx, closes, last)
        if exit_signal:
            return exit_signal
        entry_signal = self._check_entry(ctx, last)
        return self._apply_meta_filter(entry_signal, bars)

    def _compute_indicators(self, closes, last, first_pct, max_loss):
        ma20 = sma(closes, 20)
        ma60 = sma(closes, 60) if len(closes) >= 60 else ma20
        trend_up = ma20 > ma60 and last["close"] > ma20
        pullback_to_ma20 = abs(last["close"] - ma20) / ma20 < 0.02 if ma20 > 0 else False
        dif_series = [fa - sl for fa, sl in zip(ema(closes, 12), ema(closes, 26))]
        dea_series = ema(dif_series, 9) if len(dif_series) >= 9 else dif_series
        dif = dif_series[-1]
        prev_dif = dif_series[-2] if len(dif_series) >= 2 else 0
        dea = dea_series[-1]
        prev_dea = dea_series[-2] if len(dea_series) >= 2 else 0
        return {
            "trend_up": trend_up, "pullback_to_ma20": pullback_to_ma20,
            "first_pct": first_pct, "max_loss": max_loss, "ma20": ma20, "ma60": ma60,
            "dif": dif, "prev_dif": prev_dif, "dea": dea, "prev_dea": prev_dea,
        }

    def _check_exit(self, ctx, closes, last):
        if last["close"] < ctx["ma20"] * 0.97:
            result = {"action": "sell", "price": last["close"], "reason": "below_ma20"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if ctx["prev_dif"] >= ctx["prev_dea"] and ctx["dif"] < ctx["dea"]:
            result = {"action": "sell", "price": last["close"], "reason": "macd_death"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if last["close"] < closes[-3] * 0.93:
            result = {"action": "sell", "price": last["close"], "reason": "deep_drawdown"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        return None

    def _check_entry(self, ctx, last):
        if not (ctx["trend_up"] and ctx["pullback_to_ma20"]):
            conditions = {"trend_up": ctx["trend_up"], "pullback_to_ma20": ctx["pullback_to_ma20"]}
            self._log_entry_fail(conditions, f"date={last.get('date','')}")
            return None
        # 3 阶段建仓：根据 close 距 MA20 的涨幅区分
        ma20 = ctx["ma20"]
        close = last["close"]
        pct_above = (close - ma20) / ma20 if ma20 > 0 else 0
        if pct_above < 0.05:
            stage = "first_20%"
        elif pct_above < 0.15:
            stage = "add_30%"
        else:
            stage = "add_50%"
        result = {
            "action": "buy", "price": close,
            "stop_loss": round(ctx["ma20"] * (1 - ctx["max_loss"]), 3),
            "take_profit": round(close * 1.15, 3),
            "first_pct": ctx["first_pct"], "stage": stage,
            "pct_above_ma20": round(pct_above, 4),
        }
        self._log_signal("buy", result, f"date={last.get('date','')}")
        return result

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