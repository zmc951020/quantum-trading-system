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
    
    # ============ 韬定律集群集成方法 ============
    
    def optimize_with_tau_cluster(self, strategy_name: str, strategy_instance: Any,
                                   market_data: Optional[Any] = None) -> Dict[str, Any]:
        """
        使用韬定律优化器集群深度优化策略参数
        
        这是 Aurora 系统与韬定律集群的核心集成点。
        该方法会:
        1. 提取策略的可优化参数
        2. 使用参数空间折叠技术搜索最优参数组合
        3. 通过相似参数缓存避免重复计算
        4. 将优化结果持久化保存到参数存储
        
        Args:
            strategy_name: 策略名称（唯一标识）
            strategy_instance: 策略实例（StrategyBase子类）
            market_data: 市场数据（DataFrame或类似结构，可选）
            
        Returns:
            优化结果字典，包含最佳参数、评分、改进幅度等
        """
        print(f"\n{'='*80}")
        print(f"🔬 韬定律集群优化: {strategy_name}")
        print(f"{'='*80}")
        
        # 延迟导入桥接器（避免循环依赖）
        try:
            from monitor.tau_cluster_bridge import get_tau_bridge
            bridge = get_tau_bridge()
        except ImportError as e:
            print(f"[WARN] 无法加载韬定律集群桥接器: {e}")
            return {
                'success': False,
                'error': f'桥接器加载失败: {e}',
                'message': '请确保韬定律集群模块已正确安装'
            }
        
        # 检查桥接器状态
        status = bridge.get_status_report()
        print(f"⚙️  桥接器状态:")
        print(f"   • 韬定律集群: {'✅ 可用' if status['tau_cluster_available'] else '⚠️ 不可用 (使用简化优化器)'}")
        print(f"   • 参数存储: {'✅ 已连接' if status['param_store_available'] else '⚠️ 未连接'}")
        
        # 获取之前的评分
        previous_score = 0.0
        if status['param_store_available']:
            previous_score = bridge._get_previous_score(strategy_name)
            if previous_score > 0:
                print(f"   • 历史最佳评分: {previous_score:.4f}")
        
        print(f"\n🚀 开始优化...")
        
        # 运行优化
        result = bridge.optimize_strategy(
            strategy_name=strategy_name,
            strategy_instance=strategy_instance,
            market_data=market_data,
            previous_score=previous_score
        )
        
        # 打印结果
        print(f"\n📊 优化结果:")
        if result.success:
            print(f"   ✅ 成功: {result.optimization_method}")
            print(f"   📈 最佳评分: {result.best_score:.4f} (改进: {result.improvement:+.4f})")
            print(f"   ⏱️  优化时间: {result.optimization_time:.2f}秒")
            
            if result.best_params:
                print(f"   ⚙️  最佳参数 ({len(result.best_params)}个):")
                for i, (k, v) in enumerate(list(result.best_params.items())[:10]):
                    print(f"      • {k}: {v:.6f}")
                if len(result.best_params) > 10:
                    print(f"      ... 还有 {len(result.best_params) - 10} 个参数")
            
            print(f"\n📈 回测摘要:")
            print(f"   • 总收益率: {result.total_return*100:.2f}%")
            print(f"   • 夏普比率: {result.sharpe_ratio:.4f}")
            print(f"   • 最大回撤: {result.max_drawdown*100:.2f}%")
            print(f"   • 胜率: {result.win_rate*100:.2f}%")
            print(f"   • 交易次数: {result.total_trades}")
            
            if result.improvement > 0.01:
                print(f"\n🔥 策略性能显著改善 ({result.improvement*100:.1f}%)，建议应用新参数")
            elif result.improvement > 0:
                print(f"\n✅ 策略性能略有改善 ({result.improvement*100:.1f}%)")
            else:
                print(f"\n⚠️  未能找到更好的参数 ({result.improvement*100:.1f}%)，当前参数已近最优")
        else:
            print(f"   ❌ 失败: {result.debug_info.get('error', '未知错误')}")
        
        print(f"\n{'='*80}")
        
        return result.to_dict()
    
    def optimize_all_strategies(self, strategy_manager: Any,
                                 market_data: Optional[Any] = None) -> Dict[str, Any]:
        """
        批量优化策略管理器中的所有策略
        
        Args:
            strategy_manager: StrategyManager实例或包含strategies字典的对象
            market_data: 市场数据（可选）
            
        Returns:
            所有策略的优化结果
        """
        print(f"\n{'═'*80}")
        print(f"🎯 韬定律集群批量优化 - 所有策略")
        print(f"{'═'*80}")
        
        # 延迟导入桥接器
        try:
            from monitor.tau_cluster_bridge import get_tau_bridge
            bridge = get_tau_bridge()
        except ImportError as e:
            return {'success': False, 'error': str(e)}
        
        # 运行批量优化
        results = bridge.optimize_all_strategies(strategy_manager, market_data)
        
        # 生成汇总报告
        total = len(results)
        successful = sum(1 for r in results.values() if r.success)
        improved = sum(1 for r in results.values() if r.improvement > 0.01)
        
        # 按评分排序
        sorted_results = sorted(results.items(), key=lambda x: x[1].best_score, reverse=True)
        
        print(f"\n{'═'*80}")
        print(f"📊 批量优化摘要")
        print(f"{'═'*80}")
        print(f"   总策略数: {total}")
        print(f"   成功优化: {successful}")
        print(f"   显著改善: {improved}")
        
        if sorted_results:
            print(f"\n🏆 排名 (最佳评分):")
            for rank, (name, result) in enumerate(sorted_results[:5], 1):
                icon = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else "  "
                print(f"   {icon} {rank}. {name}: {result.best_score:.4f}")
        
        print(f"{'═'*80}")
        
        return {
            'success': True,
            'total_strategies': total,
            'successful': successful,
            'improved': improved,
            'results': {name: r.to_dict() for name, r in results.items()},
            'ranking': [(name, r.best_score) for name, r in sorted_results]
        }
    
    def apply_tau_optimization(self, strategy_name: str, strategy_instance: Any) -> bool:
        """
        将韬定律优化的最佳参数应用到策略实例
        
        Args:
            strategy_name: 策略名称
            strategy_instance: 策略实例
            
        Returns:
            是否成功应用
        """
        try:
            from monitor.tau_cluster_bridge import get_tau_bridge
            bridge = get_tau_bridge()
            return bridge.apply_optimization(strategy_name, strategy_instance)
        except Exception as e:
            print(f"[WARN] 应用优化参数失败: {e}")
            return False


