"""战法08：成交量阶梯战法 — 严格数学建模版

来源：同花顺金融大师·高阶战法
逻辑：首轮突破量>20日均量2倍 → 回调缩量至50% → 二次放大30%以上
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import sma, ema


class VolumeLadderStrategy(THSBaseStrategy):
    ID = "08_volume_ladder"
    NAME = "成交量阶梯"
    CATEGORY = "ths_advanced"
    SOURCE = "同花顺金融大师"
    RISK_LEVEL = "中"
    FIRST_VOL_RANGE = (1.5, 3.0)
    PULLBACK_VOL_RANGE = (0.4, 0.7)
    SECOND_VOL_RANGE = (1.1, 1.8)
    RISK_PER_TRADE = Decimal("0.02")
    MAX_POSITION = Decimal("0.15")

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 30:
            self._log_data_short(len(bars), 30)
            return None
        first_ratio = params.get("first_vol_ratio", 2)
        pullback_pct = params.get("pullback_vol_pct", 0.6)
        second_ratio = params.get("second_vol_ratio", 1.2)
        closes = [b["close"] for b in bars]
        vols = [b["volume"] for b in bars]
        last = bars[-1]
        ctx = self._compute_indicators(closes, vols, last, bars, first_ratio, pullback_pct, second_ratio)
        exit_signal = self._check_exit(ctx, closes, last)
        if exit_signal:
            return exit_signal
        entry_signal = self._check_entry(ctx, last)
        return self._apply_meta_filter(entry_signal, bars)

    def _compute_indicators(self, closes, vols, last, bars, first_ratio, pullback_pct, second_ratio):
        avg20 = sma(vols, 20)
        first_break_idx = None
        for i in range(len(vols) - 10, len(vols) - 2):
            if i >= 0 and vols[i] > avg20 * first_ratio and closes[i] > closes[i - 1]:
                first_break_idx = i
                break
        pullback_ok = False
        second_surge = False
        if first_break_idx is not None:
            pullback_vols = vols[first_break_idx + 1:-1]
            pullback_ok = all(v < avg20 * pullback_pct for v in pullback_vols) if pullback_vols else False
            last_vol_ratio = last["volume"] / avg20 if avg20 > 0 else 0
            second_surge = last_vol_ratio > second_ratio
        bullish_candle = last["close"] > bars[-2]["close"]
        ma20 = sma(closes, 20)
        dif_series = [fa - sl for fa, sl in zip(ema(closes, 12), ema(closes, 26))]
        dea_series = ema(dif_series, 9) if len(dif_series) >= 9 else dif_series
        dif = dif_series[-1]
        prev_dif = dif_series[-2] if len(dif_series) >= 2 else 0
        dea = dea_series[-1]
        prev_dea = dea_series[-2] if len(dea_series) >= 2 else 0
        return {
            "first_break_idx": first_break_idx, "pullback_ok": pullback_ok,
            "second_surge": second_surge, "bullish_candle": bullish_candle,
            "avg20": avg20, "ma20": ma20, "last_vol_ratio": last["volume"] / avg20 if avg20 > 0 else 0,
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
        if last["volume"] > ctx["avg20"] * 2.5 and last["close"] < closes[-2]:
            result = {"action": "sell", "price": last["close"], "reason": "heavy_sell"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        return None

    def _check_entry(self, ctx, last):
        # 核心A：二次放量（原逻辑）—— 首次突破 + 二次放量
        core_a = ctx["second_surge"] and ctx["first_break_idx"] is not None
        # 核心B：今日首次放量突破 —— 量比>2 + 阳线
        core_b = ctx["last_vol_ratio"] > 2.0 and ctx["bullish_candle"]
        core_ok = core_a or core_b
        # 辅助：3选1（回调缩量 / 阳线 / 量比显著）
        aux_score = sum([
            bool(ctx["pullback_ok"]),
            bool(ctx["bullish_candle"]),
            ctx["last_vol_ratio"] > 1.5,
        ])
        if not (core_ok and aux_score >= 1):
            conditions = {"core_a": core_a, "core_b": core_b,
                          "second_surge": ctx["second_surge"],
                          "first_break_idx": ctx["first_break_idx"],
                          "pullback_ok": ctx["pullback_ok"],
                          "bullish_candle": ctx["bullish_candle"],
                          "last_vol_ratio": ctx["last_vol_ratio"],
                          "aux_score": aux_score}
            self._log_entry_fail(conditions, f"date={last.get('date','')}")
            return None
        stop_low = last["close"] * 0.95
        result = {
            "action": "buy", "price": last["close"],
            "stop_loss": round(stop_low, 3),
            "take_profit": round(last["close"] * 1.15, 3),
            "first_break_idx": ctx["first_break_idx"],
            "last_vol_ratio": round(ctx["last_vol_ratio"], 2),
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
        return {
            "first_vol_ratio": self.FIRST_VOL_RANGE,
            "pullback_vol_pct": self.PULLBACK_VOL_RANGE,
            "second_vol_ratio": self.SECOND_VOL_RANGE,
        }

    def validate_params(self, params: dict) -> bool:
        f = params.get("first_vol_ratio", 2)
        p = params.get("pullback_vol_pct", 0.5)
        s = params.get("second_vol_ratio", 1.3)
        return f > 1 and 0 < p < 1 and s > 1