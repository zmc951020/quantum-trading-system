#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V6增强型优化器 - 陀螺策略深度优化
目标：达到金融级标准9.0
重点优化：Sortino比率、交易频率、连续亏损控制
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd
from datetime import datetime
import time
import random
from typing import Dict, List, Tuple
from dataclasses import dataclass, asdict
from copy import deepcopy

from enhanced_evaluator import EnhancedFinancialEvaluator

def log(msg):
    print(msg)
    sys.stdout.flush()

@dataclass
class Solution:
    params: Dict
    score: float
    metric_scores: Dict[str, float]
    generation: int
    age: int = 0

@dataclass
class OptimizationHistory:
    generation: int
    best_score: float
    avg_score: float
    diversity: float
    mutations: int
    improvements: int
    sortino: float = 0
    trade_freq: float = 0
    max_losses: float = 0

class GyroStrategyAdapterV2:
    """陀螺策略适配器V2 - 增强版"""
    
    def __init__(self, data):
        self.data = data
        
    def run_with_params(self, params):
        """使用给定参数运行策略"""
        np.random.seed(42)
        n_minutes = min(5000, len(self.data))
        test_data = self.data.iloc[:n_minutes].copy()
        
        prices = test_data['Close'].values
        
        equity = 100000
        max_equity = 100000
        trades = []
        current_position = 0
        position_since = None
        consecutive_losses = 0
        max_consecutive_losses = 0
        equity_curve = [100000]
        
        for i in range(720, len(prices)):
            window = prices[max(0, i-1440):i]
            
            if len(window) >= 60:
                ret = np.diff(window[-60:]) / window[-60:-1]
            else:
                ret = np.array([0.0001]*3)
            ret = np.resize(ret, 3)
            
            mom = np.mean(np.diff(window[-180:])) / window[-1] if len(window) >= 180 else 0
            vol = np.std(np.diff(window[-60:])) * np.sqrt(60) if len(window) >= 60 else 0.01
            
            omega = np.array([
                params.get('omega1', 0.95),
                params.get('omega2', 0.30),
                params.get('omega3', 0.20)
            ])
            
            main_pos = mom * omega[0] * vol
            hedge_pos = vol * omega[1] * 0.1
            time_arb_pos = np.sin(i * 0.01) * omega[2] * vol
            
            total_signal = main_pos + hedge_pos + time_arb_pos
            
            signal_threshold = params.get('signal_threshold', 0.0006)
            min_holding = params.get('min_holding', 50)
            stop_loss = params.get('stop_loss', 0.02)
            take_profit = params.get('take_profit', 0.05)
            
            price_change = (prices[i] - prices[max(0, i-1)]) / prices[max(0, i-1)]
            current_drawdown = (max_equity - equity) / max_equity if max_equity > 0 else 0
            
            if abs(price_change) > stop_loss and current_position != 0:
                daily_return = -stop_loss * current_position / (equity / prices[i])
                equity *= (1 + daily_return)
                max_equity = max(max_equity, equity)
                
                trades.append({
                    'return': daily_return,
                    'signal': total_signal,
                    'type': 'stop_loss'
                })
                
                consecutive_losses += 1
                max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
                current_position = 0
                position_since = None
                
                equity_curve.append(equity)
                continue
            
            if equity > max_equity * (1 + take_profit) and current_position != 0:
                daily_return = take_profit * current_position / (equity / prices[i])
                equity *= (1 + daily_return)
                max_equity = max(max_equity, equity)
                
                trades.append({
                    'return': daily_return,
                    'signal': total_signal,
                    'type': 'take_profit'
                })
                
                consecutive_losses = 0
                current_position = 0
                position_since = None
                
                equity_curve.append(equity)
                continue
            
            if abs(total_signal) > signal_threshold:
                if position_since is None or (i - position_since) >= min_holding:
                    if current_position != 0:
                        daily_return = (prices[i] - prices[i-1]) / prices[i-1] * current_position / (equity / prices[i])
                        equity *= (1 + daily_return)
                        max_equity = max(max_equity, equity)
                        
                        trades.append({
                            'return': daily_return,
                            'signal': total_signal,
                            'type': 'normal'
                        })
                        
                        if daily_return < 0:
                            consecutive_losses += 1
                            max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
                        else:
                            consecutive_losses = 0
                    
                    current_position = total_signal * equity / prices[i]
                    position_since = i
            
            if i > 0 and current_position != 0:
                daily_return = (prices[i] - prices[i-1]) / prices[i-1] * current_position / (equity / prices[i])
                equity *= (1 + daily_return)
                max_equity = max(max_equity, equity)
            
            if i % 60 == 0:
                equity_curve.append(equity)
        
        total_return = (equity - 100000) / 100000 * 100
        max_dd = (max_equity - equity) / max_equity * 100
        
        returns = np.array([t['return'] for t in trades]) if trades else np.array([0])
        returns_std = np.std(returns)
        sharpe = np.mean(returns) / returns_std * np.sqrt(252*24*60) if returns_std > 0 else 0
        
        downside_returns = returns[returns < 0]
        sortino = np.mean(returns) / np.sqrt(np.mean(downside_returns**2)) if len(downside_returns) > 0 and np.mean(downside_returns**2) > 0 else 0
        
        result = {
            'returns': returns,
            'days': n_minutes / 1440,
            'total_return_pct': total_return,
            'sharpe_ratio': sharpe,
            'max_drawdown_pct': max_dd,
            'total_trades': len(trades),
            'profit_factor': np.sum(returns[returns > 0]) / np.abs(np.sum(returns[returns < 0])) if np.sum(returns[returns < 0]) != 0 else 0,
            'win_rate_pct': len(returns[returns > 0]) / len(returns) * 100 if len(returns) > 0 else 0,
            'sortino_ratio': sortino,
            'max_consecutive_losses': max_consecutive_losses,
            'trade_frequency': len(trades) / (n_minutes / 1440 / 252) if n_minutes > 0 else 0,
        }
        
        return result

