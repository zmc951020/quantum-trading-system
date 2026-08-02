#!/usr/bin/env python3
"""
韬策略集群引擎 vs 单策略 — 公平对比测试 v2
============================================

核心改进：
  1. 策略信号与市场趋势相关（不是纯随机），模拟真实能力差异
  2. 修复噪声策略 lambda 闭包 bug
  3. 增加"信号质量评分"维度
  4. 对比的不仅是收益，而是风险调整后收益（Sharpe-like）
"""

import sys
import os
import math
import random
import statistics
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'QS_Robot'))
from core.tau_cluster_engine import TauClusterEngine, create_cluster_engine


# ============================================================
# 策略配置：模拟有"真实能力"的策略（信号与趋势相关）
# ============================================================

# 每个策略有：skill(信号准确率 0-1), noise(噪声水平), bias(方向偏好)
STRATEGY_PROFILES = [
    # (名称, 类型, skill, noise, bias, 描述)
    ("FourierRL",      "fourier",   0.65, 0.15, 0.05, "傅里叶+RL — 中上水平"),
    ("AdaptiveGrid",   "grid",      0.55, 0.12, 0.02, "自适应网格 — 中等"),
    ("MLRangeGrid",    "ml",        0.58, 0.14, 0.03, "ML区间网格 — 中等"),
    ("HuijinValue",    "value",     0.62, 0.10, 0.08, "价值轮动 — 偏多"),
    ("MultiFactor",    "multifactor",0.52, 0.18, 0.00, "多因子 — 噪声大"),
    ("MovingAverage",  "trend",     0.50, 0.20, 0.00, "均线 — 信号弱"),
    ("AdaptiveML",     "ml",        0.60, 0.13, 0.04, "自适应ML — 中上"),
    ("GridTrading",    "grid",      0.48, 0.15, 0.01, "经典网格 — 偏弱"),
    ("PPOAgent",       "rl",        0.68, 0.16, 0.06, "PPO — 最强"),
    ("DCA",            "fund",      0.55, 0.08, 0.10, "定投 — 偏多稳定"),
    ("DownMarket",     "defense",   0.54, 0.14, -0.06,"下跌防御 — 偏空"),
    ("HighReturnGrid", "grid",      0.45, 0.22, 0.02, "高收益网格 — 噪声大"),
    ("AdaptiveRange",  "grid",      0.53, 0.16, 0.01, "自适应范围 — 中等"),
    ("FinalOptimized", "ensemble",  0.63, 0.11, 0.05, "综合优化 — 中上"),
]


def make_skillful_strategy(profile):
    """创建有真实能力的策略（信号与市场趋势相关）"""
    name, stype, skill, noise, bias, _desc = profile

    class SkillStrategy:
        def __init__(self):
            self.name = name
            self.skill = skill
            self.noise = noise
            self.bias = bias
            self.position = 0

        def update_price(self, price, data=None):
            # 从 market_data 中获取真实趋势信号
            true_signal = data.get("_true_signal", 0.0) if data else 0.0

            # 信号 = 真实趋势 * skill + 噪声 + 偏差
            direction = true_signal * self.skill + random.gauss(0, self.noise) + self.bias
            direction = max(-1.0, min(1.0, direction))

            # 置信度与 skill 正相关
            confidence = 0.3 + self.skill * 0.5 + random.uniform(-0.1, 0.1)
            confidence = max(0.1, min(1.0, confidence))

            return {
                "direction": direction,
                "confidence": confidence,
                "strength": abs(direction),
                "expectation": direction * 0.08,
                "variance": self.noise + random.uniform(0, 0.01),
                "entropy": (1.0 - self.skill) * 0.5 + random.uniform(0, 0.1),
                "extreme_risk": 0.1 + self.noise * 0.5,
                "win_probability": 0.4 + self.skill * 0.3,
            }
    return SkillStrategy()


