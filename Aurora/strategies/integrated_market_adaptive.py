# integrated_market_adaptive.py
# 集成市场自适应策略
# 结合上涨、横盘、下跌市场的优秀策略

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
import json
import os
from ml_range_grid import MLRangeGridTrading

class IntegratedMarketAdaptive:
    """
    集成市场自适应策略
    结合上涨、横盘、下跌市场的优秀策略
    """
    
    def __init__(self, base_price: float, initial_balance: float = 100000):
        """
        初始化集成市场自适应策略
        
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
        self.last_price = base_price
        self.entry_price = 0
        
        # 策略性能历史
        self.strategy_performance = {
            'trending_up': {'total_trades': 0, 'winning_trades': 0, 'profit': 0},
            'range_bound': {'total_trades': 0, 'winning_trades': 0, 'profit': 0},
            'trending_down': {'total_trades': 0, 'winning_trades': 0, 'profit': 0}
        }
        
        # 策略参数
        self.params = {
            'trending_up': {
                'take_profit': 0.02,  # 2%止盈
                'stop_loss': 0.015,   # 1.5%止损
                'max_position': 0.8, # 80%最大持仓
                'reserve_balance': 0.2, # 20%保留资金
                'buy_threshold': 0.005,  # 0.5%回调买入
                'sell_threshold': 0.015  # 1.5%上涨卖出
            },
            'trending_down': {
                'take_profit': 0.02,  # 2%止盈
                'stop_loss': 0.01,    # 1%止损
                'max_position': 0.4,   # 40%最大持仓
                'reserve_balance': 0.5, # 50%保留资金
                'buy_levels': [0.99, 0.97, 0.95, 0.93, 0.91, 0.89], # 下跌买入点位
                'buy_amounts': []       # 对应买入金额
            }
        }
        
        # 初始化下跌买入金额
        self._init_downward_buy_amounts()
        
        # 初始化机器学习横盘网格策略
        self.ml_range_grid = MLRangeGridTrading(base_price, initial_balance)
        
        # 市场类型历史
        self.market_type_history = []
        self.last_market_type = 'range_bound'
        
        # 优秀成果传承
        self.learning_history = []
        self.best_params = self.params.copy()
        
        # 加载历史数据
        self._load_history()
    
    def _init_downward_buy_amounts(self):
        """
        初始化下跌买入金额
        """
        for level in self.params['trending_down']['buy_levels']:
            amount_ratio = (1 - level) * 20
            max_amount = self.initial_balance * 0.15
            amount = min(max_amount, self.initial_balance * 0.05 * amount_ratio)
            self.params['trending_down']['buy_amounts'].append(amount)
    
    def _load_history(self):
        """
        加载历史数据
        """
        history_file = 'strategy_history.json'
        if os.path.exists(history_file):
            try:
                with open(history_file, 'r') as f:
                    history = json.load(f)
                    if 'best_params' in history:
                        self.best_params = history['best_params']
                        self.params = self.best_params.copy()
                    if 'learning_history' in history:
                        self.learning_history = history['learning_history']
            except Exception as e:
                print(f"加载历史数据失败: {e}")
    
    def _save_history(self):
        """
        保存历史数据
        """
        history = {
            'best_params': self.best_params,
            'learning_history': self.learning_history
        }
        try:
            with open('strategy_history.json', 'w') as f:
                json.dump(history, f, indent=2)
        except Exception as e:
            print(f"保存历史数据失败: {e}")
    
    def detect_market_type(self, data: pd.Series) -> str:
        """
        检测市场类型
        
        Args:
            data: 价格数据
            
        Returns:
            市场类型: 'trending_up', 'trending_down', 'range_bound'
        """
        if len(data) < 20:
            return 'range_bound'
        
        # 计算趋势强度
        ema10 = data.ewm(span=10).mean().iloc[-1]
        ema30 = data.ewm(span=30).mean().iloc[-1]
        ema60 = data.ewm(span=60).mean().iloc[-1]
        trend_strength = (ema10 - ema60) / ema60
        
        # 计算价格范围
        recent_data = data.iloc[-20:]
        price_range = (recent_data.max() - recent_data.min()) / recent_data.mean()
        
        # 计算波动率
        volatility = recent_data.pct_change().std()
        
        # 确定市场类型 - 调整阈值
        if trend_strength < -0.01:
            return 'trending_down'
        elif trend_strength > 0.01:
            return 'trending_up'
        elif price_range < 0.03:
            return 'range_bound'
        elif price_range > 0.06:
            if trend_strength > 0:
                return 'trending_up'
            else:
                return 'trending_down'
        else:
            if abs(trend_strength) > 0.005:
                if trend_strength > 0:
                    return 'trending_up'
                else:
                    return 'trending_down'
            else:
                return 'range_bound'
    
    def update_price(self, current_price: float, data: pd.Series = None) -> Dict[str, any]:
        """
        更新价格并执行交易
        
        Args:
            current_price: 当前价格
            data: 价格数据
            
        Returns:
            交易结果
        """
        # 记录价格历史
        self.price_history.append(current_price)
        
        # 检测市场类型
        if data is not None:
            market_type = self.detect_market_type(data)
            self.market_type_history.append(market_type)
            # 增加调试信息
            if len(data) > 60:
                ema10 = data.ewm(span=10).mean().iloc[-1]
                ema30 = data.ewm(span=30).mean().iloc[-1]
                ema60 = data.ewm(span=60).mean().iloc[-1]
                trend_strength = (ema10 - ema60) / ema60
                recent_data = data.iloc[-20:]
                price_range = (recent_data.max() - recent_data.min()) / recent_data.mean()
                volatility = recent_data.pct_change().std()
                if len(self.price_history) % 50 == 0:
                    print(f"Market Type: {market_type}, Trend Strength: {trend_strength:.4f}, Price Range: {price_range:.4f}, Volatility: {volatility:.4f}")
        else:
            market_type = 'range_bound'
        
        # 计算价格变化
        price_change = (current_price - self.last_price) / self.last_price if self.last_price > 0 else 0
        
        # 通用风险控制
        if self.position > 0 and self.entry_price > 0:
            # 止损
            loss_ratio = (current_price - self.entry_price) / self.entry_price
            if loss_ratio < -self.params[market_type]['stop_loss']:
                revenue = self.position * current_price
                self.current_balance += revenue
                quantity = self.position
                self.position = 0
                self.entry_price = 0
                self.last_price = current_price
                self.strategy_performance[market_type]['total_trades'] += 1
                self.strategy_performance[market_type]['losing_trades'] = self.strategy_performance[market_type].get('losing_trades', 0) + 1
                return {
                    "action": "sell",
                    "quantity": quantity,
                    "price": current_price,
                    "balance": self.current_balance,
                    "position": self.position,
                    "market_type": market_type,
                    "reason": "stop_loss"
                }
            
            # 止盈
            profit_ratio = (current_price - self.entry_price) / self.entry_price
            if profit_ratio > self.params[market_type]['take_profit']:
                revenue = self.position * current_price
                self.current_balance += revenue
                quantity = self.position
                self.position = 0
                self.entry_price = 0
                self.last_price = current_price
                self.strategy_performance[market_type]['total_trades'] += 1
                self.strategy_performance[market_type]['winning_trades'] += 1
                self.strategy_performance[market_type]['profit'] += revenue - quantity * self.entry_price
                return {
                    "action": "sell",
                    "quantity": quantity,
                    "price": current_price,
                    "balance": self.current_balance,
                    "position": self.position,
                    "market_type": market_type,
                    "reason": "take_profit"
                }
        
        # 计算可用资金
        available_balance = self.current_balance * (1 - self.params[market_type]['reserve_balance'])
        max_position = (self.initial_balance * self.params[market_type]['max_position']) / current_price
        
        # 根据市场类型执行不同策略
        if market_type == 'trending_up':
            return self._execute_trending_up_strategy(current_price, available_balance, max_position, price_change, market_type)
        elif market_type == 'range_bound':
            return self._execute_range_bound_strategy(current_price, available_balance, max_position, market_type)
        elif market_type == 'trending_down':
            return self._execute_trending_down_strategy(current_price, available_balance, max_position, market_type)
        
        # 更新价格
        self.last_price = current_price
        return {
            "action": "hold",
            "balance": self.current_balance,
            "position": self.position,
            "market_type": market_type
        }
    
    def _execute_trending_up_strategy(self, current_price, available_balance, max_position, price_change, market_type):
        """
        执行上涨市场策略
        """
        # 增加买入机会
        if self.position == 0 and available_balance > 1000:
            # 初始买入
            buy_amount = min(available_balance * 0.4, 5000)
            buy_quantity = buy_amount / current_price
            if buy_quantity > 0.01:
                self.position += buy_quantity
                self.current_balance -= buy_amount
                self.entry_price = current_price
                self.last_price = current_price
                return {
                    "action": "buy",
                    "quantity": buy_quantity,
                    "price": current_price,
                    "balance": self.current_balance,
                    "position": self.position,
                    "market_type": market_type,
                    "reason": "trending_up_initial_buy"
                }
        elif price_change < -self.params[market_type]['buy_threshold'] and self.position < max_position and available_balance > 500:
            # 价格回调，买入
            buy_amount = min(available_balance * 0.3, 3000)
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
                        "market_type": market_type,
                        "reason": "trending_up_buy"
                    }
        elif price_change > self.params[market_type]['sell_threshold'] and self.position > 0:
            # 价格上涨，卖出部分
            sell_quantity = self.position * 0.5
            if sell_quantity > 0.01:
                sell_amount = sell_quantity * current_price
                self.position -= sell_quantity
                self.current_balance += sell_amount
                self.last_price = current_price
                self.strategy_performance[market_type]['total_trades'] += 1
                if current_price > self.entry_price:
                    self.strategy_performance[market_type]['winning_trades'] += 1
                    self.strategy_performance[market_type]['profit'] += sell_amount - sell_quantity * self.entry_price
                else:
                    self.strategy_performance[market_type]['losing_trades'] = self.strategy_performance[market_type].get('losing_trades', 0) + 1
                return {
                    "action": "sell",
                    "quantity": sell_quantity,
                    "price": current_price,
                    "balance": self.current_balance,
                    "position": self.position,
                    "market_type": market_type,
                    "reason": "trending_up_sell"
                }
        
        self.last_price = current_price
        return {
            "action": "hold",
            "balance": self.current_balance,
            "position": self.position,
            "market_type": market_type
        }
    
    def _execute_range_bound_strategy(self, current_price, available_balance, max_position, market_type):
        """
        执行横盘市场策略
        使用机器学习横盘网格策略
        """
        # 将price_history转换为pd.Series
        price_series = pd.Series(self.price_history)
        # 调用机器学习横盘网格策略
        result = self.ml_range_grid.update_price(current_price, price_series)
        
        # 更新本策略的状态
        self.current_balance = self.ml_range_grid.current_balance
        self.position = self.ml_range_grid.position
        self.last_price = current_price
        
        # 记录交易性能
        if result.get('action') == 'buy' or result.get('action') == 'sell':
            self.strategy_performance[market_type]['total_trades'] += 1
            if result.get('action') == 'sell' and 'reason' in result and result['reason'] in ['take_profit', 'grid_sell', 'mean_reversion_sell']:
                self.strategy_performance[market_type]['winning_trades'] += 1
                # 计算盈利
                if 'quantity' in result and 'price' in result:
                    profit = result['quantity'] * (result['price'] - self.entry_price)
                    self.strategy_performance[market_type]['profit'] += profit
            elif result.get('action') == 'sell' and 'reason' in result and result['reason'] == 'stop_loss':
                self.strategy_performance[market_type]['losing_trades'] = self.strategy_performance[market_type].get('losing_trades', 0) + 1
        
        # 更新入场价格
        if result.get('action') == 'buy':
            self.entry_price = current_price
        elif result.get('action') == 'sell' and self.position == 0:
            self.entry_price = 0
        
        return {
            "action": result.get('action', 'hold'),
            "balance": self.current_balance,
            "position": self.position,
            "market_type": market_type,
            "reason": result.get('reason', 'hold')
        }
    
    def _execute_trending_down_strategy(self, current_price, available_balance, max_position, market_type):
        """
        执行下跌市场策略
        """
        buy_levels = self.params[market_type]['buy_levels']
        buy_amounts = self.params[market_type]['buy_amounts']
        
        # 增加初始买入机会
        if self.position == 0 and available_balance > 1000 and current_price < self.base_price:
            # 初始买入
            buy_amount = min(available_balance * 0.2, 2000)
            buy_quantity = buy_amount / current_price
            if buy_quantity > 0.01 and self.position < max_position:
                self.position += buy_quantity
                self.current_balance -= buy_amount
                self.entry_price = current_price
                self.last_price = current_price
                return {
                    "action": "buy",
                    "quantity": buy_quantity,
                    "price": current_price,
                    "balance": self.current_balance,
                    "position": self.position,
                    "market_type": market_type,
                    "reason": "downward_initial_buy"
                }
        
        # 检查是否达到下跌买入点位
        for level, amount in zip(buy_levels, buy_amounts):
            buy_price = self.base_price * level
            if current_price <= buy_price and available_balance > amount:
                buy_quantity = amount / current_price
                if buy_quantity > 0.01 and self.position < max_position:
                    self.position += buy_quantity
                    self.current_balance -= amount
                    if self.entry_price == 0:
                        self.entry_price = current_price
                    self.last_price = current_price
                    # 移除已执行的买入点位
                    index = buy_levels.index(level)
                    buy_levels.pop(index)
                    buy_amounts.pop(index)
                    return {
                        "action": "buy",
                        "quantity": buy_quantity,
                        "price": current_price,
                        "balance": self.current_balance,
                        "position": self.position,
                        "market_type": market_type,
                        "reason": "downward_buy_level"
                    }
        
        # 反弹卖出
        if self.position > 0 and current_price > self.last_price * 1.01:
            sell_quantity = self.position * 0.7
            if sell_quantity > 0.01:
                sell_amount = sell_quantity * current_price
                self.position -= sell_quantity
                self.current_balance += sell_amount
                self.last_price = current_price
                self.strategy_performance[market_type]['total_trades'] += 1
                if current_price > self.entry_price:
                    self.strategy_performance[market_type]['winning_trades'] += 1
                    self.strategy_performance[market_type]['profit'] += sell_amount - sell_quantity * self.entry_price
                else:
                    self.strategy_performance[market_type]['losing_trades'] = self.strategy_performance[market_type].get('losing_trades', 0) + 1
                return {
                    "action": "sell",
                    "quantity": sell_quantity,
                    "price": current_price,
                    "balance": self.current_balance,
                    "position": self.position,
                    "market_type": market_type,
                    "reason": "downward_rally_sell"
                }
        
        self.last_price = current_price
        return {
            "action": "hold",
            "balance": self.current_balance,
            "position": self.position,
            "market_type": market_type
        }
    
    def learn_from_performance(self):
        """
        从性能中学习，优化策略参数
        """
        # 分析每个市场类型的表现
        for market_type in self.strategy_performance:
            performance = self.strategy_performance[market_type]
            total_trades = performance.get('total_trades', 0)
            if total_trades > 0:
                win_rate = performance.get('winning_trades', 0) / total_trades
                total_profit = performance.get('profit', 0)
                avg_profit = total_profit / total_trades if total_trades > 0 else 0
                
                # 记录学习历史
                self.learning_history.append({
                    'market_type': market_type,
                    'win_rate': win_rate,
                    'avg_profit': avg_profit,
                    'total_trades': total_trades,
                    'params': self.params[market_type].copy()
                })
                
                # 优化参数
                if win_rate < 0.5:
                    # 降低止盈，提高止损
                    self.params[market_type]['take_profit'] *= 0.9
                    self.params[market_type]['stop_loss'] *= 0.9
                elif avg_profit < 0:
                    # 减少持仓比例
                    self.params[market_type]['max_position'] *= 0.9
                else:
                    # 增加持仓比例
                    self.params[market_type]['max_position'] = min(self.params[market_type]['max_position'] * 1.05, 0.9)
        
        # 更新最佳参数
        self.best_params = self.params.copy()
        # 保存历史数据
        self._save_history()
    
    def get_performance(self) -> Dict[str, any]:
        """
        获取策略性能
        
        Returns:
            性能指标
        """
        total_trades = sum(p.get('total_trades', 0) for p in self.strategy_performance.values())
        winning_trades = sum(p.get('winning_trades', 0) for p in self.strategy_performance.values())
        total_profit = sum(p.get('profit', 0) for p in self.strategy_performance.values())
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        return {
            "initial_balance": self.initial_balance,
            "current_balance": self.current_balance,
            "return": (self.current_balance - self.initial_balance) / self.initial_balance * 100,
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "win_rate": win_rate,
            "total_profit": total_profit,
            "strategy_performance": self.strategy_performance,
            "market_type_history": self.market_type_history[-50:] if len(self.market_type_history) > 50 else self.market_type_history
        }

# 测试函数
def test_integrated_strategy():
    """
    测试集成市场自适应策略
    """
    # 生成测试数据
    np.random.seed(42)
    n = 1000
    
    # 生成包含上涨、横盘、下跌的混合市场数据
    price = [100.0]
    for i in range(1, n):
        if i < 300:
            # 上涨市场
            ret = np.random.normal(0.001, 0.001)
        elif i < 700:
            # 横盘市场
            ret = np.random.normal(0, 0.001)
        else:
            # 下跌市场
            ret = np.random.normal(-0.001, 0.001)
        price.append(price[-1] * (1 + ret))
    
    df = pd.Series(price)
    
    # 初始化策略
    strategy = IntegratedMarketAdaptive(base_price=100.0)
    
    # 模拟交易
    for i in range(len(df)):
        current_price = df.iloc[i]
        data = df.iloc[max(0, i-60):i+1]
        result = strategy.update_price(current_price, data)
        if i % 100 == 0:
            print(f"Step {i}, Price: {current_price:.2f}, Action: {result.get('action')}, Balance: {strategy.current_balance:.2f}")
    
    # 学习优化
    strategy.learn_from_performance()
    
    # 输出性能
    performance = strategy.get_performance()
    print("\n" + "=" * 60)
    print("集成市场自适应策略性能报告")
    print("=" * 60)
    print(f"初始资金: {performance['initial_balance']:.2f} 元")
    print(f"最终资金: {performance['current_balance']:.2f} 元")
    print(f"总收益率: {performance['return']:.2f}%")
    print(f"总交易次数: {performance['total_trades']}")
    print(f"胜率: {performance['win_rate']:.2f}%")
    print(f"总盈利: {performance['total_profit']:.2f} 元")
    print("\n各市场类型表现:")
    for market_type, perf in performance['strategy_performance'].items():
        total = perf.get('total_trades', 0)
        winning = perf.get('winning_trades', 0)
        win_rate = winning / total if total > 0 else 0
        print(f"{market_type}: 交易 {total} 次, 胜率 {win_rate:.2f}%, 盈利 {perf.get('profit', 0):.2f} 元")
    print("=" * 60)

if __name__ == "__main__":
    test_integrated_strategy()
