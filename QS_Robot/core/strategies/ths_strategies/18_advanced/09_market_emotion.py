"""战法09：市场情绪温度计 — 严格数学建模版

来源：同花顺金融大师·高阶战法
逻辑：上涨比例>70% + 打板次日成功率>50% + 连板增加 + 大面未超警戒
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from core.strategies.ths_strategies._indicators import sma


class MarketEmotionStrategy(THSBaseStrategy):
    ID = "09_market_emotion"
    NAME = "市场情绪温度计"
    CATEGORY = "ths_advanced"
    SOURCE = "同花顺金融大师"
    RISK_LEVEL = "中"
    UP_RATIO_RANGE = (0.6, 0.8)
    BOARD_SUCCESS_RANGE = (0.4, 0.6)
    RISK_PER_TRADE = Decimal("0.02")
    MAX_POSITION = Decimal("0.15")

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 5:
            self._log_data_short(len(bars), 5)
            return None
        up_min = params.get("up_ratio_min", 0.7)
        board_min = params.get("board_success_min", 0.5)
        alert_thr = params.get("face_alert_threshold", 0.6)
        closes = [b["close"] for b in bars]
        last = bars[-1]
        ctx = self._compute_indicators(last, bars, up_min, board_min, alert_thr)
        if ctx is None:
            return None
        exit_signal = self._check_exit(ctx, closes, last)
        if exit_signal:
            return exit_signal
        return self._check_entry(ctx, last)

    def _compute_indicators(self, last, bars, up_min, board_min, alert_thr):
        emotion = last.get("market_emotion")
        if not emotion:
            return None
        up_ratio = emotion.get("up_ratio", 0)
        board_success = emotion.get("board_success_rate", 0)
        face_alert = emotion.get("face_alert_level", 1)
        consecutive_boards = emotion.get("consecutive_boards", 0)
        prev_boards = bars[-2].get("market_emotion", {}).get("consecutive_boards", 0)
        boards_increasing = consecutive_boards > prev_boards
        return {
            "up_ratio": up_ratio, "up_min": up_min, "board_success": board_success,
            "board_min": board_min, "face_alert": face_alert, "alert_thr": alert_thr,
            "boards_increasing": boards_increasing,
            "up_ratio_ok": up_ratio > up_min,
            "board_success_ok": board_success > board_min,
            "face_alert_ok": face_alert < alert_thr,
        }

    def _check_exit(self, ctx, closes, last):
        if last["close"] < closes[-3] * 0.95:
            result = {"action": "sell", "price": last["close"], "reason": "deep_drawdown"}
            self._log_signal("sell", result, f"date={last.get('date','')}")
            return result
        return None

    def _check_entry(self, ctx, last):
        if not (ctx["up_ratio_ok"] and ctx["board_success_ok"]
                and ctx["face_alert_ok"] and ctx["boards_increasing"]):
            conditions = {"up_ratio_ok": ctx["up_ratio_ok"], "board_success_ok": ctx["board_success_ok"],
                          "face_alert_ok": ctx["face_alert_ok"], "boards_increasing": ctx["boards_increasing"]}
            self._log_entry_fail(conditions, f"date={last.get('date','')}")
            return None
        result = {
            "action": "buy", "price": last["close"],
            "stop_loss": round(last["close"] * 0.95, 3),
            "take_profit": round(last["close"] * 1.05, 3),
            "up_ratio": round(ctx["up_ratio"], 3),
            "board_success": round(ctx["board_success"], 3),
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
        return {"up_ratio_min": self.UP_RATIO_RANGE, "board_success_min": self.BOARD_SUCCESS_RANGE}

    def validate_params(self, params: dict) -> bool:
        u = params.get("up_ratio_min", 0.7)
        b = params.get("board_success_min", 0.5)
        return 0 < u < 1 and 0 < b < 1