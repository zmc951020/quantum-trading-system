#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
陀螺策略V2 - 简化高效回测版本
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
from collections import deque

from enhanced_evaluator import EnhancedFinancialEvaluator

def log(msg):
    print(msg)
    sys.stdout.flush()

class GyroStrategyTest:
    def __init__(self):
        self.omega = np.array([0.65, 0.25, 0.10])
        self.learning_rate = 2e-4
        self.reward_history = deque(maxlen=150)
        
        self.trade_history = []
        self.current_position = 0
        self.entry_price = None
        self.position_since = None
        self.consecutive_losses = 0
        self.holding_periods = []
        self.equity_curve = []
    
    def calc_momentum(self, prices, window=30):
        if len(prices) < window:
            return 0
        return np.mean(np.diff(prices[-window:])) / prices[-1]
    
    def calc_volatility(self, prices, window=30):
        if len(prices) < window:
            return 0.01
        return np.std(np.diff(prices[-window:])) * np.sqrt(60)
    
    def get_adaptive_params(self, prices):
        vol = self.calc_volatility(prices)
        base_vol = 0.01
        
        signal_threshold = max(0.00008, min(0.0006, 0.00015 + vol * 0.003))
        min_holding = max(10, min(45, 20 + int(vol * 500)))
        stop_loss = max(0.003, min(0.025, 0.008 + vol * 0.2))
        take_profit = max(0.006, min(0.05, 0.015 + vol * 0.4))
        
        return signal_threshold, min_holding, stop_loss, take_profit
    
    def get_reward(self, metrics):
        reward = 0
        if metrics.get('sharpe_ratio', 0) >= 1:
            reward += metrics.get('sharpe_ratio', 0) * 10
        else:
            reward -= abs(metrics.get('sharpe_ratio', 0) - 1) * 2
        
        if metrics.get('sortino_ratio', 0) >= 1.5:
            reward += metrics.get('sortino_ratio', 0) * 8
        
        reward -= metrics.get('max_dd', 0) * 20
        reward -= metrics.get('consecutive_losses', 0) * 4
        
        return reward
    
    def evolve_omega(self, reward):
        self.reward_history.append(reward)
        if len(self.reward_history) > 10:
            avg_reward = np.mean(self.reward_history)
            if reward > avg_reward:
                noise = np.random.normal(0, 0.02, 3) * 1.2
            else:
                noise = np.random.normal(0, 0.02, 3) * 0.8
        else:
            noise = np.random.normal(0, 0.025, 3)
        
        self.omega += noise
        self.omega = np.clip(self.omega, 0.1, 1.8)
        self.omega = self.omega / np.sum(self.omega) * 1.0
    
    def run_backtest(self, data, initial_capital=100000):
        prices = data['Close'].values
        high = data['High'].values
        low = data['Low'].values
        
        equity = initial_capital
        max_equity = initial_capital
        
        for i in range(720, len(prices)):
            price_window = prices[max(0, i-720):i]
            
            signal_threshold, min_holding, stop_loss, take_profit = self.get_adaptive_params(price_window)
            
            mom = self.calc_momentum(price_window, 30)
            vol = self.calc_volatility(price_window, 30)
            
            main_signal = mom * self.omega[0] * vol * 100
            hedge_signal = vol * self.omega[1] * 20
            time_arb = np.sin(i * 0.01) * self.omega[2] * vol
            
            total_signal = main_signal + hedge_signal + time_arb
            
            if self.current_position != 0 and self.entry_price is not None:
                price_change = prices[i] - self.entry_price
                pct_change = price_change / self.entry_price
                
                should_close = False
                if self.current_position > 0:
                    if pct_change <= -stop_loss:
                        should_close = True
                    elif pct_change >= take_profit:
                        should_close = True
                else:
                    if pct_change >= stop_loss:
                        should_close = True
                    elif pct_change <= -take_profit:
                        should_close = True
                
                holding_time = i - self.position_since if self.position_since is not None else 0
                if holding_time > min_holding * 3:
                    should_close = True
                
                if should_close:
                    ret = pct_change * np.sign(self.current_position)
                    equity *= (1 + ret)
                    max_equity = max(max_equity, equity)
                    
                    if ret < 0:
                        self.consecutive_losses += 1
                    else:
                        self.consecutive_losses = 0
                    
                    if self.position_since is not None:
                        self.holding_periods.append(holding_time)
                    
                    self.trade_history.append({
                        'return': ret,
                        'type': 'close'
                    })
                    
                    self.current_position = 0
                    self.entry_price = None
                    self.position_since = None
            
            if self.current_position == 0 and abs(total_signal) > signal_threshold and abs(mom) > signal_threshold:
                position_sign = np.sign(total_signal)
                position_size = position_sign * min(1.2, abs(total_signal) * 3) * equity / prices[i]
                
                self.current_position = position_size
                self.entry_price = prices[i]
                self.position_since = i
            
            if self.current_position != 0 and i > 0:
                price_change = (prices[i] - prices[i-1]) / prices[i-1]
                equity *= (1 + price_change * np.sign(self.current_position))
                max_equity = max(max_equity, equity)
            
            all_returns = np.array([t['return'] for t in self.trade_history]) if self.trade_history else np.array([0])
            
            metrics = {
                'sharpe_ratio': np.mean(all_returns) / np.std(all_returns) * np.sqrt(252*24*60) if len(all_returns) > 0 and np.std(all_returns) > 0 else 0,
                'sortino_ratio': self.calc_sortino(all_returns),
                'max_dd': (max_equity - equity) / max_equity if max_equity > 0 else 0,
                'consecutive_losses': self.consecutive_losses
            }
            
            reward = self.get_reward(metrics)
            self.evolve_omega(reward)
            
            self.equity_curve.append(equity)
        
        return equity, max_equity
    
    def calc_sortino(self, returns):
        if len(returns) == 0:
            return 0
        downside = returns[returns < 0]
        if len(downside) == 0:
            return np.inf
        downside_vol = np.sqrt(np.mean(downside ** 2))
        if downside_vol == 0:
            return np.inf
        return np.mean(returns) / downside_vol * np.sqrt(252*24*60)