class GyroV6OptimizerPro:
    """V6增强型优化器 - 陀螺策略专业版"""
    
    def __init__(self, data, evaluator):
        self.data = data
        self.ev = evaluator
        self.adapter = GyroStrategyAdapterV2(data)
        
        self.population_size = 30
        self.elite_size = 8
        self.mutation_rate = 0.35
        self.crossover_rate = 0.6
        
        self.population: List[Solution] = []
        self.archive: List[Solution] = []
        self.history: List[OptimizationHistory] = []
        
        self.param_spaces = {
            'omega1': [round(x * 0.05, 2) for x in range(5, 25)],
            'omega2': [round(x * 0.05, 2) for x in range(1, 15)],
            'omega3': [round(x * 0.05, 2) for x in range(1, 15)],
            'signal_threshold': [round(x * 0.00005, 5) for x in range(5, 20)],
            'min_holding': list(range(20, 80, 5)),
            'stop_loss': [round(x * 0.002, 3) for x in range(5, 25)],
            'take_profit': [round(x * 0.005, 3) for x in range(10, 50)],
        }
        
        self.adaptive_mutation_rate = 0.35
        self.stagnation_count = 0
        self.last_best_score = 0
        
        self.total_mutations = 0
        self.total_crossovers = 0
        self.total_improvements = 0
    
    def initialize_population(self):
        log("\n[初始化] 初始化种群 (专业版)...")
        
        default_params = {
            'omega1': 0.95, 'omega2': 0.30, 'omega3': 0.20,
            'signal_threshold': 0.0006, 'min_holding': 50,
            'stop_loss': 0.015, 'take_profit': 0.04,
        }
        
        score, metric_scores, _ = self.evaluate_solution(default_params)
        self.population.append(Solution(
            params=default_params,
            score=score,
            metric_scores=metric_scores,
            generation=0
        ))
        
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
        
        self.population.sort(key=lambda x: x.score, reverse=True)
        
        log(f"   种群初始化完成: {len(self.population)} 个解")
        log(f"   初始最优评分: {self.population[0].score:.2f}")
        log(f"   初始Sortino: {self.population[0].metric_scores.get('sortino_ratio', 0):.1f}")
    
    def evaluate_solution(self, params: Dict) -> Tuple[float, Dict, Dict]:
        try:
            result = self.adapter.run_with_params(params)
            
            if result['total_trades'] > 0:
                returns = result['returns']
                downside = returns[returns < 0]
                if len(downside) > 0 and np.std(downside) > 0:
                    result['sortino_ratio'] = np.mean(returns) / np.sqrt(np.mean(downside**2))
                else:
                    result['sortino_ratio'] = 0
            
            score, metric_scores, details = self.ev.evaluate(result)
            
            sortino_score = metric_scores.get('sortino_ratio', 0)
            if sortino_score < 6:
                score = score * 0.7 + sortino_score * 0.3
            
            trade_freq_score = metric_scores.get('trade_frequency', 0)
            if trade_freq_score < 5:
                score = score * 0.85 + trade_freq_score * 0.15
            
            return score, metric_scores, result
        except Exception as e:
            return 0, {}, {}
    
    def calculate_diversity(self) -> float:
        if len(self.population) < 2:
            return 0.0
        
        total_distance = 0
        count = 0
        
        for i in range(len(self.population)):
            for j in range(i+1, len(self.population)):
                p1 = self.population[i].params
                p2 = self.population[j].params
                
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
        parents = []
        tournament_size = 4
        
        for _ in range(3):
            tournament = random.sample(
                self.population[:self.population_size//2],
                min(tournament_size, len(self.population[:self.population_size//2]))
            )
            winner = max(tournament, key=lambda x: x.score)
            parents.append(winner)
        
        return parents
    
    def crossover(self, parent1: Solution, parent2: Solution) -> Solution:
        child_params = {}
        
        for key in self.param_spaces.keys():
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
        mutated_params = solution.params.copy()
        
        mutation_strength = min(4, 1 + self.stagnation_count // 3)
        num_mutations = random.randint(2, mutation_strength + 2)
        params_to_mutate = random.sample(
            list(self.param_spaces.keys()),
            min(num_mutations, len(self.param_spaces))
        )
        
        for key in params_to_mutate:
            space = self.param_spaces[key]
            current_idx = space.index(mutated_params[key]) if mutated_params[key] in space else len(space)//2
            
            shift = int(np.random.normal(0, len(space) * self.adaptive_mutation_rate))
            new_idx = max(0, min(len(space)-1, current_idx + shift))
            mutated_params[key] = space[new_idx]
        
        score, metric_scores, _ = self.evaluate_solution(mutated_params)
        self.total_mutations += 1
        
        return Solution(
            params=mutated_params,
            score=score,
            metric_scores=metric_scores,
            generation=self.current_generation
        )
    
    def update_archive(self):
        best = self.population[0]
        
        is_duplicate = False
        for archived in self.archive:
            if self.calculate_solution_distance(best, archived) < 0.1:
                is_duplicate = True
                break
        
        if not is_duplicate:
            self.archive.append(deepcopy(best))
            self.archive.sort(key=lambda x: x.score, reverse=True)
            if len(self.archive) > 30:
                self.archive = self.archive[:30]
    
    def calculate_solution_distance(self, s1: Solution, s2: Solution) -> float:
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
        if self.stagnation_count > 5:
            self.adaptive_mutation_rate = min(0.7, 0.35 + self.stagnation_count * 0.03)
        else:
            self.adaptive_mutation_rate = 0.35
        
        if self.stagnation_count > 15 and self.archive:
            log(f"\n   [档案注入] 检测到停滞，引入精英解")
            elite = random.choice(self.archive[:8])
            elite.age = 0
            elite.generation = self.current_generation
            self.population[-1] = elite
            self.stagnation_count = 0
    
    def evolve_generation(self):
        new_population = []
        
        elites = self.population[:self.elite_size]
        for elite in elites:
            elite.age += 1
            new_population.append(elite)
        
        while len(new_population) < self.population_size:
            op = random.random()
            
            if op < self.crossover_rate and len(self.population) >= 2:
                parents = self.select_parents()
                child = self.crossover(parents[0], parents[1])
                new_population.append(child)
            else:
                parent = random.choice(self.population[:self.population_size//2])
                child = self.mutate(parent)
                new_population.append(child)
        
        self.population = new_population
        self.population.sort(key=lambda x: x.score, reverse=True)
        
        self.update_archive()
        
        current_best = self.population[0].score
        if current_best > self.last_best_score:
            self.total_improvements += 1
            self.stagnation_count = 0
            self.last_best_score = current_best
        else:
            self.stagnation_count += 1
        
        self.adaptive_adjustment()
    
    def optimize(self, max_generations: int = 100, target_score: float = 9.0) -> Tuple[float, Dict, Dict]:
        log("\n[V6专业优化器] 开始深度优化...")
        log(f"   目标评分: {target_score} (金融级标准)")
        log(f"   最大迭代次数: {max_generations}")
        log(f"   种群大小: {self.population_size}")
        log(f"   精英保留数: {self.elite_size}")
        log("")
        
        start_time = time.time()
        self.current_generation = 0
        
        self.initialize_population()
        
        best_ever = 0
        
        for gen in range(max_generations):
            self.current_generation = gen + 1
            
            self.evolve_generation()
            
            diversity = self.calculate_diversity()
            avg_score = np.mean([s.score for s in self.population])
            
            best = self.population[0]
            sortino = best.metric_scores.get('sortino_ratio', 0)
            trade_freq = best.metric_scores.get('trade_frequency', 0)
            max_losses = best.metric_scores.get('max_consecutive_losses', 0)
            
            self.history.append(OptimizationHistory(
                generation=gen + 1,
                best_score=best.score,
                avg_score=avg_score,
                diversity=diversity,
                mutations=self.total_mutations,
                improvements=self.total_improvements,
                sortino=sortino,
                trade_freq=trade_freq,
                max_losses=max_losses
            ))
            
            if best.score > best_ever:
                best_ever = best.score
            
            elapsed = time.time() - start_time
            grade = self.ev.get_grade(best.score)
            
            improvement_needed = target_score - best.score
            progress = (best.score / target_score) * 100
            
            log(f"   迭代 {gen+1:3d} | 最优: {best.score:5.2f} ({grade}) | "
                f"平均: {avg_score:5.2f} | Sortino: {sortino:4.1f} | "
                f"频率: {trade_freq:4.1f} | 停滞: {self.stagnation_count} | "
                f"耗时: {elapsed:.1f}s | 距目标: {improvement_needed:+.2f}")
            
            if best.score >= target_score:
                log(f"\n   [成功] 在第 {gen+1} 次迭代达到金融级标准 {target_score}!")
                log(f"   最终评分: {best.score:.2f} | Sortino: {sortino:.1f} | 交易频率: {trade_freq:.1f}")
                break
            
            if self.stagnation_count > 30:
                log(f"\n   [重启] 检测到长期停滞，注入多样性")
                for i in range(5):
                    params = {}
                    for key, space in self.param_spaces.items():
                        params[key] = random.choice(space)
                    score, metric_scores, _ = self.evaluate_solution(params)
                    self.population[-(i+1)] = Solution(
                        params=params,
                        score=score,
                        metric_scores=metric_scores,
                        generation=gen + 1
                    )
                self.population.sort(key=lambda x: x.score, reverse=True)
                self.stagnation_count = 0
        
        best = self.population[0]
        return best.score, best.params, best.metric_scores

def main():
    log("="*90)
    log("V6增强型优化器 - 陀螺策略深度优化")
    log("目标：达到金融级标准 9.0")
    log("="*90)
    
    log("\n[数据] 准备测试数据...")
    
    np.random.seed(42)
    n_minutes = 8000
    dates = pd.date_range(start='2024-01-01', periods=n_minutes, freq='min')
    
    prices = np.zeros(n_minutes)
    prices[0] = 100.0
    for i in range(1, n_minutes):
        hour_of_day = i % 1440 / 1440
        if hour_of_day < 0.25:
            dr = np.random.normal(0.00015, 0.001)
        elif hour_of_day < 0.5:
            dr = np.random.normal(0.00025, 0.0015)
        elif hour_of_day < 0.75:
            dr = np.random.normal(0.0002, 0.0012)
        else:
            dr = np.random.normal(0.00008, 0.0008)
        prices[i] = prices[i-1] * (1 + dr)
    
    data = pd.DataFrame({
        'Open': prices * (1 + np.random.randn(n_minutes) * 0.0005),
        'High': np.maximum(prices, prices * (1 + np.random.randn(n_minutes) * 0.0005)) * (1 + np.random.rand(n_minutes) * 0.001),
        'Low': np.minimum(prices, prices * (1 + np.random.randn(n_minutes) * 0.0005)) * (1 - np.random.rand(n_minutes) * 0.001),
        'Close': prices,
        'Volume': np.random.randint(10000, 100000, n_minutes)
    }, index=dates)
    
    log(f"   测试数据: {n_minutes} 分钟 ({n_minutes/1440:.1f} 天)")
    
    evaluator = EnhancedFinancialEvaluator()
    optimizer = GyroV6OptimizerPro(data, evaluator)
    
    best_score, best_params, best_metrics = optimizer.optimize(max_generations=100, target_score=9.0)
    
    log("\n" + "="*90)
    log("[结果] 深度优化结果")
    log("="*90)
    
    grade = evaluator.get_grade(best_score)
    log(f"\n   最终评分: {best_score:.2f} ({grade})")
    
    log("\n   所有指标得分:")
    sorted_metrics = sorted(best_metrics.items(), key=lambda x: x[1], reverse=True)
    for k, v in sorted_metrics:
        status = "[优秀]" if v >= 8 else "[良好]" if v >= 6 else "[一般]" if v >= 4 else "[待改进]"
        log(f"   {status} {k:<25}: {v:.1f}")
    
    log("\n   最优参数:")
    for k, v in best_params.items():
        log(f"   - {k}: {v}")
    
    log("\n   优化统计:")
    log(f"   - 总迭代次数: {len(optimizer.history)}")
    log(f"   - 总变异次数: {optimizer.total_mutations}")
    log(f"   - 总交叉次数: {optimizer.total_crossovers}")
    log(f"   - 总改进次数: {optimizer.total_improvements}")
    log(f"   - 精英档案大小: {len(optimizer.archive)}")
    
    if optimizer.history:
        h = optimizer.history[-1]
        log(f"\n   最终状态:")
        log(f"   - 最优评分: {h.best_score:.2f}")
        log(f"   - 平均评分: {h.avg_score:.2f}")
        log(f"   - 多样性: {h.diversity:.4f}")
        log(f"   - Sortino: {h.sortino:.1f}")
        log(f"   - 交易频率: {h.trade_freq:.1f}")
        log(f"   - 最大连续亏损: {h.max_losses}")
    
    log("\n   演进轨迹 (关键节点):")
    checkpoints = [1, 10, 20, 30, 40, 50, 75, 100]
    for gen in checkpoints:
        if gen <= len(optimizer.history):
            h = optimizer.history[gen-1]
            log(f"   Gen {gen:3d}: Best={h.best_score:5.2f} Avg={h.avg_score:5.2f} "
                f"Sortino={h.sortino:4.1f} Freq={h.trade_freq:4.1f} Div={h.diversity:.3f}")
    
    success = best_score >= 9.0
    log(f"\n   [{'成功' if success else '未完成'}] 优化{'已' if success else '尚未'}达到金融级标准 9.0")
    
    log("\n" + "="*90)
    log("V6深度优化完成!")
    log("="*90)

if __name__ == "__main__":
    main()
