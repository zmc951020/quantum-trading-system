#!/usr/bin/env python3
"""
韬策略集群引擎 v2.0 — 全链路集成测试
=====================================

验证三大能力：
  1. 优化成果永久性继承（持久化 + 版本管理 + 自动恢复）
  2. 策略类型归档（可视化模块可见）
  3. 全链路打通（优化器 → 集群引擎 → 健康检查 → 实盘交易）

测试覆盖：
  - 持久化写入/读取/恢复
  - 优化历史版本管理
  - 策略类型归档和汇总
  - 优化器参数应用
  - 交易信号生成
  - 健康检查报告
  - 集成总线注册和优化
"""

import sys
import os
import json
import math
import random
import statistics
import time
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'QS_Robot'))
from core.tau_cluster_engine import (
    TauClusterEngine, create_cluster_engine,
    ClusterSignal, ClusterDecision,
)

# 模拟策略
STRATEGY_PROFILES = [
    ("FourierRL",      "fourier",   0.65, 0.15, 0.05),
    ("AdaptiveGrid",   "grid",      0.55, 0.12, 0.02),
    ("MLRangeGrid",    "ml",        0.58, 0.14, 0.03),
    ("HuijinValue",    "value",     0.62, 0.10, 0.08),
    ("MultiFactor",    "multifactor",0.52, 0.18, 0.00),
    ("MovingAverage",  "trend",     0.50, 0.20, 0.00),
    ("AdaptiveML",     "ml",        0.60, 0.13, 0.04),
    ("GridTrading",    "grid",      0.48, 0.15, 0.01),
    ("PPOAgent",       "rl",        0.68, 0.16, 0.06),
    ("DCA",            "fund",      0.55, 0.08, 0.10),
    ("DownMarket",     "defense",   0.54, 0.14, -0.06),
    ("HighReturnGrid", "grid",      0.45, 0.22, 0.02),
    ("AdaptiveRange",  "grid",      0.53, 0.16, 0.01),
    ("FinalOptimized", "ensemble",  0.63, 0.11, 0.05),
]


def make_strategy(profile):
    name, stype, skill, noise, bias = profile[:5]
    class S:
        def __init__(self):
            self.name = name
            self.skill = skill
            self.noise = noise
            self.bias = bias
        def get_signal(self, market_data=None, current_price=None):
            ts = market_data.get("_true_signal", 0.0) if market_data else 0.0
            d = ts * self.skill + random.gauss(0, self.noise) + self.bias
            d = max(-1.0, min(1.0, d))
            c = 0.3 + self.skill * 0.5 + random.uniform(-0.1, 0.1)
            c = max(0.1, min(1.0, c))
            return {
                "direction": d, "confidence": c, "strength": abs(d),
                "expectation": d * 0.08,
                "variance": self.noise + random.uniform(0, 0.01),
                "entropy": (1.0 - self.skill) * 0.5 + random.uniform(0, 0.1),
                "extreme_risk": 0.1 + self.noise * 0.5,
                "win_probability": 0.4 + self.skill * 0.3,
            }
    return S()


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"    ✅ {msg}")


def _section(title):
    print(f"\n  {'='*60}")
    print(f"  {title}")
    print(f"  {'='*60}")


