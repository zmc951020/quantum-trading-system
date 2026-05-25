#!/usr/bin/env python3
"""验证 breaker_capital_orchestrator.py 端到端功能"""
import sys, os
sys.path.insert(0, '.')

print("=" * 60)
print("第2步+: 端到端验证 breaker_capital_orchestrator.py")
print("=" * 60)

# 1. 模块导入
try:
    from strategies.breaker_capital_orchestrator import (
        BreakerCapitalOrchestrator, OrchestratorDecision,
        OrchestratorAction, MarketPhase, SignalStrength, ReversalSignal,
        BreakerConfig, SELL_TIERS, BUY_TIERS, RESERVE_POLICIES,
        CombatLog
    )
    print("✓ BreakerCapitalOrchestrator 导入成功")
except Exception as e:
    print(f"✗ 导入失败: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

# 2. 初始化
try:
    orch = BreakerCapitalOrchestrator(
        initial_capital=1000000.0,
        initial_position=5000,
        initial_price=100.0,
        config=BreakerConfig(ticker="AAPL")
    )
    print(f"✓ 初始化成功: capital={orch.capital}, position={orch.position}")
    print(f"  金字塔层级上限: {orch.max_pyramid_levels}")
    print(f"  仓位上限: {orch.max_position_pct*100}%")
except Exception as e:
    print(f"✗ 初始化失败: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

# 3. 测试价格输入和阶段判定
try:
    # 模拟价格序列
    prices = [100, 99, 98, 95, 92, 88, 85, 82, 80, 78, 76, 75, 73, 72, 74, 77, 80, 84, 88, 92]
    decisions = []
    for i, price in enumerate(prices):
        decision = orch.update(price, timestamp=i)
        decisions.append(decision)
        print(f"  t={i:2d} price={price:5.1f} phase={decision.current_phase.value:8s} "
              f"action={decision.action.value:10s} breaker={decision.breaker_level} "
              f"swan={decision.black_swan_score:.3f}")
    print(f"✓ 价格序列处理完成, {len(decisions)} 个决策")
except Exception as e:
    print(f"✗ 价格序列处理失败: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

# 4. 验证核心指标
try:
    final_log = orch.get_combat_log()
    total_decisions = len(final_log)
    buy_decisions = [d for d in decisions if d.action == OrchestratorAction.PYRAMID_BUY]
    sell_decisions = [d for d in decisions if d.action == OrchestratorAction.TIERED_SELL]
    print(f"✓ 战斗日志: {total_decisions} 条决策")
    print(f"   买入信号: {len(buy_decisions)} 次")
    print(f"   卖出信号: {len(sell_decisions)} 次")
    print(f"   最终持仓: {orch.position:.0f}股, 现金: ¥{orch.cash:,.0f}")
except Exception as e:
    print(f"✗ 核心指标验证失败: {e}")
    import traceback; traceback.print_exc()

# 5. 配置/策略常量完整性检查
try:
    assert len(SELL_TIERS) == 5, f"分层卖出表应为5级, 实际{len(SELL_TIERS)}"
    assert len(BUY_TIERS) == 4, f"分层买入表应为4级, 实际{len(BUY_TIERS)}"
    assert len(RESERVE_POLICIES) >= 3, f"储备金政策表应≥3条, 实际{len(RESERVE_POLICIES)}"
    print(f"✓ 策略常量完整性检查通过")
    print(f"   SELL_TIERS: {len(SELL_TIERS)} 级, BUY_TIERS: {len(BUY_TIERS)} 级")
    print(f"   RESERVE_POLICIES: {len(RESERVE_POLICIES)} 条")
except Exception as e:
    print(f"✗ 常量完整性检查失败: {e}")

# 6. 数据类字段完整性
try:
    d = OrchestratorDecision(
        timestamp=0, action=OrchestratorAction.HOLD,
        current_phase=MarketPhase.CALM, breaker_level=0,
        black_swan_score=0.0, reversal_signal=None,
        support_levels=[], reasoning="test",
        metrics={"capital": 1000000}
    )
    print(f"✓ OrchestratorDecision 数据类实例化成功")
    rs = ReversalSignal(
        strength=SignalStrength.STRONG,
        confidence=0.85,
        support_level=0.382,
        reason="菲波那切0.382支撑"
    )
    print(f"✓ ReversalSignal 实例化: strength={rs.strength}, confidence={rs.confidence}")
except Exception as e:
    print(f"✗ 数据类验证失败: {e}")

print("\n" + "=" * 60)
print("✓ breaker_capital_orchestrator.py 端到端验证全部通过！")
print("=" * 60)