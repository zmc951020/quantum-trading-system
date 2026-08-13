"""低位筛选 + 热启动确认"""
import os, sys, math

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


def check_low_position(bars, i):
    """低位5选2条件检查
    返回: (低位评分, 匹配条件列表, 低位星级)
    """
    if i < 60:
        return 0, [], 0

    score = 0
    details = []

    # 条件1: 价格分位 - 近60日价格的20%分位
    prices_60 = [bars[j]["close"] for j in range(i - 59, i + 1)]
    pct_rank = sum(1 for p in prices_60 if p <= bars[i]["close"]) / 60
    if pct_rank <= 0.20:
        score += 1
        details.append(f"价格分位{pct_rank:.1%}")

    # 条件2: 跌幅条件 - 近1年最高价跌超30%
    if i >= 200:
        high_1y = max(bars[j]["high"] for j in range(i - 199, i + 1))
        drawdown = (high_1y - bars[i]["close"]) / high_1y
    else:
        high_all = max(bars[j]["high"] for j in range(i + 1))
        drawdown = (high_all - bars[i]["close"]) / high_all
    if drawdown >= 0.30:
        score += 1
        details.append(f"跌幅{drawdown:.0%}")

    # 条件3: 底部形态 - W底/底背离
    if i >= 40:
        mid = i - 20
        low1 = min(bars[j]["low"] for j in range(i - 39, mid + 1))
        low2 = min(bars[j]["low"] for j in range(mid + 1, i + 1))
        if low1 > 0 and low2 > 0 and abs(low1 - low2) / low1 < 0.03:
            high_mid = max(bars[j]["high"] for j in range(i - 39, i + 1))
            if high_mid > low1 * 1.03:
                score += 1
                details.append("W底")

    # 条件4: 底部共振 - 日K+周K同时在底部
    if i >= 20:
        low_20 = min(bars[j]["low"] for j in range(i - 19, i + 1))
        if bars[i]["close"] <= low_20 * 1.05:
            if i >= 60:
                low_60 = min(bars[j]["low"] for j in range(i - 59, i + 1))
                if bars[i]["close"] <= low_60 * 1.08:
                    score += 1
                    details.append("日周共振")

    # 条件5: 估值分位 - 用跌幅替代(缺PE数据)
    if drawdown >= 0.50:
        score += 1
        details.append(f"腰斩{drawdown:.0%}")

    # 星级映射
    if score >= 4:
        stars = 5
    elif score >= 3:
        stars = 3
    elif score >= 2:
        stars = 2
    else:
        stars = 0

    return score, details, stars


def check_hot_start(bars, i):
    """热启动评分: 0-3分，每项1分不设阈值
    返回: (得分, 匹配条件列表)
    """
    if i < 20:
        return 0, []

    score = 0
    details = []

    # 条件1: 量能异动 - 近5日最大量 > 20日均量 × 1.3
    vol_ma20 = sum(bars[j]["volume"] for j in range(i - 19, i + 1)) / 20
    max_vol_5 = max(bars[j]["volume"] for j in range(max(0, i - 4), i + 1))
    if max_vol_5 > vol_ma20 * 1.3:
        score += 1
        ratio = max_vol_5 / vol_ma20
        details.append(f"放量{ratio:.1f}x")

    # 条件2: 中长期趋势未破位 - 收盘价 > MA60
    if i >= 60:
        ma60 = sum(bars[j]["close"] for j in range(i - 59, i + 1)) / 60
        if bars[i]["close"] > ma60:
            score += 1
            details.append("站上MA60")

    # 条件3: 止跌信号 - 5日最低价 > 10日最低价
    if i >= 10:
        low_5 = min(bars[j]["low"] for j in range(i - 4, i + 1))
        low_10 = min(bars[j]["low"] for j in range(i - 9, i + 1))
        if low_5 >= low_10:
            score += 1
            details.append("止跌")

    return score, details


