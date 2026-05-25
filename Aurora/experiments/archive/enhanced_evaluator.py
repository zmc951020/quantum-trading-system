#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增强型金融级评估器 - 包含16个协同指标
用于V6超能优化器的多维度策略评估
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime

@dataclass
class MetricScore:
    """指标得分"""
    name: str
    value: float
    score: float
    weight: float
    target: str
    status: str  # 'excellent', 'good', 'acceptable', 'poor'

class EnhancedFinancialEvaluator:
    """
    增强型金融级评估器
    
    包含16个协同指标:
    - 基础指标(6个): Sharpe, MaxDD, WinRate, ProfitFactor, AnnualReturn, Calmar
    - 协同指标(10个): Sortino, Omega, TailRatio, TradeFreq, HoldingPeriod, 
                      MarketCorr, RollingStability, RecoveryTime, ConsecLosses, InfoRatio
    """
    
    def __init__(self):
        # 基础指标权重
        self.base_weights = {
            'sharpe_ratio': 0.20,
            'max_drawdown': 0.15,
            'win_rate': 0.10,
            'profit_factor': 0.10,
            'annual_return': 0.05,
        }
        
        # 协同指标权重
        self.synergy_weights = {
            'sortino_ratio': 0.08,
            'omega_ratio': 0.05,
            'rolling_sharpe_stability': 0.05,
            'information_ratio': 0.05,
            'market_correlation': 0.04,
            'tail_ratio': 0.03,
            'trade_frequency': 0.03,
            'max_consecutive_losses': 0.03,
            'avg_holding_period': 0.02,
            'recovery_time': 0.02,
        }
        
        # 合并权重
        self.weights = {**self.base_weights, **self.synergy_weights}
        
        # 指标目标值
        self.targets = {
            'sharpe_ratio': '>= 2.0',
            'max_drawdown': '<= 5%',
            'win_rate': '>= 60%',
            'profit_factor': '>= 2.0',
            'annual_return': '>= 20%',
            'sortino_ratio': '>= 2.0',
            'omega_ratio': '>= 1.5',
            'rolling_sharpe_stability': '<= 0.5',
            'information_ratio': '>= 0.5',
            'market_correlation': '0.3-0.7',
            'tail_ratio': '>= 1.5',
            'trade_frequency': '20-50/yr',
            'max_consecutive_losses': '<= 5',
            'avg_holding_period': '5-20 days',
            'recovery_time': '<= 30 days',
        }
    
    def calculate_sortino_ratio(self, returns: np.ndarray, target_return: float = 0.0) -> float:
        """
        计算Sortino比率
        
        Sortino = (平均收益 - 目标收益) / 下行波动率
        
        优势: 只惩罚下行波动，比Sharpe更准确反映风险
        """
        if len(returns) == 0:
            return 0.0
        
        downside_returns = returns[returns < target_return]
        if len(downside_returns) == 0:
            return float('inf') if np.mean(returns) > target_return else 0.0
        
        downside_deviation = np.sqrt(np.mean((downside_returns - target_return) ** 2))
        if downside_deviation == 0:
            return 0.0
        
        return (np.mean(returns) - target_return) / downside_deviation
    
    def calculate_omega_ratio(self, returns: np.ndarray, threshold: float = 0.0) -> float:
        """
        计算Omega比率
        
        Omega = Σ(收益 > 阈值) / Σ(阈值 - 收益 < 阈值)
        
        优势: 考虑完整收益分布，对尾部风险敏感
        """
        if len(returns) == 0:
            return 0.0
        
        gains = np.sum(returns[returns > threshold] - threshold)
        losses = np.sum(threshold - returns[returns <= threshold])
        
        if losses == 0:
            return float('inf') if gains > 0 else 1.0
        
        return gains / losses
    
    def calculate_tail_ratio(self, returns: np.ndarray) -> float:
        """
        计算尾部比率
        
        Tail Ratio = P(95) / |P(5)|
        
        优势: 检测极端情况，识别肥尾特征
        """
        if len(returns) < 20:
            return 1.0
        
        p95 = np.percentile(returns, 95)
        p5 = np.percentile(returns, 5)
        
        if p5 >= 0:
            return float('inf')
        
        return p95 / abs(p5)
    
    def calculate_rolling_sharpe_stability(self, returns: np.ndarray, window: int = 20) -> float:
        """
        计算滚动夏普稳定性
        
        Stability = Std(Rolling Sharpe) / Mean(Rolling Sharpe)
        
        优势: 衡量策略持续性，避免统计幻觉
        """
        if len(returns) < window * 2:
            return 1.0
        
        rolling_sharpes = []
        for i in range(window, len(returns)):
            window_returns = returns[i-window:i]
            if np.std(window_returns) > 0:
                sharpe = np.mean(window_returns) / np.std(window_returns) * np.sqrt(252)
                rolling_sharpes.append(sharpe)
        
        if len(rolling_sharpes) == 0:
            return 1.0
        
        mean_sharpe = np.mean(rolling_sharpes)
        std_sharpe = np.std(rolling_sharpes)
        
        if mean_sharpe == 0:
            return 1.0
        
        return std_sharpe / abs(mean_sharpe)
    
    def calculate_information_ratio(self, returns: np.ndarray, benchmark_returns: np.ndarray = None) -> float:
        """
        计算信息比率
        
        IR = (策略收益 - 基准收益) / 跟踪误差
        
        优势: 衡量相对基准的超额收益能力
        """
        if len(returns) == 0:
            return 0.0
        
        # 如果没有基准，使用0作为基准
        if benchmark_returns is None:
            benchmark_returns = np.zeros(len(returns))
        
        excess_returns = returns - benchmark_returns
        tracking_error = np.std(excess_returns)
        
        if tracking_error == 0:
            return 0.0
        
        return np.mean(excess_returns) / tracking_error * np.sqrt(252)
    
    def calculate_market_correlation(self, returns: np.ndarray, market_returns: np.ndarray = None) -> float:
        """
        计算市场相关性
        
        Correlation = Corr(策略收益, 市场收益)
        
        优势: 衡量分散化程度
        """
        if len(returns) == 0:
            return 0.0
        
        # 如果没有市场数据，返回中性值
        if market_returns is None:
            return 0.5
        
        if len(market_returns) != len(returns):
            return 0.5
        
        correlation = np.corrcoef(returns, market_returns)[0, 1]
        return correlation if not np.isnan(correlation) else 0.5
    
    def calculate_trade_frequency_score(self, total_trades: int, days: int) -> float:
        """
        计算交易频率得分
        
        频率 = 总交易次数 / 年化天数
        
        理想范围: 20-50次/年
        """
        if days == 0:
            return 0.0
        
        trades_per_year = total_trades * 252 / days
        
        # 理想范围: 20-50次/年
        if 20 <= trades_per_year <= 50:
            return 10.0
        elif 10 <= trades_per_year <= 100:
            return 7.0
        else:
            return 4.0
    
    def calculate_max_consecutive_losses(self, returns: np.ndarray) -> int:
        """
        计算最大连续亏损次数
        
        优势: 衡量心理压力和资本风险
        """
        if len(returns) == 0:
            return 0
        
        max_consecutive = 0
        current_consecutive = 0
        
        for r in returns:
            if r < 0:
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 0
        
        return max_consecutive
    
    def calculate_avg_holding_period(self, trades: List[Dict]) -> float:
        """
        计算平均持仓期
        
        理想范围: 5-20天 (取决于策略类型)
        """
        if not trades:
            return 0.0
        
        holding_days = [t.get('holding_days', 0) for t in trades]
        return np.mean(holding_days) if holding_days else 0.0
    
    def calculate_recovery_time(self, drawdown_series: np.ndarray) -> float:
        """
        计算平均恢复时间
        
        优势: 衡量资本恢复能力
        """
        if len(drawdown_series) == 0:
            return 0.0
        
        # 简化计算：找到所有恢复点
        in_drawdown = False
        dd_start = 0
        recovery_times = []
        
        for i, dd in enumerate(drawdown_series):
            if dd < 0 and not in_drawdown:
                in_drawdown = True
                dd_start = i
            elif dd >= 0 and in_drawdown:
                in_drawdown = False
                recovery_times.append(i - dd_start)
        
        return np.mean(recovery_times) if recovery_times else 0.0
    
    def evaluate(self, result: Dict) -> Tuple[float, Dict[str, float], Dict[str, MetricScore]]:
        """
        综合评估策略表现
        
        返回: (总分, 各指标得分字典, 各指标详细信息)
        """
        scores = {}
        metric_details = {}
        
        # 提取基础数据
        returns = np.array(result.get('returns', []))
        trades = result.get('trades', [])
        days = result.get('days', 252)
        
        # ========== 基础指标 ==========
        
        # 1. 夏普比率
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
        
        metric_details['sharpe_ratio'] = MetricScore(
            name='Sharpe Ratio',
            value=sharpe,
            score=scores['sharpe_ratio'],
            weight=self.weights['sharpe_ratio'],
            target=self.targets['sharpe_ratio'],
            status='excellent' if sharpe >= 2.0 else 'good' if sharpe >= 1.5 else 'acceptable'
        )
        
        # 2. 最大回撤
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
        
        metric_details['max_drawdown'] = MetricScore(
            name='Max Drawdown',
            value=max_dd,
            score=scores['max_drawdown'],
            weight=self.weights['max_drawdown'],
            target=self.targets['max_drawdown'],
            status='excellent' if max_dd <= 5 else 'good' if max_dd <= 8 else 'acceptable'
        )
        
        # 3. 胜率
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
        
        metric_details['win_rate'] = MetricScore(
            name='Win Rate',
            value=win_rate,
            score=scores['win_rate'],
            weight=self.weights['win_rate'],
            target=self.targets['win_rate'],
            status='excellent' if win_rate >= 60 else 'good' if win_rate >= 55 else 'acceptable'
        )
        
        # 4. 盈亏比
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
        
        metric_details['profit_factor'] = MetricScore(
            name='Profit Factor',
            value=profit_factor,
            score=scores['profit_factor'],
            weight=self.weights['profit_factor'],
            target=self.targets['profit_factor'],
            status='excellent' if profit_factor >= 2.0 else 'good' if profit_factor >= 1.5 else 'acceptable'
        )
        
        # 5. 年化收益
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
        
        metric_details['annual_return'] = MetricScore(
            name='Annual Return',
            value=annual_return,
            score=scores['annual_return'],
            weight=self.weights['annual_return'],
            target=self.targets['annual_return'],
            status='excellent' if annual_return >= 20 else 'good' if annual_return >= 15 else 'acceptable'
        )
        
        # ========== 协同指标 ==========
        
        # 6. Sortino比率
        if len(returns) > 0:
            sortino = self.calculate_sortino_ratio(returns)
            if sortino >= 2.5:
                scores['sortino_ratio'] = 10.0
            elif sortino >= 2.0:
                scores['sortino_ratio'] = 9.0
            elif sortino >= 1.5:
                scores['sortino_ratio'] = 8.0
            elif sortino >= 1.0:
                scores['sortino_ratio'] = 7.0
            else:
                scores['sortino_ratio'] = max(0, sortino * 6)
        else:
            sortino = 0
            scores['sortino_ratio'] = 0
        
        metric_details['sortino_ratio'] = MetricScore(
            name='Sortino Ratio',
            value=sortino,
            score=scores['sortino_ratio'],
            weight=self.weights['sortino_ratio'],
            target=self.targets['sortino_ratio'],
            status='excellent' if sortino >= 2.0 else 'good' if sortino >= 1.5 else 'acceptable'
        )
        
        # 7. Omega比率
        if len(returns) > 0:
            omega = self.calculate_omega_ratio(returns)
            if omega >= 2.0:
                scores['omega_ratio'] = 10.0
            elif omega >= 1.5:
                scores['omega_ratio'] = 9.0
            elif omega >= 1.2:
                scores['omega_ratio'] = 8.0
            elif omega >= 1.0:
                scores['omega_ratio'] = 7.0
            else:
                scores['omega_ratio'] = max(0, (omega - 0.5) * 12)
        else:
            omega = 0
            scores['omega_ratio'] = 0
        
        metric_details['omega_ratio'] = MetricScore(
            name='Omega Ratio',
            value=omega,
            score=scores['omega_ratio'],
            weight=self.weights['omega_ratio'],
            target=self.targets['omega_ratio'],
            status='excellent' if omega >= 1.5 else 'good' if omega >= 1.2 else 'acceptable'
        )
        
        # 8. 尾部比率
        if len(returns) > 20:
            tail_ratio = self.calculate_tail_ratio(returns)
            if tail_ratio >= 2.0:
                scores['tail_ratio'] = 10.0
            elif tail_ratio >= 1.5:
                scores['tail_ratio'] = 9.0
            elif tail_ratio >= 1.2:
                scores['tail_ratio'] = 8.0
            else:
                scores['tail_ratio'] = max(0, tail_ratio * 6)
        else:
            tail_ratio = 1.0
            scores['tail_ratio'] = 7.0
        
        metric_details['tail_ratio'] = MetricScore(
            name='Tail Ratio',
            value=tail_ratio,
            score=scores['tail_ratio'],
            weight=self.weights['tail_ratio'],
            target=self.targets['tail_ratio'],
            status='excellent' if tail_ratio >= 1.5 else 'good' if tail_ratio >= 1.2 else 'acceptable'
        )
        
        # 9. 滚动夏普稳定性
        if len(returns) > 40:
            stability = self.calculate_rolling_sharpe_stability(returns)
            if stability <= 0.3:
                scores['rolling_sharpe_stability'] = 10.0
            elif stability <= 0.5:
                scores['rolling_sharpe_stability'] = 9.0
            elif stability <= 0.8:
                scores['rolling_sharpe_stability'] = 7.0
            else:
                scores['rolling_sharpe_stability'] = max(0, 10 - stability * 5)
        else:
            stability = 0.5
            scores['rolling_sharpe_stability'] = 8.0
        
        metric_details['rolling_sharpe_stability'] = MetricScore(
            name='Rolling Sharpe Stability',
            value=stability,
            score=scores['rolling_sharpe_stability'],
            weight=self.weights['rolling_sharpe_stability'],
            target=self.targets['rolling_sharpe_stability'],
            status='excellent' if stability <= 0.5 else 'good' if stability <= 0.8 else 'acceptable'
        )
        
        # 10. 信息比率
        if len(returns) > 0:
            info_ratio = self.calculate_information_ratio(returns)
            if info_ratio >= 1.0:
                scores['information_ratio'] = 10.0
            elif info_ratio >= 0.5:
                scores['information_ratio'] = 9.0
            elif info_ratio >= 0.3:
                scores['information_ratio'] = 8.0
            else:
                scores['information_ratio'] = max(0, info_ratio * 15)
        else:
            info_ratio = 0
            scores['information_ratio'] = 0
        
        metric_details['information_ratio'] = MetricScore(
            name='Information Ratio',
            value=info_ratio,
            score=scores['information_ratio'],
            weight=self.weights['information_ratio'],
            target=self.targets['information_ratio'],
            status='excellent' if info_ratio >= 0.5 else 'good' if info_ratio >= 0.3 else 'acceptable'
        )
        
        # 11. 市场相关性
        if len(returns) > 0:
            market_corr = self.calculate_market_correlation(returns)
            if 0.3 <= market_corr <= 0.7:
                scores['market_correlation'] = 10.0
            elif 0.2 <= market_corr <= 0.8:
                scores['market_correlation'] = 8.0
            else:
                scores['market_correlation'] = 6.0
        else:
            market_corr = 0.5
            scores['market_correlation'] = 8.0
        
        metric_details['market_correlation'] = MetricScore(
            name='Market Correlation',
            value=market_corr,
            score=scores['market_correlation'],
            weight=self.weights['market_correlation'],
            target=self.targets['market_correlation'],
            status='excellent' if 0.3 <= market_corr <= 0.7 else 'good'
        )
        
        # 12. 交易频率
        total_trades = result.get('total_trades', 0)
        scores['trade_frequency'] = self.calculate_trade_frequency_score(total_trades, days)
        trades_per_year = total_trades * 252 / days if days > 0 else 0
        
        metric_details['trade_frequency'] = MetricScore(
            name='Trade Frequency',
            value=trades_per_year,
            score=scores['trade_frequency'],
            weight=self.weights['trade_frequency'],
            target=self.targets['trade_frequency'],
            status='excellent' if 20 <= trades_per_year <= 50 else 'good'
        )
        
        # 13. 最大连续亏损
        if len(returns) > 0:
            consec_losses = self.calculate_max_consecutive_losses(returns)
            if consec_losses <= 3:
                scores['max_consecutive_losses'] = 10.0
            elif consec_losses <= 5:
                scores['max_consecutive_losses'] = 9.0
            elif consec_losses <= 8:
                scores['max_consecutive_losses'] = 7.0
            else:
                scores['max_consecutive_losses'] = max(0, 10 - (consec_losses - 5) * 1.5)
        else:
            consec_losses = 0
            scores['max_consecutive_losses'] = 10.0
        
        metric_details['max_consecutive_losses'] = MetricScore(
            name='Max Consecutive Losses',
            value=consec_losses,
            score=scores['max_consecutive_losses'],
            weight=self.weights['max_consecutive_losses'],
            target=self.targets['max_consecutive_losses'],
            status='excellent' if consec_losses <= 5 else 'good' if consec_losses <= 8 else 'poor'
        )
        
        # 14. 平均持仓期
        if trades:
            avg_holding = self.calculate_avg_holding_period(trades)
            if 5 <= avg_holding <= 20:
                scores['avg_holding_period'] = 10.0
            elif 3 <= avg_holding <= 30:
                scores['avg_holding_period'] = 8.0
            else:
                scores['avg_holding_period'] = 6.0
        else:
            avg_holding = 0
            scores['avg_holding_period'] = 7.0
        
        metric_details['avg_holding_period'] = MetricScore(
            name='Avg Holding Period',
            value=avg_holding,
            score=scores['avg_holding_period'],
            weight=self.weights['avg_holding_period'],
            target=self.targets['avg_holding_period'],
            status='excellent' if 5 <= avg_holding <= 20 else 'good'
        )
        
        # 15. 恢复时间
        if 'drawdown_series' in result:
            recovery = self.calculate_recovery_time(np.array(result['drawdown_series']))
            if recovery <= 10:
                scores['recovery_time'] = 10.0
            elif recovery <= 30:
                scores['recovery_time'] = 9.0
            elif recovery <= 60:
                scores['recovery_time'] = 7.0
            else:
                scores['recovery_time'] = max(0, 10 - (recovery - 30) * 0.1)
        else:
            recovery = 0
            scores['recovery_time'] = 8.0
        
        metric_details['recovery_time'] = MetricScore(
            name='Recovery Time',
            value=recovery,
            score=scores['recovery_time'],
            weight=self.weights['recovery_time'],
            target=self.targets['recovery_time'],
            status='excellent' if recovery <= 30 else 'good' if recovery <= 60 else 'poor'
        )
        
        # 计算加权总分
        total_score = sum(scores[k] * self.weights[k] for k in self.weights if k in scores)
        
        return total_score, scores, metric_details
    
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
    
    def print_report(self, result: Dict):
        """打印详细评估报告"""
        total_score, scores, details = self.evaluate(result)
        grade = self.get_grade(total_score)
        
        print("\n" + "="*90)
        print("增强型金融级评估报告 - 16个协同指标")
        print("="*90)
        
        print(f"\n综合评分: {total_score:.2f} ({grade})")
        
        print("\n基础指标 (权重 60%):")
        print(f"{'指标':<25} {'得分':<8} {'权重':<8} {'实际值':<15} {'目标':<15} {'状态':<10}")
        print("-" * 90)
        
        for key in ['sharpe_ratio', 'max_drawdown', 'win_rate', 'profit_factor', 'annual_return']:
            if key in details:
                d = details[key]
                print(f"{d.name:<25} {d.score:<8.1f} {d.weight:<8.2f} {d.value:<15.2f} {d.target:<15} {d.status:<10}")
        
        print("\n协同指标 (权重 40%):")
        print(f"{'指标':<25} {'得分':<8} {'权重':<8} {'实际值':<15} {'目标':<15} {'状态':<10}")
        print("-" * 90)
        
        for key in ['sortino_ratio', 'omega_ratio', 'tail_ratio', 'rolling_sharpe_stability',
                     'information_ratio', 'market_correlation', 'trade_frequency', 
                     'max_consecutive_losses', 'avg_holding_period', 'recovery_time']:
            if key in details:
                d = details[key]
                print(f"{d.name:<25} {d.score:<8.1f} {d.weight:<8.2f} {d.value:<15.2f} {d.target:<15} {d.status:<10}")
        
        print("\n" + "="*90)
        
        return total_score, scores, details


# 测试代码
if __name__ == "__main__":
    # 创建测试数据
    np.random.seed(42)
    test_returns = np.random.normal(0.001, 0.02, 252)  # 一年的日收益
    
    test_result = {
        'sharpe_ratio': 1.5,
        'max_drawdown_pct': -5.0,
        'win_rate_pct': 55.0,
        'profit_factor': 1.8,
        'annual_return_pct': 15.0,
        'total_trades': 30,
        'days': 252,
        'returns': test_returns,
        'trades': [{'holding_days': 10} for _ in range(30)]
    }
    
    evaluator = EnhancedFinancialEvaluator()
    evaluator.print_report(test_result)