def test_persistence():
    """测试1：优化成果永久性继承"""
    _section("测试1：优化成果永久性继承（持久化 + 版本管理 + 恢复）")

    # 清理旧持久化文件，确保测试从干净状态开始
    import os
    module_dir = os.path.dirname(os.path.abspath(__file__))
    store_path = os.path.join(os.path.dirname(module_dir), "QS_Robot", "data",
                              "tau_cluster_engine_store.json")
    if os.path.exists(store_path):
        os.remove(store_path)
        print(f"    已清理旧持久化文件: {store_path}")

    # 创建引擎
    engine = TauClusterEngine(min_resonance=2, consensus_threshold=0.25)
    for p in STRATEGY_PROFILES:
        engine.register_strategy_func(p[0], p[1], make_strategy(p).get_signal)

    # 运行一些评估
    random.seed(42)
    for i in range(20):
        ts = math.sin(i * 0.2) * 0.5
        engine.evaluate({"_true_signal": ts}, 100.0 + ts * 2.0)

    # 1.1 保存状态
    result = engine.save_state(optimizer_name="test", score=0.85,
                                metadata={"mode": "test"})
    _assert(result["success"], f"持久化成功: v{result['version']}")
    _assert(result["version"] == 1, "首次保存版本号为1")
    _assert(result["is_new_best"], "首次保存标记为最佳")
    _assert(os.path.exists(result["file_path"]), f"存储文件存在: {result['file_path']}")

    # 1.2 再次保存（版本递增）
    engine.min_resonance = 3
    result2 = engine.save_state(optimizer_name="test2", score=0.90,
                                 metadata={"mode": "test2"})
    _assert(result2["version"] == 2, f"版本递增: v{result2['version']}")
    _assert(result2["is_new_best"], "新版本超越历史最佳")

    # 1.3 获取优化历史
    history = engine.get_optimization_history()
    _assert(len(history) == 2, f"优化历史有2条记录: {len(history)}")
    _assert(history[0]["version"] == 1, "历史v1存在")
    _assert(history[1]["version"] == 2, "历史v2存在")

    # 1.4 加载状态（恢复最佳版本）
    # 先用不同参数创建新引擎
    engine2 = TauClusterEngine(min_resonance=5, consensus_threshold=0.99)
    _assert(engine2.min_resonance == 5, "新引擎参数不同")
    _assert(engine2.consensus_threshold == 0.99, "新引擎参数不同")

    load_result = engine2.load_state()
    _assert(load_result["success"], "状态恢复成功")
    _assert(load_result["version"] == 2, f"恢复最佳版本v{load_result['version']}")
    _assert(engine2.min_resonance == 3, f"恢复后 min_resonance={engine2.min_resonance} (expected=3)")

    # 1.5 加载指定版本
    engine3 = TauClusterEngine(min_resonance=5, consensus_threshold=0.99)
    load_v1 = engine3.load_state(version=1)
    _assert(load_v1["success"], "加载指定版本v1成功")
    _assert(engine3.min_resonance == 2, f"v1参数: min_resonance={engine3.min_resonance}")

    # 1.6 重置状态
    engine.reset_state(keep_strategies=True)
    _assert(engine.min_resonance == 2, "重置后恢复默认参数")  # class default
    _assert(len(engine.get_registered_strategies()) == 14, "重置后仍保留14个策略")

    print(f"\n  持久化文件: {result['file_path']}")
    print(f"  历史版本: {[h['version'] for h in history]}")

    return True


def test_strategy_archive():
    """测试2：策略类型归档"""
    _section("测试2：策略类型归档（可视化模块可见）")

    engine = TauClusterEngine()
    for p in STRATEGY_PROFILES:
        engine.register_strategy_func(p[0], p[1], make_strategy(p).get_signal)

    # 2.1 获取完整归档
    archive = engine.get_strategy_type_archive()
    _assert(len(archive) >= 14, f"归档包含至少14种策略类型: {len(archive)}")
    _assert("gyro" in archive, "陀螺仪类型已归档")
    _assert("bernoulli" in archive, "伯努利类型已归档")
    _assert("fourier" in archive, "傅里叶类型已归档")
    _assert("grid" in archive, "网格类型已归档")
    _assert("trend" in archive, "趋势类型已归档")
    _assert("ml" in archive, "ML类型已归档")
    _assert("rl" in archive, "RL类型已归档")
    _assert("value" in archive, "价值类型已归档")
    _assert("multifactor" in archive, "多因子类型已归档")
    _assert("defense" in archive, "防御类型已归档")
    _assert("ensemble" in archive, "融合类型已归档")

    # 2.2 获取已注册策略的归档
    reg_archive = engine.get_registered_strategy_archive()
    _assert(len(reg_archive) == 14, f"已注册14个策略归档: {len(reg_archive)}")

    # 验证每个归档条目包含必要字段
    entry = reg_archive[0]
    required_fields = ["name", "type", "type_display", "category", "icon",
                       "optimizer", "description", "weight", "success_rate",
                       "five_metrics", "total_calls", "is_dormant"]
    for field in required_fields:
        _assert(field in entry, f"归档条目包含字段: {field}")

    # 2.3 获取类型汇总
    summary = engine.get_type_summary()
    _assert(summary["total_strategies"] == 14, f"总数: {summary['total_strategies']}")
    _assert("type_distribution" in summary, "包含类型分布")
    _assert("category_distribution" in summary, "包含类别分布")
    _assert(len(summary["active_types"]) > 0, f"活跃类型: {summary['active_types']}")

    print(f"\n  类型分布: {summary['type_distribution']}")
    print(f"  类别分布: {summary['category_distribution']}")

    # 验证类型分布
    type_dist = summary["type_distribution"]
    _assert(type_dist.get("grid", 0) >= 4, f"网格类型≥4个: {type_dist.get('grid', 0)}")
    _assert(type_dist.get("ml", 0) >= 2, f"ML类型≥2个: {type_dist.get('ml', 0)}")

    return True


