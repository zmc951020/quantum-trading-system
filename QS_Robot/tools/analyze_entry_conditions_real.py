"""入场条件严格度分析 — 真实历史数据版

与 analyze_entry_conditions.py 的区别：
  - 使用 AKShare 真实 A 股 K 线数据，而非随机游走模拟数据
  - 为外部字段（北向资金、利润增长等）注入真实概率分布的模拟值
  - 输出格式与旧版完全一致，方便对比
"""
import sys
import os
import random
import importlib
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.strategies.ths_strategies.base import THSBaseStrategy

# ============================================================
# 真实数据获取
# ============================================================
def fetch_real_kline(symbol: str, days: int = 120) -> list[dict] | None:
    """从 AKShare 获取真实K线，转为策略标准 bar 格式"""
    try:
        from core.data_fetcher import get_data_fetcher
        fetcher = get_data_fetcher()
        data = fetcher.get_kline(symbol, period="daily", days=days)
        if not data or data.get("count", 0) < 60:
            return None
        closes = data.get("closes", [])
        opens = data.get("opens", [])
        highs = data.get("highs", [])
        lows = data.get("lows", [])
        vols = data.get("volumes", [])
        dates = data.get("dates", [])
        n = min(len(closes), len(opens), len(highs), len(lows), len(vols))
        bars = []
        for i in range(n):
            bars.append({
                "date": str(dates[i]) if i < len(dates) else f"D{i}",
                "open": float(opens[i]), "close": float(closes[i]),
                "high": float(highs[i]), "low": float(lows[i]),
                "volume": float(vols[i]),
            })
        return bars
    except Exception as e:
        print(f"  [WARN] 获取 {symbol} 失败: {e}")
        return None


# ============================================================
# 外部字段注入：基于真实概率分布模拟
# ============================================================
def inject_external_fields(bars: list[dict], symbol: str) -> list[dict]:
    """为每个 bar 注入外部数据字段，模拟真实市场中的出现概率"""
    rng = random.Random(hash(symbol) + 42)
    n = len(bars)
    for i, bar in enumerate(bars):
        # 北向资金：约35%的交易日有净流入>10亿
        bar["north_inflow"] = rng.uniform(5, 80) if rng.random() < 0.35 else rng.uniform(-20, 8)
        # 板块集中度：约40%概率
        bar["sector_concentrated"] = rng.random() < 0.40
        # 龙虎榜量化净买：约25%概率
        bar["dragon_list"] = {"quant_net_buy": rng.uniform(100, 5000) if rng.random() < 0.25 else 0}
        # 利润增长：约60%的股票有正增长
        bar["profit_growth"] = rng.uniform(-30, 80) if rng.random() < 0.60 else rng.uniform(-50, -5)
        # 市值（亿）：偏中小盘（龙头股通常在20-80亿），约70%在此区间
        bar["market_cap"] = rng.uniform(20, 80) if rng.random() < 0.70 else rng.uniform(5, 200)
        bar["circulating_cap"] = bar["market_cap"] * rng.uniform(0.6, 0.95)
        # ST标记：约5%概率
        bar["is_st"] = rng.random() < 0.05
        # 主力资金净流入：约40%概率
        bar["main_inflow"] = rng.uniform(100, 10000) if rng.random() < 0.40 else rng.uniform(-5000, 0)
        # ETF标记
        bar["is_etf"] = symbol.startswith("51") or symbol.startswith("15")
        # 板块数据（5句口诀抓龙头 k2/k5 需要）
        bar["sector"] = {
            "limit_up_count": rng.randint(1, 8) if rng.random() < 0.50 else 0,
            "pct_change": rng.uniform(-2, 4),
        }
        # 夹板单/大单托底/DDY/走势独立：各约35%概率
        bar["sandwich"] = rng.random() < 0.35
        bar["big_support"] = rng.random() < 0.35
        bar["ddy_red"] = rng.random() < 0.35
        bar["independent"] = rng.random() < 0.35
        # 问财匹配：约50%概率
        bar["all_matched"] = rng.random() < 0.50
    return bars


# ============================================================
# 股票池：30只代表性A股
# ============================================================
STOCK_POOL = [
    "000001",  # 平安银行
    "000002",  # 万科A
    "000333",  # 美的集团
    "000651",  # 格力电器
    "000858",  # 五粮液
    "002415",  # 海康威视
    "002594",  # 比亚迪
    "002230",  # 科大讯飞
    "300750",  # 宁德时代
    "300059",  # 东方财富
    "600519",  # 贵州茅台
    "600036",  # 招商银行
    "600276",  # 恒瑞医药
    "600887",  # 伊利股份
    "600030",  # 中信证券
    "600900",  # 长江电力
    "601318",  # 中国平安
    "601166",  # 兴业银行
    "601012",  # 隆基绿能
    "600585",  # 海螺水泥
    "600809",  # 山西汾酒
    "002475",  # 立讯精密
    "000568",  # 泸州老窖
    "600690",  # 海尔智家
    "002714",  # 牧原股份
    "300124",  # 汇川技术
    "601899",  # 紫金矿业
    "002352",  # 顺丰控股
    "600031",  # 三一重工
    "000725",  # 京东方A
]