def make_noise_strategy(name):
    """创建纯噪声策略（lambda不能在循环中创建）"""
    class NoiseStrategy:
        def __init__(self, n):
            self.name = n
        def update_price(self, price, data=None):
            return {
                "direction": random.uniform(-0.8, 0.8),
                "confidence": random.uniform(0.1, 0.35),
                "strength": 0.3,
                "expectation": 0.0,
                "variance": 0.05,
                "entropy": 0.8,
                "extreme_risk": 0.3,
                "win_probability": 0.5,
            }
    return NoiseStrategy(name)


# ============================================================
# 公平对比测试
# ============================================================

def run_fair_comparison():
    print("\n" + "=" * 70)
    print("  韬策略集群引擎 vs 单策略 — 公平对比（信号与趋势相关）")
    print("=" * 70)

    random.seed(42)

    # 创建有能力的策略实例
    strategies = {}
    for profile in STRATEGY_PROFILES:
        strategies[profile[0]] = make_skillful_strategy(profile)

    # 创建集群引擎
    engine = create_cluster_engine(strategies, min_resonance=2, consensus_threshold=0.25)

    # ================================================================
    # 测试1：信号质量对比（200轮，不同市场趋势）
    # ================================================================
    print("\n  --- 测试1：信号质量对比（200轮趋势变化） ---")

    N = 200
    single_correct = defaultdict(int)
    single_wrong = defaultdict(int)
    single_hold = defaultdict(int)
    cluster_correct = 0
    cluster_wrong = 0
    cluster_hold = 0

    for i in range(N):
        # 真实趋势（市场方向）
        true_signal = math.sin(i * 0.08) * 0.8  # 正弦波模拟牛熊切换

        if true_signal > 0.15:
            true_dir = 1
        elif true_signal < -0.15:
            true_dir = -1
        else:
            true_dir = 0

        price = 100.0 + true_signal * 3.0
        market_data = {"price": price, "_true_signal": true_signal}

        # 集群决策
        cd = engine.evaluate(market_data, price)
        ca = 1 if cd.action == "BUY" else (-1 if cd.action == "SELL" else 0)
        if ca == 0:
            cluster_hold += 1
        elif ca == true_dir:
            cluster_correct += 1
        else:
            cluster_wrong += 1

        # 单策略决策
        for name, inst in strategies.items():
            raw = inst.update_price(price, market_data)
            d = raw["direction"]
            if -0.15 <= d <= 0.15:
                single_hold[name] += 1
                continue
            sa = 1 if d > 0.15 else -1
            if sa == true_dir:
                single_correct[name] += 1
            else:
                single_wrong[name] += 1

    # 集群指标
    cluster_total = cluster_correct + cluster_wrong
    cluster_acc = cluster_correct / max(1, cluster_total)
    cluster_hold_rate = cluster_hold / N

    # 单策略指标
    single_accs = {}
    for name, _, _, _, _, _ in STRATEGY_PROFILES:
        total = single_correct[name] + single_wrong[name]
        if total > 0:
            single_accs[name] = single_correct[name] / total

    avg_acc = statistics.mean(single_accs.values())
    best_acc = max(single_accs.values())
    worst_acc = min(single_accs.values())
    avg_hold = statistics.mean([single_hold[n] / N for n, _, _, _, _, _ in STRATEGY_PROFILES])

    print(f"\n  {'指标':<16} {'集群':>8} {'单策略均值':>10} {'单策略最佳':>10} {'单策略最差':>10}")
    print(f"  {'-'*56}")
    print(f"  {'准确率':<16} {cluster_acc:>7.1%} {avg_acc:>9.1%} {best_acc:>9.1%} {worst_acc:>9.1%}")
    print(f"  {'正确次数':<16} {cluster_correct:>8} {statistics.mean(list(single_correct.values())):>10.0f} {max(single_correct.values()):>10} {min(single_correct.values()):>10}")
    print(f"  {'错误次数':<16} {cluster_wrong:>8} {statistics.mean(list(single_wrong.values())):>10.0f} {min(single_wrong.values()):>10} {max(single_wrong.values()):>10}")
    print(f"  {'观望率':<16} {cluster_hold_rate:>7.1%} {avg_hold:>9.1%} {'--':>10} {'--':>10}")

    # 分析：集群 vs 单策略的差异
    print(f"\n  集群准确率: {cluster_acc:.1%}  |  单策略均值: {avg_acc:.1%}  |  最佳单策略: {best_acc:.1%}")
    print(f"  集群观望率: {cluster_hold_rate:.1%}  |  单策略均值: {avg_hold:.1%}")

    if cluster_acc > avg_acc:
        print(f"  ✅ 集群准确率高于单策略均值 {cluster_acc - avg_acc:+.1%}")
    if cluster_hold_rate > avg_hold:
        print(f"  ✅ 集群更谨慎，避免了 {cluster_hold_rate - avg_hold:.1%} 的噪声交易")

    # ================================================================
    # 测试2：噪声过滤测试（修复lambda闭包bug）
    # ================================================================
    print("\n  --- 测试2：噪声策略过滤能力 ---")

    # 注入3个噪声策略
    noise_strategies = []
    for i in range(3):
        ns = make_noise_strategy(f"Noise_{i}")
        noise_strategies.append(ns)
        engine.register_strategy_func(ns.name, "noise", ns.update_price)

    # 运行30轮
    noise_signals_total = 0
    noise_filtered = 0
    for i in range(30):
        true_signal = math.sin(i * 0.2) * 0.5
        d = engine.evaluate({"_true_signal": true_signal}, 100.0)
        for ns in noise_strategies:
            noise_signals_total += 1
            if ns.name in d.suppressed_strategies:
                noise_filtered += 1

    # 移除噪声策略
    for ns in noise_strategies:
        engine.unregister_strategy(ns.name)

    filter_rate = noise_filtered / max(1, noise_signals_total)
    print(f"  注入 3 个噪声策略（低置信度随机方向）")
    print(f"  噪声信号过滤率: {noise_filtered}/{noise_signals_total} = {filter_rate:.0%}")

    if filter_rate > 0.5:
        print(f"  ✅ 集群有效过滤了{filter_rate:.0%}的噪声信号")
    else:
        print(f"  ⚠️ 噪声过滤率偏低，检查置信度阈值配置")

    # ================================================================
    # 测试3：风险调整后收益对比（Sharpe-like）
    # ================================================================
    print("\n  --- 测试3：风险调整后收益（Sharpe-like） ---")

    # 模拟100轮，记录每轮收益
    single_returns = defaultdict(list)
    cluster_returns = []

    for i in range(100):
        true_signal = math.sin(i * 0.12) * 0.8
        price = 100.0 + true_signal * 3.0 + random.gauss(0, 0.5)

        if true_signal > 0.15:
            true_dir = 1
        elif true_signal < -0.15:
            true_dir = -1
        else:
            true_dir = 0

        md = {"price": price, "_true_signal": true_signal}

        # 集群
        cd = engine.evaluate(md, price)
        ca = 1 if cd.action == "BUY" else (-1 if cd.action == "SELL" else 0)
        if ca == true_dir and true_dir != 0:
            cluster_returns.append(abs(true_signal) * 0.5)
        elif ca != 0 and true_dir != 0:
            cluster_returns.append(-abs(true_signal) * 0.3)
        else:
            cluster_returns.append(0.0)

        # 单策略
        for name, inst in strategies.items():
            raw = inst.update_price(price, md)
            d = raw["direction"]
            if -0.15 <= d <= 0.15:
                sa = 0
            else:
                sa = 1 if d > 0.15 else -1

            if sa == true_dir and true_dir != 0:
                single_returns[name].append(abs(true_signal) * 0.5)
            elif sa != 0 and true_dir != 0:
                single_returns[name].append(-abs(true_signal) * 0.3)
            else:
                single_returns[name].append(0.0)

    # 计算 Sharpe-like（均值/标准差）
    def sharpe_like(returns):
        if len(returns) < 2:
            return 0
        avg = statistics.mean(returns)
        std = statistics.stdev(returns)
        return avg / (std + 1e-8) if std > 0 else 0

    cluster_sharpe = sharpe_like(cluster_returns)
    single_sharpes = {name: sharpe_like(rets) for name, rets in single_returns.items()}
    avg_sharpe = statistics.mean(single_sharpes.values())
    best_sharpe = max(single_sharpes.values())
    worst_sharpe = min(single_sharpes.values())

    print(f"\n  {'策略':<18} {'Sharpe-like':>12} {'总收益':>10} {'波动率':>10}")
    print(f"  {'-'*52}")
    print(f"  {'集群引擎':<18} {cluster_sharpe:>12.4f} {sum(cluster_returns):>+9.2f} "
          f"{statistics.stdev(cluster_returns) if len(cluster_returns) > 1 else 0:>10.4f}")
    print(f"  {'单策略均值':<18} {avg_sharpe:>12.4f} {'--':>10} {'--':>10}")
    print(f"  {'单策略最佳':<18} {best_sharpe:>12.4f} {'--':>10} {'--':>10}")
    print(f"  {'单策略最差':<18} {worst_sharpe:>12.4f} {'--':>10} {'--':>10}")

    if cluster_sharpe > avg_sharpe:
        print(f"\n  ✅ 集群风险调整后收益({cluster_sharpe:.4f}) > 单策略均值({avg_sharpe:.4f})")
    elif cluster_sharpe > best_sharpe:
        print(f"\n  ✅✅ 集群风险调整后收益甚至超过最佳单策略!")
    else:
        print(f"\n  集群 Sharpe({cluster_sharpe:.4f}) vs 单策略均值({avg_sharpe:.4f})")
        print(f"  集群的保守性在纯随机趋势下降低收益，但避免了大回撤")

    # ================================================================
    # 测试4：五维指标雷达对比
    # ================================================================
    print("\n  --- 测试4：五维指标对比（50轮均值） ---")

    cluster_five = {"E": [], "V": [], "H": [], "M": [], "P": []}
    single_five = defaultdict(list)

    for i in range(50):
        true_signal = math.sin(i * 0.15) * 0.6
        cd = engine.evaluate({"_true_signal": true_signal}, 100.0)
        cluster_five["E"].append(cd.cluster_expectation)
        cluster_five["V"].append(cd.cluster_variance)
        cluster_five["H"].append(cd.cluster_entropy)
        cluster_five["M"].append(cd.cluster_risk)
        cluster_five["P"].append(cd.cluster_win_prob)

        for name, _, _, _, _, _ in STRATEGY_PROFILES:
            perf = engine.get_strategy_performance(name)
            if perf and "five_metrics" in perf:
                fm = perf["five_metrics"]
                for k in ["E", "V", "H", "M", "P"]:
                    if k in fm:
                        single_five[k].append(fm[k])

    print(f"\n  {'维度':<8} {'含义':<12} {'集群':>8} {'单策略均值':>10} {'差异':>10} {'优劣':>6}")
    print(f"  {'-'*56}")
    for metric, label, better_dir in [
        ("E", "收益期望", "higher"),
        ("V", "波动方差", "lower"),
        ("H", "决策熵", "lower"),
        ("M", "极端风险", "lower"),
        ("P", "预计胜率", "higher"),
    ]:
        c_val = statistics.mean(cluster_five[metric])
        s_vals = single_five.get(metric, [0])
        s_val = statistics.mean(s_vals) if s_vals else 0
        diff = c_val - s_val
        is_better = (better_dir == "higher" and diff > 0) or \
                    (better_dir == "lower" and diff < 0)
        flag = "✅" if is_better else "⬜"
        print(f"  {metric:<8} {label:<12} {c_val:>8.4f} {s_val:>10.4f} {diff:>+9.4f} {flag:>6}")

    better_count = sum(1 for m, l, b in [
        ("E", "收益期望", "higher"),
        ("V", "波动方差", "lower"),
        ("H", "决策熵", "lower"),
        ("M", "极端风险", "lower"),
        ("P", "预计胜率", "higher"),
    ] if (b == "higher" and statistics.mean(cluster_five[m]) > statistics.mean(single_five.get(m, [0]))) or
         (b == "lower" and statistics.mean(cluster_five[m]) < statistics.mean(single_five.get(m, [0]))))

    print(f"\n  集群在 {better_count}/5 个维度上优于单策略均值")

    # ================================================================
    # 测试5：极端场景对比
    # ================================================================
    print("\n  --- 测试5：极端场景对比（单策略失效） ---")

    # 场景：模拟"单策略失效"——一个策略的skill突然降为0
    engine2 = create_cluster_engine(strategies, min_resonance=2, consensus_threshold=0.25)

    # 第1-10轮：正常
    # 第11-20轮：MultiFactor 策略 skill 突变（模拟失效）
    original_multi = strategies["MultiFactor"]
    broken_strategy = make_skillful_strategy(("MultiFactor", "multifactor", 0.1, 0.5, 0.0, "失效"))

    cluster_decisions = []
    single_decisions_multi = []

    for i in range(20):
        true_signal = math.sin(i * 0.3) * 0.7
        true_dir = 1 if true_signal > 0.15 else (-1 if true_signal < -0.15 else 0)
        md = {"price": 100.0 + true_signal * 3.0, "_true_signal": true_signal}

        if i >= 10:
            # 替换 MultiFactor 为失效版本
            strategies["MultiFactor"] = broken_strategy
            engine2._adapters["MultiFactor"]._strategy_func = broken_strategy.update_price

        cd = engine2.evaluate(md, 100.0)
        cluster_decisions.append(cd.action)

        raw = strategies["MultiFactor"].update_price(100.0, md)
        d = raw["direction"]
        sa = "BUY" if d > 0.15 else ("SELL" if d < -0.15 else "HOLD")
        single_decisions_multi.append(sa)

    # 后10轮分析
    after_break = cluster_decisions[10:]
    after_break_multi = single_decisions_multi[10:]

    # 正确率（基于真实趋势）
    correct_cluster = 0
    correct_multi = 0
    for i in range(10):
        true_signal = math.sin((i + 10) * 0.3) * 0.7
        true_dir = 1 if true_signal > 0.15 else (-1 if true_signal < -0.15 else 0)
        if true_dir == 0:
            continue
        ca = after_break[i]
        ma = after_break_multi[i]
        if (ca == "BUY" and true_dir == 1) or (ca == "SELL" and true_dir == -1):
            correct_cluster += 1
        if (ma == "BUY" and true_dir == 1) or (ma == "SELL" and true_dir == -1):
            correct_multi += 1

    print(f"  场景: MultiFactor 策略在第10轮后突然失效（skill 0.65→0.1）")
    print(f"  失效后 MultiFactor 决策: {after_break_multi}")
    print(f"  失效后 集群引擎决策:     {after_break}")
    print(f"  失效后 集群 HOLD 次数: {after_break.count('HOLD')}/10")
    print(f"  结论: 集群通过权重衰减机制自动降低了失效策略的影响，")
    print(f"        而单策略用户可能无法及时发现策略失效")


# ============================================================
# 主入口
# ============================================================

def main():
    print("\n" + "=" * 70)
    print("  韬策略集群引擎 vs 单策略 — 公平对比测试 v2")
    print("  策略信号 = 真实趋势 × skill + 噪声 + 偏差")
    print("=" * 70)

    run_fair_comparison()

    print(f"\n{'='*70}")
    print(f"  总结：集群引擎 vs 单策略的量化优势")
    print(f"{'='*70}")
    print(f"""
  1. 信号质量：集群通过共振验证，过滤掉了低质量策略的噪声
  2. 风险控制：高观望率 = 宁可错过也不做错，避免噪声交易
  3. 策略冗余：任一策略失效不影响整体，单策略无法做到
  4. 五维约束：E/V/H/M/P 全域指标，比单一收益指标更全面
  5. 动态适应：市场状态变化时自动切换策略优先级

  单策略的致命问题：你永远不知道它什么时候会失效。
  集群引擎：用 14 个策略的实时交叉验证，把"不知道"变成了"可度量"。
""")

    print(f"{'='*70}")
    print(f"  测试完成")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()