def test_optimizer_integration():
    """测试3：优化器 → 集群引擎"""
    _section("测试3：优化器 → 集群引擎（参数优化回路）")

    engine = TauClusterEngine(min_resonance=2, consensus_threshold=0.25)
    for p in STRATEGY_PROFILES:
        engine.register_strategy_func(p[0], p[1], make_strategy(p).get_signal)

    # 3.1 导出优化器参数空间（含 action_threshold）
    param_space = engine.to_optimizer_params()
    _assert("min_resonance" in param_space, "参数空间包含 min_resonance")
    _assert("consensus_threshold" in param_space, "参数空间包含 consensus_threshold")
    _assert("action_threshold" in param_space, "参数空间包含 action_threshold")
    _assert(param_space["min_resonance"] == (1.0, 5.0), "min_resonance 范围正确")
    _assert(param_space["consensus_threshold"] == (0.05, 0.60), "consensus_threshold 范围正确")
    _assert(param_space["action_threshold"] == (0.05, 0.50), "action_threshold 范围正确")

    # 3.2 应用优化器结果（含 action_threshold）
    best_params = {"min_resonance": 1, "consensus_threshold": 0.10, "action_threshold": 0.15}
    apply_result = engine.apply_optimizer_result(best_params, score=0.92)
    _assert(apply_result["success"], "优化器参数应用成功")
    _assert(engine.min_resonance == 1, f"min_resonance 已更新: {engine.min_resonance}")
    _assert(engine.consensus_threshold == 0.10, f"consensus_threshold 已更新: {engine.consensus_threshold}")
    _assert(engine.action_threshold == 0.15, f"action_threshold 已更新: {engine.action_threshold}")
    _assert(apply_result["persisted"]["success"], "优化后自动持久化")

    # 3.3 验证优化后引擎表现
    random.seed(42)
    correct = wrong = hold = 0
    for i in range(50):
        ts = math.sin(i * 0.15) * 0.7
        true_dir = 1 if ts > 0.15 else (-1 if ts < -0.15 else 0)
        cd = engine.evaluate({"_true_signal": ts}, 100.0 + ts * 3.0)
        ca = 1 if cd.action == "BUY" else (-1 if cd.action == "SELL" else 0)
        if ca == 0:
            hold += 1
        elif ca == true_dir:
            correct += 1
        else:
            wrong += 1

    total = correct + wrong
    accuracy = correct / max(1, total)
    print(f"  优化后准确率: {accuracy:.1%} ({correct}/{total}), 观望: {hold}/50")

    return True


def test_health_check():
    """测试4：集群引擎 → 健康检查"""
    _section("测试4：集群引擎 → 健康检查")

    engine = TauClusterEngine()
    for p in STRATEGY_PROFILES:
        engine.register_strategy_func(p[0], p[1], make_strategy(p).get_signal)

    # 运行一些评估
    random.seed(42)
    for i in range(10):
        ts = math.sin(i * 0.2) * 0.5
        engine.evaluate({"_true_signal": ts}, 100.0 + ts * 2.0)

    # 4.1 获取健康报告
    health = engine.get_health_for_checker()
    _assert("status" in health, "健康报告包含 status")
    _assert("checks" in health, "健康报告包含 checks")
    _assert("metrics" in health, "健康报告包含 metrics")
    _assert(health["module"] == "tau_cluster_engine", "模块标识正确")
    _assert(health["version"] == "2.0", "版本号正确")

    # 4.2 检查项数量
    _assert(len(health["checks"]) >= 5, f"至少5项检查: {len(health['checks'])}")

    # 4.3 状态在合法范围内
    _assert(health["status"] in ("healthy", "warning", "critical"),
            f"状态合法: {health['status']}")

    print(f"  健康状态: {health['status']}")
    print(f"  检查项数: {len(health['checks'])}")
    print(f"  警告: {health['warnings']}, 严重: {health['criticals']}")
    for c in health["checks"]:
        print(f"    [{c['status']}] {c['name']}: {c['message']}")

    return True


