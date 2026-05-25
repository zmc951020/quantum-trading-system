#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UnifiedRiskController — 统一风险预算管理
========================================
增益性优化模块，不修改现有策略代码，通过依赖注入提供全局风险聚合能力。

设计目标：
  1. 全局风险预算分配（按策略历史夏普比率加权）
  2. 策略内风险分配（按信号置信度加权）
  3. 逐笔风险校验（单笔 ≤ 总预算 × 1%）
  4. 多策略并行时总敞口可控

使用方式：
  controller = UnifiedRiskController()
  controller.enabled = True
  controller.set_capital(100000.0)
  risk_budget = controller.get_strategy_budget('FinalMarketAdaptive')
  is_safe = controller.check_trade(trade_data)

回滚方式：
  controller.enabled = False  # 各策略回退到自有风控逻辑
"""

import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


@dataclass
class RiskBudget:
    """风险预算"""
    total_budget: float = 0.0
    used_budget: float = 0.0
    remaining_budget: float = 0.0
    strategy_allocations: Dict[str, float] = field(default_factory=dict)
    strategy_usage: Dict[str, float] = field(default_factory=dict)


@dataclass
class TradeRiskCheck:
    """交易风险校验结果"""
    passed: bool = True
    risk_score: float = 0.0
    reason: str = ""
    suggested_action: str = "proceed"  # proceed / reduce / reject


class UnifiedRiskController:
    """
    统一风险预算管理器

    单例模式，全局唯一实例，默认关闭。
    提供全局风险预算分配、逐笔风险校验、多策略风险聚合功能。
    """

    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self.enabled = False

        # 风险配置
        self.config = {
            'max_total_exposure_pct': 0.15,      # 总风险暴露 ≤ 总资本 × 15%
            'max_single_strategy_pct': 0.40,     # 单策略VaR贡献度 ≤ 总VaR × 40%
            'max_single_trade_pct': 0.005,       # 单笔风险价值 ≤ 总资本 × 0.5%
            'max_daily_loss_pct': 0.02,          # 日内最大亏损 ≤ 总资本 × 2%
            'max_leverage': 1.0,                 # 最大杠杆
            'var_confidence': 0.95,              # VaR置信度
            'volatility_target': 0.20,           # 目标年化波动率
        }

        # 资本信息
        self._total_capital = 0.0
        self._daily_loss = 0.0
        self._daily_trade_count = 0
        self._reset_day = datetime.now().date()

        # 策略风险记录
        self._strategy_risk: Dict[str, Dict] = defaultdict(lambda: {
            'var_contribution': 0.0,
            'current_exposure': 0.0,
            'daily_pnl': 0.0,
            'trade_count': 0,
            'sharpe_ratio': 0.0,
            'volatility': 0.0,
            'max_drawdown': 0.0,
        })

        # 市场状态中心（延迟加载）
        self._market_hub = None

        # 统计
        self._total_checks = 0
        self._total_rejections = 0

        logger.info("[UnifiedRiskController] 初始化完成，默认关闭")

    @property
    def market_hub(self):
        """延迟加载市场状态中心"""
        if self._market_hub is None:
            try:
                from signals.market_state_hub import MarketStateHub
                self._market_hub = MarketStateHub()
            except Exception as e:
                logger.warning(f"[UnifiedRiskController] MarketStateHub 加载失败: {e}")
        return self._market_hub

    # ==================== 核心接口 ====================

    def set_capital(self, capital: float):
        """
        设置总资本

        Args:
            capital: 总资本金额
        """
        self._total_capital = capital
        logger.info(f"[UnifiedRiskController] 总资本设置为: {capital:.2f}")

    def get_capital(self) -> float:
        """获取总资本"""
        return self._total_capital

    def register_strategy(self, strategy_name: str,
                         sharpe_ratio: float = 0.0,
                         volatility: float = 0.0):
        """
        注册策略到风险管理系统

        Args:
            strategy_name: 策略名称
            sharpe_ratio: 历史夏普比率
            volatility: 历史波动率
        """
        self._strategy_risk[strategy_name]['sharpe_ratio'] = sharpe_ratio
        self._strategy_risk[strategy_name]['volatility'] = volatility
        logger.info(f"[UnifiedRiskController] 策略 {strategy_name} 已注册")

    def update_strategy_risk(self, strategy_name: str,
                            current_exposure: float = None,
                            daily_pnl: float = None,
                            var_contribution: float = None):
        """
        更新策略风险状态

        Args:
            strategy_name: 策略名称
            current_exposure: 当前风险暴露
            daily_pnl: 当日盈亏
            var_contribution: VaR贡献度
        """
        if strategy_name not in self._strategy_risk:
            self.register_strategy(strategy_name)

        record = self._strategy_risk[strategy_name]
        if current_exposure is not None:
            record['current_exposure'] = current_exposure
        if daily_pnl is not None:
            record['daily_pnl'] += daily_pnl
        if var_contribution is not None:
            record['var_contribution'] = var_contribution

    def get_risk_budget(self) -> RiskBudget:
        """
        获取当前风险预算状态

        Returns:
            风险预算对象
        """
        budget = RiskBudget()

        if not self.enabled or self._total_capital <= 0:
            return budget

        # 总风险预算 = 总资本 × 目标波动率 × VaR乘数
        var_multiplier = {
            0.95: 1.65,
            0.99: 2.33,
        }.get(self.config['var_confidence'], 1.65)

        budget.total_budget = (
            self._total_capital *
            self.config['volatility_target'] *
            var_multiplier
        )

        # 按策略历史夏普比率加权分配
        total_sharpe = sum(
            s['sharpe_ratio'] for s in self._strategy_risk.values()
        )

        if total_sharpe > 0:
            for name, record in self._strategy_risk.items():
                weight = record['sharpe_ratio'] / total_sharpe
                allocation = budget.total_budget * weight

                # 限制单策略最大分配
                max_allocation = budget.total_budget * self.config['max_single_strategy_pct']
                allocation = min(allocation, max_allocation)

                budget.strategy_allocations[name] = allocation
                budget.strategy_usage[name] = record['current_exposure']

        budget.used_budget = sum(
            s['current_exposure'] for s in self._strategy_risk.values()
        )
        budget.remaining_budget = budget.total_budget - budget.used_budget

        return budget

    def check_trade(self, trade_data: Dict[str, Any]) -> TradeRiskCheck:
        """
        校验一笔交易是否在风险预算内

        Args:
            trade_data: 交易数据字典，包含:
                - strategy: 策略名称
                - quantity: 数量
                - price: 价格
                - side: 方向 ('buy'/'sell')
                - portfolio_value: 当前组合价值（可选）

        Returns:
            风险校验结果
        """
        self._total_checks += 1

        if not self.enabled:
            return TradeRiskCheck()

        # 每日重置
        self._check_daily_reset()

        strategy = trade_data.get('strategy', 'unknown')
        quantity = trade_data.get('quantity', 0)
        price = trade_data.get('price', 0)
        side = trade_data.get('side', 'buy')
        portfolio_value = trade_data.get('portfolio_value', self._total_capital)

        # 计算交易价值
        trade_value = quantity * price

        # 校验1: 单笔风险价值
        max_single_trade = self._total_capital * self.config['max_single_trade_pct']
        if trade_value > max_single_trade:
            self._total_rejections += 1
            return TradeRiskCheck(
                passed=False,
                risk_score=min(trade_value / max_single_trade, 10.0),
                reason=f"单笔交易价值 {trade_value:.2f} 超过限制 {max_single_trade:.2f}",
                suggested_action="reject"
            )

        # 校验2: 日内最大亏损
        if self._daily_loss < -self._total_capital * self.config['max_daily_loss_pct']:
            self._total_rejections += 1
            return TradeRiskCheck(
                passed=False,
                risk_score=9.0,
                reason=f"日内亏损 {self._daily_loss:.2f} 超过限制",
                suggested_action="reject"
            )

        # 校验3: 策略风险暴露
        if strategy in self._strategy_risk:
            record = self._strategy_risk[strategy]
            budget = self.get_risk_budget()

            strategy_budget = budget.strategy_allocations.get(strategy, 0)
            new_exposure = record['current_exposure'] + trade_value

            if strategy_budget > 0 and new_exposure > strategy_budget:
                # 计算超出的比例
                overage_ratio = new_exposure / strategy_budget
                if overage_ratio > 1.2:  # 超过20%则拒绝
                    self._total_rejections += 1
                    return TradeRiskCheck(
                        passed=False,
                        risk_score=min(overage_ratio, 10.0),
                        reason=f"策略 {strategy} 风险暴露 {new_exposure:.2f} 超过预算 {strategy_budget:.2f}",
                        suggested_action="reject"
                    )
                elif overage_ratio > 1.0:  # 超过预算但未超20%，建议减少
                    return TradeRiskCheck(
                        passed=True,
                        risk_score=overage_ratio * 5,
                        reason=f"策略 {strategy} 风险暴露接近预算上限",
                        suggested_action="reduce"
                    )

        # 校验4: 全局风险暴露
        total_exposure = sum(
            s['current_exposure'] for s in self._strategy_risk.values()
        )
        max_exposure = self._total_capital * self.config['max_total_exposure_pct']
        if total_exposure + trade_value > max_exposure:
            self._total_rejections += 1
            return TradeRiskCheck(
                passed=False,
                risk_score=8.0,
                reason=f"全局风险暴露 {total_exposure + trade_value:.2f} 超过限制 {max_exposure:.2f}",
                suggested_action="reject"
            )

        # 校验5: 市场状态感知（如果可用）
        if self.market_hub and self.market_hub.enabled:
            try:
                market_state = self.market_hub.get_market_regime({})
                if market_state and hasattr(market_state, 'regime'):
                    regime = market_state.regime.value if hasattr(market_state.regime, 'value') else str(market_state.regime)
                    if regime == 'trending_down' and side == 'buy':
                        # 下跌市中买入，提高风险评分
                        return TradeRiskCheck(
                            passed=True,
                            risk_score=6.0,
                            reason=f"下跌市中买入操作，建议谨慎",
                            suggested_action="reduce"
                        )
            except Exception as e:
                logger.debug(f"[UnifiedRiskController] 市场状态检查失败: {e}")

        # 更新日内交易计数
        self._daily_trade_count += 1

        return TradeRiskCheck(
            passed=True,
            risk_score=0.0,
            reason="风险校验通过",
            suggested_action="proceed"
        )

    def report_trade_result(self, trade_data: Dict[str, Any]):
        """
        报告交易结果，更新风险状态

        Args:
            trade_data: 交易结果数据，包含:
                - strategy: 策略名称
                - profit: 盈亏金额
                - trade_value: 交易价值
        """
        if not self.enabled:
            return

        strategy = trade_data.get('strategy', 'unknown')
        profit = trade_data.get('profit', 0)
        trade_value = trade_data.get('trade_value', 0)

        if strategy in self._strategy_risk:
            record = self._strategy_risk[strategy]
            record['daily_pnl'] += profit
            record['current_exposure'] += trade_value
            record['trade_count'] += 1

        self._daily_loss += profit

    def check_strategy_risk(self, strategy_name: str, params: Dict) -> Dict:
        """
        校验策略风险（供 ValidationPipeline 调用）

        Args:
            strategy_name: 策略名称
            params: 策略参数

        Returns:
            风险校验结果字典，包含:
                - global_exposure: 全局风险暴露比例
                - single_trade_risk: 单笔交易风险比例
                - max_daily_loss: 日内最大亏损比例
                - passed: 是否通过
                - details: 详细风险信息
        """
        if strategy_name not in self._strategy_risk:
            self.register_strategy(strategy_name)

        record = self._strategy_risk[strategy_name]
        budget = self.get_risk_budget()

        # 计算全局风险暴露比例
        total_exposure = sum(
            s['current_exposure'] for s in self._strategy_risk.values()
        )
        global_exposure = total_exposure / max(self._total_capital, 1)

        # 计算单笔交易风险比例（基于参数中的仓位比例）
        position_pct = params.get('max_position', params.get('position_pct', 0.1))
        single_trade_risk = position_pct * 0.1  # 假设10%的止损

        # 日内最大亏损比例
        max_daily_loss = abs(self._daily_loss) / max(self._total_capital, 1)

        # 风险检查
        checks = {
            'global_exposure': global_exposure <= self.config['max_total_exposure_pct'],
            'single_trade_risk': single_trade_risk <= self.config['max_single_trade_pct'],
            'max_daily_loss': max_daily_loss <= self.config['max_daily_loss_pct'],
        }
        passed = all(checks.values())

        return {
            'global_exposure': global_exposure,
            'single_trade_risk': single_trade_risk,
            'max_daily_loss': max_daily_loss,
            'passed': passed,
            'checks': checks,
            'details': {
                'strategy': strategy_name,
                'current_exposure': record['current_exposure'],
                'daily_pnl': record['daily_pnl'],
                'trade_count': record['trade_count'],
                'var_contribution': record['var_contribution'],
                'budget_allocation': budget.strategy_allocations.get(strategy_name, 0),
                'budget_usage': budget.strategy_usage.get(strategy_name, 0),
                'sharpe_ratio': record['sharpe_ratio'],
                'volatility': record['volatility'],
            }
        }

    def get_strategy_risk_report(self, strategy_name: str) -> Dict:
        """
        获取策略风险报告

        Args:
            strategy_name: 策略名称

        Returns:
            风险报告字典
        """
        record = self._strategy_risk.get(strategy_name, {})
        if not record:
            return {}

        budget = self.get_risk_budget()
        allocation = budget.strategy_allocations.get(strategy_name, 0)
        usage = budget.strategy_usage.get(strategy_name, 0)

        return {
            'strategy': strategy_name,
            'current_exposure': record['current_exposure'],
            'daily_pnl': record['daily_pnl'],
            'trade_count': record['trade_count'],
            'var_contribution': record['var_contribution'],
            'budget_allocation': allocation,
            'budget_usage': usage,
            'budget_utilization_pct': (usage / allocation * 100) if allocation > 0 else 0,
            'sharpe_ratio': record['sharpe_ratio'],
            'volatility': record['volatility'],
        }

    def get_global_risk_report(self) -> Dict:
        """
        获取全局风险报告

        Returns:
            全局风险报告字典
        """
        budget = self.get_risk_budget()

        return {
            'enabled': self.enabled,
            'total_capital': self._total_capital,
            'total_budget': budget.total_budget,
            'used_budget': budget.used_budget,
            'remaining_budget': budget.remaining_budget,
            'budget_utilization_pct': (
                (budget.used_budget / budget.total_budget * 100)
                if budget.total_budget > 0 else 0
            ),
            'daily_loss': self._daily_loss,
            'daily_loss_pct': (
                (self._daily_loss / self._total_capital * 100)
                if self._total_capital > 0 else 0
            ),
            'daily_trade_count': self._daily_trade_count,
            'total_checks': self._total_checks,
            'total_rejections': self._total_rejections,
            'rejection_rate': (
                (self._total_rejections / self._total_checks * 100)
                if self._total_checks > 0 else 0
            ),
            'active_strategies': list(self._strategy_risk.keys()),
            'config': self.config.copy(),
        }

    def reset_daily(self):
        """重置每日统计"""
        self._daily_loss = 0.0
        self._daily_trade_count = 0
        self._reset_day = datetime.now().date()

        for record in self._strategy_risk.values():
            record['daily_pnl'] = 0.0
            record['trade_count'] = 0

        logger.info("[UnifiedRiskController] 每日风险统计已重置")

    # ==================== 内部方法 ====================

    def _check_daily_reset(self):
        """检查是否需要每日重置"""
        today = datetime.now().date()
        if today != self._reset_day:
            self.reset_daily()


# ==================== 全局单例 ====================

_global_controller = None


def get_risk_controller() -> UnifiedRiskController:
    """获取全局风险控制器实例"""
    global _global_controller
    if _global_controller is None:
        _global_controller = UnifiedRiskController()
    return _global_controller


# ==================== 便捷函数 ====================

def check_trade(trade_data: Dict[str, Any]) -> TradeRiskCheck:
    """便捷函数：校验交易风险"""
    controller = get_risk_controller()
    return controller.check_trade(trade_data)


def get_risk_report() -> Dict:
    """便捷函数：获取全局风险报告"""
    controller = get_risk_controller()
    return controller.get_global_risk_report()


# ==================== 自测 ====================

if __name__ == '__main__':
    controller = get_risk_controller()
    controller.enabled = True
    controller.set_capital(100000.0)

    print("=" * 60)
    print("UnifiedRiskController 自测")
    print("=" * 60)

    # 注册策略
    controller.register_strategy('StrategyA', sharpe_ratio=1.5, volatility=0.25)
    controller.register_strategy('StrategyB', sharpe_ratio=0.8, volatility=0.35)

    # 获取风险预算
    budget = controller.get_risk_budget()
    print(f"\n风险预算:")
    print(f"  总预算: {budget.total_budget:.2f}")
    print(f"  已使用: {budget.used_budget:.2f}")
    print(f"  剩余: {budget.remaining_budget:.2f}")
    for name, alloc in budget.strategy_allocations.items():
        print(f"  {name}: {alloc:.2f}")

    # 测试交易校验
    test_trades = [
        {'strategy': 'StrategyA', 'quantity': 100, 'price': 50.0, 'side': 'buy'},
        {'strategy': 'StrategyA', 'quantity': 1000, 'price': 100.0, 'side': 'buy'},
        {'strategy': 'StrategyB', 'quantity': 50, 'price': 30.0, 'side': 'sell'},
    ]

    for i, trade in enumerate(test_trades):
        result = controller.check_trade(trade)
        print(f"\n交易 {i+1}: {trade['strategy']} {trade['side']} {trade['quantity']}@{trade['price']}")
        print(f"  通过: {result.passed}")
        print(f"  风险评分: {result.risk_score:.2f}")
        print(f"  建议: {result.suggested_action}")
        print(f"  原因: {result.reason}")

        # 报告交易结果
        controller.report_trade_result({
            'strategy': trade['strategy'],
            'profit': 100.0 if result.passed else 0,
            'trade_value': trade['quantity'] * trade['price'],
        })

    # 全局风险报告
    report = controller.get_global_risk_report()
    print(f"\n全局风险报告:")
    print(f"  总资本: {report['total_capital']:.2f}")
    print(f"  总预算: {report['total_budget']:.2f}")
    print(f"  预算利用率: {report['budget_utilization_pct']:.1f}%")
    print(f"  日内亏损: {report['daily_loss']:.2f}")
    print(f"  拒绝率: {report['rejection_rate']:.1f}%")
    print(f"  活跃策略: {report['active_strategies']}")

    print("\n✅ UnifiedRiskController 自测完成！")
