"""同花顺金融大师策略基类

统一接口：generate_signal / calc_position / get_param_space / validate_params
所有 14 策略 + 18 高阶战法必须继承此类，确保熵韬优化器统一调度
"""
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any


class THSBaseStrategy(ABC):
    """同花顺策略抽象基类

    属性:
        NAME: 策略名（中文）
        CATEGORY: 分类（固定 "ths_strategies"）
        SOURCE: 来源（同花顺金融大师）
        RISK_LEVEL: 风险等级（低/中/高）
    """
    NAME: str = ""
    CATEGORY: str = "ths_strategies"
    SOURCE: str = "同花顺金融大师"
    RISK_LEVEL: str = "中"

    @abstractmethod
    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        """生成买卖信号

        Args:
            bars: K线数据列表（含 open/high/low/close/volume/date）
            params: 策略参数

        Returns:
            信号字典 {action, price, stop_loss, take_profit, ...} 或 None
        """

    @abstractmethod
    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        """计算仓位（Decimal 精度，禁止 float）"""

    @abstractmethod
    def get_param_space(self) -> dict[str, tuple]:
        """返回参数空间（供熵韬优化器寻优）"""

    @abstractmethod
    def validate_params(self, params: dict) -> bool:
        """参数校验"""
