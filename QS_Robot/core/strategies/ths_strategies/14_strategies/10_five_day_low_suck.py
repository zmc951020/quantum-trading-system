"""策略10：5日线超短低吸战法 — 严格数学建模版

来源：同花顺金融大师·策略战法
逻辑：5日线上方运行 + 均线向上 + 回踩1日不破 + 缩量收阳
"""
from decimal import Decimal
from core.strategies.ths_strategies._ma_pullback_base import MAPullbackBase


class FiveDayLowSuckStrategy(MAPullbackBase):
    ID = "10_five_day_low_suck"
    NAME = "5日线超短低吸"
    CATEGORY = "ths_strategies"
    SOURCE = "同花顺金融大师"
    RISK_LEVEL = "低"
    MA_PERIOD = 5
    PULLBACK_DAYS = 1
    POSITION_RATIO = Decimal("0.08")
    MAX_POSITION = Decimal("0.10")