def main():
    np.random.seed(42)
    n_minutes = 5000
    dates = pd.date_range(start='2024-01-01', periods=n_minutes, freq='min')
    
    prices = np.zeros(n_minutes)
    prices[0] = 100.0
    for i in range(1, n_minutes):
        hour_of_day = i % 1440 / 1440
        if hour_of_day < 0.25:
            dr = np.random.normal(0.0001, 0.0012)
        elif hour_of_day < 0.5:
            dr = np.random.normal(0.00025, 0.0018)
        elif hour_of_day < 0.75:
            dr = np.random.normal(0.00018, 0.0015)
        else:
            dr = np.random.normal(0.00008, 0.0009)
        prices[i] = prices[i-1] * (1 + dr)
    
    data = pd.DataFrame({
        'Open': prices * (1 + np.random.randn(n_minutes) * 0.0004),
        'High': np.maximum(prices, prices * (1 + np.random.randn(n_minutes) * 0.0004)) * (1 + np.random.rand(n_minutes) * 0.0008),
        'Low': np.minimum(prices, prices * (1 + np.random.randn(n_minutes) * 0.0004)) * (1 - np.random.rand(n_minutes) * 0.0008),
        'Close': prices,
        'Volume': np.random.randint(12000, 90000, n_minutes)
    }, index=dates)
    
    strategy = GyroStrategyTest()
    final_equity, max_equity = strategy.run_backtest(data, 100000)
    
    all_returns = np.array([t['return'] for t in strategy.trade_history]) if strategy.trade_history else np.array([0])
    
    total_return = (final_equity - 100000) / 100000 * 100
    max_dd = (max_equity - final_equity) / max_equity * 100 if max_equity > 0 else 0
    
    returns_std = np.std(all_returns) if len(all_returns) > 0 else 0
    sharpe = np.mean(all_returns) / returns_std * np.sqrt(252*24*60) if returns_std > 0 else 0
    
    sortino = strategy.calc_sortino(all_returns)
    
    result_for_eval = {
        'returns': all_returns,
        'days': n_minutes / 1440,
        'total_return_pct': total_return,
        'sharpe_ratio': sharpe,
        'max_drawdown_pct': max_dd,
        'total_trades': len(strategy.trade_history),
        'profit_factor': np.sum(all_returns[all_returns > 0]) / np.abs(np.sum(all_returns[all_returns < 0])) if np.sum(all_returns[all_returns < 0]) != 0 else 0,
        'win_rate_pct': len(all_returns[all_returns > 0]) / len(all_returns) * 100 if len(all_returns) > 0 else 0,
    }
    
    evaluator = EnhancedFinancialEvaluator()
    score, metric_scores, _ = evaluator.evaluate(result_for_eval)
    
    log("="*90)
    log("陀螺策略V2 - 简化高效回测")
    log("="*90)
    log(f"测试数据: {n_minutes}分钟 ({n_minutes/1440:.1f}天)")
    log(f"最终权益: ${final_equity:.2f}")
    log(f"总收益率: {total_return:.2f}%")
    log(f"最大回撤: {max_dd:.2f}%")
    log(f"交易次数: {len(strategy.trade_history)}")
    log(f"夏普比率: {sharpe:.2f}")
    log(f"索提诺比率: {sortino:.2f}")
    log(f"平均持仓: {np.mean(strategy.holding_periods):.0f}分钟" if strategy.holding_periods else "平均持仓: N/A")
    log("\n综合评分: {:.2f} ({})".format(score, evaluator.get_grade(score)))
    log("\n各指标得分:")
    for k, v in sorted(metric_scores.items(), key=lambda x: x[1], reverse=True):
        status = "[OK]" if v >= 8 else "[WARN]" if v >= 6 else "[FAIL]"
        log(f"{status} {k:<25}: {v:.1f}")
    log("\n最终omega: [{:.3f}, {:.3f}, {:.3f}]".format(strategy.omega[0], strategy.omega[1], strategy.omega[2]))
    log("="*90)

if __name__ == "__main__":
    main()
