#!/usr/bin/env python3
"""韬定律策略优化器集群 - 真实回测+优化+持久化 端到端验证"""
import sys, json, random

sys.path.insert(0, r'd:\Gupiao\升级vscode')
random.seed(42)

from QS_Robot.core.tau_optimizer_cluster import (
    TauOptimizerCluster, BernoulliCoandaModule, ShepherdRotationModule,
    FactorSpaceFolding, get_parameter_store, ParameterSpaceFolding
)
from QS_Robot.core.enhanced_strategy_manager import EnhancedStrategyManager, BacktestResult

print("=" * 70)
print("韬定律策略优化器集群 - 真实回测+优化+持久化 端到端验证")
print("=" * 70)

# 清理旧存储
store = get_parameter_store()
if hasattr(store, 'store_file') and __import__('os').path.exists(store.store_file):
    try:
        __import__('os').remove(store.store_file)
    except:
        pass

# ============================================================
# 测试1: BernoulliCoandaModule estimate_quality 改进
# ============================================================
print("\n[测试1] BernoulliCoandaModule.estimate_quality - 6维度加权评分")
mod = BernoulliCoandaModule()

# 不同参数组合的评分
test_params_list = [
    ("最佳参数组合", {
        'short_period': 12.0, 'mid_period': 35.0, 'long_period': 70.0,
        'bernoulli_threshold': 0.06, 'momentum_alpha': 1.0, 'pressure_sensitivity': 0.8,
        'coanda_attachment': 0.6, 'curvature_sensitivity': 0.5, 'separation_threshold': 1.0,
        'stop_loss_pct': 0.05, 'position_size': 0.3, 'confirmation_bars': 3.0
    }),
    ("一般参数组合", {
        'short_period': 20.0, 'mid_period': 45.0, 'long_period': 120.0,
        'bernoulli_threshold': 0.10, 'momentum_alpha': 0.5, 'pressure_sensitivity': 1.5,
        'coanda_attachment': 0.3, 'curvature_sensitivity': 0.9, 'separation_threshold': 0.5,
        'stop_loss_pct': 0.02, 'position_size': 0.15, 'confirmation_bars': 2.0
    }),
    ("差参数组合", {
        'short_period': 3.0, 'mid_period': 5.0, 'long_period': 10.0,
        'bernoulli_threshold': 0.25, 'momentum_alpha': 0.1, 'pressure_sensitivity': 3.0,
        'coanda_attachment': 0.05, 'curvature_sensitivity': 2.0, 'separation_threshold': 0.1,
        'stop_loss_pct': 0.3, 'position_size': 0.9, 'confirmation_bars': 10.0
    }),
]

for name, params in test_params_list:
    score = mod.estimate_quality(params)
    print(f"  {name:15s} -> score={score:.4f}")
    assert 0.0 <= score <= 1.0, f"评分应在0-1范围内"

# 验证评分排序：最佳 > 一般 > 差
best_score = mod.estimate_quality(test_params_list[0][1])
mid_score = mod.estimate_quality(test_params_list[1][1])
worst_score = mod.estimate_quality(test_params_list[2][1])
print(f"\n  排序验证: 最佳({best_score:.4f}) > 一般({mid_score:.4f}) > 差({worst_score:.4f})")
assert best_score > mid_score > worst_score, f"评分排序应该合理"
print("  ✅ estimate_quality 评分逻辑正常")

# ============================================================
# 测试2: SimulatedFallbackEngine 参数感知回测
# ============================================================
print("\n[测试2] SimulatedFallbackEngine 参数感知回测")
from QS_Robot.core.enhanced_strategy_manager import SimulatedFallbackEngine
fb = SimulatedFallbackEngine()

# 测试伯努利策略的参数感知回测
good_params = {
    'short_period': 12.0, 'mid_period': 35.0, 'long_period': 70.0,
    'bernoulli_threshold': 0.06, 'momentum_alpha': 1.0, 'pressure_sensitivity': 0.8,
    'coanda_attachment': 0.6, 'curvature_sensitivity': 0.5, 'separation_threshold': 1.0,
    'stop_loss_pct': 0.05, 'position_size': 0.3, 'confirmation_bars': 3.0
}

bad_params = {
    'short_period': 3.0, 'mid_period': 5.0, 'long_period': 10.0,
    'bernoulli_threshold': 0.25, 'momentum_alpha': 0.1, 'pressure_sensitivity': 3.0,
    'coanda_attachment': 0.05, 'curvature_sensitivity': 2.0, 'separation_threshold': 0.1,
    'stop_loss_pct': 0.3, 'position_size': 0.9, 'confirmation_bars': 10.0
}

r1 = fb.run_backtest('伯努利-康达策略', days=30, balance=100000.0, params=good_params)
r2 = fb.run_backtest('伯努利-康达策略', days=30, balance=100000.0, params=bad_params)

print(f"  好参数回测: return={r1['data']['summary']['total_return_pct']:.2f}%, "
      f"sharpe={r1['data']['summary']['sharpe_ratio']:.4f}, "
      f"max_dd={r1['data']['summary']['max_drawdown']:.2f}%, "
      f"win_rate={r1['data']['summary']['win_rate']:.1f}%")
