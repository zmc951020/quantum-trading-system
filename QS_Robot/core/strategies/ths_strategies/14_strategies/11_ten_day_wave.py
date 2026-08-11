"""策略11：10日线波段滚动战法 — 严格数学建模版

来源：同花顺金融大师·策略战法
逻辑：10日线上方运行 + 均线向上 + 连续2日回调不破 + 缩量收阳
"""
from decimal import Decimal
from core.strategies.ths_strategies._ma_pullback_base import MAPullbackBase


class TenDayWaveStrategy(MAPullbackBase):
    ID = "11_ten_day_wave"
    NAME = "10日线波段滚动"
    CATEGORY = "ths_strategies"
    SOURCE = "同花顺金融大师"
    RISK_LEVEL = "低"
    MA_PERIOD = 10
    PULLBACK_DAYS = 2
    POSITION_RATIO = Decimal("0.10")