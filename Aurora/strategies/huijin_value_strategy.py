#!/usr/bin/env python3
"""
汇金价值AI轮动策略 - Aurora系统适配器
"""

import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from .strategy_base import StrategyBase
import sys
import os

# 直接添加汇金价值AI轮动策略的绝对路径
huijin_path = r"D:\Gupiao\量化交易测试设备方案\攒机\量化交易\汇金价值AI轮动策略"
sys.path.insert(0, huijin_path)

# 现在可以直接导入
from strategy_engine import HuijinValueStrategyEngine, SignalType, StrategyState, Signal, Position, StockCandidate


class HuijinValueStrategy(StrategyBase):
    """
    汇金价值AI轮动策略适配器
    让汇金价值AI轮动策略符合Aurora系统的StrategyBase接口
    """
    
    def __init__(self, initial_balance: float = 100000):
        """
        初始化策略
        
        Args:
            initial_balance: 初始资金
        """
        super().__init__(base_price=0, initial_balance=initial_balance)
        
        # 加载策略配置
        config_path = r"D:\Gupiao\量化交易测试设备方案\攒机\量化交易\汇金价值AI轮动策略\strategy_config.json"
        self.engine = HuijinValueStrategyEngine(config_path)
        
        # 初始化资金
        self.engine.total_capital = initial_balance
        
        # 日志配置
        self.logger = logging.getLogger('HuijinValueStrategy')
        
    def update_price(self, current_price: float, data: Optional[Any] = None) -> Dict[str, Any]:
        """
        更新价格并执行交易
        
        Args:
            current_price: 当前价格
            data: 价格数据（可选）
            
        Returns:
            交易结果
        """
        try:
            # 盘前扫描
            if self.engine.current_state == StrategyState.IDLE:
                candidates = self.engine.scan_market()
                filtered_candidates = self.engine.filter_stocks(candidates)
                
                # 生成交易信号
                signals = self.engine.generate_signals()
                
                # 检查风控
                alerts = self.engine.check_risk_controls()
                
            # 执行交易
            executed_signals = []
            for signal in self.engine.pending_signals:
                if signal.confirm_status == "CONFIRMED" and signal.trade_status == "PENDING":
                    if self.engine.execute_signal(signal.signal_id):
                        executed_signals.append(signal)
            
            # 更新资金和持仓
            self.current_balance = self.engine.total_capital - sum(
                pos.current_position_value for pos in self.engine.positions.values()
            )
            self.position = len(self.engine.positions)
            
            return {
                "action": "execute" if executed_signals else "hold",
                "balance": self.current_balance,
                "position": self.position,
                "executed_signals": len(executed_signals),
                "pending_signals": len(self.engine.pending_signals),
                "state": self.engine.current_state.value
            }
            
        except Exception as e:
            self.logger.error(f"策略执行错误: {e}")
            return {
                "action": "hold",
                "balance": self.current_balance,
                "position": self.position,
                "error": str(e)
            }
    
    def get_performance(self) -> Dict[str, float]:
        """
        获取策略性能指标
        
        Returns:
            性能指标字典
        """
        try:
            total_value = self.current_balance + sum(
                pos.current_position_value for pos in self.engine.positions.values()
            )
            total_return = (total_value - self.initial_balance) / self.initial_balance
            
            # 计算胜率
            winning_trades = sum(1 for pos in self.engine.positions.values() 
                                if pos.profit_loss_ratio > 0)
            total_trades = len(self.engine.positions)
            win_rate = winning_trades / total_trades if total_trades > 0 else 0
            
            return {
                "balance": self.current_balance,
                "total_value": total_value,
                "total_return": total_return,
                "win_rate": win_rate,
                "total_trades": total_trades,
                "winning_trades": winning_trades,
                "positions": len(self.engine.positions)
            }
            
        except Exception as e:
            self.logger.error(f"获取性能指标错误: {e}")
            return {
                "balance": self.current_balance,
                "total_value": self.current_balance,
                "total_return": 0,
                "win_rate": 0,
                "total_trades": 0,
                "winning_trades": 0,
                "positions": 0
            }
    
    def get_market_state(self) -> str:
        """
        获取市场状态
        
        Returns:
            市场状态
        """
        return self.engine.current_state.value
    
    def get_pending_signals(self) -> List[Signal]:
        """
        获取待处理信号
        
        Returns:
            待处理信号列表
        """
        return self.engine.get_pending_signals()
    
    def get_positions(self) -> Dict[str, Position]:
        """
        获取持仓
        
        Returns:
            持仓字典
        """
        return self.engine.get_positions()
    
    def confirm_signal(self, signal_id: str) -> bool:
        """
        确认信号
        
        Args:
            signal_id: 信号ID
            
        Returns:
            是否确认成功
        """
        return self.engine.confirm_signal(signal_id)
    
    def execute_signal(self, signal_id: str) -> bool:
        """
        执行信号
        
        Args:
            signal_id: 信号ID
            
        Returns:
            是否执行成功
        """
        return self.engine.execute_signal(signal_id)
    
    def scan_market(self) -> List[StockCandidate]:
        """
        盘前扫描
        
        Returns:
            候选股票列表
        """
        return self.engine.scan_market()
