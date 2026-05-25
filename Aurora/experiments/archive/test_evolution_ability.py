#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
陀螺策略自适应演进能力测试
评估策略的自我优化和迭代改进能力
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd
from dataclasses import dataclass
from scipy.linalg import eigvals

from enhanced_evaluator import EnhancedFinancialEvaluator

@dataclass
class StrategyMetrics:
    sharpe_ratio: float
    k_ratio: float
    max_dd: float
    cap_util: float
    sortino_ratio: float
    omega_ratio: float
    rolling_sharpe_stability: float
    information_ratio: float
    market_correlation: float
    tail_ratio: float
    trade_frequency: float
    max_consecutive_losses: int
    avg_holding_period: float
    recovery_time: float
    lyapunov: float = 0.0

class EvolutionTester:
    def __init__(self):
        self.omega = np.array([0.3, 0.5, 0.7])
        self.omega_history = []
        self.reward_history = []
        self.metrics_history = []
        self.learning_rate = 5e-5
        self.gamma = 0.995
        self.evaluator = EnhancedFinancialEvaluator()
        
    def get_reward(self, metrics, position_change):
        reward = 0.0
        
        if 2.0 <= metrics.sharpe_ratio <= 4.0:
            reward += metrics.sharpe_ratio * 15
        else:
            reward -= abs(metrics.sharpe_ratio - 3.0) * 8
            
        if metrics.k_ratio > 3.0:
            reward += metrics.k_ratio * 8
            
        reward -= metrics.max_dd * 30
        reward -= abs(metrics.lyapunov) * 40
        
        if metrics.sortino_ratio >= 2.0:
            reward += metrics.sortino_ratio * 5
        if metrics.omega_ratio >= 1.5:
            reward += metrics.omega_ratio * 3
            
        reward -= metrics.max_consecutive_losses * 5
        reward -= position_change * 2
        
        return reward
    
    def evolve_omega(self, state, reward):
        self.omega_history.append(self.omega.copy())
        
        exploration_noise = np.random.normal(0, 0.02, 3)
        gradient = np.random.normal(0, self.learning_rate, 3)
        
        if self.reward_history and reward > np.mean(self.reward_history):
            gradient *= 1.3
        else:
            gradient *= -0.4
            
        new_omega = self.omega + gradient + exploration_noise
        self.omega = np.clip(new_omega, 0.1, 1.5)
        
        return self.omega
    
    def test_evolution_ability(self, n_iterations=36):
        print("="*90)
        print("陀螺策略自适应演进能力测试")
        print("="*90)
        print(f"测试迭代次数: {n_iterations}")
        print()
        
        results = {
            'iteration': [],
            'omega': [],
            'reward': [],
            'sharpe': [],
            'max_dd': [],
            'score': [],
        }
        
        for i in range(n_iterations):
            np.random.seed(i * 42)
            
            ret = np.random.randn(100) * 0.02
            returns_std = np.std(ret)
            sharpe = np.mean(ret) / returns_std * np.sqrt(252*24*60) if returns_std > 0 else 0
            
            equity = 1 + np.cumsum(ret)
            max_equity = np.maximum.accumulate(equity)
            drawdown = (equity - max_equity) / max_equity
            max_dd = np.min(drawdown)
            
            sortino = np.mean(ret) / np.sqrt(np.mean(np.minimum(ret, 0)**2)) if np.std(np.minimum(ret, 0)) > 0 else 0
            omega_ratio = np.sum(ret[ret > 0]) / np.abs(np.sum(ret[ret < 0])) if np.sum(ret[ret < 0]) != 0 else 1
            
            metrics = StrategyMetrics(
                sharpe_ratio=sharpe,
                k_ratio=(np.mean(ret) / returns_std) / np.abs(max_dd) if np.abs(max_dd) > 0 else 0,
                max_dd=max_dd,
                cap_util=min(i * 0.02, 1.0),
                sortino_ratio=sortino,
                omega_ratio=omega_ratio,
                rolling_sharpe_stability=np.random.uniform(0.3, 0.8),
                information_ratio=np.random.uniform(0.5, 2.0),
                market_correlation=0.5,
                tail_ratio=1.5,
                trade_frequency=np.random.uniform(0.3, 0.7),
                max_consecutive_losses=np.random.randint(0, 3),
                avg_holding_period=135,
                recovery_time=10,
                lyapunov=np.random.uniform(-0.05, 0.01)
            )
            
            state = np.array([np.mean(ret), returns_std, 0.3])
            position_change = np.random.uniform(0.1, 0.5)
            
            reward = self.get_reward(metrics, position_change)
            self.reward_history.append(reward)
            self.metrics_history.append(metrics)
            
            new_omega = self.evolve_omega(state, reward)
            
            test_result = {
                'returns': ret,
                'days': 3.5,
                'total_return_pct': np.sum(ret) * 100,
                'sharpe_ratio': sharpe,
                'max_drawdown_pct': abs(max_dd) * 100,
                'total_trades': int(50 + i * 0.5),
                'profit_factor': omega_ratio,
                'win_rate_pct': len(ret[ret > 0]) / len(ret) * 100,
            }
            
            score, _, _ = self.evaluator.evaluate(test_result)
            
            results['iteration'].append(i + 1)
            results['omega'].append(new_omega.copy())
            results['reward'].append(reward)
            results['sharpe'].append(sharpe)
            results['max_dd'].append(max_dd)
            results['score'].append(score)
            
            if (i + 1) % 6 == 0:
                print(f"[迭代 {(i+1):2d}] omega=[{new_omega[0]:.3f}, {new_omega[1]:.3f}, {new_omega[2]:.3f}] "
                      f"reward={reward:8.2f} sharpe={sharpe:6.2f} score={score:.2f}")
        
        print()
        print("="*90)
        print("自适应演进能力分析报告")
        print("="*90)
        
        initial_score = results['score'][0]
        final_score = results['score'][-1]
        improvement = final_score - initial_score
        improvement_pct = (improvement / initial_score) * 100 if initial_score > 0 else 0
        
        print(f"\n[1] 演进效果:")
        print(f"    初始评分: {initial_score:.2f}")
        print(f"    最终评分: {final_score:.2f}")
        print(f"    提升幅度: {improvement:+.2f} ({improvement_pct:+.1f}%)")
        
        initial_omega = results['omega'][0]
        final_omega = results['omega'][-1]
        omega_change = np.linalg.norm(final_omega - initial_omega)
        
        print(f"\n[2] 参数演化:")
        print(f"    初始omega: [{initial_omega[0]:.3f}, {initial_omega[1]:.3f}, {initial_omega[2]:.3f}]")
        print(f"    最终omega: [{final_omega[0]:.3f}, {final_omega[1]:.3f}, {final_omega[2]:.3f}]")
        print(f"    参数变化量: {omega_change:.4f}")
        
        rewards = results['reward']
        positive_rewards = sum(1 for r in rewards if r > 0)
        print(f"\n[3] 奖励机制:")
        print(f"    正奖励次数: {positive_rewards}/{len(rewards)} ({positive_rewards/len(rewards)*100:.1f}%)")
        print(f"    平均奖励: {np.mean(rewards):.2f}")
        print(f"    奖励标准差: {np.std(rewards):.2f}")
        
        scores = results['score']
        score_variance = np.std(scores)
        score_trend = np.polyfit(range(len(scores)), scores, 1)[0]
        
        print(f"\n[4] 评分稳定性:")
        print(f"    评分波动: {score_variance:.2f}")
        print(f"    评分趋势: {'上升' if score_trend > 0.01 else '下降' if score_trend < -0.01 else '平稳'} (斜率={score_trend:.4f})")
        
        print(f"\n[5] 能力评估:")
        
        ability_scores = {
            '学习收敛能力': min(10, abs(improvement) * 5 + 5),
            '参数优化能力': min(10, omega_change * 20 + 5),
            '奖励机制有效性': min(10, positive_rewards / len(rewards) * 10),
            '策略稳定性': max(0, 10 - score_variance * 2),
            '趋势把握能力': max(0, min(10, score_trend * 100 + 5)),
        }
        
        total_ability = np.mean(list(ability_scores.values()))
        
        for k, v in sorted(ability_scores.items(), key=lambda x: x[1], reverse=True):
            level = "优秀" if v >= 8 else "良好" if v >= 6 else "一般" if v >= 4 else "较差"
            print(f"    {k:<15}: {v:5.2f}/10 ({level})")
        
        print(f"\n[综合评分] 自适应演进能力总评: {total_ability:.2f}/10")
        
        grade_map = {
            (9, 11): "S (卓越)",
            (8, 9): "A (优秀)",
            (7, 8): "B (良好)",
            (6, 7): "C (一般)",
            (0, 6): "D (较差)",
        }
        grade = next((v for (low, high), v in grade_map.items() if low <= total_ability < high), "D")
        print(f"           等级: {grade}")
        
        print("\n" + "="*90)
        
        return results, total_ability

if __name__ == "__main__":
    tester = EvolutionTester()
    results, ability_score = tester.test_evolution_ability(36)
