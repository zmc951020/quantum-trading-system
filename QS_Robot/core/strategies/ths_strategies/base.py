"""同花顺金融大师策略基类

统一接口：generate_signal / calc_position / get_param_space / validate_params
所有 14 策略 + 18 高阶战法必须继承此类，确保熵韬优化器统一调度
"""
import logging
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any


class THSBaseStrategy(ABC):
    """同花顺策略抽象基类

    属性:
        ID: 策略ID（与JSON元数据 id 字段对应，如 "01_macd_wave"）
        NAME: 策略名（中文）
        CATEGORY: 分类（固定 "ths_strategies"）
        SOURCE: 来源（同花顺金融大师）
        RISK_LEVEL: 风险等级（低/中/高）
    """
    ID: str = ""
    NAME: str = ""
    CATEGORY: str = "ths_strategies"
    SOURCE: str = "同花顺金融大师"
    RISK_LEVEL: str = "中"

    @property
    def logger(self) -> logging.Logger:
        """策略专属 logger，自动以模块路径命名"""
        if not hasattr(self, "_logger"):
            self._logger = logging.getLogger(f"ths.{self.ID}")
        return self._logger

    def _log_signal(self, action: str, signal: dict, extra: str = "") -> None:
        """统一信号日志格式"""
        if action == "buy":
            self.logger.info(
                "📈 [%s] 买入信号 | 价格=%.2f 止损=%.2f 止盈=%.2f %s",
                self.NAME, signal["price"], signal["stop_loss"], signal["take_profit"], extra)
        elif action == "sell":
            reason = signal.get("reason", "unknown")
            self.logger.info(
                "📉 [%s] 卖出信号 | 价格=%.2f 原因=%s %s",
                self.NAME, signal["price"], reason, extra)

    def _log_entry_fail(self, conditions: dict, extra: str = "") -> None:
        """记录入场条件不满足详情"""
        failed = [k for k, v in conditions.items() if not v]
        if failed:
            self.logger.debug("[%s] 入场未触发 | 失败条件: %s %s", self.NAME, ",".join(failed), extra)

    def _log_data_short(self, bars: int, need: int) -> None:
        """数据不足日志"""
        self.logger.debug("[%s] 数据不足 | 当前=%d 需要=%d", self.NAME, bars, need)

    @abstractmethod
    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        """生成买卖信号"""

    @abstractmethod
    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        """计算仓位（Decimal 精度，禁止 float）"""

    @abstractmethod
    def get_param_space(self) -> dict[str, tuple]:
        """返回参数空间（供熵韬优化器寻优）"""

    @abstractmethod
    def validate_params(self, params: dict) -> bool:
        """参数校验"""