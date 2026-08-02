"""策略13：60日线牛熊分界战法

来源：同花顺金融大师·策略战法
逻辑：60日线上方运行 + 均线向上 + 连续5日回调不破 + 缩量企稳
"""
from decimal import Decimal
from core.strategies.ths_strategies._ma_pullback_base import MAPullbackBase


class SixtyDayBullBearStrategy(MAPullbackBase):
    NAME = "60日线牛熊分界"
    RISK_LEVEL = "中"
    MA_PERIOD = 60
    PULLBACK_DAYS = 5
    POSITION_RATIO = Decimal("0.15")
