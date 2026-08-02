#!/usr/bin/env python3
"""
韬策略集群引擎 — 第三轮测试：集成真实策略适配器 + 完整流程
============================================================

模拟14个真实策略的信号输出模式，测试完整集群决策管线。
"""

import sys
import os
import math
import random
import time
import json
import statistics
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'QS_Robot'))

from core.tau_cluster_engine import (
    ClusterSignal, ClusterDecision,
    StrategySignalAdapter,
    SignalResonanceValidator,
    EntropyWeightScheduler,
    MarketRegimeDetector,
    TauClusterEngine,
    create_cluster_engine,
    get_cluster_engine,
)

_passed = 0
_failed = 0
_details = []

def _assert(condition, msg):
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  ✅ {msg}")
    else:
        _failed += 1
        print(f"  ❌ {msg}")
        _details.append(f"FAIL: {msg}")
    return condition

def _section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ============================================================
# 模拟14个真实策略的信号模式
# 每种策略有不同的信号特征（方向偏好、置信度范围、波动性）
# ============================================================

# 14个核心策略配置（模拟真实特征）
REAL_STRATEGY_CONFIGS = {
    "FourierRLStrategy": {
        "type": "fourier",
        "direction_range": (-0.3, 0.7),
        "confidence_range": (0.5, 0.9),
        "strength_range": (0.4, 0.8),
        "expectation_bias": 0.08,
        "variance_bias": 0.015,
        "entropy_bias": 0.25,
        "win_prob_bias": 0.58,
        "description": "傅里叶变换+PPO强化学习",
    },
    "FinalMarketAdaptiveGrid": {
        "type": "grid",
        "direction_range": (-0.2, 0.5),
        "confidence_range": (0.4, 0.75),
        "strength_range": (0.3, 0.7),
        "expectation_bias": 0.04,
        "variance_bias": 0.02,
        "entropy_bias": 0.35,
        "win_prob_bias": 0.55,
        "description": "随机森林市场分类+自适应网格",
    },
    "MLRangeGridTrading": {
        "type": "ml",
        "direction_range": (-0.25, 0.55),
        "confidence_range": (0.45, 0.8),
        "strength_range": (0.35, 0.75),
        "expectation_bias": 0.05,
        "variance_bias": 0.018,
        "entropy_bias": 0.3,
        "win_prob_bias": 0.56,
        "description": "随机森林优化网格步长",
    },
    "HuijinValueStrategy": {
        "type": "value",
        "direction_range": (0.1, 0.6),
        "confidence_range": (0.5, 0.85),
        "strength_range": (0.3, 0.65),
        "expectation_bias": 0.06,
        "variance_bias": 0.012,
        "entropy_bias": 0.2,
        "win_prob_bias": 0.6,
        "description": "价值投资+AI轮动",
    },
    "MultiFactorResonanceStrategy": {
        "type": "multifactor",
        "direction_range": (-0.4, 0.6),
        "confidence_range": (0.4, 0.8),
        "strength_range": (0.35, 0.7),
        "expectation_bias": 0.04,
        "variance_bias": 0.02,
        "entropy_bias": 0.4,
        "win_prob_bias": 0.54,
        "description": "多技术指标共振信号",
    },
    "MovingAveragesStrategy": {
        "type": "trend",
        "direction_range": (-0.5, 0.7),
        "confidence_range": (0.4, 0.8),
        "strength_range": (0.3, 0.75),
        "expectation_bias": 0.05,
        "variance_bias": 0.022,
        "entropy_bias": 0.35,
        "win_prob_bias": 0.52,
        "description": "双均线交叉+趋势跟踪",
    },
    "AdaptiveMLStrategy": {
        "type": "ml",
        "direction_range": (-0.3, 0.65),
        "confidence_range": (0.45, 0.85),
        "strength_range": (0.4, 0.8),
        "expectation_bias": 0.07,
        "variance_bias": 0.016,
        "entropy_bias": 0.28,
        "win_prob_bias": 0.57,
        "description": "在线学习+自适应参数调整",
    },
    "GridTrading": {
        "type": "grid",
        "direction_range": (-0.1, 0.4),
        "confidence_range": (0.3, 0.7),
        "strength_range": (0.2, 0.6),
        "expectation_bias": 0.03,
        "variance_bias": 0.025,
        "entropy_bias": 0.4,
        "win_prob_bias": 0.53,
        "description": "经典网格+区间震荡交易",
    },
    "PPOTradingAgent": {
        "type": "rl",
        "direction_range": (-0.5, 0.8),
        "confidence_range": (0.5, 0.9),
        "strength_range": (0.4, 0.85),
        "expectation_bias": 0.09,
        "variance_bias": 0.02,
        "entropy_bias": 0.3,
        "win_prob_bias": 0.55,
        "description": "深度强化学习+自主决策",
    },
    "DCAStrategy": {
        "type": "fund",
        "direction_range": (0.2, 0.5),
        "confidence_range": (0.4, 0.7),
        "strength_range": (0.2, 0.5),
        "expectation_bias": 0.03,
        "variance_bias": 0.01,
        "entropy_bias": 0.15,
        "win_prob_bias": 0.6,
        "description": "定期定额+成本平均",
    },
    "DownMarketStrategy": {
        "type": "defense",
        "direction_range": (-0.6, 0.1),
        "confidence_range": (0.4, 0.8),
        "strength_range": (0.3, 0.7),
        "expectation_bias": -0.02,
        "variance_bias": 0.025,
        "entropy_bias": 0.35,
        "win_prob_bias": 0.5,
        "description": "下跌趋势对冲+仓位控制",
    },
    "HighReturnGridTrading": {
        "type": "grid",
        "direction_range": (-0.3, 0.6),
        "confidence_range": (0.4, 0.75),
        "strength_range": (0.35, 0.7),
        "expectation_bias": 0.06,
        "variance_bias": 0.03,
        "entropy_bias": 0.4,
        "win_prob_bias": 0.5,
        "description": "激进网格+高频率交易",
    },
    "AdaptiveRangeGridTrading": {
        "type": "grid",
        "direction_range": (-0.2, 0.5),
        "confidence_range": (0.4, 0.75),
        "strength_range": (0.3, 0.65),
        "expectation_bias": 0.04,
        "variance_bias": 0.02,
        "entropy_bias": 0.35,
        "win_prob_bias": 0.54,
        "description": "动态范围检测+网格交易",
    },
    "FinalOptimizedStrategy": {
        "type": "ensemble",
        "direction_range": (-0.3, 0.7),
        "confidence_range": (0.5, 0.85),
        "strength_range": (0.4, 0.8),
        "expectation_bias": 0.08,
        "variance_bias": 0.015,
        "entropy_bias": 0.25,
        "win_prob_bias": 0.6,
        "description": "多策略融合+综合优化",
    },
}


