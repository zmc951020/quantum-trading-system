#!/usr/bin/env python3
"""
韬策略集群引擎 — 综合测试套件
==============================

测试覆盖：
  1. 数据模型：ClusterSignal / ClusterDecision 创建和序列化
  2. 熵计算：香农熵 / 决策熵 / 信号熵
  3. 策略适配器：函数模式 / 实例模式 / 信号解析
  4. 信号共振：多策略交叉验证 / 冲突仲裁 / 熵过滤
  5. 动态权重：等权初始化 / 质量衰减 / 休眠恢复 / 市场偏置
  6. 市场状态：趋势识别 / 震荡识别 / 高波动识别
  7. 集群引擎：多策略注册 / 评估决策 / 权重收敛 / 健康报告
  8. 压力测试：大量信号 / 快速连续评估 / 极端场景
"""

import sys
import os
import math
import random
import time
import statistics

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'QS_Robot'))

from core.tau_cluster_engine import (
    ClusterSignal, ClusterDecision,
    EntropyTools,
    StrategySignalAdapter,
    SignalResonanceValidator,
    EntropyWeightScheduler,
    MarketRegimeDetector,
    TauClusterEngine,
    create_cluster_engine,
)

# 固定随机种子确保可复现
random.seed(42)


# ============================================================
# 辅助函数
# ============================================================

def _mock_signal_func(name: str, direction: float, confidence: float = 0.7,
                       strength: float = 0.6) -> callable:
    """创建模拟信号函数"""
    def _func(market_data=None, current_price=None):
        return {
            "direction": direction,
            "confidence": confidence,
            "strength": strength,
            "expectation": direction * 0.1,
            "variance": 0.02,
            "entropy": 0.3,
            "extreme_risk": 0.15,
            "win_probability": 0.55 + random.uniform(-0.05, 0.05),
        }
    return _func


def _assert(condition: bool, msg: str) -> bool:
    if not condition:
        print(f"  ❌ FAIL: {msg}")
        return False
    print(f"  ✅ PASS: {msg}")
    return True


def _section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ============================================================
# 测试1: 数据模型
# ============================================================

def test_data_models():
    _section("测试1: 数据模型")

    # ClusterSignal
    sig = ClusterSignal(
        strategy_name="test_strategy",
        direction=0.75,
        confidence=0.8,
        strength=0.7,
        expectation=0.05,
        variance=0.01,
        entropy=0.25,
        extreme_risk=0.12,
        win_probability=0.6,
    )
    _assert(sig.is_bullish, "should be bullish")
    _assert(not sig.is_bearish, "should not be bearish")
    _assert(not sig.is_neutral, "should not be neutral")

    d = sig.to_dict()
    _assert(d["strategy"] == "test_strategy", "to_dict strategy name")
    _assert(d["direction"] == 0.75, "to_dict direction")
    _assert(d["is_bullish"] == True, "to_dict is_bullish")

    # ClusterDecision
    dec = ClusterDecision(
        direction=0.6,
        confidence=0.75,
        position_ratio=0.5,
        stop_loss=95.0,
        take_profit=110.0,
        total_signals=10,
        bullish_count=7,
        bearish_count=2,
        neutral_count=1,
        resonance_count=5,
        consensus_ratio=0.55,
        cluster_expectation=0.04,
        cluster_variance=0.01,
        cluster_entropy=0.3,
        cluster_risk=0.15,
        cluster_win_prob=0.62,
    )
    _assert(dec.action == "BUY", "buy action")
    dec_dict = dec.to_dict()
    _assert(dec_dict["action"] == "BUY", "to_dict action")

    # HOLD test
    hold_dec = ClusterDecision(direction=0.1, confidence=0.3, position_ratio=0.1,
                                stop_loss=0, take_profit=0)
    _assert(hold_dec.action == "HOLD", "hold action")

    # SELL test
    sell_dec = ClusterDecision(direction=-0.5, confidence=0.7, position_ratio=0.4,
                                stop_loss=0, take_profit=0)
    _assert(sell_dec.action == "SELL", "sell action")


# ============================================================
# 测试2: 熵计算
# ============================================================

