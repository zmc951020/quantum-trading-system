#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V6超能优化器 - 伯努利-康达策略深度迭代优化
目标: 达到金融级标准 9.0
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd
from datetime import datetime
import json
import time
import random

print("="*90)
print("V6 Ultra Optimizer - Bernoulli-Coanda Strategy Deep Iteration")
print("Target: Financial Grade Standard 9.0")
print("="*90)

from strategies.bernoulli_coanda_strategy import (
    bernoulli_coanda_strategy,
    BernoulliCoandaParameters
)

# ============================================================================
# Financial Grade 9.0 Evaluator
# ============================================================================

class FinancialGradeEvaluator:
    def __init__(self):
        self.weights = {
            'sharpe_ratio': 0.25,
            'max_drawdown': 0.20,
            'win_rate': 0.15,
            'profit_factor': 0.15,
            'annual_return': 0.15,
            'calmar_ratio': 0.10,
        }
        
    def evaluate(self, result: dict) -> tuple:
        scores = {}
        
        sharpe = result.get('sharpe_ratio', 0)
        if sharpe >= 2.5:
            scores['sharpe_ratio'] = 10.0
        elif sharpe >= 2.0:
            scores['sharpe_ratio'] = 9.0
        elif sharpe >= 1.5:
            scores['sharpe_ratio'] = 8.0
        elif sharpe >= 1.0:
            scores['sharpe_ratio'] = 7.0
        else:
            scores['sharpe_ratio'] = max(0, sharpe * 6)
        
        max_dd = abs(result.get('max_drawdown_pct', 0))
        if max_dd <= 3:
            scores['max_drawdown'] = 10.0
        elif max_dd <= 5:
            scores['max_drawdown'] = 9.0
        elif max_dd <= 8:
            scores['max_drawdown'] = 8.0
        elif max_dd <= 10:
            scores['max_drawdown'] = 7.0
        else:
            scores['max_drawdown'] = max(0, 10 - (max_dd - 10) * 0.3)
        
        win_rate = result.get('win_rate_pct', 0)
        if win_rate >= 70:
            scores['win_rate'] = 10.0
        elif win_rate >= 60:
            scores['win_rate'] = 9.0
        elif win_rate >= 55:
            scores['win_rate'] = 8.0
        elif win_rate >= 50:
            scores['win_rate'] = 7.0
        else:
            scores['win_rate'] = max(0, (win_rate - 40) * 0.7)
        
        profit_factor = result.get('profit_factor', 0)
        if profit_factor >= 3.0:
            scores['profit_factor'] = 10.0
        elif profit_factor >= 2.5:
            scores['profit_factor'] = 9.0
        elif profit_factor >= 2.0:
            scores['profit_factor'] = 8.0
        elif profit_factor >= 1.5:
            scores['profit_factor'] = 7.0
        else:
            scores['profit_factor'] = max(0, profit_factor * 4)
        
        annual_return = result.get('annual_return_pct', 0)
        if annual_return >= 30:
            scores['annual_return'] = 10.0
        elif annual_return >= 20:
            scores['annual_return'] = 9.0
        elif annual_return >= 15:
            scores['annual_return'] = 8.0
        elif annual_return >= 10:
            scores['annual_return'] = 7.0
        else:
            scores['annual_return'] = max(0, annual_return * 0.6)
        
        if max_dd > 0:
            calmar = annual_return / max_dd
        else:
            calmar = 0
        
        if calmar >= 4.0:
            scores['calmar_ratio'] = 10.0
        elif calmar >= 3.0:
            scores['calmar_ratio'] = 9.0
        elif calmar >= 2.0:
            scores['calmar_ratio'] = 8.0
        elif calmar >= 1.5:
            scores['calmar_ratio'] = 7.0
        else:
            scores['calmar_ratio'] = max(0, calmar * 4)
        
        total_score = sum(scores[key] * self.weights[key] for key in self.weights)
        
        return total_score, scores

# ============================================================================
# Generate Test Data
# ============================================================================
print("\n1. Generating test data...")

np.random.seed(42)
n_days = 500
dates = pd.date_range(start='2021-01-01', periods=n_days, freq='D')

prices = np.zeros(n_days)
prices[0] = 100.0

for i in range(1, n_days):
    if i < 150:
        daily_return = np.random.normal(0.002, 0.015)
    elif i < 300:
        daily_return = np.random.normal(-0.0015, 0.02)
    elif i < 420:
        daily_return = np.random.normal(0.0008, 0.012)
    else:
        daily_return = np.random.normal(0.0015, 0.016)
    
    prices[i] = prices[i-1] * (1 + daily_return)