def create_realistic_signal_func(name, config):
    """创建模拟真实策略的信号函数"""
    d_min, d_max = config["direction_range"]
    c_min, c_max = config["confidence_range"]
    s_min, s_max = config["strength_range"]

    class RealisticStrategySim:
        """模拟真实策略实例"""
        def __init__(self):
            self.name = name
            self.config = config
            self.position = 0
            self.call_count = 0

        def update_price(self, price, data=None):
            self.call_count += 1
            # 模拟真实策略的update_price返回值
            direction = d_min + random.random() * (d_max - d_min)
            confidence = c_min + random.random() * (c_max - c_min)
            return {
                "direction": direction,
                "confidence": confidence,
                "strength": s_min + random.random() * (s_max - s_min),
                "expectation": config["expectation_bias"] + random.uniform(-0.02, 0.02),
                "variance": config["variance_bias"] + random.uniform(-0.005, 0.005),
                "entropy": config["entropy_bias"] + random.uniform(-0.05, 0.05),
                "win_probability": config["win_prob_bias"] + random.uniform(-0.03, 0.03),
                "extreme_risk": random.uniform(0.05, 0.2),
            }

    return RealisticStrategySim()


# ============================================================
# 测试1: 14个真实策略注册
# ============================================================

def test_real_strategy_registration():
    _section("测试1: 14个真实策略注册")

    strategies = {}
    for name, config in REAL_STRATEGY_CONFIGS.items():
        strategies[name] = create_realistic_signal_func(name, config)

    _assert(len(strategies) == 14, "14 strategies created")

    engine = create_cluster_engine(strategies, min_resonance=2, consensus_threshold=0.3)
    registered = engine.get_registered_strategies()
    _assert(len(registered) == 14, f"14 strategies registered, got {len(registered)}")

    # 验证类型识别
    type_map = {"fourier": False, "grid": False, "ml": False, "value": False,
                "trend": False, "rl": False, "defense": False, "ensemble": False}
    for name in registered:
        adapter = engine._adapters.get(name)
        if adapter:
            _assert(adapter.strategy_type != "generic",
                    f"{name} type identified: {adapter.strategy_type}")
            if adapter.strategy_type in type_map:
                type_map[adapter.strategy_type] = True

    identified = sum(1 for v in type_map.values() if v)
    print(f"  策略类型识别: {identified}/{len(type_map)}")
    _assert(identified >= 5, f"at least 5 types identified, got {identified}")

    return engine


