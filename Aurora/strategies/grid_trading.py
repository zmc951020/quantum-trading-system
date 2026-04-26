#!/usr/bin/env python3
"""
网格化交易策略实现
"""

import numpy as np
import pandas as pd
import random
from typing import List, Dict, Tuple, Optional

class GridTrading:
    """
    网格化交易策略
    """
    
    def __init__(self, base_price: float, grid_spacing: float, 
                 grid_levels: int = 10, initial_balance: float = 100000):
        """
        初始化网格化交易策略
        
        Args:
            base_price: 基准价格
            grid_spacing: 网格间距
            grid_levels: 网格层数
            initial_balance: 初始资金
        """
        self.base_price = base_price
        self.grid_spacing = grid_spacing
        self.grid_levels = grid_levels
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.position = 0
        self.grids = self._create_grids()
        self.price_history = []
        self.is_active = True
        self.last_grid_index = 0  # 上次所在的网格索引
        self.last_price = base_price  # 上次价格
        self.entry_price = 0  # 入场价格
        self.consecutive_holds = 0  # 连续不交易次数
        self.min_grid_spacing = 0.003  # 最小网格间距
        self.max_grid_spacing = 0.02  # 最大网格间距
    
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
            市场类型: 'trending_up', 'trending_down', 'range_bound'
        """
        # 计算关键指标
        returns = data.pct_change().dropna()
        
        if len(returns) < 20:
            return 'range_bound'
        
        # 计算趋势强度
        ema20 = data.ewm(span=20, adjust=False).mean()
        ema50 = data.ewm(span=50, adjust=False).mean()
        trend_strength = (ema20.iloc[-1] - ema50.iloc[-1]) / ema50.iloc[-1]
        
        # 计算价格范围
        price_range = (data.iloc[-20:].max() - data.iloc[-20:].min()) / data.iloc[-20:].mean()
        
        # 确定市场类型
        if abs(trend_strength) > 0.05:  # 优化：0.02 -> 0.05（趋势强度>5%才切换）
            if trend_strength > 0:
                return 'trending_up'
            else:
                return 'trending_down'
        elif price_range < 0.05:  # 优化：0.03 -> 0.05（价格范围<5%视为横盘）
            # 窄幅横盘，适合网格交易
            return 'range_bound'
        elif price_range > 0.10:  # 优化：0.08 -> 0.10（价格范围>10%视为宽幅波动）
            # 宽幅波动，适合趋势交易
            if trend_strength > 0:
                return 'trending_up'
            else:
                return 'trending_down'
        else:
            # 中等波动，根据趋势强度判断
            if abs(trend_strength) > 0.03:  # 优化：0.01 -> 0.03
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
            data: 价格数据（用于市场类型检测）
            
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
        
        # 动态调整网格参数
        if len(self.price_history) > 20:
            recent_prices = pd.Series(self.price_history[-20:])
            volatility = recent_prices.pct_change().std()
            # 根据波动率调整网格间距
            optimal_spacing = max(self.min_grid_spacing, min(self.max_grid_spacing, volatility * 2))
            if abs(optimal_spacing - self.grid_spacing) > 0.001:
                self.grid_spacing = optimal_spacing
                self.grids = self._create_grids()
        
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
            buy_amount = min(abs(grid_change) * 1500, available_balance)
            if buy_amount > 50:  # 最小买入金额50元
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
            sell_quantity = min(abs(grid_change) * 1500 / current_price, self.position)
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
        # 如果价格下跌超过2%且有可用资金，自动加仓
        if price_change < -0.02 and available_balance > 1000:
            buy_amount = min(available_balance * 0.3, 5000)
            if buy_amount > 100:
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
            "pnl": self.current_balance - self.initial_balance,
            "return": (self.current_balance / self.initial_balance - 1) * 100
        }

class MLGridTrading:
    """
    基于机器学习的网格化交易策略
    """
    
    def __init__(self, base_price: float, initial_balance: float = 100000):
        """
        初始化基于机器学习的网格化交易策略
        
        Args:
            base_price: 基准价格
            initial_balance: 初始资金
        """
        self.base_price = base_price
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.position = 0
        self.grid_levels = 10
        self.grid_spacing = 0.01  # 初始网格间距
        self.price_history = []
        self.volatility_history = []
        self.best_spacing = 0.01
        self.is_active = True
        
        # 导入机器学习模块
        try:
            from ml.dynamic_grid import GridStepOptimizer
            self.optimizer = GridStepOptimizer()
            self.use_ml = True
        except:
            self.use_ml = False
    
    def detect_market_type(self, data: pd.Series) -> str:
        """
        检测市场类型
        
        Args:
            data: 价格数据
            
        Returns:
            市场类型: 'trending_up', 'trending_down', 'range_bound'
        """
        # 计算关键指标
        returns = data.pct_change().dropna()
        
        if len(returns) < 20:
            return 'range_bound'
        
        # 计算趋势强度
        ema20 = data.ewm(span=20, adjust=False).mean()
        ema50 = data.ewm(span=50, adjust=False).mean()
        trend_strength = (ema20.iloc[-1] - ema50.iloc[-1]) / ema50.iloc[-1]
        
        # 计算价格范围
        price_range = (data.iloc[-20:].max() - data.iloc[-20:].min()) / data.iloc[-20:].mean()
        
        # 确定市场类型
        if abs(trend_strength) > 0.02:
            if trend_strength > 0:
                return 'trending_up'
            else:
                return 'trending_down'
        elif price_range < 0.03:
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
            if abs(trend_strength) > 0.01:
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
            data: 历史价格数据（用于机器学习和市场类型检测）
            
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
                        "grid_spacing": self.grid_spacing,
                        "reason": "market_not_range_bound"
                    }
                return {"action": "hold", "balance": self.current_balance, "position": self.position, "grid_spacing": self.grid_spacing, "reason": "market_not_range_bound"}
        
        # 如果策略未激活，不执行交易
        if not self.is_active:
            return {"action": "hold", "balance": self.current_balance, "position": self.position, "grid_spacing": self.grid_spacing, "reason": "strategy_inactive"}
        
        # 动态调整网格间距
        if self.use_ml and data is not None and len(data) > 30:
            # 使用机器学习优化网格间距
            try:
                # 计算当前波动率
                if len(self.price_history) > 14:
                    returns = pd.Series(self.price_history).pct_change()
                    current_volatility = returns.iloc[-14:].std()
                    self.volatility_history.append(current_volatility)
                
                # 计算最优网格间距
                self.grid_spacing = self.optimizer.calculate_optimal_grid_step(data)
                self.best_spacing = self.grid_spacing
            except:
                pass
        elif len(self.price_history) > 14:
            # 简单的波动率调整
            returns = pd.Series(self.price_history).pct_change()
            current_volatility = returns.iloc[-14:].std()
            # 根据波动率调整网格间距
            self.grid_spacing = max(0.005, min(current_volatility * 2, 0.05))
        
        # 创建网格
        grids = []
        for i in range(-self.grid_levels, self.grid_levels + 1):
            price = self.base_price * (1 + self.grid_spacing) ** i
            grids.append(price)
        grids = sorted(grids)
        
        # 找到当前价格所在的网格区间
        for i in range(len(grids) - 1):
            if grids[i] <= current_price < grids[i + 1]:
                # 计算应该持有的仓位（优化资金使用）
                # 根据当前价格位置和资金状况调整仓位大小
                position_factor = 1.0
                if len(self.price_history) > 50:
                    # 根据价格趋势调整仓位
                    recent_prices = self.price_history[-50:]
                    trend = (recent_prices[-1] - recent_prices[0]) / recent_prices[0]
                    if trend > 0.05:
                        # 上升趋势，增加仓位
                        position_factor = 1.2
                    elif trend < -0.05:
                        # 下降趋势，减少仓位
                        position_factor = 0.8
                
                # 计算目标仓位
                target_position = int((i - self.grid_levels) * 10 * position_factor)  # 每个网格10个单位
                position_change = target_position - self.position
                
                # 执行交易
                if position_change > 0:
                    # 买入
                    cost = position_change * current_price
                    # 预留20%资金作为缓冲
                    if cost <= self.current_balance * 0.8:
                        self.position = target_position
                        self.current_balance -= cost
                        return {
                            "action": "buy",
                            "quantity": position_change,
                            "price": current_price,
                            "balance": self.current_balance,
                            "position": self.position,
                            "grid_spacing": self.grid_spacing
                        }
                elif position_change < 0:
                    # 卖出
                    quantity = abs(position_change)
                    revenue = quantity * current_price
                    self.position = target_position
                    self.current_balance += revenue
                    return {
                        "action": "sell",
                        "quantity": quantity,
                        "price": current_price,
                        "balance": self.current_balance,
                        "position": self.position,
                        "grid_spacing": self.grid_spacing
                    }
                break
        
        return {"action": "hold", "balance": self.current_balance, "position": self.position, "grid_spacing": self.grid_spacing}
    
    def get_performance(self) -> Dict[str, float]:
        """
        获取策略性能
        
        Returns:
            性能指标
        """
        return {
            "initial_balance": self.initial_balance,
            "current_balance": self.current_balance,
            "pnl": self.current_balance - self.initial_balance,
            "return": (self.current_balance / self.initial_balance - 1) * 100,
            "best_grid_spacing": self.best_spacing
        }

class MonteCarloSimulation:
    """
    蒙特卡洛模拟
    """
    
    def __init__(self, num_simulations: int = 10000, time_horizon: int = 252):
        """
        初始化蒙特卡洛模拟
        
        Args:
            num_simulations: 模拟次数
            time_horizon: 时间范围（天数）
        """
        self.num_simulations = num_simulations
        self.time_horizon = time_horizon
    
    def simulate(self, initial_price: float, mu: float, sigma: float) -> np.ndarray:
        """
        执行蒙特卡洛模拟
        
        Args:
            initial_price: 初始价格
            mu: 预期收益率
            sigma: 波动率
            
        Returns:
            模拟价格路径
        """
        # 生成随机收益率
        returns = np.random.normal(mu / self.time_horizon, sigma / np.sqrt(self.time_horizon), 
                                 (self.time_horizon, self.num_simulations))
        
        # 计算价格路径
        price_paths = np.zeros((self.time_horizon + 1, self.num_simulations))
        price_paths[0] = initial_price
        
        for t in range(1, self.time_horizon + 1):
            price_paths[t] = price_paths[t-1] * (1 + returns[t-1])
        
        return price_paths

class GridSearchOptimizer:
    """
    网格搜索优化器
    """
    
    def __init__(self, param_ranges: Dict[str, List[float]]):
        """
        初始化网格搜索优化器
        
        Args:
            param_ranges: 参数范围
        """
        self.param_ranges = param_ranges
    
    def optimize(self, objective_function, **kwargs) -> Tuple[Dict[str, float], float]:
        """
        执行网格搜索优化
        
        Args:
            objective_function: 目标函数
            **kwargs: 其他参数
            
        Returns:
            (最佳参数, 最佳目标值)
        """
        best_params = None
        best_value = -float('inf')
        
        # 生成所有参数组合
        param_combinations = self._generate_combinations()
        
        for params in param_combinations:
            value = objective_function(params, **kwargs)
            if value > best_value:
                best_value = value
                best_params = params
        
        return best_params, best_value
    
    def _generate_combinations(self) -> List[Dict[str, float]]:
        """
        生成所有参数组合
        
        Returns:
            参数组合列表
        """
        # 简化实现，实际应用中可能需要更复杂的处理
        combinations = [{}]
        
        for param, values in self.param_ranges.items():
            new_combinations = []
            for combo in combinations:
                for value in values:
                    new_combo = combo.copy()
                    new_combo[param] = value
                    new_combinations.append(new_combo)
            combinations = new_combinations
        
        return combinations