# ============================================================
# 数据收集：猴子补丁
# ============================================================
def collect_condition_stats(strategies, all_bars_sets: list[tuple[str, list[dict]]]):
    """运行所有策略，收集入场条件失败统计数据"""
    strategy_stats: dict[str, Counter] = defaultdict(Counter)
    global_condition: Counter = Counter()
    strategy_calls: Counter = Counter()
    strategy_success: Counter = Counter()
    original_methods = {}
    collected_data = {}

    def make_collector(sid):
        def collector(self, conditions, extra=""):
            collected_data.setdefault(sid, []).append(dict(conditions))
            original_methods[sid](self, conditions, extra)
        return collector

    for s in strategies:
        sid = s.ID
        original_methods[sid] = s._log_entry_fail
        s._log_entry_fail = make_collector(sid).__get__(s, type(s))

    try:
        for symbol, bars in all_bars_sets:
            for s in strategies:
                strategy_calls[s.ID] += 1
                try:
                    signal = s.generate_signal(bars, {})
                    if signal and signal.get("action") == "buy":
                        strategy_success[s.ID] += 1
                except Exception:
                    pass

            for sid, entries in collected_data.items():
                for entry in entries:
                    for cond, passed in entry.items():
                        if not passed:
                            strategy_stats[sid][cond] += 1
                            global_condition[cond] += 1
            collected_data.clear()
    finally:
        for s in strategies:
            if s.ID in original_methods:
                s._log_entry_fail = original_methods[s.ID]

    return strategy_stats, global_condition, strategy_calls, strategy_success


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
    logging.getLogger("ths").setLevel(logging.WARNING)

    strategies = load_strategies()
    print(f"已加载 {len(strategies)} 个策略\n")

    # 获取真实数据
    print("=" * 72)
    print("  正在从 AKShare 获取真实 K 线数据...")
    print("=" * 72)
    all_bars_sets = []
    success_count = 0
    for symbol in STOCK_POOL:
        bars = fetch_real_kline(symbol, days=120)
        if bars:
            bars = inject_external_fields(bars, symbol)
            all_bars_sets.append((symbol, bars))
            success_count += 1
            print(f"  ✅ {symbol} ({len(bars)} 条)")
        else:
            print(f"  ❌ {symbol} 获取失败")

    if success_count == 0:
        print("\n⚠️ AKShare 数据获取全部失败，降级为模拟数据...")
        # 降级：使用模拟数据但注入外部字段
        from analyze_entry_conditions import generate_market_data
        scenarios = ["bull", "ranging", "bear", "v_reversal", "slow_grind", "whipsaw", "gap_up", "crash"]
        for scenario in scenarios:
            for seed in range(3):
                bars = generate_market_data(scenario, seed=seed * 100 + hash(scenario) % 1000)
                bars = inject_external_fields(bars, f"mock_{scenario}_{seed}")
                all_bars_sets.append((f"mock_{scenario}_{seed}", bars))

    total_runs = len(strategies) * len(all_bars_sets)
    print(f"\n运行配置: {len(all_bars_sets)} 组数据 × {len(strategies)} 策略 = {total_runs} 次信号生成\n")

    strategy_stats, global_condition, strategy_calls, strategy_success = collect_condition_stats(
        strategies, all_bars_sets
    )

    # ============================================================
    # 报告1: 条件严格度排名
    # ============================================================
    cond_per_strategy_rate: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for s in strategies:
        stats = strategy_stats.get(s.ID, Counter())
        total = strategy_calls[s.ID]
        if total == 0:
            continue
        for cond, count in stats.items():
            rate = count / total * 100
            cond_per_strategy_rate[cond].append((s.NAME, rate))

    print("=" * 72)
    print("  报告1: 条件严格度排名（真实数据 + 外部字段模拟）")
    print("=" * 72)
    print(f"  {'排名':<4} {'条件':<22} {'平均失败率':<10} {'影响策略数':<10} {'涉及策略'}")
    print(f"  {'─' * 72}")

    ranked = sorted(cond_per_strategy_rate.items(), key=lambda x: -max(r for _, r in x[1]) if x[1] else 0)
    for rank, (cond, entries) in enumerate(ranked, 1):
        max_rate = max(r for _, r in entries)
        if max_rate < 5:
            break
        n = len(entries)
        bar = "▓" * int(max_rate / 4)
        names = ", ".join(f"{name}({r:.0f}%)" for name, r in sorted(entries, key=lambda x: -x[1])[:4])
        if len(entries) > 4:
            names += f" +{len(entries)-4}个"
        print(f"  {rank:<4} {cond:<22} {max_rate:>6.1f}%    {bar:<20} {n:<10} {names}")

    # ============================================================
    # 报告2: 策略入场成功率
    # ============================================================
    print(f"\n{'=' * 72}")
    print("  报告2: 策略入场成功率 + 瓶颈条件（真实数据）")
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

    strategy_summary.sort(key=lambda x: x[2])
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
    # 报告3: P0 策略专项对比
    # ============================================================
    p0_ids = {"16_three_line_cross", "08_volume_ladder", "06_expma_double_cross"}
    print(f"\n{'=' * 72}")
    print("  报告3: P0/P1 策略条件详细对比")
    print("=" * 72)
    for s in strategies:
        if s.ID in p0_ids:
            stats = strategy_stats.get(s.ID, Counter())
            total = strategy_calls[s.ID]
            sr = strategy_success[s.ID] / total * 100 if total > 0 else 0
            print(f"\n  📊 {s.NAME} ({s.ID})")
            print(f"     入场成功率: {sr:.1f}% ({strategy_success[s.ID]}/{total})")
            print(f"     条件明细:")
            for cond, count in stats.most_common():
                rate = count / total * 100 if total > 0 else 0
                level = "🔴" if rate > 50 else "🟡" if rate > 30 else "🟢"
                print(f"       {level} {cond}: 失败 {count}次 ({rate:.1f}%)")

    return 0


if __name__ == "__main__":
    sys.exit(main())