def test_entropy():
    _section("测试2: 熵计算")

    # 完全确定的序列 → 熵=0
    h = EntropyTools.shannon_entropy([1.0, 1.0, 1.0, 1.0, 1.0])
    _assert(h == 0.0, f"deterministic entropy = 0, got {h:.4f}")

    # 均匀分布 → 熵=log2(bins)
    h = EntropyTools.shannon_entropy([0, 1, 2, 3, 4, 5, 6, 7, 8, 9], bins=10)
    _assert(h > 2.5, f"uniform entropy > 2.5, got {h:.4f}")

    # 单值 → 熵=0
    h = EntropyTools.shannon_entropy([5.0])
    _assert(h == 0.0, "single value entropy = 0")

    # 决策熵：全部同向 → 低熵
    h = EntropyTools.decision_entropy([0.5, 0.7, 0.3, 0.4, 0.6])
    _assert(h < 0.5, f"same direction decision entropy < 0.5, got {h:.4f}")

    # 决策熵：方向混合 → 高熵
    h = EntropyTools.decision_entropy([0.5, -0.5, 0.3, -0.7, 0.1, -0.3])
    _assert(h > 0.5, f"mixed direction decision entropy > 0.5, got {h:.4f}")

    # 信号熵：分歧 → 高熵
    h = EntropyTools.signal_entropy([0.9, 0.8, -0.9, -0.8, 0.1, -0.2])
    _assert(h > 0.5, f"divergent signal entropy > 0.5, got {h:.4f}")


# ============================================================
# 测试3: 策略适配器
# ============================================================

def test_adapter():
    _section("测试3: 策略适配器")

    # 3a: 函数模式
    func = _mock_signal_func("bernoulli", 0.6, 0.8, 0.7)
    adapter = StrategySignalAdapter("bernoulli", "bernoulli", signal_func=func)
    sig = adapter.get_signal({}, 100.0)
    _assert(sig is not None, "function adapter returns signal")
    _assert(sig.strategy_name == "bernoulli", "correct strategy name")
    _assert(sig.is_bullish, "bernoulli is bullish")
    _assert(sig.confidence == 0.8, "confidence preserved")

    # 3b: 字典信号解析
    adapter2 = StrategySignalAdapter("fourier", "fourier",
                                      signal_func=lambda *a: {"direction": -0.5, "confidence": 0.6})
    sig2 = adapter2.get_signal({}, 100.0)
    _assert(sig2 is not None, "dict adapter returns signal")
    _assert(sig2.is_bearish, "fourier is bearish")

    # 3c: 直接ClusterSignal返回
    adapter3 = StrategySignalAdapter("gyro", "gyro",
                                      signal_func=lambda *a: ClusterSignal(
                                          strategy_name="", direction=0.3, confidence=0.5, strength=0.4))
    sig3 = adapter3.get_signal({}, 100.0)
    _assert(sig3 is not None, "ClusterSignal adapter returns signal")
    _assert(sig3.strategy_name == "gyro", "name override works")

    # 3d: 成功率追踪
    _assert(adapter.get_success_rate() == 1.0, "100% success rate after 1 call")

    # 3e: 五维指标
    metrics = adapter.get_five_metrics()
    _assert(all(k in metrics for k in ["E", "V", "H", "M", "P"]), "five metrics keys present")


# ============================================================
# 测试4: 信号共振验证
# ============================================================

