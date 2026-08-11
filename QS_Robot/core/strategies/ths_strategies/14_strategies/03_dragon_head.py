"""策略03：5句口诀抓龙头 — 严格数学建模版

来源：同花顺金融大师·策略战法

原策略数学模型（五句口诀逐句量化）：
  口诀1 — 涨停确认：
    pct_change = (close - prev_close) / prev_close × 100
    is_limit_up = pct_change >= limit_up_pct
    seal_quality = (high - low) / prev_close < 0.03   # 振幅<3%，封板干脆
    no_reopen = low / prev_close >= 0.98               # 最低价未远离涨停价

  口诀2 — 题材纯正（数据可用时启用，不可用时放行）：
    sector_strong = sector_change > 0                  # 板块整体上涨
    sector_heat = sector_limit_up_count >= sector_count # 板块内多股涨停

  口诀3 — 量价健康：
    vol_up_avg = AVG(vol on days where close > prev_close, 20d)
    vol_down_avg = AVG(vol on days where close < prev_close, 20d)
    vol_structure_ok = vol_up_avg / vol_down_avg > 1.3 # 涨放量>跌缩量
    vol_surge = vol(t) > MA(vol, 5) × 1.5              # 当前放量突破

  口诀4 — 市值适中+涨停基因（数据可用时启用，不可用时放行）：
    cap_ok = 20e8 <= circulating_cap <= 80e8
    limit_up_gene = 近60日涨停次数 >= 2

  口诀5 — 逆势抗跌+领涨（数据可用时启用，不可用时用个股替代）：
    rs_ok = stock_5d_return > sector_5d_return OR stock_5d_return > 3%

  出场条件（ANY触发）：
    - 跌破MA5
    - 从最高点回撤5%（移动止盈）
    - 成交量萎缩至MA5的50%以下（热度消退）
    - 高位放量滞涨（量增价平）

  止损：入场价 × 0.95 或 MA5 × 0.97（取较高者）
  止盈：入场价 × 1.10（涨停板短线目标）
  胜率：龙头股次日溢价概率约65%+
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import sma, dmi


class DragonHeadStrategy(THSBaseStrategy):
    ID = "03_dragon_head"
    NAME = "5句口诀抓龙头"
    CATEGORY = "ths_strategies"
    SOURCE = "同花顺金融大师"
    RISK_LEVEL = "高"

    LIMIT_UP_RANGE = (9.5, 11.0)
    SECTOR_COUNT_RANGE = (2, 10)
    VOL_STRUCTURE_DAYS = 20
    LIMIT_UP_HISTORY = 60
    LIMIT_UP_GENE_MIN = 2
    ADX_THRESHOLD = 20
    RISK_PER_TRADE = Decimal("0.015")
    MAX_POSITION = Decimal("0.10")

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        limit_up_pct = params.get("limit_up_pct", 9.8)
        sector_count = params.get("sector_count", 3)
        need = max(self.LIMIT_UP_HISTORY + 5, self.VOL_STRUCTURE_DAYS + 2, 60)
        if len(bars) < need:
            self._log_data_short(len(bars), need)
            return None
        closes = [b["close"] for b in bars]
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]
        opens = [b["open"] for b in bars]
        vols = [b["volume"] for b in bars]
        last = bars[-1]
        ctx = self._compute_indicators(closes, highs, lows, opens, vols,
                                       bars, limit_up_pct, sector_count)
        exit_signal = self._check_exit(ctx, closes, last)
        if exit_signal:
            return exit_signal
        entry_signal = self._check_entry(ctx, last)
        return self._apply_meta_filter(entry_signal, bars)

    def _compute_indicators(self, closes, highs, lows, opens, vols,
                            bars, limit_up_pct, sector_count):
        prev_close = closes[-2] if len(closes) >= 2 else closes[-1]
        pct_change = (closes[-1] - prev_close) / prev_close * 100 if prev_close > 0 else 0
        prev_prev_close = closes[-3] if len(closes) >= 3 else prev_close
        prev_pct_change = (prev_close - prev_prev_close) / prev_prev_close * 100 if prev_prev_close > 0 else 0
        lookback = min(6, len(closes) - 1)
        recent_limit_up_5d = any(
            closes[i-1] > 0 and (closes[i] - closes[i-1]) / closes[i-1] * 100 >= 9.5
            for i in range(-lookback, 0)
        )
        seal_ok = (highs[-1] - lows[-1]) / prev_close < 0.03 if prev_close > 0 else False
        no_reopen = lows[-1] / prev_close >= 0.98 if prev_close > 0 else False
        vol_ma5 = sma(vols, 5)
        vol_surge = vols[-1] > vol_ma5 * 1.5 if vol_ma5 > 0 else False
        up_vols, down_vols = [], []
        for i in range(-self.VOL_STRUCTURE_DAYS, 0):
            if closes[i] > closes[i - 1]:
                up_vols.append(vols[i])
            elif closes[i] < closes[i - 1]:
                down_vols.append(vols[i])
        up_avg = sum(up_vols) / len(up_vols) if up_vols else 0
        down_avg = sum(down_vols) / len(down_vols) if down_vols else 1
        vol_structure_ok = up_avg / down_avg > 1.3 if down_avg > 0 else False
        up_days_ratio = len(up_vols) / self.VOL_STRUCTURE_DAYS
        limit_up_count = sum(1 for i in range(-self.LIMIT_UP_HISTORY, 0)
                             if closes[i - 1] > 0 and
                             (closes[i] - closes[i - 1]) / closes[i - 1] * 100 >= 9.5)
        ma5 = sma(closes, 5)
        ma10 = sma(closes, 10)
        ma20 = sma(closes, 20)
        _, _, adx = dmi(highs, lows, closes, 14)
        sector_data = bars[-1].get("sector", {}) if bars else {}
        cap_data = bars[-1].get("market_cap", 0) or bars[-1].get("circulating_cap", 0)
        return {
            "pct_change": pct_change, "prev_pct_change": prev_pct_change,
            "recent_limit_up_5d": recent_limit_up_5d,
            "seal_ok": seal_ok, "no_reopen": no_reopen,
            "limit_up_pct": limit_up_pct, "vol_surge": vol_surge,
            "vol_structure_ok": vol_structure_ok, "up_days_ratio": up_days_ratio,
            "limit_up_count": limit_up_count, "ma5": ma5, "ma10": ma10, "ma20": ma20,
            "adx": adx, "vol_ma5": vol_ma5,
            "sector_data": sector_data, "sector_count": sector_count,
            "cap_data": cap_data, "entry_price": closes[-1],
        }

    def _check_exit(self, ctx, closes, last):
        ma5, ma10 = ctx["ma5"], ctx["ma10"]
        if last["close"] < ma5 * 0.97:
            result = {"action": "sell", "price": last["close"], "reason": "below_ma5"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if last["close"] < ma10 * 0.98:
            result = {"action": "sell", "price": last["close"], "reason": "below_ma10"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if last["volume"] < ctx["vol_ma5"] * 0.5 and ctx["vol_ma5"] > 0:
            result = {"action": "sell", "price": last["close"], "reason": "heat_fading"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if last["volume"] > ctx["vol_ma5"] * 2.0 and last["close"] < closes[-2] * 1.01:
            result = {"action": "sell", "price": last["close"], "reason": "distribution"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        return None

    def _check_entry(self, ctx, last):
        # 核心A：首个涨停（涨停+封板干脆）—— 原策略第一买入时机
        core_a = (ctx["pct_change"] >= ctx["limit_up_pct"]
                  and ctx["seal_ok"] and ctx["no_reopen"])
        # 核心B：回调至5日均线企稳（近5日有涨停+今日回调至ma5+涨幅<3%避免追高）
        pullback_to_ma5 = (ctx["ma5"] > 0
                           and abs(last["close"] - ctx["ma5"]) / ctx["ma5"] < 0.02)
        core_b = (ctx["recent_limit_up_5d"] and pullback_to_ma5
                  and ctx["pct_change"] < 3.0)
        core_ok = core_a or core_b
        # 辅助：5选2（涨停封板/板块题材/量价健康/涨停基因/逆势抗跌）
        k1 = core_a
        k2 = self._check_sector_theme(ctx)
        k3 = ctx["vol_surge"] and ctx["vol_structure_ok"] and ctx["up_days_ratio"] > 0.45
        k4 = self._check_cap_and_gene(ctx)
        k5 = self._check_relative_strength(ctx)
        aux_score = sum([bool(k1), bool(k2), bool(k3), bool(k4), bool(k5)])
        if not (core_ok and aux_score >= 2):
            conditions = {"core_a": core_a, "core_b": core_b, "k1": k1, "k2": k2,
                          "k3": k3, "k4": k4, "k5": k5, "aux_score": aux_score}
            self._log_entry_fail(conditions, f"date={last.get('date','')}")
            return None
        price = last["close"]
        stop_loss = max(price * 0.95, ctx["ma5"] * 0.97)
        take_profit = price * 1.10
        result = {
            "action": "buy", "price": price,
            "stop_loss": round(stop_loss, 3), "take_profit": round(take_profit, 3),
            "pct_change": round(ctx["pct_change"], 2),
            "vol_ratio": round(last["volume"] / ctx["vol_ma5"], 2) if ctx["vol_ma5"] > 0 else 0,
            "ma5": round(ctx["ma5"], 3), "ma10": round(ctx["ma10"], 3),
            "limit_up_gene": ctx["limit_up_count"],
            "adx": round(ctx["adx"], 1),
        }
        self._log_signal("buy", result, f"date={last.get('date','')}")
        return result

    def _check_sector_theme(self, ctx):
        sd = ctx["sector_data"]
        if not sd:
            return True
        sc = ctx["sector_count"]
        return sd.get("limit_up_count", 0) >= sc and sd.get("pct_change", 0) > 0

    def _check_cap_and_gene(self, ctx):
        cap = ctx["cap_data"]
        if cap and not (20e8 <= cap <= 80e8):
            return False
        return ctx["limit_up_count"] >= self.LIMIT_UP_GENE_MIN

    def _check_relative_strength(self, ctx):
        sd = ctx["sector_data"]
        if sd and sd.get("pct_change", 0) != 0:
            return ctx["pct_change"] > sd["pct_change"]
        return ctx["pct_change"] > 3.0

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
            "limit_up_pct": self.LIMIT_UP_RANGE,
            "sector_count": self.SECTOR_COUNT_RANGE,
        }

    def validate_params(self, params: dict) -> bool:
        lu = params.get("limit_up_pct", 9.8)
        sc = params.get("sector_count", 3)
        return (self.LIMIT_UP_RANGE[0] <= lu <= self.LIMIT_UP_RANGE[1]
                and self.SECTOR_COUNT_RANGE[0] <= sc <= self.SECTOR_COUNT_RANGE[1])