#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
股票池智能管理系统 - 预实盘模拟引擎
"""
from typing import List, Dict
import random
from datetime import datetime, timedelta
from stock_pool.core.models import Stock, Strategy, SimulationResult


class PreTradingSimulator:
    """预实盘模拟测试引擎"""
    
    def __init__(self):
        self.simulation_config = {
            'duration': 30,           # 模拟天数
            'initial_capital': 1000000,  # 初始资金
            'slippage': 0.001,        # 滑点
            'transaction_cost': 0.0005  # 交易成本
        }
    
    def _generate_simulated_prices(self, stock: Stock, days: int) -> List[float]:
        """生成模拟价格序列"""
        prices = [stock.price]
        volatility = stock.volatility
        
        for _ in range(days):
            # 随机游走模型
            change = prices[-1] * (random.gauss(0, volatility) * 0.1)
            new_price = max(0.01, prices[-1] + change)
            prices.append(new_price)
        
        return prices
    
    def _evaluate_strategy(self, stock: Stock, strategy: Strategy, prices: List[float]) -> dict:
        """评估策略在价格序列上的表现"""
        capital = self.simulation_config['initial_capital']
        position = 0
        trades = 0
        win_count = 0
        max_drawdown = 0
        peak_total = capital  # 总资产峰值（现金 + 持仓价值）
        
        for i in range(1, len(prices)):
            price = prices[i]
            
            # 计算当前总资产（现金 + 持仓价值）
            current_total = capital + (position * price if position > 0 else 0)
            
            # 更新总资产峰值
            peak_total = max(peak_total, current_total)
            
            # 计算回撤（只在有持仓时计算）
            if position > 0 and peak_total > 0:
                drawdown = (peak_total - current_total) / peak_total
                max_drawdown = max(max_drawdown, drawdown)
            
            # 简化的策略信号
            signal = self._generate_signal(stock, strategy, prices[:i], i)
            
            if signal == 'buy' and position == 0:
                # 买入（用50%的资本）
                buy_amount = capital * 0.5
                position = int(buy_amount // (price * (1 + self.simulation_config['slippage'])))
                cost = position * price * (1 + self.simulation_config['slippage'])
                capital -= cost + cost * self.simulation_config['transaction_cost']
                trades += 1
                entry_price = price
            
            elif signal == 'sell' and position > 0:
                # 卖出
                revenue = position * price * (1 - self.simulation_config['slippage'])
                capital += revenue - revenue * self.simulation_config['transaction_cost']
                trades += 1
                
                if price > entry_price:
                    win_count += 1
                
                position = 0
        
        # 最终清算
        if position > 0:
            revenue = position * prices[-1] * (1 - self.simulation_config['slippage'])
            capital += revenue - revenue * self.simulation_config['transaction_cost']
        
        total_return = (capital - self.simulation_config['initial_capital']) / self.simulation_config['initial_capital'] * 100
        
        # 计算夏普比率（简化版）
        daily_returns = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices))]
        if daily_returns:
            mean_return = sum(daily_returns) / len(daily_returns)
            std_return = (sum((r - mean_return)**2 for r in daily_returns) / len(daily_returns)) ** 0.5
            sharpe_ratio = mean_return / std_return * (252 ** 0.5) if std_return > 0 else 0
        else:
            sharpe_ratio = 0
        
        trade_pairs = trades // 2
        win_rate = (win_count / trade_pairs) * 100 if trade_pairs > 0 else 0
        
        return {
            'total_return': total_return,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown * 100,
            'win_rate': win_rate,
            'trades': trades
        }
    
    def _generate_signal(self, stock: Stock, strategy: Strategy, prices: List[float], day: int) -> str:
        """生成交易信号"""
        if len(prices) < 5:
            return 'hold'
        
        # 简化的策略逻辑
        recent_prices = prices[-5:]
        ma5 = sum(recent_prices) / 5
        ma20 = sum(prices[-20:]) / min(20, len(prices))
        
        if strategy.type == 'trend':
            if prices[-1] > ma5 and ma5 > ma20:
                return 'buy'
            elif prices[-1] < ma5 and ma5 < ma20:
                return 'sell'
        elif strategy.type == 'oscillate':
            if prices[-1] < ma5 * 0.98:
                return 'buy'
            elif prices[-1] > ma5 * 1.02:
                return 'sell'
        elif strategy.type == 'momentum':
            momentum = (prices[-1] - prices[-5]) / prices[-5]
            if momentum > 0.05:
                return 'buy'
            elif momentum < -0.03:
                return 'sell'
        
        return 'hold'
    
    def run_simulation(self, stock: Stock, strategy: Strategy) -> SimulationResult:
        """运行单股票-策略模拟"""
        prices = self._generate_simulated_prices(stock, self.simulation_config['duration'])
        result = self._evaluate_strategy(stock, strategy, prices)
        
        # 计算模拟评分（总分40分，对应综合评分的40%权重）
        score = 0
        
        # 收益率评分（16分）
        if result['total_return'] > 10:
            score += 16
        elif result['total_return'] > 5:
            score += 12
        elif result['total_return'] > 0:
            score += 8
        elif result['total_return'] > -5:
            score += 4
        else:
            score += 2
        
        # 夏普比率评分（10分）
        sharpe = abs(result['sharpe_ratio'])
        if sharpe > 2:
            score += 10
        elif sharpe > 1.5:
            score += 8
        elif sharpe > 1:
            score += 6
        elif sharpe > 0.5:
            score += 4
        else:
            score += 2
        
        # 最大回撤评分（8分）
        if result['max_drawdown'] < 5:
            score += 8
        elif result['max_drawdown'] < 10:
            score += 6
        elif result['max_drawdown'] < 15:
            score += 4
        else:
            score += 2
        
        # 胜率评分（6分）
        if result['win_rate'] > 60:
            score += 6
        elif result['win_rate'] > 50:
            score += 4
        elif result['trades'] > 0:
            score += 3
        else:
            score += 2
        
        return SimulationResult(
            stock=stock,
            strategy=strategy,
            total_return=round(result['total_return'], 2),
            sharpe_ratio=round(result['sharpe_ratio'], 2),
            max_drawdown=round(result['max_drawdown'], 2),
            win_rate=round(result['win_rate'], 2),
            trades=result['trades'],
            duration=self.simulation_config['duration'],
            passed=score >= 25,
            score=score
        )
    
    def batch_simulate(self, stocks: List[Stock], strategies: List[Strategy]) -> List[SimulationResult]:
        """批量模拟测试"""
        results = []
        for stock in stocks:
            for strategy in strategies:
                result = self.run_simulation(stock, strategy)
                results.append(result)
        return results