def test_resonance():
    _section("测试4: 信号共振验证")

    validator = SignalResonanceValidator(min_resonance=2, consensus_threshold=0.4)

    # 4a: 空信号
    _, report = validator.validate([])
    _assert(not report["passed"], "empty signals not passed")

    # 4b: 高度共识（6个看多，1个看空）
    signals = [
        ClusterSignal(strategy_name="s1", direction=0.7, confidence=0.8, strength=0.7),
        ClusterSignal(strategy_name="s2", direction=0.6, confidence=0.75, strength=0.6),
        ClusterSignal(strategy_name="s3", direction=0.5, confidence=0.7, strength=0.65),
        ClusterSignal(strategy_name="s4", direction=0.8, confidence=0.85, strength=0.8),
        ClusterSignal(strategy_name="s5", direction=0.4, confidence=0.65, strength=0.55),
        ClusterSignal(strategy_name="s6", direction=0.65, confidence=0.7, strength=0.6),
        ClusterSignal(strategy_name="s7", direction=-0.2, confidence=0.5, strength=0.3),
    ]
    _, report = validator.validate(signals)
    _assert(report["passed"], "high consensus passed")
    _assert(report["bullish"] == 6, "6 bullish")
    _assert(report["bearish"] == 1, "1 bearish")
    _assert(report["has_resonance"], "has resonance")

    # 4c: 分歧场景（4看多，4看空）
    mixed = [
        ClusterSignal(strategy_name="a1", direction=0.6, confidence=0.7, strength=0.6),
        ClusterSignal(strategy_name="a2", direction=0.5, confidence=0.65, strength=0.55),
        ClusterSignal(strategy_name="a3", direction=0.4, confidence=0.6, strength=0.5),
        ClusterSignal(strategy_name="a4", direction=0.3, confidence=0.55, strength=0.45),
        ClusterSignal(strategy_name="b1", direction=-0.6, confidence=0.7, strength=0.6),
        ClusterSignal(strategy_name="b2", direction=-0.5, confidence=0.65, strength=0.55),
        ClusterSignal(strategy_name="b3", direction=-0.4, confidence=0.6, strength=0.5),
        ClusterSignal(strategy_name="b4", direction=-0.3, confidence=0.55, strength=0.45),
    ]
    _, report = validator.validate(mixed)
    _assert(not report["passed"], "mixed signals not passed")
    _assert(report["signal_entropy"] > 0.5, "high entropy in mixed")

    # 4d: 低置信度过滤
    noisy = [
        ClusterSignal(strategy_name="n1", direction=0.7, confidence=0.25, strength=0.5),
        ClusterSignal(strategy_name="n2", direction=0.6, confidence=0.2, strength=0.4),
        ClusterSignal(strategy_name="n3", direction=0.5, confidence=0.8, strength=0.6),
        ClusterSignal(strategy_name="n4", direction=0.4, confidence=0.75, strength=0.55),
    ]
    _, report = validator.validate(noisy)
    _assert(report["noise"] >= 2, f"low confidence filtered, noise={report['noise']}")


# ============================================================
# 测试5: 动态权重调度
# ============================================================

def test_weight_scheduler():
    _section("测试5: 动态权重调度")

    scheduler = EntropyWeightScheduler(decay_rate=0.3, max_dormant_rounds=10)

    # 初始等权
    s1 = ClusterSignal(strategy_name="s1", direction=0.6, confidence=0.8, strength=0.7,
                        entropy=0.1, variance=0.01, win_probability=0.65)
    s2 = ClusterSignal(strategy_name="s2", direction=0.5, confidence=0.7, strength=0.6,
                        entropy=0.2, variance=0.02, win_probability=0.6)
    s3 = ClusterSignal(strategy_name="s3", direction=0.4, confidence=0.6, strength=0.5,
                        entropy=0.3, variance=0.03, win_probability=0.55)

    w = scheduler.update_weights([s1, s2, s3])
    _assert(len(w) == 3, "3 strategies weighted")
    _assert(abs(sum(w.values()) - 1.0) < 0.01, f"weights sum to 1, got {sum(w.values()):.4f}")

    # 多轮后高质策略权重上升
    for _ in range(20):
        w = scheduler.update_weights([s1, s2, s3])
    _assert(w["s1"] > w["s3"], "s1 weight > s3 weight (better quality)")

    # 休眠机制
    poor = ClusterSignal(strategy_name="poor", direction=0.1, confidence=0.2, strength=0.1,
                          entropy=0.9, variance=0.1, win_probability=0.3)
    w2 = scheduler.update_weights([poor, s1])
    _assert(w2["poor"] < w2["s1"], "poor strategy lower weight")

    # 市场状态偏置
    scheduler.set_regime_priorities("trending", ["s1"])
    w3 = scheduler.update_weights([s1, s2, s3], market_regime="trending")
    _assert(w3["s1"] > w["s1"], "s1 boosted in trending regime")


# ============================================================
# 测试6: 市场状态识别
# ============================================================

def test_regime_detector():
    _section("测试6: 市场状态识别")

    detector = MarketRegimeDetector(lookback=20)

    # 初始状态
    _assert(detector.detect() == "unknown", "initial unknown")

    # 喂入趋势数据
    for i in range(30):
        detector.feed(100.0 + i * 0.5)  # 稳步上升
    _assert(detector.detect() == "trending", "uptrend detected")

    # 喂入震荡数据
    detector2 = MarketRegimeDetector(lookback=20)
    for i in range(30):
        detector2.feed(100.0 + math.sin(i * 0.5) * 0.5)
    regime = detector2.detect()
    _assert(regime in ("ranging", "trending"), f"oscillation -> {regime}")

    # 喂入下跌数据
    detector3 = MarketRegimeDetector(lookback=20)
    for i in range(30):
        detector3.feed(100.0 - i * 0.3)
    _assert(detector3.detect() == "bearish", "downtrend -> bearish")


