"""战法09：市场情绪温度计

来源：同花顺金融大师·高阶战法
逻辑：上涨比例>70% + 打板次日成功率>50% + 连板增加 + 大面未超警戒
"""
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy


class MarketEmotionStrategy(THSBaseStrategy):
    NAME = "市场情绪温度计"
    CATEGORY = "ths_advanced"
    RISK_LEVEL = "中"
    UP_RATIO_RANGE = (0.6, 0.8)
    BOARD_SUCCESS_RANGE = (0.4, 0.6)

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < 5:
            return None
        up_min = params.get("up_ratio_min", 0.7)
        board_min = params.get("board_success_min", 0.5)
        alert_thr = params.get("face_alert_threshold", 0.6)
        last = bars[-1]
        emotion = last.get("market_emotion")
        if not emotion:
            return None
        up_ratio = emotion.get("up_ratio", 0)
        board_success = emotion.get("board_success_rate", 0)
        face_alert = emotion.get("face_alert_level", 1)
        consecutive_boards = emotion.get("consecutive_boards", 0)
        prev_boards = bars[-2].get("market_emotion", {}).get("consecutive_boards", 0)
        boards_increasing = consecutive_boards > prev_boards
        if up_ratio > up_min and board_success > board_min and face_alert < alert_thr and boards_increasing:
            return {
                "action": "buy",
                "price": last["close"],
                "stop_loss": round(last["close"] * 0.95, 3),
                "take_profit": round(last["close"] * 1.05, 3),
                "up_ratio": round(up_ratio, 3),
                "board_success": round(board_success, 3),
            }
        return None

    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        if signal.get("action") != "buy":
            return Decimal("0")
        return (capital * Decimal("0.10")).quantize(Decimal("0.01"))

    def get_param_space(self) -> dict[str, tuple]:
        return {"up_ratio_min": self.UP_RATIO_RANGE, "board_success_min": self.BOARD_SUCCESS_RANGE}

    def validate_params(self, params: dict) -> bool:
        u = params.get("up_ratio_min", 0.7)
        b = params.get("board_success_min", 0.5)
        return 0 < u < 1 and 0 < b < 1