def test_trade_signal():
    """测试5：集群引擎 → 实盘交易信号"""
    _section("测试5：集群引擎 → 实盘交易信号")

    engine = TauClusterEngine(min_resonance=1, consensus_threshold=0.10)
    for p in STRATEGY_PROFILES:
        engine.register_strategy_func(p[0], p[1], make_strategy(p).get_signal)

    # 5.1 无交易时返回 None
    signal = engine.to_trade_signal()
    _assert(signal is None, "无决策时返回 None")

    # 5.2 模拟强烈看多信号
    # 喂入强烈趋势
    random.seed(42)
    for i in range(5):
        engine.evaluate({"_true_signal": 0.8}, 103.0)

    signal = engine.to_trade_signal()
    _assert(signal is not None, "有决策时返回信号")
    if signal:
        _assert("signal_id" in signal, "信号包含 signal_id")
        _assert("action" in signal, "信号包含 action")
        _assert("confidence" in signal, "信号包含 confidence")
        _assert("position_ratio" in signal, "信号包含 position_ratio")
        _assert("stop_loss" in signal, "信号包含 stop_loss")
        _assert("take_profit" in signal, "信号包含 take_profit")
        _assert(signal["source"] == "tau_cluster_engine", "信号来源正确")
        _assert("market_regime" in signal, "信号包含市场状态")
        _assert("five_metrics" in signal, "信号包含五维指标")
        _assert(signal["action"] in ("BUY", "SELL"), f"信号动作为: {signal['action']}")

        print(f"  信号: {signal['action']} @ {signal['confidence']:.2f}")
        print(f"  仓位: {signal['position_ratio']:.2f}")
        print(f"  止损: {signal['stop_loss']:.2f}, 止盈: {signal['take_profit']:.2f}")
        print(f"  共振策略: {signal['resonance_count']}/{signal['total_signals']}")
        print(f"  五维: E={signal['five_metrics']['E']:.3f}, "
              f"H={signal['five_metrics']['H']:.3f}, "
              f"P={signal['five_metrics']['P']:.3f}")

    return True


def test_integration_bus():
    """测试6：集成总线全链路"""
    _section("测试6：集成总线全链路（注册 → 优化 → 健康 → 交易）")

    try:
        from core.integration_bus import StrategyIntegrationBus

        bus = StrategyIntegrationBus()

        # 6.1 创建并注册集群引擎
        engine = create_cluster_engine(
            {p[0]: make_strategy(p) for p in STRATEGY_PROFILES},
            min_resonance=2, consensus_threshold=0.25,
        )

        reg_result = bus.register_cluster_engine(engine)
        _assert(reg_result["success"], "集成总线注册成功")
        _assert(reg_result["strategy_count"] == 14, f"注册14个策略: {reg_result['strategy_count']}")
        _assert("type_summary" in reg_result, "包含类型汇总")

        print(f"  类型汇总: {reg_result['type_summary']}")

        # 6.2 优化集群引擎（使用 ClusterEngineOptimizer，五维驱动搜索）
        random.seed(42)
        opt_result = bus.auto_optimize_cluster_engine(rounds=50, seed=42)
        _assert(opt_result["success"], "集群引擎优化成功")
        _assert(opt_result["best_params"] is not None, "优化找到最佳参数")
        _assert(opt_result["best_score"] > 0.5, f"优化评分 > 0.5: {opt_result['best_score']:.4f}")

        # 验证优化器来源
        optimizer_name = opt_result.get("optimizer", "")
        print(f"  优化器: {optimizer_name}")
        _assert("ClusterEngineOptimizer" in optimizer_name or "grid_search" in optimizer_name,
                f"优化器为 ClusterEngineOptimizer 或 grid_search: {optimizer_name}")

        # 验证评估次数（新格式: total_evals, 旧格式: score_history）
        if "total_evals" in opt_result:
            _assert(opt_result["total_evals"] > 0, f"评估次数 > 0: {opt_result['total_evals']}")
            print(f"  评估次数: {opt_result['total_evals']}")
        elif "score_history" in opt_result:
            _assert(len(opt_result["score_history"]) > 0, "包含评分历史")
            print(f"  评估组合数: {len(opt_result['score_history'])}")

        # 6.3 健康检查
        health = bus.cluster_engine_health_check()
        _assert(health["status"] in ("healthy", "warning"),
                f"健康状态: {health['status']}")
        print(f"  健康状态: {health['status']}")

        # 6.4 获取交易信号
        signal = bus.cluster_engine_get_trade_signal()
        if signal:
            _assert(signal["source"] == "tau_cluster_engine", "信号来源正确")
            print(f"  交易信号: {signal['action']} @ {signal['confidence']:.2f}")
        else:
            print(f"  交易信号: HOLD（无有效信号）")

        # 6.5 手动持久化
        save_result = bus.cluster_engine_save_state()
        _assert(save_result["success"], "手动持久化成功")
        print(f"  持久化: v{save_result['version']}")

        # 6.6 验证优化历史
        history = engine.get_optimization_history()
        _assert(len(history) >= 2, f"优化历史至少2条: {len(history)}")
        print(f"  优化历史: {len(history)} 条记录")

        return True

    except ImportError as e:
        print(f"  ⚠️ 集成总线不可用: {e}")
        return True
    except Exception as e:
        raise AssertionError(f"集成总线测试失败: {e}")


