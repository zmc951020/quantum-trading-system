#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
金融级标准9.0评估体系
使用超能优化器V6对伯努利-康达策略进行深度迭代优化
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd
from datetime import datetime
import json
import time
from collections import defaultdict

print("="*90)
print("超能优化器V6 - 伯努利-康达策略深度迭代优化")
print("目标: 达到金融级标准 9.0")
print("="*90)

from strategies.bernoulli_coanda_strategy import (
    bernoulli_coanda_strategy,
    BernoulliCoandaParameters
)

print()

# ============================================================================
# 金融级标准9.0评估体系
# ============================================================================

class FinancialGradeEvaluator:
    """金融级标准9.0评估器"""
    
    def __init__(self):
        self.weights = {
            'sharpe_ratio': 0.25,      # 夏普比率 25%
            'max_drawdown': 0.20,      # 最大回撤 20%
            'win_rate': 0.15,          # 胜率 15%
            'profit_factor': 0.15,     # 盈亏比 15%
            'annual_return': 0.15,     # 年化收益 15%
            'calmar_ratio': 0.10,      # 卡玛比率 10%
        }
        
    def evaluate(self, result: dict) -> float:
        """
        评估策略得分 (0-10)
        金融级标准9.0要求各指标达到优秀水平
        """
        scores = {}
        
        # 1. 夏普比率 (目标 >= 2.0)
        sharpe = result.get('sharpe_ratio', 0)
        if sharpe >= 2.5:
            scores['sharpe_ratio'] = 10.0
        elif sharpe >= 2.0:
            scores['sharpe_ratio'] = 9.0
        elif sharpe >= 1.5:
            scores['sharpe_ratio'] = 8.0
        elif sharpe >= 1.0:
            scores['sharpe_ratio'] = 7.0
        elif sharpe >= 0.5:
            scores['sharpe_ratio'] = 5.0
        else:
            scores['sharpe_ratio'] = max(0, sharpe * 8)
        
        # 2. 最大回撤 (目标 <= 5%)
        max_dd = abs(result.get('max_drawdown_pct', 0))
        if max_dd <= 3:
            scores['max_drawdown'] = 10.0
        elif max_dd <= 5:
            scores['max_drawdown'] = 9.0
        elif max_dd <= 8:
            scores['max_drawdown'] = 8.0
        elif max_dd <= 10:
            scores['max_drawdown'] = 7.0
        elif max_dd <= 15:
            scores['max_drawdown'] = 5.0
        else:
            scores['max_drawdown'] = max(0, 10 - (max_dd - 15) * 0.5)
        
        # 3. 胜率 (目标 >= 60%)
        win_rate = result.get('win_rate_pct', 0)
        if win_rate >= 70:
            scores['win_rate'] = 10.0
        elif win_rate >= 60:
            scores['win_rate'] = 9.0
        elif win_rate >= 55:
            scores['win_rate'] = 8.0
        elif win_rate >= 50:
            scores['win_rate'] = 7.0
        elif win_rate >= 45:
            scores['win_rate'] = 5.0
        else:
            scores['win_rate'] = max(0, win_rate - 30) * 0.5
        
        # 4. 盈亏比 (目标 >= 2.0)
        profit_factor = result.get('profit_factor', 0)
        if profit_factor >= 3.0:
            scores['profit_factor'] = 10.0
        elif profit_factor >= 2.5:
            scores['profit_factor'] = 9.0
        elif profit_factor >= 2.0:
            scores['profit_factor'] = 8.0
        elif profit_factor >= 1.5:
            scores['profit_factor'] = 7.0
        elif profit_factor >= 1.0:
            scores['profit_factor'] = 5.0
        else:
            scores['profit_factor'] = max(0, profit_factor * 4)
        
        # 5. 年化收益率 (目标 >= 20%)
        annual_return = result.get('annual_return_pct', 0)
        if annual_return >= 30:
            scores['annual_return'] = 10.0
        elif annual_return >= 20:
            scores['annual_return'] = 9.0
        elif annual_return >= 15:
            scores['annual_return'] = 8.0
        elif annual_return >= 10:
            scores['annual_return'] = 7.0
        elif annual_return >= 5:
            scores['annual_return'] = 5.0
        else:
            scores['annual_return'] = max(0, annual_return * 0.8)
        
        # 6. 卡玛比率 = 年化收益 / 最大回撤
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
        elif calmar >= 1.0:
            scores['calmar_ratio'] = 5.0
        else:
            scores['calmar_ratio'] = max(0, calmar * 4)
        
        # 计算加权总分
        total_score = sum(scores[key] * self.weights[key] for key in self.weights)
        
        return total_score, scores
    
    def get_grade(self, score: float) -> str:
        """根据得分确定等级"""
        if score >= 9.5:
            return "S+ (卓越)"
        elif score >= 9.0:
            return "S (优秀)"
        elif score >= 8.0:
            return "A (良好)"
        elif score >= 7.0:
            return "B (合格)"
        elif score >= 6.0:
            return "C (一般)"
        else:
            return "D (不合格)"
    
    def get_targets(self) -> dict:
        """获取金融级标准9.0的目标值"""
        return {
            'sharpe_ratio': '>= 2.0',
            'max_drawdown': '<= 5%',
            'win_rate': '>= 60%',
            'profit_factor': '>= 2.0',
            'annual_return': '>= 20%',
            'calmar_ratio': '>= 3.0'
        }

