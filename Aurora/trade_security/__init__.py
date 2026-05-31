"""
交易安全模块 - 向后兼容接口
==============================
P1-1 模块拆分：将 trade_security.py（715行）拆分为4个独立子模块

子模块:
  - trade_security.validator      : TradeSecurityValidator（交易验证器）
  - trade_security.critical_path   : CriticalPathValidator（毫秒级关键路径验证）
  - trade_security.fund_security   : FundSecurityValidator（资金安全保护）
  - trade_security.execution_engine: TradeExecutionEngine（交易执行引擎）

向后兼容:
  原有 `from trade_security import trade_validator` 仍然可用
"""

from .validator import TradeSecurityValidator, trade_validator
from .critical_path import CriticalPathValidator, critical_path_validator
from .fund_security import FundSecurityValidator, fund_security_validator
from .execution_engine import TradeExecutionEngine, trade_execution_engine

__all__ = [
    "TradeSecurityValidator",
    "CriticalPathValidator",
    "FundSecurityValidator",
    "TradeExecutionEngine",
    "trade_validator",
    "critical_path_validator",
    "fund_security_validator",
    "trade_execution_engine",
]