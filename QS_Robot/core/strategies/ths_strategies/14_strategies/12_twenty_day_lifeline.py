"""策略12：20日线生命线低吸战法

来源：同花顺金融大师·策略战法
逻辑：20日线上方运行 + 均线向上 + 连续3日回调不破 + 缩量收阳
"""
from decimal import Decimal
from core.strategies.ths_strategies._ma_pullback_base import MAPullbackBase


class TwentyDayLifelineStrategy(MAPullbackBase):
    NAME = "20日线生命线低吸"
    RISK_LEVEL = "中"
    MA_PERIOD = 20
    PULLBACK_DAYS = 3
    POSITION_RATIO = Decimal("0.12")
