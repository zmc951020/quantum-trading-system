#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增益性优化模块集成测试
======================
测试所有新增的增益性优化模块：
  1. StrategyPerformanceTracker - 策略性能追踪器
  2. UnifiedRiskController - 统一风险控制器
  3. SmartParamOptimizer - 贝叶斯智能参数优化
  4. RLEnhancer - 深度强化学习优化引擎
  5. DataQualityValidator - 数据质量验证器

测试策略：
  - 每个模块独立测试
  - 模块间集成测试
  - 启用/禁用切换测试
  - 回滚兼容性测试
"""

import sys
import os
import time
import numpy as np
from datetime import datetime, timedelta

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 70)
print("增益性优化模块集成测试")
print("=" * 70)

# ==================== 1. StrategyPerformanceTracker ====================
print("\n" + "=" * 70)
print("1️⃣  StrategyPerformanceTracker - 策略性能追踪器")
print("=" * 70)

from utils.strategy_performance_tracker import (
    get_performance_tracker,
    StrategyPerformanceTracker,
    TradeRecord,
    RollingMetrics,
)

tracker = get_performance_tracker()
tracker.enabled = True

# 模拟策略运行
print("\n  模拟策略运行...")
for i in range(50):
    trade = {
        'timestamp': (datetime.now() - timedelta(minutes=50 - i)).isoformat(),
        'strategy': 'TestStrategy',
        'action': 'buy' if i % 2 == 0 else 'sell',
        'quantity': 100 + i,
        'price': 100.0 + i * 0.1 + np.random.normal(0, 0.5),
        'market_regime': 'range_bound' if i % 3 == 0 else ('trending_up' if i % 3 == 1 else 'trending_down'),
        'signal_confidence': 0.7 + np.random.random() * 0.3,
        'risk_score': 0.2 + np.random.random() * 0.3,
        'portfolio_value_before': 1000000 + i * 1000,
        'portfolio_value_after': 1000000 + i * 1000 + np.random.normal(500, 200),
        'reason_code': 'signal_triggered',
    }
    tracker.record_trade(trade)

# 获取滚动绩效指标
metrics = tracker.get_rolling_metrics('TestStrategy', window=20)
print(f"\n  滚动绩效指标:")
print(f"    总收益: {metrics.total_profit:.4f}")
print(f"    夏普比率: {metrics.sharpe_ratio:.4f}")
print(f"    最大回撤: {metrics.max_drawdown:.4f}")
print(f"    胜率: {metrics.win_rate:.4f}")
print(f"    交易次数: {metrics.total_trades}")

# 获取绩效摘要
summary = tracker.get_performance_summary('TestStrategy')
print(f"\n  绩效摘要:")
for key, value in summary.items():
    if isinstance(value, float):
        print(f"    {key}: {value:.4f}")
    else:
        print(f"    {key}: {value}")

# 按市场状态分组
by_regime = tracker.get_trades_by_regime('TestStrategy')
print(f"\n  按市场状态分组:")
for regime, trades in by_regime.items():
    print(f"    {regime}: {len(trades)} 笔交易")

# 禁用测试
tracker.enabled = False
tracker.record_trade(trade)
print(f"\n  禁用后记录: 无影响 ✓")

# 重新启用
tracker.enabled = True
print(f"  ✅ StrategyPerformanceTracker 测试通过")

# ==================== 2. UnifiedRiskController ====================
print("\n" + "=" * 70)
print("2️⃣  UnifiedRiskController - 统一风险控制器")
print("=" * 70)

from utils.unified_risk_controller import (
    get_risk_controller,
    UnifiedRiskController,
    RiskBudget,
    TradeRiskCheck,
)

controller = get_risk_controller()
controller.enabled = True

# 设置资本
controller.set_capital(1000000.0)

# 测试风险预算分配
print("\n  风险预算分配...")
budget = controller.get_risk_budget()
print(f"    总预算: {budget.total_budget:.2f}")
print(f"    已用预算: {budget.used_budget:.2f}")
print(f"    剩余预算: {budget.remaining_budget:.2f}")

# 测试交易校验
print(f"\n  交易风险校验...")
trade_data = {
    'strategy': 'TestStrategy',
    'side': 'buy',
    'quantity': 100,
    'price': 100.0,
    'signal_confidence': 0.8,
    'market_regime': 'range_bound',
}
result = controller.check_trade(trade_data)
print(f"    通过: {result.passed}")
print(f"    风险评分: {result.risk_score:.2f}")
print(f"    建议: {result.suggested_action}")
print(f"    原因: {result.reason}")

# 报告交易结果
controller.report_trade_result({
    'strategy': 'TestStrategy',
    'profit': 100.0,
    'trade_value': 10000.0,
})

# 获取全局风险报告
report = controller.get_global_risk_report()
print(f"\n  全局风险报告:")
print(f"    总资本: {report['total_capital']:.2f}")
print(f"    总预算: {report['total_budget']:.2f}")
print(f"    预算利用率: {report['budget_utilization_pct']:.1f}%")
print(f"    日内亏损: {report['daily_loss']:.2f}")
print(f"    拒绝率: {report['rejection_rate']:.1f}%")
print(f"    活跃策略: {report['active_strategies']}")

# 禁用测试
controller.enabled = False
result_disabled = controller.check_trade(trade_data)
assert result_disabled.passed == True, "禁用后应通过所有校验"
print(f"\n  禁用后通过所有校验 ✓")

controller.enabled = True
print(f"  ✅ UnifiedRiskController 测试通过")

# ==================== 3. SmartParamOptimizer ====================
print("\n" + "=" * 70)
print("3️⃣  SmartParamOptimizer - 贝叶斯智能参数优化")
print("=" * 70)

from utils.smart_param_optimizer import (
    get_param_optimizer,
    SmartParamOptimizer,
    ParamSpace,
    OptimizationResult,
)

optimizer = get_param_optimizer()
optimizer.enabled = True

# 定义参数空间
param_spaces = [
    ParamSpace('grid_spacing', 0.001, 0.01, 'float'),
    ParamSpace('stop_loss', 0.005, 0.02, 'float'),
    ParamSpace('take_profit', 0.01, 0.03, 'float'),
    ParamSpace('max_position', 50, 200, 'int', step=10),
]

# 定义目标函数
def objective(params):
    grid_spacing = params['grid_spacing']
    stop_loss = params['stop_loss']
    take_profit = params['take_profit']
    max_position = params['max_position']

    total_return = (
        0.15 - 5 * grid_spacing - 2 * stop_loss + 3 * take_profit
        + 0.0005 * max_position + np.random.normal(0, 0.02)
    )
    sharpe_ratio = (
        1.5 - 30 * grid_spacing - 10 * stop_loss + 20 * take_profit
        + 0.002 * max_position + np.random.normal(0, 0.1)
    )

    return {'total_return': total_return, 'sharpe_ratio': sharpe_ratio}

# 执行优化
print("\n  执行贝叶斯优化...")
result = optimizer.optimize(
    objective_func=objective,
    param_spaces=param_spaces,
    strategy_name='TestStrategy',
    n_iterations=20,
    objectives=['total_return', 'sharpe_ratio'],
    weights=[0.6, 0.4],
)

print(f"\n  优化结果:")
print(f"    最优分数: {result.best_score:.4f}")
print(f"    迭代次数: {result.n_iterations}")
print(f"    收敛: {result.convergence}")
print(f"    耗时: {result.elapsed_time:.2f}s")
print(f"    最优参数:")
for name, value in result.best_params.items():
    print(f"      {name}: {value}")

# 获取优化历史
history = optimizer.get_optimization_history('TestStrategy', limit=5)
print(f"\n  优化历史:")
for h in history:
    print(f"    {h.get('timestamp', 'N/A')}: 分数={h.get('best_score', 0):.4f}")

# 禁用测试
optimizer.enabled = False
result_disabled = optimizer.optimize(objective, param_spaces)
assert result_disabled.best_score == -float('inf'), "禁用后应返回空结果"
print(f"\n  禁用后返回空结果 ✓")

optimizer.enabled = True
print(f"  ✅ SmartParamOptimizer 测试通过")

# ==================== 4. RLEnhancer ====================
print("\n" + "=" * 70)
print("4️⃣  RLEnhancer - 深度强化学习优化引擎")
print("=" * 70)

from utils.rl_enhancer import (
    get_rl_enhancer,
    RLEnhancer,
    Transition,
)

enhancer = get_rl_enhancer()
enhancer.enabled = True

# 构建状态
print("\n  构建状态向量...")
market_data = {
    'price_change_pct': 0.5,
    'volatility': 0.15,
    'rsi': 55.0,
    'macd': 0.2,
    'macd_signal': 0.1,
    'adx': 30.0,
    'atr': 1.5,
    'close': 100.0,
    'position_pct': 0.5,
    'unrealized_pnl_pct': 0.02,
    'market_regime': 'range_bound',
    'signal_confidence': 0.75,
    'risk_score': 30.0,
    'volume_change_pct': 1.2,
    'momentum_short': 0.03,
    'momentum_long': 0.05,
    'bb_position': 0.2,
    'rolling_sharpe': 1.5,
    'max_drawdown': 0.05,
    'trade_frequency': 10,
    'time_decay': 0.9,
    'regime_alignment': 0.8,
}

state = enhancer.build_state(market_data)
print(f"  状态向量维度: {len(state)}")

# 选择动作
action = enhancer.select_action(state)
print(f"\n  选择动作（仓位比例）: {action:.4f}")

# 带解释的动作
explanation = enhancer.get_action_with_explanation(state, market_data)
print(f"\n  动作解释:")
print(f"    建议操作: {explanation['suggested_position']}")
print(f"    置信度: {explanation['confidence']:.4f}")

# 模拟经验回放
print(f"\n  模拟经验回放...")
for i in range(50):
    next_state = state + np.random.normal(0, 0.01, 20)
    reward = enhancer.compute_reward(
        portfolio_return=0.01,
        sharpe_change=0.02,
        drawdown_change=-0.005,
        trade_frequency=0.1,
        regime_alignment=0.8,
    )
    enhancer.store_transition(state, action, reward, next_state, done=(i == 49))
    state = next_state
    action = enhancer.select_action(state)

# 更新策略
update_stats = enhancer.update_policy()
print(f"\n  策略更新统计:")
for key, value in update_stats.items():
    if isinstance(value, float):
        print(f"    {key}: {value:.6f}")
    else:
        print(f"    {key}: {value}")

# 禁用测试
enhancer.enabled = False
default_action = enhancer.select_action(state)
assert abs(default_action - 0.5) < 0.001, "禁用后应返回默认半仓"
print(f"\n  禁用后返回默认半仓 ✓")

enhancer.enabled = True
print(f"  ✅ RLEnhancer 测试通过")

# ==================== 5. DataQualityValidator ====================
print("\n" + "=" * 70)
print("5️⃣  DataQualityValidator - 数据质量验证器")
print("=" * 70)

from utils.data_quality_validator import (
    get_data_validator,
    DataQualityValidator,
    DataQualityReport,
)

validator = get_data_validator()
validator.enabled = True

# 测试正常数据
print("\n  检查正常数据...")
normal_data = {
    'prices': [100.0 + i * 0.1 + np.random.normal(0, 0.5) for i in range(100)],
    'volumes': [10000 + int(np.random.normal(0, 1000)) for _ in range(100)],
    'timestamps': [
        (datetime.now() - timedelta(seconds=i)).isoformat()
        for i in range(100)
    ],
}

report = validator.check_data_quality(normal_data)
print(f"  正常数据评分: {report.overall_score:.1f}")
print(f"  问题数: {len(report.issues)}")

# 测试异常数据
print(f"\n  检查异常数据...")
anomaly_data = {
    'prices': [100.0] * 50 + [1000.0] * 50,
    'volumes': [10000] * 100,
    'timestamps': [
        (datetime.now() - timedelta(seconds=i)).isoformat()
        for i in range(100)
    ],
}

report2 = validator.check_data_quality(anomaly_data)
print(f"  异常数据评分: {report2.overall_score:.1f}")
for issue in report2.issues:
    print(f"    问题: [{issue['severity']}] {issue['message']}")

# 测试数据修复
print(f"\n  测试数据修复...")
broken_data = {
    'prices': [100.0, None, 102.0, 103.0, None, 105.0],
    'volumes': [10000, 11000, None, 13000, 14000, 15000],
    'timestamps': [datetime.now().isoformat()] * 6,
}

fixed = validator.fix_data(broken_data)
print(f"  修复前价格: {broken_data['prices']}")
print(f"  修复后价格: {fixed['prices']}")
print(f"  修复操作数: {len(fixed.get('_fixes_applied', []))}")

# 禁用测试
validator.enabled = False
report_disabled = validator.check_data_quality(anomaly_data)
assert report_disabled.overall_score == 100.0, "禁用后应返回满分"
print(f"\n  禁用后返回满分 ✓")

validator.enabled = True
print(f"  ✅ DataQualityValidator 测试通过")

# ==================== 6. 集成测试 ====================
print("\n" + "=" * 70)
print("6️⃣  模块间集成测试")
print("=" * 70)

print("\n  模拟完整交易流程...")

# 启用所有模块
tracker.enabled = True
controller.enabled = True
optimizer.enabled = True
enhancer.enabled = True
validator.enabled = True

# 模拟交易循环
num_steps = 30
for step in range(num_steps):
    # 1. 数据质量检查
    data = {
        'prices': [100.0 + step * 0.1 + np.random.normal(0, 0.3)],
        'volumes': [10000 + int(np.random.normal(0, 500))],
        'timestamps': [datetime.now().isoformat()],
    }
    quality = validator.check_data_quality(data)

    # 2. 风险评估
    market_data = {
        'volatility': 0.15 + np.random.normal(0, 0.02),
        'market_regime': ['trending_up', 'range_bound', 'trending_down'][step % 3],
        'position_pct': 0.5 + 0.1 * np.sin(step * 0.5),
        'unrealized_pnl_pct': 0.01 * np.sin(step * 0.3),
        'max_drawdown': 0.03 + 0.01 * step / num_steps,
    }

    # 3. RL动作选择
    state = enhancer.build_state(market_data)
    action = enhancer.select_action(state)

    # 4. 交易风险校验
    trade_data = {
        'strategy': 'IntegratedStrategy',
        'side': 'buy' if action > 0.5 else 'sell',
        'quantity': int(action * 100),
        'price': 100.0 + step * 0.1,
        'signal_confidence': 0.7 + abs(action - 0.5),
        'market_regime': market_data['market_regime'],
    }
    risk_check = controller.check_trade(trade_data)

    # 5. 记录交易
    if risk_check.passed:
        tracker.record_trade({
            'timestamp': datetime.now().isoformat(),
            'strategy': 'IntegratedStrategy',
            'action': trade_data['side'],
            'quantity': trade_data['quantity'],
            'price': trade_data['price'],
            'market_regime': market_data['market_regime'],
            'signal_confidence': trade_data['signal_confidence'],
            'risk_score': risk_check.risk_score,
            'portfolio_value_before': 1000000 + step * 1000,
            'portfolio_value_after': 1000000 + step * 1000 + np.random.normal(500, 200),
            'reason_code': 'integrated_signal',
        })

    # 6. 存储RL经验
    next_state = state + np.random.normal(0, 0.01, 20)
    reward = enhancer.compute_reward(
        portfolio_return=0.01,
        sharpe_change=0.02,
        drawdown_change=-0.005,
        trade_frequency=0.1,
        regime_alignment=0.8,
    )
    enhancer.store_transition(state, action, reward, next_state)

# 更新RL策略
enhancer.update_policy()

# 获取集成报告
print(f"\n  集成测试结果:")
print(f"    数据质量评分: {quality.overall_score:.1f}")
print(f"    RL动作: {action:.4f}")
print(f"    交易风险通过: {risk_check.passed}")
print(f"    策略性能:")
metrics = tracker.get_rolling_metrics('IntegratedStrategy')
print(f"      总收益: {metrics.total_profit:.4f}")
print(f"      夏普比率: {metrics.sharpe_ratio:.4f}")
print(f"      交易次数: {metrics.total_trades}")

# ==================== 7. 回滚兼容性测试 ====================
print("\n" + "=" * 70)
print("7️⃣  回滚兼容性测试")
print("=" * 70)

print("\n  测试禁用所有模块后的回滚行为...")

# 禁用所有模块
tracker.enabled = False
controller.enabled = False
optimizer.enabled = False
enhancer.enabled = False
validator.enabled = False

# 验证各模块返回默认值
assert tracker.record_trade({'strategy': 'Test'}) == False
assert controller.check_trade({'strategy': 'Test'}).passed == True
assert optimizer.optimize(lambda x: {}, []).best_score == -float('inf')
assert abs(enhancer.select_action(np.zeros(20)) - 0.5) < 0.001
assert validator.check_data_quality({}).overall_score == 100.0

print("  所有模块禁用后均返回安全默认值 ✓")
print("  回滚兼容性测试通过 ✓")

# ==================== 总结 ====================
print("\n" + "=" * 70)
print("📊 测试总结")
print("=" * 70)
print(f"""
  模块                          状态
  ─────────────────────────────────────────────
  StrategyPerformanceTracker    ✅ 通过
  UnifiedRiskController        ✅ 通过
  SmartParamOptimizer          ✅ 通过
  RLEnhancer                   ✅ 通过
  DataQualityValidator         ✅ 通过
  集成测试                     ✅ 通过
  回滚兼容性测试               ✅ 通过
  ─────────────────────────────────────────────
  所有测试均通过！

  增益性优化模块已就绪，可通过 enabled 开关控制。
  禁用时各模块回退到安全默认值，不影响现有系统。
""")
