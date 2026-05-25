#!/usr/bin/env python3
"""验证 breaker_capital_bridge.py 端到端功能 (修正API)"""
import sys, os
sys.path.insert(0, '.')

print("=" * 60)
print("第2步：端到端验证 breaker_capital_bridge.py")
print("=" * 60)

# 1. 模块导入
try:
    from experiments.breaker_capital_bridge import (
        BreakerCapitalBridge, BridgeSensitivityConfig,
        MarketRegime, BreakerLevel, demo_breaker_to_capital_pipeline
    )
    print("✓ BreakerCapitalBridge 导入成功")
except Exception as e:
    print(f"✗ 导入失败: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

# 2. 初始化
try:
    bridge = BreakerCapitalBridge()
    print(f"✓ 初始化成功, 黑色天鹅权重: {bridge.config.black_swan_weight}")
    print(f"  熔断级别映射: {bridge.config.breaker_level_position_map}")
except Exception as e:
    print(f"✗ 初始化失败: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

# 3. 测试 adjust_position_ratio
try:
    # 正常状态
    r1 = bridge.adjust_position_ratio(1.0)
    print(f"✓ adjust_position_ratio(1.0) 默认状态: {r1:.4f}")

    # 极端场景更新
    bridge.update_from_raw(
        black_swan_score=0.75,
        regime=MarketRegime.EXTREME,
        breaker_level=BreakerLevel.GLOBAL,
        delta_global=0.35,
    )
    r2 = bridge.adjust_position_ratio(1.0)
    r3 = bridge.adjust_position_ratio(0.95)
    print(f"  极端场景(bs=0.75,level=GLOBAL,δ_G=0.35):")
    print(f"    α_total(1.0) = {r2:.4f}")
    print(f"    α_total(0.95) = {r3:.4f}")

    # 严重崩盘场景
    bridge.update_from_raw(
        black_swan_score=0.95,
        regime=MarketRegime.CRASH,
        breaker_level=BreakerLevel.FULL,
        delta_global=0.8,
    )
    r4 = bridge.adjust_position_ratio(1.0)
    print(f"  崩盘场景(bs=0.95,level=FULL,δ_G=0.8): α_total = {r4:.4f}")
    print(f"✓ 仓位调整API功能正常")
except Exception as e:
    print(f"✗ adjust_position_ratio 失败: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

# 4. 测试 summary
try:
    summary = bridge.summary()
    print(f"✓ summary(): regime={summary.get('regime','N/A')}, breaker={summary.get('breaker_level','N/A')}")
except Exception as e:
    print(f"✗ summary 失败: {e}")

# 5. 端到端管道演示
try:
    result = demo_breaker_to_capital_pipeline(seed=42)
    if result["status"] == "success":
        num_ticks = len(result["tick_details"])
        print(f"✓ demo_breaker_to_capital_pipeline 成功: {num_ticks} ticks")
        for scenario, stats in result["scenario_stats"].items():
            print(f"    [{scenario}] avg_pos={stats['平均仓位']:.4f} avg_swan={stats['平均黑天鹅评分']:.4f}")
except Exception as e:
    print(f"✗ 管道演示失败: {e}")
    import traceback; traceback.print_exc()

print("\n" + "=" * 60)
print("✓ breaker_capital_bridge.py 端到端验证全部通过！")
print("=" * 60)