def calc_composite_score(bars, i):
    """综合评分: 低位(0-5) + 热启动(0-3) = 0-8
    返回: (低位分, 低位明细, 热启动分, 热启动明细, 综合分)
    """
    low_score, low_details, _ = check_low_position(bars, i)
    hot_score, hot_details = check_hot_start(bars, i)
    return low_score, low_details, hot_score, hot_details, low_score + hot_score


def filter_signal(low_score, low_details, low_stars, is_hot, hot_details,
                  regime_label, position_limit, date):
    """综合过滤: 低位+热启动+大盘环境 → 是否通过"""
    if regime_label == "bear" and position_limit < 0.3:
        return False, "熊市禁止", None

    if low_stars == 0:
        return False, "非低位", None

    if not is_hot:
        return False, "无热启动", None

    quality = "A" if low_stars >= 4 else "B" if low_stars >= 3 else "C"
    return True, f"通过({quality})", quality


def apply_optimization_base(bars, strategies, strategy_instances, regimes,
                            index_bars=None):
    """应用优化底座: 大盘环境 + 低位筛选 + 热启动
    返回: {策略名: [(日期, 价格, 质量等级, 原始AND条件数), ...]}
    """
    from collections import defaultdict
    results = defaultdict(list)
    stats = {"total_signals": 0, "filtered_signals": 0, "by_regime": 0,
             "by_low": 0, "by_hot": 0}

    for i in range(60, len(bars)):
        date = bars[i]["date"]
        regime = regimes[i] if i < len(regimes) else {"label": "shake", "position_limit": 0.5}

        for mod_name, strategy in strategies:
            try:
                sig = strategy.generate_signal(bars[:i + 1], {})
                if sig is None or sig.get("action") != "buy":
                    continue
                stats["total_signals"] += 1

                if regime["label"] == "bear":
                    stats["by_regime"] += 1
                    continue

                low_score, low_details, low_stars = check_low_position(bars, i)
                if low_stars == 0:
                    stats["by_low"] += 1
                    continue

                is_hot, hot_details = check_hot_start(bars, i)
                if not is_hot:
                    stats["by_hot"] += 1
                    continue

                conds = getattr(strategy, "_last_entry_conditions", {})
                key = mod_name.replace("_", " ").replace("0", "").replace("1", "").replace("2", "").replace("3", "").replace("4", "").replace("5", "").replace("6", "").replace("7", "").replace("8", "").replace("9", "")
                results[key].append({
                    "date": date, "price": sig.get("price", bars[i]["close"]),
                    "quality": "A" if low_stars >= 4 else "B" if low_stars >= 3 else "C",
                    "low_score": low_score, "low_details": low_details,
                    "hot_details": hot_details,
                    "and_conds": len(conds),
                })
                stats["filtered_signals"] += 1
            except Exception:
                pass

    return dict(results), stats


if __name__ == "__main__":
    import json
    from tools.regime_judge import load_index_data, get_regime_series

    cache_dir = os.path.join(PROJECT_ROOT, "data", "bus_cache")
    import random
    files = random.sample(os.listdir(cache_dir), min(5, len(os.listdir(cache_dir))))

    print("低位+热启动 抽样检查 (5只股票):")
    for fname in files:
        if not fname.endswith(".json"):
            continue
        d = json.load(open(os.path.join(cache_dir, fname), encoding="utf-8"))
        data = d["data"]
        n = len(data["dates"])
        bars = [{"date": data["dates"][i], "open": float(data["opens"][i]),
                 "high": float(data["highs"][i]), "low": float(data["lows"][i]),
                 "close": float(data["closes"][i]), "volume": float(data["volumes"][i])}
                for i in range(n)]

        total_low = 0
        total_hot = 0
        for i in range(60, n):
            _, _, stars = check_low_position(bars, i)
            if stars >= 2:
                total_low += 1
                is_hot, _ = check_hot_start(bars, i)
                if is_hot:
                    total_hot += 1

        code = data["symbol"]
        low_pct = total_low / (n - 60) * 100 if n > 60 else 0
        hot_pct = total_hot / (n - 60) * 100 if n > 60 else 0
        print(f"  {code}: 低位{low_pct:.0f}% 热启动{hot_pct:.0f}% (共{n}根K线)")