data = pd.DataFrame({
    'Open': prices * (1 + np.random.randn(n_days) * 0.003),
    'High': np.maximum(prices, prices * (1 + np.random.randn(n_days) * 0.003)) * (1 + np.random.rand(n_days) * 0.005),
    'Low': np.minimum(prices, prices * (1 + np.random.randn(n_days) * 0.003)) * (1 - np.random.rand(n_days) * 0.005),
    'Close': prices,
    'Volume': np.random.randint(2000000, 15000000, n_days)
}, index=dates)

print(f"   Test data: {n_days} days with bull/bear/trend cycles")

# ============================================================================
# V6 Deep Optimizer
# ============================================================================
print("\n2. Starting V6 Ultra Optimizer...")

class V6DeepOptimizer:
    def __init__(self, data, evaluator):
        self.data = data
        self.evaluator = evaluator
        self.best_score = 0
        self.best_params = None
        self.best_result = None
        self.iteration = 0
        
    def run_iteration(self, params_dict: dict) -> tuple:
        try:
            params = BernoulliCoandaParameters()
            for key, value in params_dict.items():
                if hasattr(params, key):
                    setattr(params, key, value)
            
            strategy = bernoulli_coanda_strategy(name=f"V6_Iter_{self.iteration}", params=params)
            result = strategy.run_backtest(self.data, 100000)
            
            score, detail_scores = self.evaluator.evaluate(result)
            
            return score, detail_scores, result
        except Exception as e:
            return 0, {}, {}
    
    def optimize(self, max_iterations=300):
        print(f"\n   Target: Financial Grade 9.0")
        print(f"   Max iterations: {max_iterations}")
        print()
        
        start_time = time.time()
        
        param_spaces = {
            'short_velocity_window': list(range(2, 8)),
            'long_velocity_window': list(range(10, 30)),
            'pressure_threshold': [round(x * 0.05, 2) for x in range(20, 80)],
            'curve_window': list(range(10, 25)),
            'adhere_threshold': [round(x * 0.005, 4) for x in range(10, 50)],
            'stop_loss_atr_multiplier': [round(x * 0.5, 1) for x in range(20, 50)],
            'take_profit_risk_reward': [round(x * 0.5, 1) for x in range(30, 60)],
            'max_holding_days': list(range(15, 40)),
        }
        
        current_params = {
            'short_velocity_window': 4,
            'long_velocity_window': 18,
            'pressure_threshold': 0.4,
            'curve_window': 15,
            'adhere_threshold': 0.02,
            'stop_loss_atr_multiplier': 2.0,
            'take_profit_risk_reward': 2.5,
            'max_holding_days': 25,
        }
        
        convergence_count = 0
        plateau_threshold = 20
        no_improve_rounds = 0
        
        while self.iteration < max_iterations:
            self.iteration += 1
            
            score, detail_scores, result = self.run_iteration(current_params)
            
            if score > self.best_score:
                self.best_score = score
                self.best_params = current_params.copy()
                self.best_result = result
                convergence_count = 0
                no_improve_rounds = 0
            else:
                convergence_count += 1
                no_improve_rounds += 1
            
            if self.iteration % 15 == 0 or self.iteration == 1:
                elapsed = time.time() - start_time
                grade = "S+" if score >= 9.5 else "S" if score >= 9.0 else "A" if score >= 8.0 else "B" if score >= 7.0 else "C"
                print(f"   Iter {self.iteration:3d} | Score: {score:5.2f} ({grade}) | Best: {self.best_score:5.2f} | "
                      f"Sharpe: {result.get('sharpe_ratio', 0):.2f} | DD: {result.get('max_drawdown_pct', 0):.1f}% | "
                      f"WR: {result.get('win_rate_pct', 0):.1f}% | Time: {elapsed:.1f}s")
            
            if self.best_score >= 9.0:
                print(f"\n   [SUCCESS] Target reached! Financial Grade 9.0!")
                break
            
            if convergence_count >= plateau_threshold:
                print(f"\n   [PLATEAU] No improvement for {convergence_count} rounds. Mutation...")
                param_to_mutate = random.choice(list(param_spaces.keys()))
                new_value = random.choice(param_spaces[param_to_mutate])
                current_params[param_to_mutate] = new_value
                convergence_count = 0
                continue
            
            if detail_scores:
                if detail_scores.get('sharpe_ratio', 0) < 7:
                    current_params['pressure_threshold'] *= 1.05
                if detail_scores.get('max_drawdown', 0) < 7:
                    current_params['stop_loss_atr_multiplier'] *= 0.92
                if detail_scores.get('win_rate', 0) < 7:
                    current_params['pressure_threshold'] *= 0.97
                if detail_scores.get('profit_factor', 0) < 7:
                    current_params['take_profit_risk_reward'] *= 1.08
                
                current_params['pressure_threshold'] = max(0.15, min(0.75, current_params['pressure_threshold']))
                current_params['stop_loss_atr_multiplier'] = max(1.0, min(4.5, current_params['stop_loss_atr_multiplier']))
                current_params['take_profit_risk_reward'] = max(1.5, min(5.5, current_params['take_profit_risk_reward']))
        
        return self.best_score, self.best_params, self.best_result

