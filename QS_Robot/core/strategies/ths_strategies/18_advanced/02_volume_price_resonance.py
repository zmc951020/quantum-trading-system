"""战法02：主力量价操盘解析 — 严格数学建模版

来源：同花顺金融大师·高阶战法
逻辑：吸筹-洗盘-拉升-出货周期，低位倍量突破+量能维持+均线多头+主力净流入
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import sma, ema


class VolumePriceResonanceStrategy(THSBaseStrategy):
    ID = "02_volume_price_resonance"
    NAME = "主力量价操盘"
    CATEGORY = "ths_advanced"
    SOURCE = "同花顺金融大师"
    RISK_LEVEL = "中"
    VOL_RATIO_RANGE = (1.5, 3.0)
    VOL_MAINTAIN_RANGE = (0.5, 0.8)
    RISK_PER_TRADE = Decimal("0.02")
    MAX_POSITION = Decimal("0.15")

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 30:
            self._log_data_short(len(bars), 30)
            return None
        vol_ratio_min = params.get("vol_ratio_min", 2)
        vol_maintain = params.get("vol_maintain_pct", 0.6)
        closes = [b["close"] for b in bars]
        vols = [b["volume"] for b in bars]
        last = bars[-1]
        ctx = self._compute_indicators(closes, vols, last, bars, vol_ratio_min, vol_maintain)
        exit_signal = self._check_exit(ctx, closes, last)
        if exit_signal:
            return exit_signal
        entry_signal = self._check_entry(ctx, last)
        return self._apply_meta_filter(entry_signal, bars)

    def _compute_indicators(self, closes, vols, last, bars, vol_ratio_min, vol_maintain):
        avg20 = sma(vols, 20)
        vol_ratio = last["volume"] / avg20 if avg20 > 0 else 0
        recent3_vol = sum(b["volume"] for b in bars[-4:-1]) / 3 if len(bars) >= 4 else 0
        vol_hold = recent3_vol > avg20 * vol_maintain if avg20 > 0 else False
        ma5 = sma(closes, 5)
        ma10 = sma(closes, 10)
        ma20 = sma(closes, 20)
        bullish = ma5 > ma10 > ma20
        low_pos = last["close"] < sma(closes, 60) * 1.1 if len(closes) >= 60 else True
        main_inflow = last.get("main_net_inflow", 0) > 0
        dif_series = [fa - sl for fa, sl in zip(ema(closes, 12), ema(closes, 26))]
        dea_series = ema(dif_series, 9) if len(dif_series) >= 9 else dif_series
        dif = dif_series[-1]
        prev_dif = dif_series[-2] if len(dif_series) >= 2 else 0
        dea = dea_series[-1]
        prev_dea = dea_series[-2] if len(dea_series) >= 2 else 0
        low5 = min(b["low"] for b in bars[-5:])
        return {
            "vol_ratio": vol_ratio, "vol_ratio_min": vol_ratio_min,
            "vol_hold": vol_hold, "bullish": bullish, "low_pos": low_pos,
            "main_inflow": main_inflow, "ma20": ma20, "avg20": avg20, "low5": low5,
            "dif": dif, "prev_dif": prev_dif, "dea": dea, "prev_dea": prev_dea,
            "vol_ratio_ok": vol_ratio > vol_ratio_min,
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
        # 核心：量价共振（放量 + 均线多头）
        core_ok = ctx["vol_ratio_ok"] and ctx["bullish"]
        # 辅助：3选1（量能维持 / 低位 / 主力净流入）
        aux_score = sum([
            bool(ctx["vol_hold"]),
            bool(ctx["low_pos"]),
            bool(ctx["main_inflow"]),
        ])
        if not (core_ok and aux_score >= 1):
            conditions = {"vol_ratio_ok": ctx["vol_ratio_ok"], "bullish": ctx["bullish"],
                          "vol_hold": ctx["vol_hold"], "low_pos": ctx["low_pos"],
                          "main_inflow": ctx["main_inflow"], "aux_score": aux_score}
            self._log_entry_fail(conditions, f"date={last.get('date','')}")
            return None
        result = {
            "action": "buy", "price": last["close"],
            "stop_loss": round(ctx["low5"] * 0.98, 3),
            "take_profit": round(last["close"] * 1.20, 3),
            "vol_ratio": round(ctx["vol_ratio"], 2),
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
        return {"vol_ratio_min": self.VOL_RATIO_RANGE, "vol_maintain_pct": self.VOL_MAINTAIN_RANGE}

    def validate_params(self, params: dict) -> bool:
        v = params.get("vol_ratio_min", 2)
        m = params.get("vol_maintain_pct", 0.6)
        return self.VOL_RATIO_RANGE[0] <= v <= self.VOL_RATIO_RANGE[1] and 0 < m < 1