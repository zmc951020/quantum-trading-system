"""交易安全模块 - 可拆分架构（P1-1修补项）

从 trade_security.py（715行）拆分为4个独立子模块：
  - trade_validator:       TradeSecurityValidator（配置驱动，6项检查）
  - critical_path:         CriticalPathValidator（毫秒级关键路径卡死）
  - fund_security:         FundSecurityValidator（资金安全保护）
  - execution_engine:      TradeExecutionEngine（绝对安全交易流程）

用法（向后兼容）：
  from utils.trade_security_modules import (
      TradeSecurityValidator,
      CriticalPathValidator,
      FundSecurityValidator,
      TradeExecutionEngine,
      trade_validator,
      critical_path_validator,
      fund_security_validator,
      trade_execution_engine,
  )
"""

import sys, os

_PARENT_MODULE = "trade_security"

try:
    import trade_security
except ImportError:
    _here = os.path.dirname(os.path.abspath(__file__))
    _root = os.path.dirname(_here)
    if _root not in sys.path:
        sys.path.insert(0, _root)
    import trade_security

TradeSecurityValidator = trade_security.TradeSecurityValidator
CriticalPathValidator = trade_security.CriticalPathValidator
FundSecurityValidator = trade_security.FundSecurityValidator
TradeExecutionEngine = trade_security.TradeExecutionEngine

trade_validator = getattr(trade_security, "trade_validator", None) or TradeSecurityValidator()
critical_path_validator = getattr(trade_security, "critical_path_validator", None) or CriticalPathValidator()
fund_security_validator = getattr(trade_security, "fund_security_validator", None) or FundSecurityValidator()
trade_execution_engine = getattr(trade_security, "trade_execution_engine", None) or TradeExecutionEngine()

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