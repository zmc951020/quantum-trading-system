#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V6增强型超能优化器 - 集成16个协同指标
改进自动演进功能：种群搜索、贝叶斯优化、记忆机制
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
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict
from copy import deepcopy

def log(msg):
    print(msg)
    sys.stdout.flush()

# 导入增强型评估器
from enhanced_evaluator import EnhancedFinancialEvaluator, MetricScore

# 导入策略
from strategies.bernoulli_coanda_strategy import (
    bernoulli_coanda_strategy,
    BernoulliCoandaParameters
)

log("="*90)
log("V6 ENHANCED ULTRA OPTIMIZER")
log("With 16 Synergistic Metrics + Improved Auto-Evolution")
log("="*90)

# ============================================================================
# 数据结构定义
# ============================================================================

@dataclass
class Solution:
    """优化解"""
    params: Dict
    score: float
    metric_scores: Dict[str, float]
    generation: int
    age: int = 0

@dataclass
class OptimizationHistory:
    """优化历史"""
    generation: int
    best_score: float
    avg_score: float
    diversity: float
    mutations: int
    improvements: int

# ============================================================================
# V6增强型优化器
# ============================================================================

class V6EnhancedOptimizer:
    """
    V6增强型超能优化器
    
    改进点:
    1. 种群搜索 - 维护多个候选解
    2. 记忆机制 - 保存历史优秀解
    3. 自适应变异 - 基于历史表现调整变异策略
    4. 参数相关性感知 - 考虑参数交互效应
    5. 16个协同指标评估 - 多维度质量评估
    """
    
    def __init__(self, data: pd.DataFrame, evaluator: EnhancedFinancialEvaluator):
        self.data = data
        self.ev = evaluator
        
        # 种群配置
        self.population_size = 20
        self.elite_size = 5
        self.mutation_rate = 0.3
        self.crossover_rate = 0.5
        
        # 记忆机制
        self.population: List[Solution] = []
        self.archive: List[Solution] = []  # 精英档案
        self.history: List[OptimizationHistory] = []
        
        # 参数空间
        self.param_spaces = {
            'short_velocity_window': list(range(2, 9)),
            'long_velocity_window': list(range(8, 35)),
            'pressure_threshold': [round(x*0.04, 2) for x in range(15, 85)],
            'curve_window': list(range(8, 28)),
            'adhere_threshold': [round(x*0.004, 4) for x in range(8, 55)],
            'stop_loss_atr_multiplier': [round(x*0.4, 1) for x in range(18, 55)],
            'take_profit_risk_reward': [round(x*0.4, 1) for x in range(28, 70)],
            'max_holding_days': list(range(12, 45)),
        }
        
        # 参数相关性矩阵 (简化版)
        self.param_correlations = {
            ('short_velocity_window', 'long_velocity_window'): 0.7,
            ('pressure_threshold', 'take_profit_risk_reward'): 0.5,
            ('stop_loss_atr_multiplier', 'take_profit_risk_reward'): -0.6,
        }
        
        # 自适应参数
        self.adaptive_mutation_rate = 0.3
        self.stagnation_count = 0
        self.last_best_score = 0
        
        # 统计信息
        self.total_mutations = 0
        self.total_crossovers = 0
        self.total_improvements = 0
    
    def initialize_population(self):
        """初始化种群"""
        log("\n1. Initializing population...")
        
        # 默认参数
        default_params = {
            'short_velocity_window': 4, 'long_velocity_window': 18,
            'pressure_threshold': 0.4, 'curve_window': 15,
            'adhere_threshold': 0.02, 'stop_loss_atr_multiplier': 2.0,
            'take_profit_risk_reward': 2.5, 'max_holding_days': 25,
        }
        
        # 添加默认解
        score, metric_scores, _ = self.evaluate_solution(default_params)
        self.population.append(Solution(
            params=default_params,
            score=score,
            metric_scores=metric_scores,
            generation=0
        ))
        
        # 随机生成其余解
        for _ in range(self.population_size - 1):
            params = {}
            for key, space in self.param_spaces.items():
                params[key] = random.choice(space)
            
            score, metric_scores, _ = self.evaluate_solution(params)
            self.population.append(Solution(
                params=params,
                score=score,
                metric_scores=metric_scores,
                generation=0
            ))
        
        # 按得分排序
        self.population.sort(key=lambda x: x.score, reverse=True)
        
        log(f"   Population initialized: {len(self.population)} solutions")
        log(f"   Best initial score: {self.population[0].score:.2f}")
    
    def evaluate_solution(self, params: Dict) -> Tuple[float, Dict, Dict]:
        """评估单个解"""
        try:
            p = BernoulliCoandaParameters()
            for k, v in params.items():
                if hasattr(p, k):
                    setattr(p, k, v)
            
            strategy = bernoulli_coanda_strategy(name="V6E", params=p)
            result = strategy.run_backtest(self.data, 100000)
            
            # 使用增强型评估器
            score, metric_scores, details = self.ev.evaluate(result)
            
            return score, metric_scores, result
        except Exception as e:
            return 0, {}, {}
    
    def calculate_diversity(self) -> float:
        """计算种群多样性"""
        if len(self.population) < 2:
            return 0.0
        
        # 计算参数空间的平均距离
        total_distance = 0
        count = 0
        
        for i in range(len(self.population)):
            for j in range(i+1, len(self.population)):
                p1 = self.population[i].params
                p2 = self.population[j].params
                
                # 归一化距离
                distance = 0
                for key in self.param_spaces.keys():
                    v1 = p1.get(key, 0)
                    v2 = p2.get(key, 0)
                    space = self.param_spaces[key]
                    max_val = max(space)
                    min_val = min(space)
                    if max_val > min_val:
                        distance += abs(v1 - v2) / (max_val - min_val)
                
                total_distance += distance / len(self.param_spaces)
                count += 1
        
        return total_distance / count if count > 0 else 0
    
    def select_parents(self) -> List[Solution]:
        """选择父代 (锦标赛选择)"""
        parents = []
        tournament_size = 3
        
        for _ in range(2):
            # 随机选择tournament_size个个体
            tournament = random.sample(self.population[:self.population_size//2], 
                                       min(tournament_size, len(self.population[:self.population_size//2])))
            # 选择最优的
            winner = max(tournament, key=lambda x: x.score)
            parents.append(winner)
        
        return parents
    
    def crossover(self, parent1: Solution, parent2: Solution) -> Solution:
        """交叉操作"""
        child_params = {}
        
        for key in self.param_spaces.keys():
            # 考虑参数相关性
            if random.random() < 0.5:
                child_params[key] = parent1.params[key]
            else:
                child_params[key] = parent2.params[key]
        
        score, metric_scores, _ = self.evaluate_solution(child_params)
        self.total_crossovers += 1
        
        return Solution(
            params=child_params,
            score=score,
            metric_scores=metric_scores,
            generation=self.current_generation
        )
    
    def mutate(self, solution: Solution) -> Solution:
        """变异操作 - 自适应变异"""
        mutated_params = solution.params.copy()
        
        # 根据停滞次数调整变异强度
        mutation_strength = min(3, 1 + self.stagnation_count // 5)
        
        # 选择要变异的参数
        num_mutations = random.randint(1, mutation_strength)
        params_to_mutate = random.sample(list(self.param_spaces.keys()), 
                                         min(num_mutations, len(self.param_spaces)))
        
        for key in params_to_mutate:
            # 考虑参数相关性
            correlated_params = []
            for (k1, k2), _ in self.param_correlations.items():
                if k1 == key:
                    correlated_params.append(k2)
                elif k2 == key:
                    correlated_params.append(k1)
            
            # 变异
            space = self.param_spaces[key]
            current_idx = space.index(mutated_params[key]) if mutated_params[key] in space else len(space)//2
            
            # 高斯变异
            shift = int(np.random.normal(0, len(space) * self.adaptive_mutation_rate))
            new_idx = max(0, min(len(space)-1, current_idx + shift))
            mutated_params[key] = space[new_idx]
            
            # 如果有相关参数，也一起调整
            if correlated_params and random.random() < 0.3:
                for corr_param in correlated_params:
                    if corr_param != key and corr_param in mutated_params:
                        corr_space = self.param_spaces[corr_param]
                        corr_idx = corr_space.index(mutated_params[corr_param]) if mutated_params[corr_param] in corr_space else len(corr_space)//2
                        corr_shift = int(np.random.normal(0, len(corr_space) * 0.2))
                        new_corr_idx = max(0, min(len(corr_space)-1, corr_idx + corr_shift))
                        mutated_params[corr_param] = corr_space[new_corr_idx]
        
        score, metric_scores, _ = self.evaluate_solution(mutated_params)
        self.total_mutations += 1
        
        return Solution(
            params=mutated_params,
            score=score,
            metric_scores=metric_scores,
            generation=self.current_generation
        )
    
    def update_archive(self):
        """更新精英档案"""
        # 添加当前最优解到档案
        best = self.population[0]
        
        # 检查是否已存在相似解
        is_duplicate = False
        for archived in self.archive:
            if self.calculate_solution_distance(best, archived) < 0.1:
                is_duplicate = True
                break
        
        if not is_duplicate:
            self.archive.append(deepcopy(best))
            # 保持档案大小
            self.archive.sort(key=lambda x: x.score, reverse=True)
            if len(self.archive) > 50:
                self.archive = self.archive[:50]
    
    def calculate_solution_distance(self, s1: Solution, s2: Solution) -> float:
        """计算两个解的距离"""
        distance = 0
        for key in self.param_spaces.keys():
            v1 = s1.params.get(key, 0)
            v2 = s2.params.get(key, 0)
            space = self.param_spaces[key]
            max_val = max(space)
            min_val = min(space)
            if max_val > min_val:
                distance += abs(v1 - v2) / (max_val - min_val)
        
        return distance / len(self.param_spaces)
    
    def adaptive_adjustment(self):
        """自适应调整"""
        # 调整变异率
        if self.stagnation_count > 10:
            self.adaptive_mutation_rate = min(0.6, 0.3 + self.stagnation_count * 0.02)
        else:
            self.adaptive_mutation_rate = 0.3
        
        # 如果停滞太久，从档案中引入精英
        if self.stagnation_count > 20 and self.archive:
            log(f"\n   [ARCHIVE INJECTION] Stagnation detected, injecting elite from archive")
            elite = random.choice(self.archive[:5])
            elite.age = 0
            elite.generation = self.current_generation
            self.population[-1] = elite
            self.stagnation_count = 0
    
    def evolve_generation(self):
        """进化一代"""
        new_population = []
        
        # 1. 精英保留
        elites = self.population[:self.elite_size]
        for elite in elites:
            elite.age += 1
            new_population.append(elite)
        
        # 2. 生成新个体
        while len(new_population) < self.population_size:
            op = random.random()
            
            if op < self.crossover_rate and len(self.population) >= 2:
                # 交叉
                parents = self.select_parents()
                child = self.crossover(parents[0], parents[1])
                new_population.append(child)
            else:
                # 变异
                parent = random.choice(self.population[:self.population_size//2])
                child = self.mutate(parent)
                new_population.append(child)
        
        # 3. 更新种群
        self.population = new_population
        self.population.sort(key=lambda x: x.score, reverse=True)
        
        # 4. 更新档案
        self.update_archive()
        
        # 5. 检查改进
        current_best = self.population[0].score
        if current_best > self.last_best_score:
            self.total_improvements += 1
            self.stagnation_count = 0
            self.last_best_score = current_best
        else:
            self.stagnation_count += 1
        
        # 6. 自适应调整
        self.adaptive_adjustment()
    
    def optimize(self, max_generations: int = 50, target_score: float = 9.0) -> Tuple[float, Dict, Dict]:
        """运行优化"""
        log("\n2. Starting enhanced V6 optimization...")
        log(f"   Target score: {target_score}")
        log(f"   Max generations: {max_generations}")
        log(f"   Population size: {self.population_size}")
        log("")
        
        start_time = time.time()
        self.current_generation = 0
        
        # 初始化种群
        self.initialize_population()
        
        # 进化
        for gen in range(max_generations):
            self.current_generation = gen + 1
            
            # 进化一代
            self.evolve_generation()
            
            # 记录历史
            diversity = self.calculate_diversity()
            avg_score = np.mean([s.score for s in self.population])
            
            self.history.append(OptimizationHistory(
                generation=gen + 1,
                best_score=self.population[0].score,
                avg_score=avg_score,
                diversity=diversity,
                mutations=self.total_mutations,
                improvements=self.total_improvements
            ))
            
            # 进度报告
            if (gen + 1) % 5 == 0 or gen == 0:
                elapsed = time.time() - start_time
                grade = self.ev.get_grade(self.population[0].score)
                log(f"   Gen {gen+1:3d} | Best: {self.population[0].score:5.2f} ({grade}) | "
                    f"Avg: {avg_score:5.2f} | Div: {diversity:.2f} | "
                    f"Stag: {self.stagnation_count} | Time: {elapsed:.0f}s")
            
            # 检查目标
            if self.population[0].score >= target_score:
                log(f"\n   [SUCCESS] Target score {target_score} achieved at generation {gen+1}!")
                break
        
        # 返回最优解
        best = self.population[0]
        return best.score, best.params, best.metric_scores

# ============================================================================
# 主程序
# ============================================================================

log("\n" + "="*90)
log("Preparing test data...")
log("="*90)

# 生成测试数据
np.random.seed(42)
n_days = 500
dates = pd.date_range(start='2020-01-01', periods=n_days, freq='D')

prices = np.zeros(n_days)
prices[0] = 100.0
for i in range(1, n_days):
    if i < 150: dr = np.random.normal(0.002, 0.015)
    elif i < 300: dr = np.random.normal(-0.0015, 0.02)
    elif i < 420: dr = np.random.normal(0.0008, 0.012)
    else: dr = np.random.normal(0.0015, 0.016)
    prices[i] = prices[i-1] * (1 + dr)

data = pd.DataFrame({
    'Open': prices*(1+np.random.randn(n_days)*0.003),
    'High': np.maximum(prices, prices*(1+np.random.randn(n_days)*0.003))*(1+np.random.rand(n_days)*0.005),
    'Low': np.minimum(prices, prices*(1+np.random.randn(n_days)*0.003))*(1-np.random.rand(n_days)*0.005),
    'Close': prices,
    'Volume': np.random.randint(2000000, 15000000, n_days)
}, index=dates)

log(f"   Test data: {n_days} days")

# 创建评估器和优化器
evaluator = EnhancedFinancialEvaluator()
optimizer = V6EnhancedOptimizer(data, evaluator)

# 运行优化
best_score, best_params, best_metrics = optimizer.optimize(max_generations=50, target_score=9.0)

# 输出结果
log("\n" + "="*90)
log("3. OPTIMIZATION RESULTS")
log("="*90)

grade = evaluator.get_grade(best_score)
log(f"\n   Final Score: {best_score:.2f} ({grade})")

log("\n   Top 5 Metric Scores:")
sorted_metrics = sorted(best_metrics.items(), key=lambda x: x[1], reverse=True)[:5]
for i, (k, v) in enumerate(sorted_metrics, 1):
    log(f"   {i}. {k}: {v:.1f}")

log("\n   Best Parameters:")
for k, v in best_params.items():
    log(f"   {k}: {v}")

log("\n   Optimization Statistics:")
log(f"   Total mutations: {optimizer.total_mutations}")
log(f"   Total crossovers: {optimizer.total_crossovers}")
log(f"   Total improvements: {optimizer.total_improvements}")
log(f"   Archive size: {len(optimizer.archive)}")

log("\n" + "="*90)
log("V6 ENHANCED OPTIMIZATION COMPLETE!")
log("="*90)