# ============ 便捷函数 ============

def get_performance_analyzer() -> StrategyPerformanceAnalyzer:
    """获取策略性能分析器实例"""
    return StrategyPerformanceAnalyzer()


def run_tau_optimization(strategy_name: str, strategy_instance: Any,
                         market_data: Optional[Any] = None) -> Dict[str, Any]:
    """
    便捷函数：运行韬定律集群优化
    
    Args:
        strategy_name: 策略名称
        strategy_instance: 策略实例
        market_data: 市场数据（可选）
        
    Returns:
        优化结果字典
    """
    analyzer = StrategyPerformanceAnalyzer()
    return analyzer.optimize_with_tau_cluster(strategy_name, strategy_instance, market_data)


def run_batch_tau_optimization(strategy_manager: Any,
                                market_data: Optional[Any] = None) -> Dict[str, Any]:
    """
    便捷函数：批量运行韬定律集群优化
    
    Args:
        strategy_manager: 策略管理器
        market_data: 市场数据（可选）
        
    Returns:
        批量优化结果
    """
    analyzer = StrategyPerformanceAnalyzer()
    return analyzer.optimize_all_strategies(strategy_manager, market_data)


# ============ 韬定律集群模块检测 ============

def check_tau_cluster_available() -> Dict[str, Any]:
    """
    检测韬定律集群是否可用
    
    Returns:
        检测结果字典
    """
    try:
        from monitor.tau_cluster_bridge import get_tau_bridge
        bridge = get_tau_bridge()
        return {
            'available': True,
            'status': bridge.get_status_report(),
            'message': '韬定律集群桥接器已就绪'
        }
    except Exception as e:
        return {
            'available': False,
            'error': str(e),
            'message': '韬定律集群桥接器不可用，请检查安装'
        }


# ============ 模块初始化 ============

if __name__ == "__main__":
    print("=" * 80)
    print("策略性能分析器与韬定律集群集成 - 自检")
    print("=" * 80)
    
    # 检测韬定律集群
    tau_status = check_tau_cluster_available()
    print(f"\n🔍 韬定律集群检测: {'✅ 可用' if tau_status['available'] else '⚠️ 不可用'}")
    
    if tau_status['available']:
        print(f"   详情: {tau_status['status']}")
    else:
        print(f"   原因: {tau_status.get('error', '未知')}")
    
    # 初始化分析器
    analyzer = StrategyPerformanceAnalyzer()
    print(f"\n✅ 策略性能分析器初始化完成")
    
    print("\n" + "=" * 80)
    print("💡 使用方法:")
    print("   analyzer = StrategyPerformanceAnalyzer()")
    print("   result = analyzer.optimize_with_tau_cluster('策略名', strategy_instance)")
    print("   analyzer.apply_tau_optimization('策略名', strategy_instance)")
    print("=" * 80)