print("="*90)
print("金融级标准9.0评估体系")
print("="*90)
evaluator = FinancialGradeEvaluator()
targets = evaluator.get_targets()
print("\n目标指标:")
for key, value in targets.items():
    print(f"  • {key}: {value}")

# ============================================================================
# 生成测试数据
# ============================================================================
print("\n" + "="*90)
print("准备测试数据...")
print("="*90)

np.random.seed(42)
n_days = 500
dates = pd.date_range(start='2021-01-01', periods=n_days, freq='D')

# 生成更真实的市场数据
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

print(f"✅ 测试数据: {n_days}天, 包含牛熊震荡周期")

# ============================================================================
# V6超能优化器 - 深度迭代优化
# ============================================================================
print("\n" + "="*90)
print("启动超能优化器V6 - 深度迭代优化")
print("="*90)

class V6DeepOptimizer:
    """V6超能优化器深度迭代"""
    
    def __init__(self, data, evaluator):
        self.data = data
        self.evaluator = evaluator
        self.history = []
        self.best_score = 0
        self.best_params = None
        self.best_result = None
        self.iteration = 0
        self.target_score = 9.0
        
    def run_iteration(self, params_dict: dict) -> tuple:
        """运行一次迭代"""
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
            print(f"   迭代{self.iteration}出错: {e}")
            return 0, {}, {}
    
    def optimize(self, max_iterations=200):
        """运行优化"""
        print(f"\n目标: 达到金融级标准 {self.target_score}")
        print(f"最大迭代次数: {max_iterations}")
        print()
        
        start_time = time.time()
        
        # 参数搜索空间
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
        
        # 初始化参数
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
        plateau_threshold = 15
        
        while self.iteration < max_iterations:
            self.iteration += 1
            
            # 评估当前参数
            score, detail_scores, result = self.run_iteration(current_params)
            
            # 记录历史
            self.history.append({
                'iteration': self.iteration,
                'score': score,
                'params': current_params.copy(),
                'result': result
            })
            
            # 更新最佳
            if score > self.best_score:
                self.best_score = score
                self.best_params = current_params.copy()
                self.best_result = result
                convergence_count = 0
            else:
                convergence_count += 1
            
            # 进度显示
            if self.iteration % 10 == 0 or self.iteration == 1:
                elapsed = time.time() - start_time
                grade = self.evaluator.get_grade(score)
                print(f"迭代 {self.iteration:3d} | "
                      f"当前: {score:5.2f} ({grade}) | "
                      f"最佳: {self.best_score:5.2f} | "
                      f"夏普: {result.get('sharpe_ratio', 0):.2f} | "
                      f"回撤: {result.get('max_drawdown_pct', 0):.1f}% | "
                      f"耗时: {elapsed:.1f}秒")
            
            # 检查是否达标
            if self.best_score >= self.target_score:
                print(f"\n🎉 达到目标！金融级标准 {self.target_score}！")
                break
            
            # 检查是否陷入 plateau
            if convergence_count >= plateau_threshold:
                print(f"\n⚠️  连续{convergence_count}次未改进，执行跳出策略...")
                # 随机扰动
                import random
                param_to_mutate = random.choice(list(param_spaces.keys()))
                new_value = random.choice(param_spaces[param_to_mutate])
                current_params[param_to_mutate] = new_value
                convergence_count = 0
                continue
            
            # 智能参数调整
            if detail_scores:
                # 根据得分调整参数
                if detail_scores.get('sharpe_ratio', 0) < 7:
                    # 夏普比率不足，增加确认条件
                    current_params['pressure_threshold'] *= 1.1
                if detail_scores.get('max_drawdown', 0) < 7:
                    # 回撤过大，收紧止损
                    current_params['stop_loss_atr_multiplier'] *= 0.9
                if detail_scores.get('win_rate', 0) < 7:
                    # 胜率不足，放宽入场
                    current_params['pressure_threshold'] *= 0.95
                if detail_scores.get('profit_factor', 0) < 7:
                    # 盈亏比不足，调整止盈
                    current_params['take_profit_risk_reward'] *= 1.1
                
                # 限制参数范围
                current_params['pressure_threshold'] = max(0.2, min(0.8, current_params['pressure_threshold']))
                current_params['stop_loss_atr_multiplier'] = max(1.0, min(4.0, current_params['stop_loss_atr_multiplier']))
                current_params['take_profit_risk_reward'] = max(1.5, min(5.0, current_params['take_profit_risk_reward']))
        
        return self.best_score, self.best_params, self.best_result

