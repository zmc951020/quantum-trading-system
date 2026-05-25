"""一次性归档脚本：将实验性和重复文件移入 experiments/archive/"""
import shutil
import os

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

archived = 0

# 归档测试文件
test_files = [
    'test_gyro_simple.py', 'test_gyro_strategy.py', 'test_gyro_trading.py',
    'test_gyro_v6_optimizer.py', 'test_gyro_v6_pro.py', 'test_initial_score.py',
    'test_opt.py', 'test_v7_gyro_with_v6.py', 'test_workflow_integration.py',
    'test_enhanced_gyro.py', 'test_evolution_ability.py', 'test_final_summary.py',
    'test_complete_integration.py',
]
for f in test_files:
    if os.path.exists(f):
        shutil.move(f, os.path.join('experiments/archive', f))
        archived += 1
        print(f"  ✓ {f}")

# 归档策略变体文件（保留核心策略）
strategy_files = [
    'strategies/bernoulli_coanda_strategy.py',
    'strategies/bernoulli_coanda_optimizer.py',
    'strategies/breaker_capital_orchestrator.py',
    'strategies/gyro_minute_strategy.py',
    'strategies/gyro_minute_strategy_v2.py',
    'strategies/gyro_minute_strategy_v3.py',
    'strategies/gyro_minute_strategy_v4.py',
    'strategies/gyro_minute_strategy_v5.py',
    'strategies/gyro_precession_strategy.py',
    'strategies/gyro_precession_strategy_restored.py',
    'strategies/gyro_optimized_strategy.py',
]
for f in strategy_files:
    if os.path.exists(f):
        dst = os.path.join('experiments/archive', os.path.basename(f))
        shutil.move(f, dst)
        archived += 1
        print(f"  ✓ {f}")

# 归档模板文件
template_files = [
    'templates/strategy_monitor.html',
    'templates/strategy_platform.html',
    'templates/system_maintenance.html',
]
for f in template_files:
    if os.path.exists(f):
        shutil.move(f, os.path.join('experiments/archive', os.path.basename(f)))
        archived += 1
        print(f"  ✓ {f}")

# 归档其他文件
misc_files = [
    'tests/test_system_maintenance.py',
    'web/templates/',
    'd',
    'anomaly_detector.py', 'auto_healer.py',
    'strategy_api.py', 'strategy_diagnosis.py', 'strategy_health_maintenance.py',
    'strategy_monitor.py', 'strategy_optimizer_bridge.py',
]
for f in misc_files:
    if os.path.exists(f):
        dst = os.path.join('experiments/archive', os.path.basename(f.rstrip('/')) if f.endswith('/') else os.path.basename(f))
        try:
            if os.path.isdir(f):
                shutil.move(f, dst)
            else:
                shutil.move(f, dst)
            archived += 1
            print(f"  ✓ {f}")
        except Exception as e:
            print(f"  ✗ {f}: {e}")

print(f"\n共归档 {archived} 个文件")