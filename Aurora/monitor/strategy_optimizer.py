#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略模型效益分析与优化检测模块
提供策略表现评估和优化建议
"""

import numpy as np
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

# 优化优先级
class OptimizationPriority(Enum):
    CRITICAL = "critical"      # 必须立即优化
    HIGH = "high"            # 建议尽快优化
    MEDIUM = "medium"        # 可以稍后优化
    LOW = "low"              # 可选优化

@dataclass
class OptimizationSuggestion:
    """优化建议条目"""
    category: str           # 优化类别
    priority: OptimizationPriority
    description: str       # 问题描述
    suggestion: str      # 优化建议
    estimated_impact: str  # 预期影响
    current_value: Any    # 当前值
    target_value: Any   # 目标值

@dataclass
class StrategyMetrics:
    """策略性能指标"""
    total_return: float        # 总收益率
    win_rate: float          # 胜率
    max_drawdown: float      # 最大回撤
    sharpe_ratio: float     # 夏普比率
    max_position_ratio: float   # 最大资金使用率
    trading_frequency: float # 交易频率（日均交易次数）

class StrategyPerformanceAnalyzer:
    """
    策略模型效益分析器
    评估策略表现并生成优化建议
    """

    def __init__(self):
        self.optimization_suggestions: List[OptimizationSuggestion] = []
        self.performance_history: List[Dict] = []
        self.current_metrics: Optional[StrategyMetrics] = None
        print("[StrategyPerformanceAnalyzer] 策略效益分析器初始化完成")

    def analyze_strategy(self, results: Dict[str, Any]) -> StrategyMetrics:
        """
        分析策略表现并生成性能指标

        Args:
            results: 策略测试结果

        Returns:
            StrategyMetrics 对象
        """
        print("\n📊 策略模型效益分析")
        print("=" * 80)

        # 从结果中提取指标
        total_return = results.get('total_return', 0.0)
        max_drawdown = results.get('max_drawdown', 0.0)
        win_rate = results.get('win_rate', 0.0)
        sharpe_ratio = results.get('sharpe_ratio', 0.0)
        trading_frequency = results.get('trading_frequency', 0.0)

        metrics = StrategyMetrics(
            total_return=total_return,
            win_rate=win_rate,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            max_position_ratio=results.get('max_position_ratio', 0.0),
            trading_frequency=trading_frequency
        )

        self.current_metrics = metrics

        # 打印指标
        print(f"\n📈 策略收益: {total_return*100:.2f}%")
        print(f"📉 最大回撤: {max_drawdown*100:.2f}%")
        print(f"🎯 胜率: {win_rate*100:.2f}%")
        print(f"⚡ 夏普比率: {sharpe_ratio:.2f}")
        print(f"💰 交易频率: {trading_frequency:.2f} 次/天")

        # 检查各项指标
        self.optimization_suggestions = []
        self._check_return(metrics)
        self._check_drawdown(metrics)
        self._check_win_rate(metrics)
        self._check_sharpe(metrics)
        self._check_trading_frequency(metrics)
        self._check_position_usage(metrics)

        return metrics

    def _check_return(self, metrics: StrategyMetrics):
        """检查收益率指标"""
        if metrics.total_return < 0:
            self.optimization_suggestions.append(OptimizationSuggestion(
                category="收益优化",
                priority=OptimizationPriority.HIGH,
                description=f"策略当前收益率为负: {metrics.total_return*100:.2f}%",
                suggestion="建议检查策略逻辑，考虑调整市场类型判断或参数设置",
                estimated_impact="预期可以实现正收益",
                current_value=metrics.total_return,
                target_value="> 0%"
            ))
        elif metrics.total_return < 0.02:  # 2%
            self.optimization_suggestions.append(OptimizationSuggestion(
                category="收益优化",
                priority=OptimizationPriority.MEDIUM,
                description=f"策略收益率较低: {metrics.total_return*100:.2f}%",
                suggestion="考虑优化入场/止损策略，提高交易频率或调整参数",
                estimated_impact="预期收益可以提升3-5%",
                current_value=metrics.total_return,
                target_value="> 2%"
            ))

    def _check_drawdown(self, metrics: StrategyMetrics):
        """检查最大回撤"""
        if metrics.max_drawdown > 0.2:  # 20%
            self.optimization_suggestions.append(OptimizationSuggestion(
                category="风控优化",
                priority=OptimizationPriority.CRITICAL,
                description=f"最大回撤过大: {metrics.max_drawdown*100:.2f}%",
                suggestion="建议收紧止损条件，降低仓位或增加保护机制",
                estimated_impact="预期可以将回撤降至10%以内",
                current_value=metrics.max_drawdown,
                target_value="< 10%"
            ))
        elif metrics.max_drawdown > 0.1:  # 10%
            self.optimization_suggestions.append(OptimizationSuggestion(
                category="风控优化",
                priority=OptimizationPriority.HIGH,
                description=f"最大回撤偏高: {metrics.max_drawdown*100:.2f}%",
                suggestion="建议优化风控参数，考虑增加保护机制",
                estimated_impact="预期可以进一步降低回撤",
                current_value=metrics.max_drawdown,
                target_value="< 8%"
            ))

    def _check_win_rate(self, metrics: StrategyMetrics):
        """检查胜率"""
        if metrics.win_rate < 0.4:  # 40%
            self.optimization_suggestions.append(OptimizationSuggestion(
                category="信号优化",
                priority=OptimizationPriority.HIGH,
                description=f"胜率过低: {metrics.win_rate*100:.2f}%",
                suggestion="建议优化入场信号，提高信号质量检测",
                estimated_impact="预期可以提升至50%以上",
                current_value=metrics.win_rate,
                target_value="> 50%"
            ))
        elif metrics.win_rate < 0.5:  # 50%
            self.optimization_suggestions.append(OptimizationSuggestion(
                category="信号优化",
                priority=OptimizationPriority.MEDIUM,
                description=f"胜率一般: {metrics.win_rate*100:.2f}%",
                suggestion="可以进一步优化入场信号，提高胜率",
                estimated_impact="预期有提升空间",
                current_value=metrics.win_rate,
                target_value="> 55%"
            ))

    def _check_sharpe(self, metrics: StrategyMetrics):
        """检查夏普比率"""
        if metrics.sharpe_ratio < 0.5:
            self.optimization_suggestions.append(OptimizationSuggestion(
                category="风险调整收益优化",
                priority=OptimizationPriority.HIGH,
                description=f"夏普比率过低: {metrics.sharpe_ratio:.2f}",
                suggestion="建议优化风险收益比，提高风险调整后收益",
                estimated_impact="预期夏普比率可以提升至1.0以上",
                current_value=metrics.sharpe_ratio,
                target_value="> 1.0"
            ))

    def _check_trading_frequency(self, metrics: StrategyMetrics):
        """检查交易频率"""
        if metrics.trading_frequency < 0.1:
            self.optimization_suggestions.append(OptimizationSuggestion(
                category="活跃度优化",
                priority=OptimizationPriority.MEDIUM,
                description=f"交易频率过低: {metrics.trading_frequency:.2f} 次/天",
                suggestion="建议增加交易机会，优化参数",
                estimated_impact="预期可以提高交易活跃度",
                current_value=metrics.trading_frequency,
                target_value="> 0.5 次/天"
            ))
        elif metrics.trading_frequency > 2.0:
            self.optimization_suggestions.append(OptimizationSuggestion(
                category="交易成本优化",
                priority=OptimizationPriority.MEDIUM,
                description=f"交易频率过高: {metrics.trading_frequency:.2f} 次/天",
                suggestion="建议减少无效交易，优化交易过滤机制",
                estimated_impact="降低交易成本，提高稳定性",
                current_value=metrics.trading_frequency,
                target_value="< 1.0 次/天"
            ))

    def _check_position_usage(self, metrics: StrategyMetrics):
        """检查资金使用率"""
        if metrics.max_position_ratio < 0.3:
            self.optimization_suggestions.append(OptimizationSuggestion(
                category="资金管理优化",
                priority=OptimizationPriority.MEDIUM,
                description=f"资金使用率偏低: {metrics.max_position_ratio*100:.2f}%",
                suggestion="可以适当提高资金使用",
                estimated_impact="预期提高资金使用效率",
                current_value=metrics.max_position_ratio,
                target_value="> 50%"
            ))

    def get_optimization_report(self) -> Dict[str, Any]:
        """
        生成优化建议报告

        Returns:
            优化建议报告
        """
        print("\n" + "=" * 80)
        print("📋 策略优化项目检测报告")
        print("=" * 80)

        # 按优先级排序建议
        priority_order = {
            OptimizationPriority.CRITICAL: 0,
            OptimizationPriority.HIGH: 1,
            OptimizationPriority.MEDIUM: 2,
            OptimizationPriority.LOW: 3
        }
        sorted_suggestions = sorted(
            self.optimization_suggestions,
            key=lambda x: priority_order[x.priority]
        )

        # 统计
        critical_count = sum(1 for s in self.optimization_suggestions if s.priority == OptimizationPriority.CRITICAL)
        high_count = sum(1 for s in self.optimization_suggestions if s.priority == OptimizationPriority.HIGH)
        medium_count = sum(1 for s in self.optimization_suggestions if s.priority == OptimizationPriority.MEDIUM)
        low_count = sum(1 for s in self.optimization_suggestions if s.priority == OptimizationPriority.LOW)

        print(f"\n📌 待优化项目统计:")
        print(f"   🔴 严重 (必须立即处理): {critical_count}")
        print(f"   🟠 高优先级: {high_count}")
        print(f"   🟡 中优先级: {medium_count}")
        print(f"   🟢 低优先级: {low_count}")

        print(f"\n📝 详细优化建议:")

        idx = 1
        for suggestion in sorted_suggestions:
            priority_icon = {
                OptimizationPriority.CRITICAL: "🔴",
                OptimizationPriority.HIGH: "🟠",
                OptimizationPriority.MEDIUM: "🟡",
                OptimizationPriority.LOW: "🟢"
            }.get(suggestion.priority, "⚪")

            print(f"\n{idx}. {priority_icon} 【{suggestion.category}】")
            print(f"   ⚠️ 问题: {suggestion.description}")
            print(f"   💡 建议: {suggestion.suggestion}")
            print(f"   🎯 目标: {suggestion.target_value}")
            print(f"   📈 预期影响: {suggestion.estimated_impact}")
            print(f"   📊 当前: {suggestion.current_value}")

            idx += 1

        if not self.optimization_suggestions:
            print("\n✅ 策略表现优秀，暂无优化建议！")

        print("\n" + "=" * 80)

        return {
            "metrics": self.current_metrics,
            "suggestions": self.optimization_suggestions,
            "summary": {
                "critical": critical_count,
                "high": high_count,
                "medium": medium_count,
                "low": low_count,
                "total": len(self.optimization_suggestions)
            },
            "overall_assessment": "表现优秀" if not self.optimization_suggestions else "需要优化"
        }