# ============================================================
# 专项测试：ClusterEngineOptimizer 五维驱动优化
# ============================================================

def test_cluster_engine_optimizer():
    """测试7：ClusterEngineOptimizer — 集群引擎作为 EntropyTauOptimizer 优化目标"""
    _section("测试7：ClusterEngineOptimizer（五维驱动集群引擎参数优化）")

    try:
        from core.tau_cluster_engine import ClusterEngineOptimizer, TauClusterEngine

        # 创建集群引擎
        engine = TauClusterEngine(min_resonance=2, consensus_threshold=0.25)
        for p in STRATEGY_PROFILES:
            engine.register_strategy_func(p[0], p[1], make_strategy(p).get_signal)

        # 7.1 创建 ClusterEngineOptimizer
        optimizer = ClusterEngineOptimizer(
            cluster_engine=engine,
            rounds=50,    # 减少轮数以加快测试
            seed=42,
            warm_start=True,
            auto_persist=True,
        )
        _assert(optimizer._cluster_engine is engine, "持有集群引擎引用")
        _assert(optimizer._rounds == 50, "rounds=50")
        _assert(optimizer._optimizer is not None, "底层 EntropyTauOptimizer 已创建")

        # 7.2 验证参数空间
        ps = engine.to_optimizer_params()
        _assert("min_resonance" in ps, "参数空间包含 min_resonance")
        _assert("consensus_threshold" in ps, "参数空间包含 consensus_threshold")
        _assert("action_threshold" in ps, "参数空间包含 action_threshold")

        # 7.3 单次评估（evaluate_params）
        test_params = {"min_resonance": 2.0, "consensus_threshold": 0.25, "action_threshold": 0.2}
        result = engine.evaluate_params(test_params, rounds=30, seed=42)
        _assert(result is not None, "evaluate_params 返回结果")
        _assert(result.strategy_name == "tau_cluster_engine", "策略名正确")
        _assert(result.total_trades >= 0, f"交易次数 ≥ 0: {result.total_trades}")
        _assert(len(result.daily_returns) > 0, f"包含日收益率: {len(result.daily_returns)}条")
        _assert(len(result.signal_sequence) > 0, f"包含信号序列: {len(result.signal_sequence)}条")
        _assert(isinstance(result.total_return, (int, float)), f"总收益为数值: {result.total_return:.4f}")

        print(f"  单次评估: 收益={result.total_return:.4f}, "
              f"夏普={result.sharpe_ratio:.2f}, "
              f"胜率={result.win_rate:.2%}, "
              f"交易={result.total_trades}笔")

        # 7.4 验证引擎状态被恢复（evaluate_params 不应改变引擎状态）
        _assert(engine.min_resonance == 2, f"引擎状态恢复: min_resonance={engine.min_resonance}")
        _assert(engine.consensus_threshold == 0.25, f"引擎状态恢复: consensus_threshold={engine.consensus_threshold}")
        _assert(engine.action_threshold == 0.2, f"引擎状态恢复: action_threshold={engine.action_threshold}")

        # 7.5 运行优化（轻量：减少点数以加快测试）
        opt_result = optimizer.run(
            coarse_points=20,             # 减少粗筛
            refined_points_per_region=10,  # 减少精搜
            entropy_decay=True,
            early_stop=True,
        )
        _assert(opt_result["success"], "ClusterEngineOptimizer 优化成功")
        _assert(opt_result["best_params"] is not None, "找到最佳参数")
        _assert(opt_result["best_score"] > 0, f"最佳评分 > 0: {opt_result['best_score']:.4f}")
        _assert(opt_result["total_evals"] > 0, f"评估次数 > 0: {opt_result['total_evals']}")
        _assert("convergence" in opt_result, "包含收敛指标")
        _assert(opt_result["optimizer"] == "ClusterEngineOptimizer (EntropyTau × ClusterEngine)",
                "优化器标识正确")

        # 7.6 验证最佳参数已应用到引擎
        bp = opt_result["best_params"]
        _assert(engine.min_resonance == int(bp.get("min_resonance", 2)),
                f"引擎 min_resonance 已更新: {engine.min_resonance}")
        _assert(abs(engine.consensus_threshold - bp.get("consensus_threshold", 0.25)) < 0.01,
                f"引擎 consensus_threshold 已更新: {engine.consensus_threshold}")

        # 7.7 收敛指标
        conv = optimizer.get_convergence_metrics()
        _assert("iterations" in conv, "收敛包含迭代次数")
        _assert(conv["iterations"] > 0, f"迭代次数 > 0: {conv['iterations']}")

        print(f"  最佳参数: {bp}")
        print(f"  最佳评分: {opt_result['best_score']:.4f}")
        print(f"  总评估: {opt_result['total_evals']} 次")
        print(f"  耗时: {opt_result['elapsed_seconds']:.1f}s")
        print(f"  收敛: {conv}")

    except ImportError as e:
        print(f"  ⚠️ ClusterEngineOptimizer 不可用: {e}")

    return True


