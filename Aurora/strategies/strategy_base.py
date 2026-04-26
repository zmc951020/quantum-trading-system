#!/usr/bin/env python3
"""
策略抽象基类和插件架构
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional, Any
import pandas as pd

class StrategyBase(ABC):
    """
    策略基类，定义所有策略必须实现的接口
    """
    
    def __init__(self, base_price: float, initial_balance: float = 100000):
        """
        初始化策略
        
        Args:
            base_price: 基准价格
            initial_balance: 初始资金
        """
        self.base_price = base_price
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.position = 0
        self.is_active = True
        self.last_price = base_price
        self.entry_price = 0
        
        # 交易统计
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.profit_history = []
    
    @abstractmethod
    def update_price(self, current_price: float, data: Optional[pd.Series] = None) -> Dict[str, Any]:
        """
        更新价格并执行交易
        
        Args:
            current_price: 当前价格
            data: 价格数据（可选）
            
        Returns:
            交易结果
        """
        pass
    
    @abstractmethod
    def get_performance(self) -> Dict[str, float]:
        """
        获取策略性能指标
        
        Returns:
            性能指标字典
        """
        pass
    
    def set_active(self, active: bool):
        """
        设置策略是否激活
        
        Args:
            active: 是否激活
        """
        self.is_active = active
    
    def get_balance(self) -> float:
        """
        获取当前资金
        
        Returns:
            当前资金
        """
        return self.current_balance
    
    def get_position(self) -> float:
        """
        获取当前持仓
        
        Returns:
            当前持仓
        """
        return self.position

class StrategyManager:
    """
    策略管理器，负责策略的注册、选择和切换
    """
    
    def __init__(self):
        """
        初始化策略管理器
        """
        self.strategies = {}
        self.active_strategy = None
    
    def register_strategy(self, name: str, strategy: StrategyBase):
        """
        注册策略
        
        Args:
            name: 策略名称
            strategy: 策略实例
        """
        self.strategies[name] = strategy
    
    def select_strategy(self, name: str) -> bool:
        """
        选择策略
        
        Args:
            name: 策略名称
            
        Returns:
            是否选择成功
        """
        if name in self.strategies:
            # 停用之前的策略
            if self.active_strategy and self.active_strategy in self.strategies:
                self.strategies[self.active_strategy].set_active(False)
            
            # 激活新策略
            self.active_strategy = name
            self.strategies[name].set_active(True)
            return True
        return False
    
    def get_active_strategy(self) -> Optional[StrategyBase]:
        """
        获取当前激活的策略
        
        Returns:
            当前激活的策略实例
        """
        if self.active_strategy and self.active_strategy in self.strategies:
            return self.strategies[self.active_strategy]
        return None
    
    def get_strategy(self, name: str) -> Optional[StrategyBase]:
        """
        获取指定策略
        
        Args:
            name: 策略名称
            
        Returns:
            策略实例
        """
        return self.strategies.get(name)
    
    def list_strategies(self) -> list:
        """
        列出所有注册的策略
        
        Returns:
            策略名称列表
        """
        return list(self.strategies.keys())
    
    def update_price(self, current_price: float, data: Optional[pd.Series] = None) -> Dict[str, Any]:
        """
        使用当前激活的策略更新价格并执行交易
        
        Args:
            current_price: 当前价格
            data: 价格数据（可选）
            
        Returns:
            交易结果
        """
        strategy = self.get_active_strategy()
        if strategy and strategy.is_active:
            return strategy.update_price(current_price, data)
        return {"action": "hold", "balance": 0, "position": 0}
    
    def get_active_performance(self) -> Dict[str, float]:
        """
        获取当前激活策略的性能指标
        
        Returns:
            性能指标字典
        """
        strategy = self.get_active_strategy()
        if strategy:
            return strategy.get_performance()
        return {}