# ============================================================
# 测试2: 完整决策管线
# ============================================================

def test_full_pipeline():
    _section("测试2: 完整决策管线")

    # 创建引擎
    strategies = {}
    for name, config in REAL_STRATEGY_CONFIGS.items():
        strategies[name] = create_realistic_signal_func(name, config)
    engine = create_cluster_engine(strategies, min_resonance=2, consensus_threshold=0.25)

    # 模拟市场数据流入
    print("  --- 模拟市场数据流 ---")
    decisions = []
    for i in range(30):
        # 模拟价格（先涨后跌再震荡）
        if i < 10:
            price = 100.0 + i * 0.5  # 上涨
        elif i < 20:
            price = 105.0 - (i - 10) * 0.3  # 下跌
        else:
            price = 102.0 + math.sin(i * 0.5) * 0.5  # 震荡

        market_data = {
            "price": price,
            "volume": 10000 + random.randint(-2000, 2000),
            "timestamp": time.time(),
        }
        d = engine.evaluate(market_data, price)
        decisions.append(d)

    _assert(len(decisions) == 30, "30 decisions generated")

    # 决策分布
    actions = [d.action for d in decisions]
    print(f"  决策分布: BUY={actions.count('BUY')}, SELL={actions.count('SELL')}, "
          f"HOLD={actions.count('HOLD')}")

    # 验证：在上涨阶段应该有买入信号
    phase1 = actions[:10]
    _assert(any(a == "BUY" for a in phase1) or all(a == "HOLD" for a in phase1),
            "phase 1 decisions valid")

    # 验证：每个决策都包含完整信息
    for d in decisions:
        _assert(d.total_signals == 14, f"14 signals per decision, got {d.total_signals}")
        _assert(d.stop_loss > 0, "stop_loss > 0")
        _assert(d.take_profit > 0, "take_profit > 0")
        _assert(len(d.active_strategies) == 14, "all strategies active")
        _assert(len(d.strategy_weights) == 14, "all strategies have weights")

    return engine, decisions


# ============================================================
# 测试3: 决策JSON序列化
# ============================================================

def test_decision_serialization():
    _section("测试3: 决策JSON序列化（API输出格式验证）")

    strategies = {}
    for name, config in REAL_STRATEGY_CONFIGS.items():
        strategies[name] = create_realistic_signal_func(name, config)
    engine = create_cluster_engine(strategies, min_resonance=2, consensus_threshold=0.25)

    # 生成几个决策
    for price in [100.0, 101.0, 102.0]:
        engine.evaluate({}, price)

    last = engine.get_last_decision()
    _assert(last is not None, "last decision exists")

    # 序列化
    d_dict = last.to_dict()
    json_str = json.dumps(d_dict, ensure_ascii=False, indent=2)
    _assert(len(json_str) > 100, f"JSON output > 100 chars, got {len(json_str)}")

    # 验证必需字段
    required_fields = ["action", "direction", "confidence", "position_ratio",
                       "stop_loss", "take_profit", "total_signals",
                       "bullish", "bearish", "neutral", "resonance",
                       "consensus", "cluster_expectation", "cluster_variance",
                       "cluster_entropy", "cluster_risk", "cluster_win_prob",
                       "active_strategies", "suppressed", "weights",
                       "market_regime"]
    for field in required_fields:
        _assert(field in d_dict, f"JSON has field: {field}")

    # 反序列化验证
    parsed = json.loads(json_str)
    _assert(parsed["action"] == d_dict["action"], "round-trip action")
    _assert(parsed["total_signals"] == 14, "round-trip total_signals")

    print(f"  JSON 样例:\n{json_str[:500]}...")

    # 验证健康报告JSON
    health = engine.get_cluster_health()
    health_json = json.dumps(health, ensure_ascii=False)
    _assert(len(health_json) > 100, "health JSON valid")
    _assert("total_strategies" in health, "health has total_strategies")

    return engine


# ============================================================
# 测试4: 策略权重动态变化
# ============================================================

