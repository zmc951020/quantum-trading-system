"""策略04：龙虎榜跟庄 — 严格数学建模版

来源：同花顺金融大师·策略战法

原策略数学模型：
  龙虎榜确认：
    dragon_day = 最近 max_dragon_days 日内有龙虎榜数据的K线
    net_buy_ratio = institutional_net_buy / dragon_volume × 100
    inst_ok = net_buy_ratio >= institutional_buy_pct  # 机构参与度达标

  回调确认：
    pullback_ratio = (dragon_close - current_close) / dragon_close
    pullback_ok = 0.02 <= pullback_ratio <= 0.08  # 浅回调2-8%
    ma_support = close > MA(20) × 0.98            # 不破核心均线

  缩量起爆确认：
    vol_shrink = current_vol < dragon_vol × 0.5     # 缩至龙虎榜日50%
    vol_trend_down = 近3日量逐日递减              # 持续缩量趋势
    vol_breakout = current_vol > prev_vol × 1.2     # 当日放量起爆

  趋势确认：
    adx_ok = ADX(14) > 20                           # 趋势强度
    ma20_up = MA20(t) > MA20(t-5)                   # 均线向上（主力护盘）

  入场条件（ALL）：
    inst_ok AND pullback_ok AND ma_support AND vol_shrink
    AND vol_trend_down AND vol_breakout AND adx_ok AND ma20_up

  出场条件（ANY）：
    - 跌破MA20（主力弃守）
    - 放量下跌（vol>MA5×2 且 收跌）
    - 从龙虎榜日收盘价回撤超10%
    - MACD死叉

  止损：MA20 × 0.97 或 龙虎榜日最低价（取较高者）
  止盈：龙虎榜日收盘价 × 1.12（跟庄目标12%）
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import sma, ema, dmi


class DragonListFollowStrategy(THSBaseStrategy):
    ID = "04_dragon_list_follow"
    NAME = "龙虎榜跟庄"
    CATEGORY = "ths_strategies"
    SOURCE = "同花顺金融大师"
    RISK_LEVEL = "中"

    INST_BUY_RANGE = (5, 50)
    PULLBACK_DAYS_RANGE = (2, 7)
    MAX_DRAGON_DAYS = 10
    MA_PERIOD = 20
    ADX_THRESHOLD = 20
    RISK_PER_TRADE = Decimal("0.02")
    MAX_POSITION = Decimal("0.15")

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        inst_buy_pct = params.get("institutional_buy_pct", 15)
        pullback_days = params.get("pullback_days", 3)
        need = max(self.MAX_DRAGON_DAYS + 2, self.MA_PERIOD + 5, 60)
        if len(bars) < need:
            self._log_data_short(len(bars), need)
            return None
        closes = [b["close"] for b in bars]
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]
        vols = [b["volume"] for b in bars]
        last = bars[-1]
        ctx = self._compute_indicators(bars, closes, highs, lows, vols,
                                       inst_buy_pct, pullback_days)
        if ctx is None:
            return None
        exit_signal = self._check_exit(ctx, closes, last)
        if exit_signal:
            return exit_signal
        return self._check_entry(ctx, closes, vols, last)

    def _compute_indicators(self, bars, closes, highs, lows, vols,
                            inst_buy_pct, pullback_days):
        dragon_day, dragon_idx = None, -1
        for i in range(-self.MAX_DRAGON_DAYS, 0):
            dl = bars[i].get("dragon_list")
            if dl and dl.get("institutional_net_buy", 0) > 0:
                dragon_day = bars[i]
                dragon_idx = i
                break
        if dragon_day is None:
            return None
        net_buy = dragon_day["dragon_list"]["institutional_net_buy"]
        net_buy_ratio = net_buy / dragon_day["volume"] * 100 if dragon_day["volume"] > 0 else 0
        inst_ok = net_buy_ratio >= inst_buy_pct
        pullback = (dragon_day["close"] - closes[-1]) / dragon_day["close"] if dragon_day["close"] > 0 else 0
        pullback_ok = 0.02 <= pullback <= 0.08
        ma20 = sma(closes, self.MA_PERIOD)
        ma20_prev5 = sma(closes[:-5], self.MA_PERIOD)
        ma_support = closes[-1] > ma20 * 0.98
        ma20_up = ma20 > ma20_prev5
        dragon_vol = dragon_day["volume"]
        vol_shrink = vols[-1] < dragon_vol * 0.5
        vol_trend_down = (len(vols) >= 3 and
                          vols[-1] < vols[-2] < vols[-3])
        vol_breakout = vols[-1] > vols[-2] * 1.2 if len(vols) >= 2 else False
        _, _, adx = dmi(highs, lows, closes, 14)
        dif_series = self._compute_dif_series(closes, 12, 26)
        dea_series = ema(dif_series, 9) if len(dif_series) >= 9 else dif_series
        dif = dif_series[-1]
        prev_dif = dif_series[-2] if len(dif_series) >= 2 else 0
        dea = dea_series[-1]
        prev_dea = dea_series[-2] if len(dea_series) >= 2 else 0
        return {
            "dragon_day": dragon_day, "dragon_idx": dragon_idx,
            "net_buy_ratio": net_buy_ratio, "inst_ok": inst_ok,
            "pullback": pullback, "pullback_ok": pullback_ok,
            "ma20": ma20, "ma20_up": ma20_up, "ma_support": ma_support,
            "vol_shrink": vol_shrink, "vol_trend_down": vol_trend_down,
            "vol_breakout": vol_breakout, "adx": adx,
            "dif": dif, "prev_dif": prev_dif, "dea": dea, "prev_dea": prev_dea,
            "dragon_vol": dragon_vol, "dragon_close": dragon_day["close"],
            "dragon_low": dragon_day.get("low", dragon_day["close"]),
        }

    def _check_exit(self, ctx, closes, last):
        ma20 = ctx["ma20"]
        dif, prev_dif = ctx["dif"], ctx["prev_dif"]
        dea, prev_dea = ctx["dea"], ctx["prev_dea"]
        if last["close"] < ma20 * 0.97:
            result = {"action": "sell", "price": last["close"], "reason": "below_ma20"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if last["close"] < ctx["dragon_close"] * 0.90:
            result = {"action": "sell", "price": last["close"], "reason": "deep_pullback"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if prev_dif >= prev_dea and dif < dea:
            result = {"action": "sell", "price": last["close"], "reason": "macd_death"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        if last["volume"] > ctx["dragon_vol"] * 1.5 and last["close"] < closes[-2]:
            result = {"action": "sell", "price": last["close"], "reason": "heavy_sell"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        return None

    def _check_entry(self, ctx, closes, vols, last):
        if not (ctx["inst_ok"] and ctx["pullback_ok"] and ctx["ma_support"]
                and ctx["vol_shrink"] and ctx["vol_trend_down"]
                and ctx["vol_breakout"] and ctx["adx"] > self.ADX_THRESHOLD
                and ctx["ma20_up"]):
            conditions = {"inst_ok": ctx["inst_ok"], "pullback_ok": ctx["pullback_ok"], "ma_support": ctx["ma_support"], "vol_shrink": ctx["vol_shrink"], "vol_trend_down": ctx["vol_trend_down"], "vol_breakout": ctx["vol_breakout"], "adx_ok": ctx["adx"] > self.ADX_THRESHOLD, "ma20_up": ctx["ma20_up"]}
            self._log_entry_fail(conditions, f"date={last.get('date','')}")
            return None
        price = last["close"]
        stop_loss = max(ctx["ma20"] * 0.97, ctx["dragon_low"] * 0.98)
        take_profit = ctx["dragon_close"] * 1.12
        result = {
            "action": "buy", "price": price,
            "stop_loss": round(stop_loss, 3), "take_profit": round(take_profit, 3),
            "dragon_close": round(ctx["dragon_close"], 2),
            "pullback_pct": round(ctx["pullback"] * 100, 1),
            "net_buy_ratio": round(ctx["net_buy_ratio"], 1),
            "vol_shrink_ratio": round(last["volume"] / ctx["dragon_vol"], 2),
            "ma20": round(ctx["ma20"], 3), "adx": round(ctx["adx"], 1),
        }
        self._log_signal("buy", result, f"date={last.get('date','')}")
        return result

    def _compute_dif_series(self, closes, fast, slow):
        ema_fast = ema(closes, fast)
        ema_slow = ema(closes, slow)
        return [ema_fast[i] - ema_slow[i] for i in range(len(closes))]

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
            "institutional_buy_pct": self.INST_BUY_RANGE,
            "pullback_days": self.PULLBACK_DAYS_RANGE,
        }

    def validate_params(self, params: dict) -> bool:
        ip = params.get("institutional_buy_pct", 15)
        pd = params.get("pullback_days", 3)
        return (self.INST_BUY_RANGE[0] <= ip <= self.INST_BUY_RANGE[1]
                and self.PULLBACK_DAYS_RANGE[0] <= pd <= self.PULLBACK_DAYS_RANGE[1])