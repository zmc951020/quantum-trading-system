"""战法05：筹码分布低位单峰密集 — 严格数学建模版

来源：同花顺金融大师·高阶战法
逻辑：低位筹码单峰密集，获利盘≥70%，套牢盘≤20%，穿透率高且量小
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import sma, ema


class ChipDistributionStrategy(THSBaseStrategy):
    ID = "05_chip_distribution"
    NAME = "筹码单峰密集"
    CATEGORY = "ths_advanced"
    SOURCE = "同花顺金融大师"
    RISK_LEVEL = "中"
    PROFIT_RATIO_RANGE = (0.6, 0.9)
    TRAP_RATIO_RANGE = (0.1, 0.3)
    RISK_PER_TRADE = Decimal("0.02")
    MAX_POSITION = Decimal("0.15")

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 30:
            self._log_data_short(len(bars), 30)
            return None
        profit_min = params.get("profit_ratio_min", 0.7)
        trap_max = params.get("trap_ratio_max", 0.2)
        closes = [b["close"] for b in bars]
        last = bars[-1]
        ctx = self._compute_indicators(closes, last, bars, profit_min, trap_max)
        if ctx is None:
            return None
        exit_signal = self._check_exit(ctx, closes, last)
        if exit_signal:
            return exit_signal
        entry_signal = self._check_entry(ctx, last)
        return self._apply_meta_filter(entry_signal, bars)

    def _compute_indicators(self, closes, last, bars, profit_min, trap_max):
        chip = last.get("chip_distribution")
        ma60 = sma(closes, 60) if len(closes) >= 60 else sma(closes, len(closes))
        low_pos = last["close"] < ma60 * 1.05
        vol_ma20 = sma([b["volume"] for b in bars], 20)
        if chip:
            profit_ratio = chip.get("profit_ratio", 0)
            trap_ratio = chip.get("trap_ratio", 1)
            concentration = chip.get("concentration", 0)
            penetrate = chip.get("penetration", 0)
        else:
            profit_ratio, trap_ratio, concentration, penetrate = self._estimate_chip(closes, bars, last)
        vol_small = last["volume"] < vol_ma20 * 0.8
        dif_series = [fa - sl for fa, sl in zip(ema(closes, 12), ema(closes, 26))]
        dea_series = ema(dif_series, 9) if len(dif_series) >= 9 else dif_series
        dif = dif_series[-1]
        prev_dif = dif_series[-2] if len(dif_series) >= 2 else 0
        dea = dea_series[-1]
        prev_dea = dea_series[-2] if len(dea_series) >= 2 else 0
        return {
            "profit_ratio": profit_ratio, "profit_min": profit_min,
            "trap_ratio": trap_ratio, "trap_max": trap_max,
            "concentration": concentration, "low_pos": low_pos,
            "penetrate": penetrate, "vol_small": vol_small, "ma60": ma60,
            "chip": chip or {}, "dif": dif, "prev_dif": prev_dif, "dea": dea, "prev_dea": prev_dea,
            "profit_ok": profit_ratio >= profit_min,
            "trap_ok": trap_ratio <= trap_max,
            "concentration_ok": concentration > 0.7,
            "penetrate_ok": penetrate > 0,
        }

    def _estimate_chip(self, closes, bars, last):
        """无外部筹码数据时，基于价格历史估算筹码分布"""
        window = min(60, len(closes))
        recent_closes = closes[-window:]
        current_close = last["close"]
        recent_vols = [b["volume"] for b in bars[-window:]]
        total_vol = sum(recent_vols) if recent_vols else 1
        profit_vol = sum(v for c, v in zip(recent_closes, recent_vols) if c <= current_close)
        profit_ratio = profit_vol / total_vol if total_vol > 0 else 0
        trap_ratio = 1 - profit_ratio
        avg = sum(recent_closes) / len(recent_closes)
        variance = sum((c - avg) ** 2 for c in recent_closes) / len(recent_closes)
        std = variance ** 0.5
        concentration = 1 - min(std / avg, 1) if avg > 0 else 0
        avg_vol = total_vol / len(recent_vols) if recent_vols else 1
        penetrate = last["volume"] / avg_vol if avg_vol > 0 else 0
        return profit_ratio, trap_ratio, concentration, penetrate

    def _check_exit(self, ctx, closes, last):
        if last["close"] < ctx["ma60"] * 0.97:
            result = {"action": "sell", "price": last["close"], "reason": "below_ma60"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if ctx["prev_dif"] >= ctx["prev_dea"] and ctx["dif"] < ctx["dea"]:
            result = {"action": "sell", "price": last["close"], "reason": "macd_death"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        return None

    def _check_entry(self, ctx, last):
        # 核心：低位（low_pos）—— 筹码单峰密集战法的本质前提
        core_ok = ctx["low_pos"]
        # 辅助：4选2（获利盘/套牢盘/集中度/穿透率）
        aux_score = sum([
            bool(ctx["profit_ok"]),
            bool(ctx["trap_ok"]),
            bool(ctx["concentration_ok"]),
            bool(ctx["penetrate_ok"]),
        ])
        if not (core_ok and aux_score >= 2):
            conditions = {"core_ok": core_ok, "profit_ok": ctx["profit_ok"], "trap_ok": ctx["trap_ok"],
                          "concentration_ok": ctx["concentration_ok"],
                          "penetrate_ok": ctx["penetrate_ok"], "aux_score": aux_score}
            self._log_entry_fail(conditions, f"date={last.get('date','')}")
            return None
        result = {
            "action": "buy", "price": last["close"],
            "stop_loss": round(ctx["chip"].get("peak_low", last["close"] * 0.95), 3),
            "take_profit": round(last["close"] * 1.20, 3),
            "profit_ratio": round(ctx["profit_ratio"], 3),
            "trap_ratio": round(ctx["trap_ratio"], 3),
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
        return {"profit_ratio_min": self.PROFIT_RATIO_RANGE, "trap_ratio_max": self.TRAP_RATIO_RANGE}

    def validate_params(self, params: dict) -> bool:
        p = params.get("profit_ratio_min", 0.7)
        t = params.get("trap_ratio_max", 0.2)
        return 0 < p < 1 and 0 < t < 1