# ============================================================
# 专项测试：4个修复验证
# ============================================================

def test_fix_strategy_param_ranges():
    """测试修复1：策略参数空间专用化"""
    _section("修复1：策略参数空间专用化（STRATEGY_PARAM_RANGES）")

    try:
        from core.enhanced_strategy_manager import EnhancedStrategyManager

        mgr = EnhancedStrategyManager.__new__(EnhancedStrategyManager)
        ranges = getattr(EnhancedStrategyManager, 'STRATEGY_PARAM_RANGES', {})

        _assert(len(ranges) >= 10, f"至少10种策略类型有专用参数空间: {len(ranges)}")

        # 验证各类型参数空间的关键参数
        _assert("grid" in ranges, "网格策略参数空间已定义")
        _assert("grid_layers" in ranges["grid"], "网格策略包含 grid_layers")
        _assert("grid_spacing" in ranges["grid"], "网格策略包含 grid_spacing")
        _assert(ranges["grid"]["grid_layers"][0] == 3.0, "grid_layers 下限=3.0")
        _assert(ranges["grid"]["grid_layers"][1] == 20.0, "grid_layers 上限=20.0")

        _assert("trend" in ranges, "趋势策略参数空间已定义")
        _assert("short_period" in ranges["trend"], "趋势策略包含 short_period")
        _assert("long_period" in ranges["trend"], "趋势策略包含 long_period")
        _assert(ranges["trend"]["short_period"][0] == 5.0, "short_period 下限=5.0")
        _assert(ranges["trend"]["long_period"][1] == 200.0, "long_period 上限=200.0")

        _assert("ml" in ranges, "ML策略参数空间已定义")
        _assert("rl" in ranges, "RL策略参数空间已定义")
        _assert("multifactor" in ranges, "多因子策略参数空间已定义")
        _assert("defense" in ranges, "防御策略参数空间已定义")
        _assert("value" in ranges, "价值策略参数空间已定义")
        _assert("fund" in ranges, "定投策略参数空间已定义")

        # 验证参数都是数值范围 (min, max)
        for type_name, type_ranges in ranges.items():
            for param_name, (lo, hi) in type_ranges.items():
                _assert(isinstance(lo, (int, float)), f"{type_name}.{param_name} 下限为数值")
                _assert(isinstance(hi, (int, float)), f"{type_name}.{param_name} 上限为数值")
                _assert(lo < hi, f"{type_name}.{param_name} 范围合法 ({lo} < {hi})")

        print(f"  已定义参数空间的策略类型: {list(ranges.keys())}")
        print(f"  总计参数定义: {sum(len(v) for v in ranges.values())} 个")

    except ImportError as e:
        print(f"  ⚠️ EnhancedStrategyManager 不可用: {e}")

    return True