# 运行优化
optimizer = V6DeepOptimizer(data, evaluator)
best_score, best_params, best_result = optimizer.optimize(max_iterations=200)

# ============================================================================
# 输出最终结果
# ============================================================================
print("\n" + "="*90)
print("优化完成 - 最终结果")
print("="*90)

if best_result:
    final_score, final_scores = evaluator.evaluate(best_result)
    grade = evaluator.get_grade(final_score)
    
    print(f"\n🏆 最终评分: {final_score:.2f} ({grade})")
    print("\n📊 各指标得分:")
    print(f"{'指标':<20} {'得分':<8} {'目标':<15} {'实际值':<15}")
    print("-" * 60)
    
    metric_names = {
        'sharpe_ratio': '夏普比率',
        'max_drawdown': '最大回撤',
        'win_rate': '胜率',
        'profit_factor': '盈亏比',
        'annual_return': '年化收益',
        'calmar_ratio': '卡玛比率'
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
        print(f"{name:<20} {final_scores[key]:<8.1f} {targets[key]:<15} {actual_values[key]:<15}")
    
    print("\n📈 核心指标:")
    print(f"  总收益率: {best_result.get('total_return_pct', 0):+.2f}%")
    print(f"  夏普比率: {best_result.get('sharpe_ratio', 0):.2f}")
    print(f"  最大回撤: {best_result.get('max_drawdown_pct', 0):.2f}%")
    print(f"  交易次数: {best_result.get('total_trades', 0)}")
    print(f"  胜率: {best_result.get('win_rate_pct', 0):.1f}%")
    
    print("\n⚙️  最佳参数:")
    for key, value in best_params.items():
        print(f"  {key}: {value}")
    
    # 保存最佳参数
    config_dir = 'optimization_configs'
    os.makedirs(config_dir, exist_ok=True)
    config_file = os.path.join(config_dir, 'BCQ_V6_Optimized_Grade9.json')
    
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
    
    print(f"\n✅ 优化结果已保存到: {config_file}")

print("\n" + "="*90)
print("V6深度迭代优化完成！")
print("="*90)