# Run optimization
evaluator = FinancialGradeEvaluator()
optimizer = V6DeepOptimizer(data, evaluator)
best_score, best_params, best_result = optimizer.optimize(max_iterations=300)

# ============================================================================
# Output Results
# ============================================================================
print("\n" + "="*90)
print("3. Optimization Results")
print("="*90)

if best_result:
    final_score, final_scores = evaluator.evaluate(best_result)
    grade = "S+" if final_score >= 9.5 else "S" if final_score >= 9.0 else "A" if final_score >= 8.0 else "B" if final_score >= 7.0 else "C"
    
    print(f"\n   Final Score: {final_score:.2f} (Grade: {grade})")
    
    print("\n   Score Breakdown:")
    print("   " + "-" * 60)
    print(f"   {'Metric':<20} {'Score':<10} {'Target':<15} {'Actual':<15}")
    print("   " + "-" * 60)
    
    metric_names = {
        'sharpe_ratio': 'Sharpe Ratio',
        'max_drawdown': 'Max Drawdown',
        'win_rate': 'Win Rate',
        'profit_factor': 'Profit Factor',
        'annual_return': 'Annual Return',
        'calmar_ratio': 'Calmar Ratio'
    }
    
    targets = {
        'sharpe_ratio': '>= 2.0',
        'max_drawdown': '<= 5%',
        'win_rate': '>= 60%',
        'profit_factor': '>= 2.0',
        'annual_return': '>= 20%',
        'calmar_ratio': '>= 3.0'
    }
    
    actual_values = {
        'sharpe_ratio': f"{best_result.get('sharpe_ratio', 0):.2f}",
        'max_drawdown': f"{best_result.get('max_drawdown_pct', 0):.1f}%",
        'win_rate': f"{best_result.get('win_rate_pct', 0):.1f}%",
        'profit_factor': f"{best_result.get('profit_factor', 0):.2f}",
        'annual_return': f"{best_result.get('annual_return_pct', 0):.1f}%",
        'calmar_ratio': f"{best_result.get('annual_return_pct', 0) / max(abs(best_result.get('max_drawdown_pct', 0)), 0.01):.2f}"
    }
    
    for key, name in metric_names.items():
        status = "[OK]" if final_scores[key] >= 7 else "[!]"
        print(f"   {status} {name:<17} {final_scores[key]:<10.1f} {targets[key]:<15} {actual_values[key]:<15}")
    
    print("\n   Core Metrics:")
    print(f"   Total Return: {best_result.get('total_return_pct', 0):+.2f}%")
    print(f"   Sharpe Ratio: {best_result.get('sharpe_ratio', 0):.2f}")
    print(f"   Max Drawdown: {best_result.get('max_drawdown_pct', 0):.2f}%")
    print(f"   Trades: {best_result.get('total_trades', 0)}")
    print(f"   Win Rate: {best_result.get('win_rate_pct', 0):.1f}%")
    
    print("\n   Best Parameters:")
    for key, value in best_params.items():
        print(f"   {key}: {value}")
    
    config_dir = 'optimization_configs'
    os.makedirs(config_dir, exist_ok=True)
    config_file = os.path.join(config_dir, 'BCQ_V6_Grade9_Final.json')
    
    config = {
        'optimization_time': datetime.now().isoformat(),
        'final_score': final_score,
        'grade': grade,
        'parameters': best_params,
        'metrics': {
            'total_return': best_result.get('total_return_pct', 0),
            'sharpe_ratio': best_result.get('sharpe_ratio', 0),
            'max_drawdown': best_result.get('max_drawdown_pct', 0),
            'win_rate': best_result.get('win_rate_pct', 0),
            'profit_factor': best_result.get('profit_factor', 0),
            'annual_return': best_result.get('annual_return_pct', 0)
        }
    }
    
    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    
    print(f"\n   [SAVED] Results saved to: {config_file}")

print("\n" + "="*90)
print("V6 Ultra Optimization Complete!")
print("="*90)