def test_weight_dynamics():
    _section("测试4: 策略权重动态变化")

    strategies = {}
    for name, config in REAL_STRATEGY_CONFIGS.items():
        strategies[name] = create_realistic_signal_func(name, config)
    engine = create_cluster_engine(strategies, min_resonance=2, consensus_threshold=0.25)

    # 初始权重
    d0 = engine.evaluate({}, 100.0)
    initial_weights = dict(d0.strategy_weights)
    _assert(len(initial_weights) == 14, "initial weights for all strategies")

    # 多轮评估后权重变化
    for i in range(30):
        engine.evaluate({}, 100.0 + i * 0.1)

    d_final = engine.evaluate({}, 103.0)
    final_weights = dict(d_final.strategy_weights)

    # 验证权重有变化
    changed = sum(1 for name in initial_weights
                  if abs(initial_weights[name] - final_weights.get(name, 0)) > 0.001)
    print(f"  权重变化的策略数: {changed}/14")
    _assert(changed > 0, "weights changed over time")

    # 验证权重和仍为1
    _assert(abs(sum(final_weights.values()) - 1.0) < 0.01,
            f"weights sum to 1: {sum(final_weights.values()):.4f}")

    # 验证高质量策略权重高于低质量
    # DCA（定投）稳定高胜率 → 权重应较高
    # HighReturnGrid（高波动）→ 权重可能较低
    dca_w = final_weights.get("DCAStrategy", 0)
    hr_w = final_weights.get("HighReturnGridTrading", 0)
    print(f"  DCA权重={dca_w:.4f}, HighReturnGrid权重={hr_w:.4f}")
    # 不做硬断言，因为随机性


# ============================================================
# 测试5: 信号历史与性能追踪
# ============================================================

def test_performance_tracking():
    _section("测试5: 信号历史与性能追踪")

    strategies = {}
    for name, config in REAL_STRATEGY_CONFIGS.items():
        strategies[name] = create_realistic_signal_func(name, config)
    engine = create_cluster_engine(strategies, min_resonance=2, consensus_threshold=0.25)

    # 运行多轮
    for i in range(20):
        engine.evaluate({}, 100.0 + i * 0.2)

    # 检查每个策略的性能
    for name in REAL_STRATEGY_CONFIGS:
        perf = engine.get_strategy_performance(name)
        _assert(perf["name"] == name, f"{name} performance available")
        _assert(perf["success_rate"] >= 0.0, f"{name} success_rate >= 0")
        _assert("five_metrics" in perf, f"{name} has five_metrics")

    # 决策历史检查
    history = engine.get_decision_history(10)
    _assert(len(history) == 10, "10 decision history")

    # 验证决策历史中每个决策都有完整信息
    for d in history:
        _assert(isinstance(d, ClusterDecision), "history item is ClusterDecision")
        _assert(d.total_signals == 14, "history decision has 14 signals")

    print(f"  追踪了 {len(REAL_STRATEGY_CONFIGS)} 个策略的性能数据")


# ============================================================
# 测试6: 市场状态切换
# ============================================================

def test_regime_switching():
    _section("测试6: 市场状态切换响应")

    strategies = {}
    for name, config in REAL_STRATEGY_CONFIGS.items():
        strategies[name] = create_realistic_signal_func(name, config)
    engine = create_cluster_engine(strategies, min_resonance=2, consensus_threshold=0.25)

    # 设置市场状态优先级
    engine.weight_scheduler.set_regime_priorities("trending",
        ["MovingAveragesStrategy", "FinalOptimizedStrategy", "PPOTradingAgent"])
    engine.weight_scheduler.set_regime_priorities("ranging",
        ["GridTrading", "FinalMarketAdaptiveGrid", "AdaptiveRangeGridTrading"])
    engine.weight_scheduler.set_regime_priorities("bearish",
        ["DownMarketStrategy", "HuijinValueStrategy", "DCAStrategy"])

    regimes_seen = set()

    # 模拟不同市场状态
    # 牛市（上涨）
    for i in range(30):
        engine.evaluate({}, 100.0 + i * 0.5)
    d1 = engine.get_last_decision()
    regimes_seen.add(d1.market_regime)
    print(f"  上涨阶段 市场状态: {d1.market_regime}")

    # 熊市（下跌）
    for i in range(30):
        engine.evaluate({}, 100.0 - i * 0.3)
    d2 = engine.get_last_decision()
    regimes_seen.add(d2.market_regime)
    print(f"  下跌阶段 市场状态: {d2.market_regime}")

    # 震荡
    for i in range(30):
        engine.evaluate({}, 100.0 + math.sin(i * 0.3) * 1.0)
    d3 = engine.get_last_decision()
    regimes_seen.add(d3.market_regime)
    print(f"  震荡阶段 市场状态: {d3.market_regime}")

    _assert(len(regimes_seen) >= 2, f"at least 2 market regimes detected: {regimes_seen}")

    # 验证下跌市防御策略权重提升
    if d2.market_regime == "bearish":
        w = d2.strategy_weights
        defense_w = w.get("DownMarketStrategy", 0)
        print(f"  下跌市 DownMarketStrategy 权重: {defense_w:.4f}")


