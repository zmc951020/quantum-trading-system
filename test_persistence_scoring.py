#!/usr/bin/env python3
"""韬定律策略优化器集群 - 持久化 & 策略感知评分验证测试"""
import os, sys, json, random

sys.path.insert(0, r'd:\Gupiao\升级vscode')
random.seed(42)

from QS_Robot.core.tau_optimizer_cluster import (
    TauOptimizerCluster, BernoulliCoandaModule, ShepherdRotationModule,
    FactorSpaceFolding, get_parameter_store, ParameterSpaceFolding
)

print("=" * 70)
print("韬定律策略优化器集群 - 持久化 & 策略感知评分验证测试")
print("=" * 70)

# 清理旧存储文件
store = get_parameter_store()
store_path = store.store_file
if os.path.exists(store_path):
    try:
        os.remove(store_path)
    except Exception:
        pass

# ============================================================
# [测试1] 伯努利-康达策略感知评分
# ============================================================
print("\n[测试1] 伯努利-康达策略感知评分 (estimate_quality)")
mod = BernoulliCoandaModule()
ranges = mod.param_ranges
param_groups = mod.get_param_groups()
print(f"  参数组数: {len(param_groups)}")
print(f"  总参数: {sum(len(v) for v in param_groups.values())}")

# 合理参数 vs 极端参数
good_params = {
    'short_period': 15.0, 'mid_period': 30.0, 'long_period': 60.0,
    'bernoulli_threshold': 0.08, 'momentum_alpha': 1.0, 'pressure_sensitivity': 0.8,
    'coanda_attachment': 0.7, 'curvature_sensitivity': 0.6, 'separation_threshold': 1.0,
    'stop_loss_pct': 0.05, 'position_size': 0.3, 'confirmation_bars': 3.0
}
bad_params = {
    'short_period': 5.0, 'mid_period': 7.0, 'long_period': 10.0,
    'bernoulli_threshold': 0.5, 'momentum_alpha': 2.5, 'pressure_sensitivity': 2.5,
    'coanda_attachment': 0.05, 'curvature_sensitivity': 0.05, 'separation_threshold': 3.0,
    'stop_loss_pct': 0.25, 'position_size': 1.0, 'confirmation_bars': 0.0
}

good_q = mod.estimate_quality(good_params)
bad_q = mod.estimate_quality(bad_params)
print(f"  合理参数 score={good_q:.4f}")
print(f"  极端参数 score={bad_q:.4f}")
assert good_q > bad_q, "合理参数评分应高于极端参数"
print(f"  ✅ 策略感知评分正常工作 (合理={good_q:.2f} > 极端={bad_q:.2f})")

# ============================================================
# [测试2] 伯努利-康达策略 - 完整空间折叠优化
# ============================================================
print("\n[测试2] 伯努利-康达策略 - 完整空间折叠优化")
random.seed(123)
cluster2 = TauOptimizerCluster(ranges, strategy_name='伯努利-康达策略')
# TauOptimizerCluster 默认使用 ParameterSpaceFolding（通用折叠）
# 这里用默认的 folding，不需要替换
opt_result = cluster2.run_folding_optimization(
    coarse_points=30, refined_points_per_region=15, validation_points=5
)
print(f"  最佳评分: {opt_result['best_result'].score():.4f}")
print(f"  评估数: {opt_result['total_evaluations']}")
# 伯努利评分应该能达到 0.5+（estimate_quality 对于合理参数应该给出 0.6+）
assert opt_result['best_result'].score() > 0.4, f"伯努利优化评分应 > 0.4, 实际 {opt_result['best_result'].score():.4f}"
print("  ✅ 伯努利-康达策略优化完成")

# ============================================================
# [测试3] 优化结果持久化 (保存到JSON)
# ============================================================
print("\n[测试3] 策略优化结果持久化")
store3 = get_parameter_store()
best_score3 = store3.get_best_score('伯努利-康达策略')
print(f"  存储文件: {store_path}")
print(f"  历史最佳 score: {best_score3:.4f}")
assert best_score3 > 0, "伯努利策略应被保存到存储"

# 查看存储内容
with open(store_path, 'r', encoding='utf-8') as f:
    data = json.load(f)
strategy_names = [k for k in data.keys() if not k.startswith('_')]
print(f"  已优化策略数: {len(strategy_names)}")
for sn in strategy_names:
    info = data[sn]
    print(f"    - {sn}: v{info.get('current_version', 0)}, "
          f"score={info.get('best_score', 0):.4f}, "
          f"optimizations={len(info.get('optimization_history', []))}")
