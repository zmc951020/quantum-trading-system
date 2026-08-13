"""入场条件严格度分析

运行全部32策略 × 多批次模拟数据，收集每个入场条件的失败频率，
按条件严格度排名，输出分析报告。
"""
import sys
import os
import math
import random
import importlib
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.strategies.ths_strategies.base import THSBaseStrategy


# ============================================================
# 数据生成：多种市场环境 × 多个随机种子 = 大量样本
# ============================================================
def generate_market_data(scenario: str, days=120, seed=1) -> list[dict]:
    """生成指定场景的模拟K线"""
    rng = random.Random(seed)
    bars = []
    price = {"bull": 12.0, "ranging": 15.0, "bear": 22.0, "v_reversal": 12.0,
             "slow_grind": 10.0, "whipsaw": 18.0, "gap_up": 10.0, "crash": 25.0}[scenario]

    for i in range(days):
        if scenario == "bull":
            trend = 0.003
        elif scenario == "bear":
            trend = -0.003
        elif scenario == "v_reversal":
            trend = -0.004 if i < days // 2 else 0.004
        elif scenario == "crash":
            trend = -0.006 if i < days // 3 else 0.001
        elif scenario == "gap_up":
            trend = 0.005 if i < days // 4 else 0.001
        else:
            trend = 0.0

        if scenario == "whipsaw":
            cycle = math.sin(i * 2 * math.pi / 15) * price * 0.03
        elif scenario == "slow_grind":
            cycle = math.sin(i * 2 * math.pi / 40) * price * 0.02
        elif scenario == "ranging":
            cycle = math.sin(i * 2 * math.pi / 30) * price * 0.05
        else:
            cycle = 0.0

        noise = rng.gauss(0, price * 0.015)
        price += price * trend + cycle + noise
        price = max(price, 0.5)

        bar = {
            "date": (datetime(2024, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d"),
            "open": round(price * (1 - rng.uniform(0, 0.005)), 3),
            "close": round(price, 3),
            "high": round(price * (1 + rng.uniform(0, 0.015)), 3),
            "low": round(price * (1 - rng.uniform(0, 0.015)), 3),
            "volume": int(rng.lognormvariate(11, 0.5)),
        }
        bars.append(bar)
    return bars


# ============================================================
# 数据收集：猴子补丁 _log_entry_fail
# ============================================================
def collect_condition_stats(strategies, scenarios, seeds_per_scenario=5):
    """运行所有策略，收集入场条件失败统计数据"""
    # 策略级统计: {strategy_id: {condition: fail_count}}
    strategy_stats: dict[str, Counter] = defaultdict(Counter)
    # 全局条件统计: {condition: total_fail_count}
    global_condition: Counter = Counter()
    # 策略调用次数
    strategy_calls: Counter = Counter()
    # 入场成功次数
    strategy_success: Counter = Counter()

    # 保存原始方法
    original_methods = {}
    collected_data = {}

    def make_collector(sid):
        def collector(self, conditions, extra=""):
            collected_data.setdefault(sid, []).append(dict(conditions))
            # 仍然调用原始方法（输出日志）
            original_methods[sid](self, conditions, extra)
        return collector

    # 猴子补丁所有策略
    for s in strategies:
        sid = s.ID
        original_methods[sid] = s._log_entry_fail
        s._log_entry_fail = make_collector(sid).__get__(s, type(s))

    try:
        # 运行所有场景
        for scenario in scenarios:
            for seed in range(seeds_per_scenario):
                bars = generate_market_data(scenario, seed=seed * 100 + hash(scenario) % 1000)
                for s in strategies:
                    strategy_calls[s.ID] += 1
                    try:
                        signal = s.generate_signal(bars, {})
                        if signal and signal.get("action") == "buy":
                            strategy_success[s.ID] += 1
                    except Exception:
                        pass

                # 处理收集到的数据
                for sid, entries in collected_data.items():
                    for entry in entries:
                        for cond, passed in entry.items():
                            if not passed:
                                strategy_stats[sid][cond] += 1
                                global_condition[cond] += 1
                collected_data.clear()
    finally:
        # 恢复原始方法
        for s in strategies:
            if s.ID in original_methods:
                s._log_entry_fail = original_methods[s.ID]

    return strategy_stats, global_condition, strategy_calls, strategy_success


# ============================================================
# 加载策略
# ============================================================
def load_strategies():
    base = Path(r"d:\Gupiao\升级vscode\QS_Robot\core\strategies\ths_strategies")
    strategies = []
    for subdir, prefix in [("14_strategies", "14_strategies"), ("18_advanced", "18_advanced")]:
        d = base / subdir
        for f in sorted(d.glob("*.py")):
            if f.name.startswith("_"):
                continue
            mod = importlib.import_module(
                f"core.strategies.ths_strategies.{prefix}.{f.stem}"
            )
            for name in dir(mod):
                cls = getattr(mod, name)
                if (isinstance(cls, type) and issubclass(cls, THSBaseStrategy)
                        and cls is not THSBaseStrategy and cls.ID and cls.NAME):
                    strategies.append(cls())
                    break
    return strategies


# ============================================================
# 主分析
# ============================================================
def main():
    import logging
    logging.getLogger("ths").setLevel(logging.WARNING)  # 抑制日志噪音

    strategies = load_strategies()
    print(f"已加载 {len(strategies)} 个策略\n")

    scenarios = ["bull", "ranging", "bear", "v_reversal", "slow_grind", "whipsaw", "gap_up", "crash"]
    seeds_per = 5  # 每个场景5个随机种子
    total_runs = len(strategies) * len(scenarios) * seeds_per

    print(f"运行配置: {len(scenarios)} 场景 × {seeds_per} 种子 × {len(strategies)} 策略 = {total_runs} 次信号生成")
    print("场景: 牛市/震荡/熊市/V型反转/慢牛/锯齿/跳空/崩盘\n")

    strategy_stats, global_condition, strategy_calls, strategy_success = collect_condition_stats(
        strategies, scenarios, seeds_per
    )

    # ============================================================
    # 构建：条件→各策略内失败率 映射
    # ============================================================
    # cond_per_strategy_rate: {condition: [(strategy_name, fail_rate%), ...]}
    cond_per_strategy_rate: dict[str, list[tuple[str, float]]] = defaultdict(list)
    cond_avg_rate: dict[str, float] = {}

    for s in strategies:
        stats = strategy_stats.get(s.ID, Counter())
        total = strategy_calls[s.ID]
        if total == 0:
            continue
        for cond, count in stats.items():
            rate = count / total * 100
            cond_per_strategy_rate[cond].append((s.NAME, rate))

    for cond, entries in cond_per_strategy_rate.items():
        cond_avg_rate[cond] = sum(r for _, r in entries) / len(entries)

    # ============================================================
    # 报告1: 按策略内平均失败率排名（真正瓶颈）
    # ============================================================
    print("=" * 72)
    print("  报告1: 条件严格度排名（按策略内平均失败率，降序）")
    print("  这才是真正的瓶颈——在某策略内部，该条件有多常失败")
    print("=" * 72)
    print(f"  {'排名':<4} {'条件':<22} {'平均失败率':<10} {'影响策略数':<10} {'涉及策略'}")
    print(f"  {'─' * 72}")

    ranked_by_avg = sorted(cond_avg_rate.items(), key=lambda x: -x[1])
    for rank, (cond, avg_rate) in enumerate(ranked_by_avg, 1):
        affected = cond_per_strategy_rate[cond]
        n = len(affected)
        if avg_rate < 5:
            break  # 低于5%的不展示
        bar = "▓" * int(avg_rate / 4)
        names = ", ".join(f"{name}({r:.0f}%)" for name, r in affected[:4])
        if len(affected) > 4:
            names += f" +{len(affected)-4}个"
        print(f"  {rank:<4} {cond:<22} {avg_rate:>6.1f}%    {bar:<20} {n:<10} {names}")

    # ============================================================
    # 报告2: 每个策略的瓶颈条件 + 入场成功率
    # ============================================================
    print(f"\n{'=' * 72}")
    print("  报告2: 策略入场成功率 + 瓶颈条件（按成功率升序，最难的排前面）")
    print("=" * 72)

    strategy_summary = []
    for s in strategies:
        stats = strategy_stats.get(s.ID, Counter())
        total = strategy_calls[s.ID]
        if total == 0:
            continue
        success_rate = strategy_success[s.ID] / total * 100
        top_fails = stats.most_common(3)
        bottleneck = ", ".join(f"{c}({n/total*100:.0f}%)" for c, n in top_fails) if top_fails else "无"
        strategy_summary.append((s.ID, s.NAME, success_rate, bottleneck, total))

    strategy_summary.sort(key=lambda x: x[2])  # 按成功率升序

    print(f"  {'策略ID':<25} {'策略名':<18} {'成功率':<8} {'瓶颈条件(失败率)'}")
    print(f"  {'─' * 72}")
    for sid, name, sr, bottleneck, total in strategy_summary:
        if sr == 0:
            icon = "🔴"
        elif sr < 10:
            icon = "🟠"
        elif sr < 30:
            icon = "🟡"
        else:
            icon = "🟢"
        print(f"  {icon} {sid:<22} {name:<16} {sr:>5.1f}%   {bottleneck}")

    # ============================================================
    # 报告3: 高风险条件详细分析
    # ============================================================
    print(f"\n{'=' * 72}")
    print("  报告3: 高风险条件深度分析（策略内失败率 > 40%）")
    print("=" * 72)

    high_risk = [(cond, entries) for cond, entries in cond_per_strategy_rate.items()
                 if any(r > 40 for _, r in entries)]
    high_risk.sort(key=lambda x: -max(r for _, r in x[1]))

    for cond, entries in high_risk:
        entries_sorted = sorted(entries, key=lambda x: -x[1])
        print(f"\n  🔴 {cond}")
        for name, rate in entries_sorted:
            if rate > 40:
                level = "⚠️ 严重瓶颈" if rate > 70 else "🔶 主要瓶颈" if rate > 50 else "🔹 次要瓶颈"
                print(f"     {level} | {name}: 失败率 {rate:.1f}%")

    # ============================================================
    # 报告4: 可操作优化建议
    # ============================================================
    print(f"\n{'=' * 72}")
    print("  报告4: 可操作优化建议")
    print("=" * 72)

    suggestions = []

    # 检查模拟数据中无法满足的条件（如 north_ok, main_inflow, sandwich 等依赖外部数据）
    mock_only_conditions = {
        "north_ok": "北向资金流入",
        "dragon_ok": "龙虎榜量化资金",
        "sneaky_buy": "偷偷买入信号",
        "main_inflow": "主力资金净流入",
        "sandwich": "夹板单",
        "big_support": "大单托底",
        "ddy_red": "DDY红柱",
        "independent": "走势独立",
        "listed_ok": "上市时间",
        "profit_ok": "盈利条件",
        "sector_concentrated": "板块集中度",
        "all_matched": "问财全匹配",
    }

    for cond, entries in high_risk:
        max_rate = max(r for _, r in entries)
        if max_rate > 40:
            if cond in mock_only_conditions:
                suggestions.append(
                    f"  📌 {cond} (最高{max_rate:.0f}%): 依赖外部数据源({mock_only_conditions[cond]})，"
                    f"模拟数据中不可用，实盘中需验证数据源是否正常"
                )
            elif max_rate > 70:
                suggestions.append(
                    f"  ⚠️ {cond} (最高{max_rate:.0f}%): 阈值可能过于严格，建议检查原始策略文档中的参数范围"
                )
            elif max_rate > 50:
                suggestions.append(
                    f"  🔶 {cond} (最高{max_rate:.0f}%): 建议检查该条件在各策略中的阈值是否一致，考虑统一放宽"
                )

    for sg in suggestions:
        print(sg)

    if not suggestions:
        print("  所有条件均在合理范围内，无需调整。")

    return 0


if __name__ == "__main__":
    sys.exit(main())