#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V6深度迭代优化器 - 专注协同指标优化
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
from typing import Dict, List, Tuple
from copy import deepcopy

def log(msg):
    print(msg)
    sys.stdout.flush()

from enhanced_evaluator import EnhancedFinancialEvaluator
from strategies.bernoulli_coanda_strategy import (
    bernoulli_coanda_strategy,
    BernoulliCoandaParameters
)

log("="*90)
log("V6 DEEP ITERATION OPTIMIZER - Target: Financial Grade 9.0")
log("="*90)

# ============================================================================
# 生成更真实的测试数据
# ============================================================================

log("\n1. Preparing enhanced test data with multiple market regimes...")

np.random.seed(42)
n_days = 750  # 更长的测试周期
dates = pd.date_range(start='2020-01-01', periods=n_days, freq='D')

prices = np.zeros(n_days)
prices[0] = 100.0

for i in range(1, n_days):
    if i < 150:
        dr = np.random.normal(0.0025, 0.012)  # 牛市
    elif i < 300:
        dr = np.random.normal(-0.0018, 0.020)  # 熊市
    elif i < 450:
        dr = np.random.normal(0.0005, 0.010)  # 震荡
    elif i < 600:
        dr = np.random.normal(0.0020, 0.014)  # 上涨
    else:
        dr = np.random.normal(0.0015, 0.016)  # 稳定上涨
    prices[i] = prices[i-1] * (1 + dr)

data = pd.DataFrame({
    'Open': prices*(1+np.random.randn(n_days)*0.0025),
    'High': np.maximum(prices, prices*(1+np.random.randn(n_days)*0.0025))*(1+np.random.rand(n_days)*0.006),
    'Low': np.minimum(prices, prices*(1+np.random.randn(n_days)*0.0025))*(1-np.random.rand(n_days)*0.006),
    'Close': prices,
    'Volume': np.random.randint(2000000, 15000000, n_days)
}, index=dates)

log(f"   Test data: {n_days} days, multiple market regimes")

# ============================================================================
# 深度迭代优化器
# ============================================================================

