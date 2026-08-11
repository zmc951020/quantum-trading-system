"""战法14：逐笔成交Level-2分析 — 严格数学建模版

来源：同花顺金融大师·高阶战法
逻辑：程序化单<30% + 委买档口大单支撑 + 内外盘差值正常
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import sma


class OrderFlowAnalysisStrategy(THSBaseStrategy):
    ID = "14_order_flow_analysis"
    NAME = "Level-2逐笔分析"
    CATEGORY = "ths_advanced"
    SOURCE = "同花顺金融大师"
    RISK_LEVEL = "中"
    PROGRAM_PCT_RANGE = (0.2, 0.4)
    ABANDON_THRESHOLD_RANGE = (0.4, 0.6)
    RISK_PER_TRADE = Decimal("0.02")
    MAX_POSITION = Decimal("0.15")

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 5:
            self._log_data_short(len(bars), 5)
            return None
        prog_max = params.get("program_pct_max", 0.3)
        closes = [b["close"] for b in bars]
        vols = [b["volume"] for b in bars]
        last = bars[-1]
        ctx = self._compute_indicators(last, bars, closes, vols, prog_max)
        if ctx is None:
            return None
        exit_signal = self._check_exit(ctx, closes, last)
        if exit_signal:
            return exit_signal
        entry_signal = self._check_entry(ctx, last)
        return self._apply_meta_filter(entry_signal, bars)

    def _compute_indicators(self, last, bars, closes, vols, prog_max):
        level2 = last.get("level2")
        ma5 = sma(closes, 5) if len(closes) >= 5 else closes[-1]
        above_ma5 = last["close"] > ma5
        no_deep_drawdown = last["close"] >= closes[-3] * 0.96 if len(closes) >= 3 else True
        if level2:
            program_pct = level2.get("program_pct", 1)
            bid_support = level2.get("bid_big_order", False)
            inner_outer = level2.get("inner_outer_ratio", 1)
            normal_diff = 0.5 < inner_outer < 2.0
        else:
            program_pct, bid_support, normal_diff = self._estimate_level2(vols, closes, last)
        return {
            "program_pct": program_pct, "prog_max": prog_max,
            "bid_support": bid_support, "normal_diff": normal_diff,
            "program_ok": program_pct < prog_max,
            "ma5": ma5, "above_ma5": above_ma5, "no_deep_drawdown": no_deep_drawdown,
        }

    def _estimate_level2(self, vols, closes, last):
        """无 level2 数据时，基于成交量估算"""
        if len(vols) >= 5:
            avg_vol = sum(vols[-5:]) / 5
            variance = sum((v - avg_vol) ** 2 for v in vols[-5:]) / 5
            cv = (variance ** 0.5) / avg_vol if avg_vol > 0 else 1
            program_pct = min(max(1 - cv, 0.1), 0.9)
        else:
            program_pct = 0.5
        if len(closes) >= 2 and closes[-2] > 0:
            pct_change = (last["close"] - closes[-2]) / closes[-2]
            bid_support = pct_change > 0
        else:
            bid_support = False
        normal_diff = True
        return program_pct, bid_support, normal_diff

    def _check_exit(self, ctx, closes, last):
        if last["close"] < closes[-3] * 0.96:
            result = {"action": "sell", "price": last["close"], "reason": "deep_drawdown"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        return None

    def _check_entry(self, ctx, last):
        # 核心：站稳 ma5 + 不深度回撤
        core_ok = ctx["above_ma5"] and ctx["no_deep_drawdown"]
        # 辅助：3选1（程序化单/委买大单/内外盘）
        aux_score = sum([
            bool(ctx["program_ok"]),
            bool(ctx["bid_support"]),
            bool(ctx["normal_diff"]),
        ])
        if not (core_ok and aux_score >= 1):
            conditions = {"core_ok": core_ok, "above_ma5": ctx["above_ma5"],
                          "no_deep_drawdown": ctx["no_deep_drawdown"],
                          "program_ok": ctx["program_ok"], "bid_support": ctx["bid_support"],
                          "normal_diff": ctx["normal_diff"], "aux_score": aux_score}
            self._log_entry_fail(conditions, f"date={last.get('date','')}")
            return None
        result = {
            "action": "buy", "price": last["close"],
            "stop_loss": round(last["close"] * 0.97, 3),
            "take_profit": round(last["close"] * 1.08, 3),
            "program_pct": round(ctx["program_pct"], 3),
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
        return {"program_pct_max": self.PROGRAM_PCT_RANGE, "abandon_threshold": self.ABANDON_THRESHOLD_RANGE}

    def validate_params(self, params: dict) -> bool:
        p = params.get("program_pct_max", 0.3)
        a = params.get("abandon_threshold", 0.5)
        return 0 < p < 1 and 0 < a < 1