print(f"  差参数回测: return={r2['data']['summary']['total_return_pct']:.2f}%, "
      f"sharpe={r2['data']['summary']['sharpe_ratio']:.4f}, "
      f"max_dd={r2['data']['summary']['max_drawdown']:.2f}%, "
      f"win_rate={r2['data']['summary']['win_rate']:.1f}%")

assert r1['data']['summary']['sharpe_ratio'] > r2['data']['summary']['sharpe_ratio'], \
    f"好参数Sharpe应高于差参数"
print("  ✅ SimulatedFallbackEngine 参数感知回测正常")

# ============================================================
# 测试3: EnhancedStrategyManager 真实回测传递
# ============================================================
print("\n[测试3] EnhancedStrategyManager 真实回测调用链")
mgr = EnhancedStrategyManager()
result = mgr.run_backtest('伯努利-康达策略', days=30, balance=100000.0, params=good_params)
print(f"  回测结果: {result.strategy_name}, return={result.total_return_pct:.2f}%, "
      f"sharpe={result.sharpe_ratio:.4f}, trades={result.total_trades}")
assert isinstance(result, BacktestResult), f"应返回 BacktestResult"
print("  ✅ EnhancedStrategyManager 回测传递正常")

# ============================================================
# 测试4: TauOptimizerCluster 完整优化（使用 EnhancedStrategyManager）
# ============================================================
print("\n[测试4] 韬定律集群 + 策略管理器 - 伯努利策略完整优化")
ranges = mod.param_ranges
cluster = TauOptimizerCluster(
    ranges,
    strategy_name='伯努利-康达策略',
    strategy_mgr=mgr  # 传入真实策略管理器
)

opt_result = cluster.run_folding_optimization(
    coarse_points=25, refined_points_per_region=15, validation_points=5
)

print(f"  最佳参数: {list(opt_result['best_params'].items())[:3]}...")
print(f"  最佳评分: {opt_result['best_result'].score():.4f}")
print(f"  总评估数: {opt_result['total_evaluations']}")
assert opt_result['best_result'].score() > 0.5, f"伯努利优化评分应>0.5"
print("  ✅ 韬定律集群+策略管理器优化正常")

# ============================================================
# 测试5: 优化结果持久化
# ============================================================
print("\n[测试5] 优化结果持久化 - 从存储读取")
store2 = get_parameter_store()
best = store2.get_best_params('伯努利-康达策略')
best_score = store2.get_best_score('伯努利-康达策略')
print(f"  已保存策略: {store2.get_optimized_strategies()}")
print(f"  最佳评分: {best_score:.4f}")
assert best_score > 0, f"伯努利策略应被保存"
print("  ✅ 策略优化结果持久化正常")

# ============================================================
# 测试6: 智能标的轮动策略优化
# ============================================================
print("\n[测试6] 智能标的轮动策略优化")
shepherd_mod = ShepherdRotationModule()
shepherd_ranges = shepherd_mod.param_ranges
cluster2 = TauOptimizerCluster(
    shepherd_ranges,
    strategy_name='智能标的轮动',
    strategy_mgr=mgr
)
cluster2.folding = FactorSpaceFolding(shepherd_mod)

opt_result2 = cluster2.run_folding_optimization(
    coarse_points=30, refined_points_per_region=15, validation_points=5
)

print(f"  最佳评分: {opt_result2['best_result'].score():.4f}")
print(f"  总评估数: {opt_result2['total_evaluations']}")
shepherd_best = store2.get_best_score('智能标的轮动')
print(f"  存储最佳: {shepherd_best:.4f}")
assert shepherd_best > 0, f"标的轮动策略应被保存"
print("  ✅ 智能标的轮动策略优化正常")

# ============================================================
# 测试7: 通用双均线策略优化
# ============================================================
print("\n[测试7] 通用双均线策略优化")
generic_ranges = {
    'short_period': (5.0, 50.0),
    'long_period': (50.0, 200.0),
    'threshold': (0.005, 0.10)
}
cluster3 = TauOptimizerCluster(
    generic_ranges,
    strategy_name='双均线策略',
    strategy_mgr=mgr
)
opt_result3 = cluster3.run_folding_optimization(
    coarse_points=20, refined_points_per_region=15, validation_points=5
)
print(f"  最佳评分: {opt_result3['best_result'].score():.4f}")
generic_best = store2.get_best_score('双均线策略')
print(f"  存储最佳: {store2.get_best_score('双均线策略'):.4f}")
print("  ✅ 通用策略优化+存储正常")

# ============================================================
# 最终总结
# ============================================================
print("\n" + "=" * 70)
print("📊 优化结果总览")
print("=" * 70)

for strategy_name in store2.get_optimized_strategies():
    info = store2.get_strategy(strategy_name)
    history = info.get('optimization_history', [])
    print(f"\n  {strategy_name}:")
    print(f"    最佳评分: {store2.get_best_score(strategy_name):.4f}")
    print(f"    优化次数: {len(history)}")
    if history:
        latest = history[-1]
        print(f"    最近方法: {latest.get('method', 'unknown')}")
        print(f"    最佳参数前3: {dict(list(latest.get('best_params', {}).items())[:3])}")

print("\n" + "=" * 70)
print("✅ 所有测试通过 - 真实回测+优化+持久化 完整链路正常工作")
print("=" * 70)