# ============================================================
# 测试7: 集群引擎核心
# ============================================================

def test_cluster_engine():
    _section("测试7: 集群引擎核心")

    engine = TauClusterEngine(min_resonance=2, consensus_threshold=0.3)

    # 注册14个模拟策略
    strategy_configs = [
        ("bernoulli", "bernoulli", 0.6, 0.8),
        ("fourier", "fourier", 0.5, 0.75),
        ("gyro_v6", "gyro", 0.55, 0.7),
        ("gyro_precession", "gyro", 0.5, 0.72),
        ("fractal_chaos", "physics", 0.4, 0.65),
        ("fluid_dynamics", "physics", 0.45, 0.68),
        ("quantum_finance", "physics", 0.35, 0.62),
        ("adaptive_ml", "ml", 0.5, 0.7),
        ("dynamic_grid", "grid", 0.3, 0.6),
        ("golden_bowl", "trend", 0.55, 0.73),
        ("down_market", "trend", -0.2, 0.55),
        ("rl_adaptive", "rl", 0.4, 0.66),
        ("huijin_value", "value", 0.35, 0.63),
        ("smart_rotate", "ml", 0.45, 0.69),
    ]

    for name, stype, direction, confidence in strategy_configs:
        func = _mock_signal_func(name, direction, confidence)
        engine.register_strategy_func(name, stype, func)

    _assert(len(engine.get_registered_strategies()) == 14, "14 strategies registered")

    # 7a: 单次评估
    decision = engine.evaluate({}, 100.0)
    _assert(decision is not None, "evaluate returns decision")
    _assert(decision.action in ("BUY", "SELL", "HOLD"), f"valid action: {decision.action}")
    _assert(decision.total_signals == 14, "14 signals collected")
    _assert(0 <= decision.position_ratio <= 1.0, "position ratio in [0,1]")
    _assert(decision.stop_loss > 0, "stop_loss set")
    _assert(decision.take_profit > 0, "take_profit set")

    print(f"  📊 Decision: action={decision.action}, direction={decision.direction:.3f}, "
          f"confidence={decision.confidence:.3f}, position={decision.position_ratio:.3f}")
    print(f"  📊 Consensus: bullish={decision.bullish_count}, bearish={decision.bearish_count}, "
          f"neutral={decision.neutral_count}, resonance={decision.resonance_count}")
    print(f"  📊 Metrics: E={decision.cluster_expectation:.3f}, V={decision.cluster_variance:.3f}, "
          f"H={decision.cluster_entropy:.3f}, M={decision.cluster_risk:.3f}, P={decision.cluster_win_prob:.3f}")

    # 7b: 多轮评估（权重收敛）
    print("\n  --- 多轮评估权重收敛 ---")
    for i in range(5):
        decision = engine.evaluate({}, 100.0 + i * 0.5)
        print(f"  Round {i+1}: action={decision.action}, "
              f"confidence={decision.confidence:.3f}, "
              f"active={len(decision.active_strategies)}")

    # 7c: 集群健康报告
    health = engine.get_cluster_health()
    _assert(health["total_strategies"] == 14, "health total strategies")
    _assert(health["total_evaluations"] > 0, "health evaluations count")
    _assert("current_weights" in health, "health has weights")
    _assert("market_regime" in health, "health has market regime")
    _assert(health["last_decision"] is not None, "health has last decision")

    print(f"\n  📊 健康报告: active={health['active_strategies']}, "
          f"dormant={health['dormant_strategies']}, "
          f"regime={health['market_regime']}")

    # 7d: 单个策略绩效
    perf = engine.get_strategy_performance("bernoulli")
    _assert(perf["name"] == "bernoulli", "perf strategy name")
    _assert(perf["success_rate"] == 1.0, "perf success rate")
    _assert("five_metrics" in perf, "perf has five metrics")

    # 7e: 决策历史
    history = engine.get_decision_history(5)
    _assert(len(history) > 0, "decision history available")


# ============================================================
# 测试8: 压力测试
# ============================================================