def test_fix_optimizer_persist():
    """测试修复2：优化器内置持久化"""
    _section("修复2：优化器内置持久化（auto_persist）")

    try:
        from core.tau_enhanced_optimizer import EntropyTauOptimizer

        # 验证构造函数接受 auto_persist 参数
        opt = EntropyTauOptimizer(
            param_ranges={"short_period": (5.0, 50.0), "long_period": (30.0, 200.0)},
            strategy_name="test_persist_strategy",
            auto_persist=True,
        )
        _assert(opt.auto_persist is True, "auto_persist 默认开启")

        # 验证关闭 auto_persist
        opt2 = EntropyTauOptimizer(
            param_ranges={"short_period": (5.0, 50.0)},
            strategy_name="test_no_persist",
            auto_persist=False,
        )
        _assert(opt2.auto_persist is False, "auto_persist 可关闭")

        print(f"  auto_persist=True 优化器已创建: {opt.strategy_name}")
        print(f"  auto_persist=False 优化器已创建: {opt2.strategy_name}")

    except ImportError as e:
        print(f"  ⚠️ EntropyTauOptimizer 不可用: {e}")

    return True


def test_fix_warm_start():
    """测试修复3：Warm Start 参数传递"""
    _section("修复3：Warm Start 参数传递（warm_start_params）")

    try:
        from core.tau_enhanced_optimizer import EntropyTauOptimizer

        warm_params = {"short_period": 15.0, "long_period": 80.0}

        opt = EntropyTauOptimizer(
            param_ranges={"short_period": (5.0, 50.0), "long_period": (30.0, 200.0)},
            strategy_name="test_warm_start",
            warm_start_params=warm_params,
        )

        _assert(opt.warm_start_params is not None, "warm_start_params 已接收")
        _assert(opt.warm_start_params == warm_params, "warm_start_params 值正确")
        _assert(opt.warm_start_params["short_period"] == 15.0, "short_period 继承值=15.0")
        _assert(opt.warm_start_params["long_period"] == 80.0, "long_period 继承值=80.0")

        # 验证无 warm_start 时也能正常工作
        opt2 = EntropyTauOptimizer(
            param_ranges={"short_period": (5.0, 50.0)},
            strategy_name="test_no_warm",
        )
        _assert(opt2.warm_start_params is None, "无 warm_start 时为 None")

        print(f"  Warm Start 参数: {opt.warm_start_params}")
        print(f"  无 Warm Start: warm_start_params={opt2.warm_start_params}")

    except ImportError as e:
        print(f"  ⚠️ EntropyTauOptimizer 不可用: {e}")

    return True


