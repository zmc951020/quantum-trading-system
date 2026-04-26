#!/usr/bin/env python3
"""
基于机器学习的网格交易策略
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from ml.dynamic_grid import GridStepOptimizer

class MLGridTrading:
    """
    基于机器学习的网格交易策略
    """
    
    def __init__(self, base_price: float, initial_balance: float = 100000):
        """
        初始化基于机器学习的网格交易策略
        
        Args:
            base_price: 基准价格
            initial_balance: 初始资金
        """
        self.base_price = base_price
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.position = 0
        self.grid_spacing = 0.003  # 初始网格间距
        self.grid_levels = 15  # 网格层数
        self.grids = self._create_grids()
        self.price_history = []
        self.is_active = True
        self.last_grid_index = 0  # 上次所在的网格索引
        self.last_price = base_price  # 上次价格
        self.entry_price = 0  # 入场价格
        self.consecutive_holds = 0  # 连续不交易次数
        self.min_grid_spacing = 0.001  # 最小网格间距
        self.max_grid_spacing = 0.02  # 最大网格间距
        
        # 机器学习优化器
        self.optimizer = GridStepOptimizer()
        self.optimization_count = 0  # 优化次数
    
    def _create_grids(self) -> List[float]:
        """
        创建网格价格水平
        
        Returns:
            网格价格列表
        """
        grids = []
        for i in range(-self.grid_levels, self.grid_levels + 1):
            price = self.base_price * (1 + self.grid_spacing) ** i
            grids.append(price)
        return sorted(grids)
    
    def detect_market_type(self, data: pd.Series) -> str:
        """
        检测市场类型
        
        Args:
            data: 价格数据
            
        Returns:
            市场类型: 'range_bound', 'trending_up', 'trending_down'
        """
        if len(data) < 20:
            return 'range_bound'
        
        # 计算趋势强度
        ema20 = data.ewm(span=20).mean().iloc[-1]
        ema50 = data.ewm(span=50).mean().iloc[-1]
        trend_strength = (ema20 - ema50) / ema50
        
        # 计算价格范围
        price_range = (data.max() - data.min()) / data.mean()
        
        # 确定市场类型
        if abs(trend_strength) > 0.03:
            if trend_strength > 0:
                return 'trending_up'
            else:
                return 'trending_down'
        elif price_range < 0.04:
            # 窄幅横盘，适合网格交易
            return 'range_bound'
        elif price_range > 0.08:
            # 宽幅波动，适合趋势交易
            if trend_strength > 0:
                return 'trending_up'
            else:
                return 'trending_down'
        else:
            # 中等波动，根据趋势强度判断
            if abs(trend_strength) > 0.015:
                if trend_strength > 0:
                    return 'trending_up'
                else:
                    return 'trending_down'
            else:
                return 'range_bound'
    
    def set_active(self, active: bool):
        """
        设置策略是否激活
        
        Args:
            active: 是否激活
        """
        self.is_active = active
    
    def update_price(self, current_price: float, data: pd.Series = None) -> Dict[str, any]:
        """
        更新价格并执行交易
        
        Args:
            current_price: 当前价格
            data: 价格数据（用于市场类型检测和机器学习优化）
            
        Returns:
            交易结果
        """
        # 记录价格历史
        self.price_history.append(current_price)
        
        # 检测市场类型并决定是否执行交易
        if data is not None:
            market_type = self.detect_market_type(data)
            if market_type != 'range_bound':
                # 非网格市场，停止交易
                self.set_active(False)
                # 平仓所有仓位
                if self.position != 0:
                    revenue = self.position * current_price
                    self.current_balance += revenue
                    quantity = self.position
                    self.position = 0
                    return {
                        "action": "sell",
                        "quantity": quantity,
                        "price": current_price,
                        "balance": self.current_balance,
                        "position": self.position,
                        "reason": "market_not_range_bound"
                    }
                return {"action": "hold", "balance": self.current_balance, "position": self.position, "reason": "market_not_range_bound"}
        
        # 如果策略未激活，不执行交易
        if not self.is_active:
            return {"action": "hold", "balance": self.current_balance, "position": self.position, "reason": "strategy_inactive"}
        
        # 每20个数据点使用机器学习优化网格步长
        if data is not None and len(data) >= 30 and len(self.price_history) % 20 == 0:
            optimal_step = self.optimizer.calculate_optimal_grid_step(data)
            optimal_step = max(self.min_grid_spacing, min(self.max_grid_spacing, optimal_step))
            if abs(optimal_step - self.grid_spacing) > 0.0005:
                self.grid_spacing = optimal_step
                self.grids = self._create_grids()
                self.optimization_count += 1
        
        # 找到当前价格所在的网格区间
        current_grid_index = None
        for i in range(len(self.grids) - 1):
            if self.grids[i] <= current_price < self.grids[i + 1]:
                current_grid_index = i
                break
        
        if current_grid_index is None:
            return {"action": "hold", "balance": self.current_balance, "position": self.position}
        
        # 计算价格变化
        price_change = (current_price - self.last_price) / self.last_price if self.last_price > 0 else 0
        
        # 止损检查：如果持仓亏损超过3%，自动止损
        if self.position > 0 and self.entry_price > 0:
            loss_ratio = (current_price - self.entry_price) / self.entry_price
            if loss_ratio < -0.03:
                # 止损卖出
                revenue = self.position * current_price
                self.current_balance += revenue
                quantity = self.position
                self.position = 0
                self.entry_price = 0
                self.last_grid_index = current_grid_index
                self.last_price = current_price
                return {
                    "action": "sell",
                    "quantity": quantity,
                    "price": current_price,
                    "balance": self.current_balance,
                    "position": self.position,
                    "reason": "stop_loss"
                }
        
        # 止盈检查：如果持仓盈利超过4%，自动止盈
        if self.position > 0 and self.entry_price > 0:
            profit_ratio = (current_price - self.entry_price) / self.entry_price
            if profit_ratio > 0.04:
                # 止盈卖出70%
                sell_quantity = self.position * 0.7
                if sell_quantity > 0.01:
                    revenue = sell_quantity * current_price
                    self.current_balance += revenue
                    self.position -= sell_quantity
                    self.last_grid_index = current_grid_index
                    self.last_price = current_price
                    return {
                        "action": "sell",
                        "quantity": sell_quantity,
                        "price": current_price,
                        "balance": self.current_balance,
                        "position": self.position,
                        "reason": "take_profit"
                    }
        
        # 网格交易核心逻辑：
        # 1. 价格下跌到新的网格 -> 买入
        # 2. 价格上涨到新的网格 -> 卖出
        # 3. 不限制交易次数，只要触发条件就交易
        grid_change = current_grid_index - self.last_grid_index
        
        # 计算可用资金（保留30%作为接盘资金）
        available_balance = self.current_balance * 0.7
        
        if grid_change < 0:
            # 价格下跌到更低网格 -> 买入（低买）
            # 计算买入金额：基于网格变化和可用资金
            buy_amount = min(abs(grid_change) * 1000, available_balance)
            if buy_amount > 30:  # 最小买入金额30元
                buy_quantity = buy_amount / current_price
                if buy_quantity > 0.01:  # 最小交易量
                    self.position += buy_quantity
                    self.current_balance -= buy_amount
                    if self.entry_price == 0:
                        self.entry_price = current_price
                    self.last_grid_index = current_grid_index
                    self.last_price = current_price
                    return {
                        "action": "buy",
                        "quantity": buy_quantity,
                        "price": current_price,
                        "balance": self.current_balance,
                        "position": self.position
                    }
        elif grid_change > 0 and self.position > 0:
            # 价格上涨到更高网格 -> 卖出（高卖）
            # 计算卖出数量：基于网格变化和当前持仓
            sell_quantity = min(abs(grid_change) * 1000 / current_price, self.position)
            if sell_quantity > 0.01:  # 最小交易量
                sell_amount = sell_quantity * current_price
                self.position -= sell_quantity
                self.current_balance += sell_amount
                self.last_grid_index = current_grid_index
                self.last_price = current_price
                return {
                    "action": "sell",
                    "quantity": sell_quantity,
                    "price": current_price,
                    "balance": self.current_balance,
                    "position": self.position
                }
        
        # 市场下跌时的资金接盘机制
        # 如果价格下跌超过1.5%且有可用资金，自动加仓
        if price_change < -0.015 and available_balance > 500:
            buy_amount = min(available_balance * 0.2, 3000)
            if buy_amount > 50:
                buy_quantity = buy_amount / current_price
                if buy_quantity > 0.01:
                    self.position += buy_quantity
                    self.current_balance -= buy_amount
                    if self.entry_price == 0:
                        self.entry_price = current_price
                    self.last_price = current_price
                    return {
                        "action": "buy",
                        "quantity": buy_quantity,
                        "price": current_price,
                        "balance": self.current_balance,
                        "position": self.position,
                        "reason": "market_drop_buy"
                    }
        
        # 市场上涨时的获利了结
        # 如果价格上涨超过1.5%且有持仓，自动卖出部分
        if price_change > 0.015 and self.position > 0:
            sell_quantity = min(self.position * 0.3, 1000 / current_price)
            if sell_quantity > 0.01:
                sell_amount = sell_quantity * current_price
                self.position -= sell_quantity
                self.current_balance += sell_amount
                self.last_price = current_price
                return {
                    "action": "sell",
                    "quantity": sell_quantity,
                    "price": current_price,
                    "balance": self.current_balance,
                    "position": self.position,
                    "reason": "market_rise_sell"
                }
        
        # 更新但不交易
        self.consecutive_holds += 1
        self.last_grid_index = current_grid_index
        self.last_price = current_price
        return {"action": "hold", "balance": self.current_balance, "position": self.position}
    
    def get_performance(self) -> Dict[str, float]:
        """
        获取策略性能
        
        Returns:
            性能指标
        """
        return {
            "initial_balance": self.initial_balance,
            "current_balance": self.current_balance,
            "return": (self.current_balance - self.initial_balance) / self.initial_balance * 100
        }
