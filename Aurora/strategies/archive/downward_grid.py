#!/usr/bin/env python3
"""
下跌市场网格交易策略
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional

class DownwardGridTrading:
    """
    下跌市场网格交易策略
    """
    
    def __init__(self, base_price: float, initial_balance: float = 100000):
        """
        初始化下跌市场网格交易策略
        
        Args:
            base_price: 基准价格
            initial_balance: 初始资金
        """
        self.base_price = base_price
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.position = 0
        self.price_history = []
        self.is_active = True
        self.last_price = base_price  # 上次价格
        self.entry_price = 0  # 入场价格
        
        # 交易统计
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        
        # 风险控制参数
        self.stop_loss_threshold = 0.015  # 1.5%止损（更严格）
        self.take_profit_threshold = 0.025  # 2.5%止盈（更保守）
        self.max_position_percentage = 0.4  # 最大持仓比例（更低）
        self.reserve_balance_percentage = 0.5  # 保留资金比例（更高）
        
        # 下跌市场特定参数
        self.downward_buy_levels = []  # 下跌买入点位
        self.downward_buy_amounts = []  # 对应买入金额
        self.downward_buy_executed = []  # 已执行的买入点位
        self.downward_sell_levels = []  # 下跌反弹卖出点位
        
        # 历史最高价格
        self.highest_price = base_price
        self.last_buy_price = 0  # 上次买入价格
        self.profit_target = 0  # 盈利目标价格
        
        # 初始化下跌买入和卖出点位
        self._init_downward_levels()
    
    def _init_downward_levels(self):
        """
        初始化下跌买入和卖出点位
        """
        # 定义下跌买入点位（相对于基准价格的百分比）
        buy_levels = [0.98, 0.95, 0.92, 0.90, 0.88, 0.85, 0.82, 0.80, 0.78, 0.75, 0.72, 0.70]
        for level in buy_levels:
            price = self.base_price * level
            self.downward_buy_levels.append(price)
            # 价格越低，买入金额越大
            amount_ratio = (1 - level) * 20  # 价格越低，买入比例越高
            max_amount = self.initial_balance * 0.2  # 单次最大买入金额
            amount = min(max_amount, self.initial_balance * 0.05 * amount_ratio)
            self.downward_buy_amounts.append(amount)
            self.downward_buy_executed.append(False)
        
        # 按价格从高到低排序
        sorted_pairs = sorted(zip(self.downward_buy_levels, self.downward_buy_amounts, self.downward_buy_executed), reverse=True)
        self.downward_buy_levels, self.downward_buy_amounts, self.downward_buy_executed = zip(*sorted_pairs)
        self.downward_buy_levels = list(self.downward_buy_levels)
        self.downward_buy_amounts = list(self.downward_buy_amounts)
        self.downward_buy_executed = list(self.downward_buy_executed)
    
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
            data: 价格数据（用于市场类型检测）
            
        Returns:
            交易结果
        """
        # 记录价格历史
        self.price_history.append(current_price)
        
        # 更新历史最高价格
        if current_price > self.highest_price:
            self.highest_price = current_price
            # 价格创新高，重置买入点位
            self.downward_buy_executed = [False] * len(self.downward_buy_executed)
            self.last_buy_price = 0
            self.profit_target = 0
        
        # 计算价格变化
        price_change = (current_price - self.last_price) / self.last_price if self.last_price > 0 else 0
        
        # 止损检查：如果持仓亏损超过止损阈值，自动止损
        if self.position > 0 and self.entry_price > 0:
            loss_ratio = (current_price - self.entry_price) / self.entry_price
            if loss_ratio < -self.stop_loss_threshold:
                # 止损卖出
                revenue = self.position * current_price
                self.current_balance += revenue
                quantity = self.position
                self.position = 0
                self.entry_price = 0
                self.last_price = current_price
                self.total_trades += 1
                self.losing_trades += 1
                return {
                    "action": "sell",
                    "quantity": quantity,
                    "price": current_price,
                    "balance": self.current_balance,
                    "position": self.position,
                    "reason": "stop_loss"
                }
        
        # 止盈检查：如果持仓盈利超过止盈阈值，自动止盈
        if self.position > 0 and self.entry_price > 0:
            profit_ratio = (current_price - self.entry_price) / self.entry_price
            if profit_ratio > self.take_profit_threshold:
                # 止盈卖出全部
                revenue = self.position * current_price
                self.current_balance += revenue
                quantity = self.position
                self.position = 0
                self.entry_price = 0
                self.last_price = current_price
                self.total_trades += 1
                self.winning_trades += 1
                return {
                    "action": "sell",
                    "quantity": quantity,
                    "price": current_price,
                    "balance": self.current_balance,
                    "position": self.position,
                    "reason": "take_profit"
                }
        
        # 计算可用资金（保留reserve_balance_percentage作为接盘资金）
        available_balance = self.current_balance * (1 - self.reserve_balance_percentage)
        
        # 计算最大持仓限制
        max_position = (self.initial_balance * self.max_position_percentage) / current_price
        
        # 下跌市场的买入策略
        if self.position < max_position:
            # 检查是否达到下跌买入点位
            for i, (buy_level, buy_amount, executed) in enumerate(zip(self.downward_buy_levels, self.downward_buy_amounts, self.downward_buy_executed)):
                if current_price <= buy_level and not executed and available_balance > buy_amount:
                    # 达到买入点位
                    buy_quantity = buy_amount / current_price
                    if buy_quantity > 0.01:
                        self.position += buy_quantity
                        self.current_balance -= buy_amount
                        if self.entry_price == 0:
                            self.entry_price = current_price
                        self.last_buy_price = current_price
                        # 设置盈利目标价格（买入价格的2.5%以上）
                        self.profit_target = current_price * (1 + self.take_profit_threshold)
                        self.last_price = current_price
                        # 标记为已执行
                        self.downward_buy_executed[i] = True
                        return {
                            "action": "buy",
                            "quantity": buy_quantity,
                            "price": current_price,
                            "balance": self.current_balance,
                            "position": self.position,
                            "reason": "downward_buy_level"
                        }
        
        # 下跌市场的卖出策略（反弹卖出）
        if self.position > 0 and current_price > self.last_buy_price * 1.015:
            # 价格反弹1.5%以上，卖出部分
            sell_quantity = self.position * 0.6
            if sell_quantity > 0.01:
                sell_amount = sell_quantity * current_price
                self.position -= sell_quantity
                self.current_balance += sell_amount
                self.last_price = current_price
                self.total_trades += 1
                if current_price > self.entry_price:
                    self.winning_trades += 1
                else:
                    self.losing_trades += 1
                return {
                    "action": "sell",
                    "quantity": sell_quantity,
                    "price": current_price,
                    "balance": self.current_balance,
                    "position": self.position,
                    "reason": "downward_rally_sell"
                }
        
        # 价格创新低后的反弹卖出
        if self.position > 0 and len(self.price_history) > 5:
            recent_prices = self.price_history[-5:]
            recent_low = min(recent_prices)
            if current_price > recent_low * 1.02:
                # 价格从近期低点反弹2%以上，卖出部分
                sell_quantity = self.position * 0.5
                if sell_quantity > 0.01:
                    sell_amount = sell_quantity * current_price
                    self.position -= sell_quantity
                    self.current_balance += sell_amount
                    self.last_price = current_price
                    self.total_trades += 1
                    if current_price > self.entry_price:
                        self.winning_trades += 1
                    else:
                        self.losing_trades += 1
                    return {
                        "action": "sell",
                        "quantity": sell_quantity,
                        "price": current_price,
                        "balance": self.current_balance,
                        "position": self.position,
                        "reason": "low_bounce_sell"
                    }
        
        # 价格跌破重要支撑位后的买入
        if available_balance > 1000:
            # 检查是否跌破重要支撑位
            if len(self.price_history) > 20:
                recent_prices = self.price_history[-20:]
                support_level = min(recent_prices)
                if current_price < support_level * 0.99:
                    # 跌破支撑位，买入
                    buy_amount = min(available_balance * 0.3, 5000)
                    if buy_amount > 200:
                        buy_quantity = buy_amount / current_price
                        if buy_quantity > 0.01:
                            self.position += buy_quantity
                            self.current_balance -= buy_amount
                            if self.entry_price == 0:
                                self.entry_price = current_price
                            self.last_buy_price = current_price
                            self.profit_target = current_price * (1 + self.take_profit_threshold)
                            self.last_price = current_price
                            return {
                                "action": "buy",
                                "quantity": buy_quantity,
                                "price": current_price,
                                "balance": self.current_balance,
                                "position": self.position,
                                "reason": "support_break_buy"
                            }
        
        # 更新但不交易
        self.last_price = current_price
        return {"action": "hold", "balance": self.current_balance, "position": self.position}
    
    def get_performance(self) -> Dict[str, float]:
        """
        获取策略性能
        
        Returns:
            性能指标
        """
        win_rate = self.winning_trades / self.total_trades if self.total_trades > 0 else 0
        return {
            "initial_balance": self.initial_balance,
            "current_balance": self.current_balance,
            "return": (self.current_balance - self.initial_balance) / self.initial_balance * 100,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": win_rate,
            "final_position": self.position
        }