def test_stress():
    _section("测试8: 压力测试")

    engine = TauClusterEngine(min_resonance=2, consensus_threshold=0.3)

    # 注册14个策略
    for i in range(14):
        name = f"strategy_{i}"
        direction = random.uniform(-0.5, 0.8)
        confidence = random.uniform(0.4, 0.9)
        engine.register_strategy_func(name, "generic",
                                       _mock_signal_func(name, direction, confidence))

    # 8a: 快速连续评估
    print("  --- 100轮快速评估 ---")
    t_start = time.time()
    decisions = []
    for i in range(100):
        price = 100.0 + random.uniform(-5, 5)
        decision = engine.evaluate({}, price)
        decisions.append(decision)
    elapsed = time.time() - t_start
    print(f"  100轮评估耗时: {elapsed*1000:.1f}ms (avg={elapsed*10:.1f}ms/轮)")

    _assert(elapsed < 5.0, f"100 rounds < 5s, actual={elapsed:.2f}s")
    _assert(len(decisions) == 100, "100 decisions")

    # 统计决策分布
    buys = sum(1 for d in decisions if d.action == "BUY")
    sells = sum(1 for d in decisions if d.action == "SELL")
    holds = sum(1 for d in decisions if d.action == "HOLD")
    print(f"  决策分布: BUY={buys}, SELL={sells}, HOLD={holds}")

    # 8b: 极端场景 - 全部强烈看多
    print("\n  --- 极端场景: 全部强烈看多 ---")
    engine2 = TauClusterEngine(min_resonance=2, consensus_threshold=0.3)
    for i in range(10):
        engine2.register_strategy_func(f"bull_{i}", "trend",
                                        _mock_signal_func(f"bull_{i}", 0.9, 0.95))
    d = engine2.evaluate({}, 100.0)
    _assert(d.action == "BUY", "extreme bullish -> BUY")
    _assert(d.confidence > 0.5, "high confidence")
    _assert(d.position_ratio > 0.5, "high position ratio")
    print(f"  Extreme bullish: action={d.action}, confidence={d.confidence:.3f}, pos={d.position_ratio:.3f}")

    # 8c: 极端场景 - 全部强烈看空
    engine3 = TauClusterEngine(min_resonance=2, consensus_threshold=0.3)
    for i in range(10):
        engine3.register_strategy_func(f"bear_{i}", "trend",
                                        _mock_signal_func(f"bear_{i}", -0.9, 0.95))
    d = engine3.evaluate({}, 100.0)
    _assert(d.action == "SELL", "extreme bearish -> SELL")
    print(f"  Extreme bearish: action={d.action}, confidence={d.confidence:.3f}, pos={d.position_ratio:.3f}")

    # 8d: 极端场景 - 全部中性
    engine4 = TauClusterEngine(min_resonance=2, consensus_threshold=0.3)
    for i in range(10):
        engine4.register_strategy_func(f"neutral_{i}", "generic",
                                        _mock_signal_func(f"neutral_{i}", 0.05, 0.3))
    d = engine4.evaluate({}, 100.0)
    _assert(d.action == "HOLD", "all neutral -> HOLD")
    print(f"  All neutral: action={d.action}, confidence={d.confidence:.3f}, pos={d.position_ratio:.3f}")


# ============================================================
# 测试9: 工厂函数
# ============================================================

def test_factory():
    _section("测试9: 工厂函数")

    # 模拟策略实例
    class MockStrategy:
        def __init__(self):
            self.position = 500
        def update_price(self, price, data=None):
            return {"direction": 0.5, "confidence": 0.7}

    strategies = {
        "mock_strategy": MockStrategy(),
    }

    engine = create_cluster_engine(strategies, min_resonance=1, consensus_threshold=0.2)
    _assert(len(engine.get_registered_strategies()) == 1, "factory creates engine with strategy")
    _assert("mock_strategy" in engine.get_registered_strategies(), "strategy registered")

    d = engine.evaluate({}, 100.0)
    _assert(d is not None, "factory engine evaluates")


# ============================================================
# 主入口
# ============================================================

def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("  韬策略集群引擎 v1.0 — 综合测试套件")
    print("=" * 60)

    tests = [
        ("数据模型", test_data_models),
        ("熵计算", test_entropy),
        ("策略适配器", test_adapter),
        ("信号共振验证", test_resonance),
        ("动态权重调度", test_weight_scheduler),
        ("市场状态识别", test_regime_detector),
        ("集群引擎核心", test_cluster_engine),
        ("压力测试", test_stress),
        ("工厂函数", test_factory),
    ]

    passed = 0
    failed = 0
    for name, test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"\n  ❌ {name} 测试异常: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'='*60}")
    print(f"  测试完成: {passed} 通过, {failed} 失败, {len(tests)} 总计")
    print(f"{'='*60}")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)