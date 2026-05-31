"""交易执行引擎 - TradeExecutionEngine
从 trade_security.py 拆分，负责绝对安全的交易流程执行
"""
import time, logging
from datetime import datetime
from typing import Dict

try:
    from .critical_path import critical_path_validator
except ImportError:
    from trade_security.critical_path import critical_path_validator

logger = logging.getLogger(__name__)

class TradeExecutionEngine:
    """交易执行引擎 - 绝对安全的交易流程
    绝对顺序：1.验证（不提交订单）→ 2.只有100%通过后才提交
    """

    def __init__(self):
        self.trade_history = []
        self.rejected_trades = []

    def execute_trade(self, order_info: dict, monitor: bool = False) -> dict:
        """绝对安全的交易执行流程（带实时监控）"""
        start_time = time.time()
        monitor_logs = []

        def log(msg):
            if monitor:
                monitor_logs.append(msg)
                print(f"[监控] {msg}")

        result = {"order_id":f"TRADE_{int(time.time()*1000)}","timestamp":datetime.now().isoformat(),"order_info":order_info,"monitor_logs":monitor_logs if monitor else None}

        log("阶段1/3: 开始关键路径验证（不提交订单）")
        validation_start = time.time()
        client_ip = order_info.get("ip","")
        api_key = order_info.get("api_key","")
        allowed, reason = critical_path_validator.validate_critical_path(client_ip, api_key, check_time=True)

        validation_time = (time.time() - validation_start) * 1000
        result["validation_time_ms"] = round(validation_time, 3)

        if not allowed:
            reject_result = {**result,"status":"REJECTED_BEFORE_SUBMIT","action":"订单被拒绝（未提交）","reason":reason,"details":"关键路径验证未通过，订单尚未提交即被终止","submitted_to_exchange":False}
            self.rejected_trades.append(reject_result)
            return reject_result

        log("阶段2/3: 准备提交到交易所...")
        execution_start = time.time()
        try:
            execution_details = self._perform_exchange_trade(order_info)
            execution_time = (time.time() - execution_start) * 1000
            total_time = (time.time() - start_time) * 1000

            success_result = {**result,"status":"EXECUTED_AFTER_VALIDATION","action":"交易成功执行（验证通过后）","reason":"关键路径验证通过后提交","execution_details":execution_details,"execution_time_ms":round(execution_time,3),"total_time_ms":round(total_time,3),"submitted_to_exchange":True}
            self.trade_history.append(success_result)
            return success_result
        except Exception as e:
            error_result = {**result,"status":"ERROR_AFTER_VALIDATION","action":"交易执行出错（验证通过但提交失败）","reason":str(e),"submitted_to_exchange":False}
            self.rejected_trades.append(error_result)
            return error_result

    def _perform_exchange_trade(self, order_info: dict) -> dict:
        """执行实际的交易所交易（模拟）"""
        return {"exchange":"模拟交易所","symbol":order_info.get("symbol"),"side":order_info.get("side"),"amount":order_info.get("amount"),"price":order_info.get("price"),"executed_at":datetime.now().isoformat(),"status":"filled"}

    def get_execution_report(self) -> dict:
        total = len(self.trade_history) + len(self.rejected_trades)
        return {"total_trades":total,"successful_trades":len(self.trade_history),"rejected_trades":len(self.rejected_trades),"success_rate":round(len(self.trade_history)/total*100 if total>0 else 0,2),"recent_trades":self.trade_history[-10:],"recent_rejections":self.rejected_trades[-10:]}

trade_execution_engine = TradeExecutionEngine()