class V6DeepIterationOptimizer:
    """
    V6深度迭代优化器
    
    特点:
    1. 更大的种群 (50)
    2. 更长的迭代 (100代)
    3. 专注于协同指标优化
    4. 多策略并行搜索
    """
    
    def __init__(self, data, evaluator):
        self.data = data
        self.ev = evaluator
        
        self.population_size = 50
        self.elite_size = 10
        self.best_score = 0
        self.best_params = None
        self.best_metrics = None
        self.generation = 0
        self.stagnation = 0
        self.improvements = 0
        
        self.param_spaces = {
            'short_velocity_window': list(range(2, 10)),
            'long_velocity_window': list(range(8, 40)),
            'pressure_threshold': [round(x*0.03, 2) for x in range(10, 100)],
            'curve_window': list(range(8, 32)),
            'adhere_threshold': [round(x*0.003, 4) for x in range(5, 60)],
            'stop_loss_atr_multiplier': [round(x*0.3, 1) for x in range(15, 60)],
            'take_profit_risk_reward': [round(x*0.3, 1) for x in range(20, 80)],
            'max_holding_days': list(range(10, 50)),
        }
        
        self.population = []
        self.archive = []
    
    def evaluate(self, params):
        try:
            p = BernoulliCoandaParameters()
            for k, v in params.items():
                if hasattr(p, k):
                    setattr(p, k, v)
            
            strategy = bernoulli_coanda_strategy(name="V6Deep", params=p)
            result = strategy.run_backtest(self.data, 100000)
            
            # 确保有returns数据
            if 'returns' not in result or not result['returns']:
                trades = result.get('trades', [])
                if trades:
                    result['returns'] = [t.get('profit_pct', 0) for t in trades]
                else:
                    result['returns'] = []
            
            result['days'] = len(self.data)
            
            score, metrics, _ = self.ev.evaluate(result)
            return score, metrics, result
        except Exception as e:
            return 0, {}, {}
    
    def init_population(self):
        log("\n2. Initializing population...")
        
        # 默认参数
        default = {
            'short_velocity_window': 4, 'long_velocity_window': 18,
            'pressure_threshold': 0.4, 'curve_window': 15,
            'adhere_threshold': 0.02, 'stop_loss_atr_multiplier': 2.0,
            'take_profit_risk_reward': 2.5, 'max_holding_days': 25,
        }
        
        score, metrics, _ = self.evaluate(default)
        self.population.append({'params': default, 'score': score, 'metrics': metrics})
        
        # 随机生成
        for _ in range(self.population_size - 1):
            params = {k: random.choice(v) for k, v in self.param_spaces.items()}
            score, metrics, _ = self.evaluate(params)
            self.population.append({'params': params, 'score': score, 'metrics': metrics})
        
        self.population.sort(key=lambda x: x['score'], reverse=True)
        log(f"   Population: {len(self.population)}, Best: {self.population[0]['score']:.2f}")
    
    def crossover(self, p1, p2):
        child = {}
        for k in self.param_spaces.keys():
            child[k] = p1[k] if random.random() < 0.5 else p2[k]
        return child
    
    def mutate(self, params, strength=1):
        mutated = params.copy()
        n_mutate = random.randint(1, min(strength, 4))
        keys = random.sample(list(self.param_spaces.keys()), n_mutate)
        
        for k in keys:
            space = self.param_spaces[k]
            current = mutated[k]
            if current in space:
                idx = space.index(current)
                shift = int(np.random.normal(0, len(space) * 0.2))
                new_idx = max(0, min(len(space)-1, idx + shift))
                mutated[k] = space[new_idx]
            else:
                mutated[k] = random.choice(space)
        
        return mutated
    
    def evolve(self):
        new_pop = []
        
        # 精英保留
        for i in range(self.elite_size):
            new_pop.append(self.population[i])
        
        # 生成新个体
        while len(new_pop) < self.population_size:
            if random.random() < 0.6:
                # 交叉
                p1 = random.choice(self.population[:20])['params']
                p2 = random.choice(self.population[:20])['params']
                child = self.crossover(p1, p2)
            else:
                # 变异
                parent = random.choice(self.population[:20])['params']
                strength = 1 + self.stagnation // 10
                child = self.mutate(parent, strength)
            
            score, metrics, _ = self.evaluate(child)
            new_pop.append({'params': child, 'score': score, 'metrics': metrics})
        
        self.population = new_pop
        self.population.sort(key=lambda x: x['score'], reverse=True)
        
        # 检查改进
        if self.population[0]['score'] > self.best_score:
            self.best_score = self.population[0]['score']
            self.best_params = self.population[0]['params']
            self.best_metrics = self.population[0]['metrics']
            self.stagnation = 0
            self.improvements += 1
            return True
        else:
            self.stagnation += 1
            return False
    
    def optimize(self, max_gen=100, target=9.0):
        log("\n3. Starting deep iteration optimization...")
        log(f"   Target: {target}, Max generations: {max_gen}")
        log("")
        
        start = time.time()
        self.init_population()
        self.best_score = self.population[0]['score']
        self.best_params = self.population[0]['params']
        self.best_metrics = self.population[0]['metrics']
        
        for gen in range(max_gen):
            self.generation = gen + 1
            improved = self.evolve()
            
            if self.generation % 10 == 0 or improved:
                elapsed = time.time() - start
                grade = self.ev.get_grade(self.best_score)
                log(f"   Gen {self.generation:3d} | Best: {self.best_score:5.2f} ({grade}) | "
                    f"Stag: {self.stagnation} | Imp: {self.improvements} | Time: {elapsed:.0f}s")
                
                if improved:
                    # 显示指标详情
                    top5 = sorted(self.best_metrics.items(), key=lambda x: x[1], reverse=True)[:5]
                    log(f"        Top metrics: {', '.join([f'{k}:{v:.1f}' for k,v in top5])}")
            
            if self.best_score >= target:
                log(f"\n   [SUCCESS] Target {target} achieved!")
                break
            
            # 停滞太久，注入随机解
            if self.stagnation > 25:
                log(f"\n   [INJECTION] Stagnation {self.stagnation}, injecting random solutions")
                for i in range(5):
                    params = {k: random.choice(v) for k, v in self.param_spaces.items()}
                    score, metrics, _ = self.evaluate(params)
                    self.population[-(i+1)] = {'params': params, 'score': score, 'metrics': metrics}
                self.population.sort(key=lambda x: x['score'], reverse=True)
                self.stagnation = 0
        
        return self.best_score, self.best_params, self.best_metrics

# ============================================================================
# 运行优化
# ============================================================================

evaluator = EnhancedFinancialEvaluator()
optimizer = V6DeepIterationOptimizer(data, evaluator)
best_score, best_params, best_metrics = optimizer.optimize(max_gen=100, target=9.0)

# ============================================================================
# 输出结果
# ============================================================================

log("\n" + "="*90)
log("4. FINAL RESULTS")
log("="*90)

grade = evaluator.get_grade(best_score)
log(f"\n   Final Score: {best_score:.2f} ({grade})")

log("\n   All 16 Metrics:")
sorted_metrics = sorted(best_metrics.items(), key=lambda x: x[1], reverse=True)
for i, (k, v) in enumerate(sorted_metrics, 1):
    status = "✅" if v >= 8 else "⚠️" if v >= 6 else "❌"
    log(f"   {status} {i:2d}. {k:<25} {v:.1f}")

log("\n   Best Parameters:")
for k, v in best_params.items():
    log(f"   {k}: {v}")

log("\n   Optimization Statistics:")
log(f"   Total generations: {optimizer.generation}")
log(f"   Total improvements: {optimizer.improvements}")
log(f"   Final stagnation: {optimizer.stagnation}")

log("\n" + "="*90)
log("OPTIMIZATION COMPLETE!")
log("="*90)
