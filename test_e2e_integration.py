#!/usr/bin/env python3
"""韬定律集群端到端集成测试"""
import sys
import os

sys.path.insert(0, r'd:\Gupiao\升级vscode\QS_Robot')

from core.enhanced_strategy_manager import get_strategy_manager

mgr = get_strategy_manager()

print("=" * 60)
print("[1] 测试: get_tau_cluster_info()")
print("=" * 60)
info = mgr.get_tau_cluster_info()
print(f"  success: {info.get('success')}")
print(f"  name: {info.get('name')}")
print(f"  status: {info.get('status')}")
print(f"  features: {info.get('features')}")
print()

print("=" * 60)
print("[2] 测试: run_tau_single_eval()")
print("=" * 60)
params = {'short_period': 15, 'long_period': 60, 'threshold': 0.05, 'stop_loss': 0.08}
single = mgr.run_tau_single_eval('双均线策略', params)
print(f"  success: {single.get('success')}")
d = single.get('data', {})
print(f"  return: {d.get('total_return', 'N/A')}")
print(f"  sharpe: {d.get('sharpe_ratio', 'N/A')}")
print(f"  drawdown: {d.get('max_drawdown', 'N/A')}")
print(f"  hit_mode: {d.get('hit_mode', 'N/A')}")
print()

print("=" * 60)
print("[3] 测试: run_tau_cluster_optimization() - 精简版")
print("=" * 60)
result = mgr.run_tau_cluster_optimization(
    strategy_name='双均线策略',
    coarse_points=20,
    refined_points=30,
    target='sharpe_ratio'
)
print(f"  success: {result.get('success')}")
d = result.get('data', {})
print(f"  best_score: {d.get('best_score')}")
print(f"  best_return: {d.get('best_return')}")
print(f"  best_sharpe: {d.get('best_sharpe')}")
print(f"  best_params: {d.get('best_params')}")
print(f"  total_evals: {d.get('total_evals')}")
print(f"  time_elapsed: {d.get('time_elapsed')}s")
cs = d.get('cluster_status', {})
if isinstance(cs, dict):
    cache = cs.get('cache', {})
    if isinstance(cache, dict):
        print(f"  cache_hit_rate: {cache.get('hit_rate', 0) * 100:.1f}%")
        print(f"  exact_hits: {cache.get('exact_hits', 0)}, bucket_hits: {cache.get('bucket_hits', 0)}, neighbor_hits: {cache.get('neighbor_hits', 0)}")
        print(f"  full_computes: {cache.get('full_computes', 0)}")
print()

print("=" * 60)
print("[4] 测试: qs_robot_core.py 集成")
print("=" * 60)
from qs_robot_core import QSRobotCore, AuroraSystemIntegration

# 测试优化器列表
aurora = AuroraSystemIntegration()
optimizers = aurora.get_optimizer_list()
print(f"  优化器列表: {len(optimizers)} 个")
for opt in optimizers:
    status = "✅" if opt['status'] == 'available' or opt['status'] == 'healthy' else "⚠️"
    print(f"    {status} {opt['name']} - {opt['description']}")
print()

# 测试健康检查
print("  运行健康检查...")
health = aurora.run_health_check()
print(f"  总体状态: {health.get('overall_status')}")
for check in health.get('checks', []):
    icon = "✅" if check['status'] == 'healthy' else "⚠️" if check['status'] == 'warning' else "❌"
    print(f"    {icon} {check['name']}: {check['message']}")
print()

print("=" * 60)
print("[5] 所有测试完成!")
print("=" * 60)