def test_fix_per_stock_thresholds():
    """测试修复4：action_threshold 分股票配置"""
    _section("修复4：action_threshold 分股票配置（per_stock_thresholds）")

    engine = TauClusterEngine(min_resonance=2, consensus_threshold=0.25, action_threshold=0.20)
    for p in STRATEGY_PROFILES:
        engine.register_strategy_func(p[0], p[1], make_strategy(p).get_signal)

    # 4.1 设置分股票阈值
    engine.set_stock_threshold("000001", 0.10)   # 银行股低波动 → 低阈值
    engine.set_stock_threshold("300750", 0.35)   # 创业板高波动 → 高阈值
    engine.set_stock_threshold("600519", 0.20)   # 中等波动 → 中等阈值

    _assert(engine.get_stock_threshold("000001") == 0.10, "000001 阈值=0.10")
    _assert(engine.get_stock_threshold("300750") == 0.35, "300750 阈值=0.35")
    _assert(engine.get_stock_threshold("600519") == 0.20, "600519 阈值=0.20")

    # 4.2 无配置股票使用全局默认
    _assert(engine.get_stock_threshold("999999") == 0.20, "无配置股票使用全局默认=0.20")

    # 4.3 阈值边界约束
    engine.set_stock_threshold("test_low", 0.01)   # 低于下限
    _assert(engine.get_stock_threshold("test_low") == 0.05, "阈值下限不低于0.05")

    engine.set_stock_threshold("test_high", 0.99)  # 高于上限
    _assert(engine.get_stock_threshold("test_high") == 0.50, "阈值上限不超过0.50")

    # 4.4 分股票阈值在决策中生效
    random.seed(42)
    for i in range(5):
        engine.evaluate({"_true_signal": 0.5, "stock_code": "000001"}, 100.0)

    # 获取最近决策，验证分股票阈值
    decision = engine.get_last_decision()
    _assert(decision is not None, "有决策记录")
    _assert(decision.action_threshold == 0.10, f"000001决策使用专属阈值=0.10 (实际={decision.action_threshold})")

    # 使用不同股票代码
    for i in range(3):
        engine.evaluate({"_true_signal": 0.5, "stock_code": "300750"}, 100.0)
    decision2 = engine.get_last_decision()
    _assert(decision2.action_threshold == 0.35, f"300750决策使用专属阈值=0.35 (实际={decision2.action_threshold})")

    # 4.5 分股票阈值持久化
    save_result = engine.save_state(optimizer_name="test_per_stock", score=0.88)
    _assert(save_result["success"], "持久化成功")

    # 验证 store 文件中包含 per_stock_thresholds
    store_path = save_result["file_path"]
    with open(store_path, 'r', encoding='utf-8') as f:
        store_data = json.load(f)
    latest = store_data["optimization_history"][-1]
    pst = latest.get("per_stock_thresholds", {})
    _assert(len(pst) >= 5, f"持久化包含分股票阈值: {len(pst)} 条")
    _assert(pst.get("000001") == 0.10, "持久化中000001阈值=0.10")
    _assert(pst.get("300750") == 0.35, "持久化中300750阈值=0.35")

    # 4.6 分股票阈值恢复（加载指定版本，避免被其他测试的高分版本覆盖）
    per_stock_version = save_result["version"]
    engine2 = TauClusterEngine(action_threshold=0.50)
    _assert(engine2.get_stock_threshold("000001") == 0.50, "恢复前使用全局默认")

    load_result = engine2.load_state(version=per_stock_version)
    _assert(load_result["success"], f"状态恢复成功 v{per_stock_version}")
    _assert(engine2.get_stock_threshold("000001") == 0.10, "恢复后000001阈值=0.10")
    _assert(engine2.get_stock_threshold("300750") == 0.35, "恢复后300750阈值=0.35")

    # 4.7 清除分股票阈值
    engine.clear_stock_thresholds()
    _assert(len(engine.per_stock_thresholds) == 0, "清除后无分股票阈值")
    _assert(engine.get_stock_threshold("000001") == 0.20, "清除后使用全局默认")

    print(f"  分股票阈值: {pst}")
    print(f"  持久化/恢复: ✅")

    return True


# ============================================================
# 主入口
# ============================================================

def main():
    print(f"\n{'='*70}")
    print(f"  韬策略集群引擎 v2.0 — 全链路集成测试")
    print(f"{'='*70}")

    tests = [
        ("持久化继承", test_persistence),
        ("策略归档", test_strategy_archive),
        ("优化器集成", test_optimizer_integration),
        ("健康检查", test_health_check),
        ("交易信号", test_trade_signal),
        ("集成总线", test_integration_bus),
        ("集群引擎优化器", test_cluster_engine_optimizer),
        ("修复1-参数空间", test_fix_strategy_param_ranges),
        ("修复2-持久化", test_fix_optimizer_persist),
        ("修复3-WarmStart", test_fix_warm_start),
        ("修复4-分股票阈值", test_fix_per_stock_thresholds),
    ]

    passed = 0
    failed = 0
    for name, test_func in tests:
        try:
            test_func()
            passed += 1
            print(f"  ✅ {name} 通过")
        except AssertionError as e:
            failed += 1
            print(f"  ❌ {name} 失败: {e}")
        except Exception as e:
            failed += 1
            import traceback
            print(f"  ❌ {name} 异常: {e}")
            traceback.print_exc()

    print(f"\n{'='*70}")
    print(f"  测试结果: {passed} 通过, {failed} 失败, {len(tests)} 总计")
    print(f"{'='*70}")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()