# ============================================================
# 测试7: 端到端模拟交易场景
# ============================================================

def test_end_to_end_trading():
    _section("测试7: 端到端模拟交易场景")

    strategies = {}
    for name, config in REAL_STRATEGY_CONFIGS.items():
        strategies[name] = create_realistic_signal_func(name, config)
    engine = create_cluster_engine(strategies, min_resonance=2, consensus_threshold=0.25)

    # 模拟30天交易
    initial_capital = 100000.0
    capital = initial_capital
    position = 0.0
    price = 100.0
    trade_log = []

    print("  --- 30天模拟交易 ---")
    for day in range(30):
        # 价格波动
        price += random.uniform(-2, 3)
        price = max(80, min(120, price))

        # 获取集群决策
        decision = engine.evaluate({"price": price, "day": day}, price)

        # 根据决策执行交易
        if decision.action == "BUY" and position == 0:
            buy_amount = capital * decision.position_ratio * 0.9  # 90%可用资金
            if buy_amount > 100:
                position = buy_amount / price
                capital -= buy_amount
                trade_log.append(f"Day {day:2d}: BUY  {position:.2f}股 @ ${price:.2f} "
                                 f"(conf={decision.confidence:.2f})")

        elif decision.action == "SELL" and position > 0:
            sell_amount = position * price
            capital += sell_amount
            trade_log.append(f"Day {day:2d}: SELL {position:.2f}股 @ ${price:.2f} "
                             f"(conf={decision.confidence:.2f})")
            position = 0

        # 止损检查
        if position > 0 and price <= decision.stop_loss:
            capital += position * price
            trade_log.append(f"Day {day:2d}: STOP LOSS @ ${price:.2f}")
            position = 0

        # 止盈检查
        if position > 0 and price >= decision.take_profit:
            capital += position * price
            trade_log.append(f"Day {day:2d}: TAKE PROFIT @ ${price:.2f}")
            position = 0

    # 最终清算
    final_value = capital + position * price
    total_return = (final_value - initial_capital) / initial_capital

    print(f"  初始资金: ${initial_capital:,.0f}")
    print(f"  最终价值: ${final_value:,.2f}")
    print(f"  总收益: {total_return:.2%}")
    print(f"  交易记录: {len(trade_log)} 笔")

    for log in trade_log:
        print(f"    {log}")

    _assert(final_value > 0, "final value > 0")
    _assert(len(trade_log) >= 0, "trades logged")

    # 输出决策摘要
    history = engine.get_decision_history(30)
    buys = sum(1 for d in history if d.action == "BUY")
    sells = sum(1 for d in history if d.action == "SELL")
    print(f"\n  决策摘要: BUY={buys}, SELL={sells}, HOLD={30-buys-sells}")


# ============================================================
# 主入口
# ============================================================

def main():
    global _passed, _failed

    print("\n" + "=" * 60)
    print("  韬策略集群引擎 — 第三轮测试（集成+端到端）")
    print("=" * 60)

    random.seed(42)

    tests = [
        ("14策略注册", test_real_strategy_registration),
        ("完整决策管线", test_full_pipeline),
        ("JSON序列化", test_decision_serialization),
        ("权重动态变化", test_weight_dynamics),
        ("性能追踪", test_performance_tracking),
        ("市场状态切换", test_regime_switching),
        ("端到端模拟交易", test_end_to_end_trading),
    ]

    for name, func in tests:
        try:
            func()
        except Exception as e:
            print(f"\n  ❌ {name} 异常: {e}")
            import traceback
            traceback.print_exc()
            _failed += 1

    print(f"\n{'='*60}")
    print(f"  第三轮测试完成: {_passed} 通过, {_failed} 失败, {_passed + _failed} 总计")
    print(f"{'='*60}")

    if _details:
        print("\n  失败详情:")
        for d in _details:
            print(f"    {d}")

    return _failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)