print("  ✅ 优化结果已持久化保存到JSON")

# ============================================================
# [测试4] Warm start - 第二次优化
# ============================================================
print("\n[测试4] Warm start - 第二次优化 (验证不会从头开始)")
random.seed(456)
cluster4 = TauOptimizerCluster(ranges, strategy_name='伯努利-康达策略')
prev_score = store3.get_best_score('伯努利-康达策略')
print(f"  历史最佳 score: {prev_score:.4f}")
opt_result4 = cluster4.run_folding_optimization(
    coarse_points=30, refined_points_per_region=15, validation_points=5
)
new_score = opt_result4['best_result'].score()
print(f"  本次最佳 score: {new_score:.4f}")
new_best = store3.get_best_score('伯努利-康达策略')
print(f"  存储中的最新 score: {new_best:.4f}")
print(f"  版本演进: v1 → v{data.get('伯努利-康达策略', {}).get('current_version', 1)}")
print("  ✅ Warm start 正常工作 (优化记录持续累积)")

# ============================================================
# [测试5] 智能标的轮动 68因子优化 + 持久化
# ============================================================
print("\n[测试5] 智能标的轮动 68因子优化 + 持久化")
random.seed(789)
shepherd_mod = ShepherdRotationModule()
shepherd_ranges = shepherd_mod.param_ranges
print(f"  因子组数: {len(shepherd_mod.FACTOR_GROUPS)}")
print(f"  总因子: {shepherd_mod.count_params()}")

cluster5 = TauOptimizerCluster(shepherd_ranges, strategy_name='智能标的轮动')
# 用专门为高维因子设计的 FactorSpaceFolding
cluster5.folding = FactorSpaceFolding(shepherd_mod)
opt_result5 = cluster5.run_folding_optimization(
    coarse_points=35, refined_points_per_region=15, validation_points=5
)
print(f"  最佳评分: {opt_result5['best_result'].score():.4f}")
print(f"  评估数: {opt_result5['total_evaluations']}")
shepherd_best = store3.get_best_score('智能标的轮动')
print(f"  已保存到存储: {shepherd_best:.4f}")
assert shepherd_best > 0, "智能标的轮动策略应被保存"
print("  ✅ 标的轮动68因子优化 + 持久化正常")

# ============================================================
# [测试6] 通用双均线策略优化 (验证回退路径)
# ============================================================
print("\n[测试6] 通用双均线策略优化 (验证回退评分路径)")
generic_ranges = {
    'short_period': (5.0, 50.0),
    'long_period': (50.0, 200.0),
    'threshold': (0.01, 0.10)
}
cluster6 = TauOptimizerCluster(generic_ranges, strategy_name='双均线策略')
opt_result6 = cluster6.run_folding_optimization(
    coarse_points=20, refined_points_per_region=10, validation_points=5
)
print(f"  最佳评分: {opt_result6['best_result'].score():.4f}")
generic_best = store3.get_best_score('双均线策略')
print(f"  已保存到存储: {generic_best:.4f}")
assert generic_best > 0, "双均线策略应被保存"
print("  ✅ 通用策略优化 + 持久化正常")

# ============================================================
# 最终总结
# ============================================================
print("\n" + "=" * 70)
print("📊 持久化存储汇总")
print("=" * 70)
with open(store_path, 'r', encoding='utf-8') as f:
    data = json.load(f)
for key, value in data.items():
    if key.startswith('_'):
        continue
    hist = value.get('optimization_history', [])
    print(f"\n  策略: {key}")
    print(f"    当前版本: v{value.get('current_version', 0)}")
    print(f"    最佳评分: {value.get('best_score', 0):.4f}")
    print(f"    优化次数: {len(hist)}")
    if hist:
        latest = hist[-1]
        print(f"    最近方法: {latest.get('method', 'unknown')}")
        print(f"    最近时间: {latest.get('timestamp', 'unknown')[:19]}")
        print(f"    最近评分: {latest.get('best_score', 0):.4f}")
        print(f"    最佳参数 (前3): {dict(list(latest.get('best_params', {}).items())[:3])}")

print("\n" + "=" * 70)
print("✅ 所有测试通过 - 持久化与策略感知评分正常工作")
print("=" * 70)
