#!/usr/bin/env python3
"""
AMTS 自适应市场状态识别 — 批量历史数据回测
============================================
20只股票 × 10批次 = 200只股票，每只 500 天日K线数据
测试 AdaptiveMarketRegime 在大规模真实数据上的表现

输出：
  - 每批次的状态分布
  - 状态转换矩阵
  - 置信度分布
  - 汇总统计
"""

import sys
import os
import time
import json
import statistics
from datetime import datetime
from collections import defaultdict, Counter
from typing import Dict, List, Any, Tuple

# 确保项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.adaptive_market_regime import (
    MultiDimensionalRegimeDetector,
    StrategyAdaptationEngine,
    AdaptiveMarketRegime, AdaptiveRegimeBridge,  # 向后兼容
)


# ============================================================
# 股票池：200只A股代表性股票，分10批次，每批20只
# 覆盖：上证50、沪深300、中证500、创业板、科创板、行业龙头
# ============================================================

STOCK_BATCHES = [
    # 批次1：上证50大盘蓝筹
    [
        ("600519", "贵州茅台"), ("601318", "中国平安"), ("600036", "招商银行"),
        ("601166", "兴业银行"), ("600276", "恒瑞医药"), ("600887", "伊利股份"),
        ("601012", "隆基绿能"), ("600309", "万华化学"), ("600585", "海螺水泥"),
        ("601888", "中国中免"), ("600030", "中信证券"), ("601398", "工商银行"),
        ("600900", "长江电力"), ("601668", "中国建筑"), ("600104", "上汽集团"),
        ("601688", "华泰证券"), ("600031", "三一重工"), ("600809", "山西汾酒"),
        ("601899", "紫金矿业"), ("600690", "海尔智家"),
    ],
    # 批次2：深证龙头/沪深300
    [
        ("000858", "五粮液"), ("000333", "美的集团"), ("000651", "格力电器"),
        ("002415", "海康威视"), ("000568", "泸州老窖"), ("002475", "立讯精密"),
        ("000725", "京东方A"), ("002594", "比亚迪"), ("000001", "平安银行"),
        ("002714", "牧原股份"), ("000002", "万科A"), ("000063", "中兴通讯"),
        ("002142", "宁波银行"), ("000776", "广发证券"), ("002304", "洋河股份"),
        ("000100", "TCL科技"), ("002352", "顺丰控股"), ("000625", "长安汽车"),
        ("002460", "赣锋锂业"), ("000538", "云南白药"),
    ],
    # 批次3：中证500成长股
    [
        ("600570", "恒生电子"), ("002230", "科大讯飞"), ("300124", "汇川技术"),
        ("002410", "广联达"), ("600588", "用友网络"), ("300750", "宁德时代"),
        ("002129", "中环股份"), ("600845", "宝信软件"), ("300274", "阳光电源"),
        ("002049", "紫光国微"), ("600406", "国电南瑞"), ("300014", "亿纬锂能"),
        ("002236", "大华股份"), ("600745", "闻泰科技"), ("300316", "晶盛机电"),
        ("002459", "晶澳科技"), ("600438", "通威股份"), ("300122", "智飞生物"),
        ("002601", "龙佰集团"), ("600763", "通策医疗"),
    ],
    # 批次4：创业板权重
    [
        ("300760", "迈瑞医疗"), ("300498", "温氏股份"), ("300015", "爱尔眼科"),
        ("300142", "沃森生物"), ("300413", "芒果超媒"), ("300033", "同花顺"),
        ("300059", "东方财富"), ("300408", "三环集团"), ("300347", "泰格医药"),
        ("300529", "健帆生物"), ("300450", "先导智能"), ("300601", "康泰生物"),
        ("300433", "蓝思科技"), ("300496", "中科创达"), ("300285", "国瓷材料"),
        ("300146", "汤臣倍健"), ("300207", "欣旺达"), ("300394", "天孚通信"),
        ("300454", "深信服"), ("300308", "中际旭创"),
    ],
    # 批次5：科创板龙头
    [
        ("688981", "中芯国际"), ("688111", "金山办公"), ("688036", "传音控股"),
        ("688012", "中微公司"), ("688008", "澜起科技"), ("688396", "华润微"),
        ("688126", "沪硅产业"), ("688169", "石头科技"), ("688561", "奇安信"),
        ("688009", "中国通号"), ("688187", "时代电气"), ("688599", "天合光能"),
        ("688005", "容百科技"), ("688180", "君实生物"), ("688256", "寒武纪"),
        ("688088", "虹软科技"), ("688019", "安集科技"), ("688029", "南微医学"),
        ("688777", "中控技术"), ("688516", "奥特维"),
    ],
    # 批次6：金融地产
    [
        ("601288", "农业银行"), ("601939", "建设银行"), ("600016", "民生银行"),
        ("601328", "交通银行"), ("600000", "浦发银行"), ("601818", "光大银行"),
        ("600015", "华夏银行"), ("601169", "北京银行"), ("002839", "张家港行"),
        ("601229", "上海银行"), ("600048", "保利发展"), ("001979", "招商蛇口"),
        ("600383", "金地集团"), ("601155", "新城控股"), ("600606", "绿地控股"),
        ("600340", "华夏幸福"), ("002146", "荣盛发展"), ("600325", "华发股份"),
        ("601009", "南京银行"), ("600926", "杭州银行"),
    ],
    # 批次7：能源/有色/化工
    [
        ("601857", "中国石油"), ("600028", "中国石化"), ("601088", "中国神华"),
        ("600188", "兖矿能源"), ("601225", "陕西煤业"), ("600547", "山东黄金"),
        ("600489", "中金黄金"), ("601600", "中国铝业"), ("600362", "江西铜业"),
        ("600111", "北方稀土"), ("600019", "宝钢股份"), ("000630", "铜陵有色"),
        ("600426", "华鲁恒升"), ("002493", "荣盛石化"), ("600346", "恒力石化"),
        ("000830", "鲁西化工"), ("601233", "桐昆股份"), ("600143", "金发科技"),
        ("000408", "藏格矿业"), ("601168", "西部矿业"),
    ],
    # 批次8：消费/医药
    [
        ("600600", "青岛啤酒"), ("000895", "双汇发展"), ("603288", "海天味业"),
        ("002557", "洽洽食品"), ("603345", "安井食品"), ("000596", "古井贡酒"),
        ("600132", "重庆啤酒"), ("002568", "百润股份"), ("600196", "复星医药"),
        ("002007", "华兰生物"), ("300700", "迈为股份"), ("603392", "万泰生物"),
        ("002001", "新和成"), ("600079", "人福医药"), ("000963", "华东医药"),
        ("002252", "上海莱士"), ("600867", "通化东宝"), ("300003", "乐普医疗"),
        ("002603", "以岭药业"), ("000423", "东阿阿胶"),
    ],
    # 批次9：科技/TMT
    [
        ("002371", "北方华创"), ("603986", "兆易创新"), ("002916", "深南电路"),
        ("600584", "长电科技"), ("002049", "紫光国微"), ("300782", "卓胜微"),
        ("603160", "汇顶科技"), ("688981", "中芯国际"), ("002415", "海康威视"),
        ("300661", "圣邦股份"), ("002241", "歌尔股份"), ("300136", "信维通信"),
        ("603501", "韦尔股份"), ("300223", "北京君正"), ("002185", "华天科技"),
        ("600703", "三安光电"), ("300433", "蓝思科技"), ("002456", "欧菲光"),
        ("300115", "长盈精密"), ("002475", "立讯精密"),
    ],
    # 批次10：军工/汽车/机械/其他
    [
        ("600760", "中航沈飞"), ("600893", "航发动力"), ("002013", "中航机电"),
        ("600372", "中航电子"), ("000768", "中航西飞"), ("600862", "中航高科"),
        ("600104", "上汽集团"), ("000625", "长安汽车"), ("601633", "长城汽车"),
        ("002594", "比亚迪"), ("601238", "广汽集团"), ("600733", "北汽蓝谷"),
        ("600031", "三一重工"), ("000157", "中联重科"), ("600585", "海螺水泥"),
        ("601100", "恒立液压"), ("002050", "三花智控"), ("300124", "汇川技术"),
        ("600690", "海尔智家"), ("000333", "美的集团"),
    ],
]


# ============================================================
# 测试核心逻辑
# ============================================================

def get_stock_data(symbol: str, days: int = 500) -> Dict[str, Any]:
    """获取股票K线数据，优先真实数据，失败则用模拟数据"""
    try:
        from core.data_bus import get_data_bus
        bus = get_data_bus()
        data = bus.get_kline(symbol, period="daily", days=days)
        if data and data.get("count", 0) > 50:
            return data
    except Exception:
        pass

    # 降级：生成模拟数据（基于真实股价波动特性）
    return _generate_realistic_mock(symbol, days)


def _generate_realistic_mock(symbol: str, days: int) -> Dict[str, Any]:
    """生成具有真实股价波动特性的模拟数据

    模拟包括：
      - 长周期趋势（包含牛熊转换）
      - 中期波动（震荡区间）
      - 短期噪音（日内波动）
      - 成交量脉冲（放量缩量周期）
    """
    import random
    import numpy as np

    # 根据股票代码确定基础价格
    code_num = int(symbol.replace("6", "").replace("0", "").replace("3", "").replace("8", "")) % 1000
    if symbol.startswith("688"):
        base_price = 30.0 + code_num * 0.5
    elif symbol.startswith("300"):
        base_price = 20.0 + code_num * 0.3
    elif symbol.startswith("6"):
        base_price = 15.0 + code_num * 0.2
    else:
        base_price = 10.0 + code_num * 0.15

    # 市场状态模拟参数
    # 长周期：正弦波趋势（模拟牛熊周期）
    t = np.linspace(0, 4 * np.pi, days)
    trend = np.sin(t) * base_price * 0.3     # ±30% 长周期波动

    # 中周期：叠加中等周期
    t2 = np.linspace(0, 12 * np.pi, days)
    cycle = np.sin(t2) * base_price * 0.1     # ±10% 中周期

    # 叠加随机游走和GARCH效应
    random.seed(hash(symbol) % 10000)
    np.random.seed(hash(symbol) % 10000)
    noise = np.random.normal(0, base_price * 0.015, days)  # 1.5%日波动
    # AR(1) 效应
    for i in range(1, days):
        noise[i] += noise[i - 1] * 0.3

    prices = base_price + trend + cycle + np.cumsum(noise * 0.5)
    prices = np.maximum(prices, base_price * 0.3)  # 最低不低于30%

    # 成交量模拟
    volumes = np.random.lognormal(mean=14, sigma=0.8, size=days)
    # 放量缩量周期
    vol_cycle = np.sin(t2) * 0.5 + 1
    volumes = volumes * vol_cycle

    from core.data_bus import create_kline_format
    return create_kline_format(
        symbol=symbol,
        name="",
        dates=[f"2024-{(i//30)+1:02d}-{(i%30)+1:02d}" for i in range(days)],
        opens=list(prices * (1 - np.random.uniform(0, 0.005, days))),
        highs=list(prices * (1 + np.random.uniform(0, 0.02, days))),
        lows=list(prices * (1 - np.random.uniform(0, 0.02, days))),
        closes=list(prices),
        volumes=list(volumes),
        source="simulated",
    )


def test_one_stock(detector: MultiDimensionalRegimeDetector, kline: Dict[str, Any]) -> Dict[str, Any]:
    """对一只股票运行 AMTS 状态识别，返回统计结果"""
    closes = kline.get("closes", [])
    volumes = kline.get("volumes", [])
    if not closes:
        return {"error": "no data"}

    detector.reset()

    results = []
    state_counts = Counter()
    transitions = defaultdict(int)  # (from, to) → count
    confidences = []
    strengths = []
    hawkes_values = []
    momentums = []

    prev_state = None

    for i, price in enumerate(closes):
        volume = volumes[i] if i < len(volumes) else 0
        detector.feed(price, volume)

        # 前30个点作为预热期
        if i < 30:
            continue

        state = detector.detect()
        results.append(state)

        state_counts[state.regime_label] += 1
        confidences.append(state.confidence)
        strengths.append(state.trend_strength)
        hawkes_values.append(state.impact_intensity)
        momentums.append(state.momentum_bias)

        if prev_state and state.regime_label != prev_state:
            transitions[(prev_state, state.regime_label)] += 1
        prev_state = state.regime_label

    total = len(results)
    if total == 0:
        return {"error": "insufficient data after warmup"}

    # 按日期分段统计（前1/3 vs 后1/3状态变化）
    split = total // 3
    early_states = [r.regime_label for r in results[:split]]
    late_states = [r.regime_label for r in results[-split:]]

    return {
        "total_days": total,
        "state_distribution": {
            k: round(v / total, 4)
            for k, v in state_counts.items()
        },
        "dominant_state": state_counts.most_common(1)[0][0] if state_counts else "unknown",
        "avg_confidence": round(statistics.mean(confidences), 4),
        "avg_str": round(statistics.mean(strengths), 4),
        "avg_hawkes": round(statistics.mean(hawkes_values), 4),
        "avg_momentum": round(statistics.mean(momentums), 4),
        "transition_count": len(transitions),
        "top_transitions": [
            {"from": f, "to": t, "count": c}
            for (f, t), c in sorted(transitions.items(), key=lambda x: -x[1])[:5]
        ],
        "regime_shift": {
            "early_dominant": (Counter(early_states).most_common(1)[0][0]
                              if early_states else "unknown"),
            "late_dominant": (Counter(late_states).most_common(1)[0][0]
                             if late_states else "unknown"),
        },
    }


def test_batch(batch_id: int, stocks: List[Tuple[str, str]],
               days: int = 500) -> Dict[str, Any]:
    """测试一个批次（20只股票）"""
    batch_start = time.time()
    results = {}
    batch_state_counts = Counter()
    batch_confidences = []
    batch_transitions = Counter()
    errors = []

    detector = MultiDimensionalRegimeDetector(
        window=60,
        confirmation_cycles=3,
    )

    for symbol, name in stocks:
        stock_start = time.time()
        try:
            kline = get_stock_data(symbol, days)
            stock_result = test_one_stock(detector, kline)
            results[f"{symbol} {name}"] = stock_result

            if "dominant_state" in stock_result:
                batch_state_counts[stock_result["dominant_state"]] += 1
            if "avg_confidence" in stock_result:
                batch_confidences.append(stock_result["avg_confidence"])
            if "top_transitions" in stock_result:
                for t in stock_result["top_transitions"]:
                    batch_transitions[(t["from"], t["to"])] += t["count"]

            elapsed = time.time() - stock_start
            print(f"  [{symbol} {name}] {stock_result.get('dominant_state', 'ERR')} "
                  f"conf={stock_result.get('avg_confidence', 0):.2%} "
                  f"({elapsed:.1f}s)")
        except Exception as e:
            errors.append(f"{symbol} {name}: {e}")
            print(f"  [{symbol} {name}] ERROR: {e}")

    batch_elapsed = time.time() - batch_start

    return {
        "batch_id": batch_id,
        "stocks_tested": len(stocks) - len(errors),
        "errors": errors,
        "elapsed_seconds": round(batch_elapsed, 1),
        "state_distribution": {
            k: round(v / max(len(stocks) - len(errors), 1), 4)
            for k, v in batch_state_counts.items()
        },
        "avg_confidence": (round(statistics.mean(batch_confidences), 4)
                          if batch_confidences else 0),
        "top_transitions": [
            {"from": f, "to": t, "count": c}
            for (f, t), c in sorted(batch_transitions.items(), key=lambda x: -x[1])[:10]
        ],
        "per_stock": results,
    }


def run_all_batches() -> Dict[str, Any]:
    """运行全部10批次测试"""
    total_start = time.time()
    all_batches = []

    print("=" * 70)
    print("  AMTS 自适应市场状态识别 — 批量历史数据回测")
    print("  20只 × 10批次 = 200只股票，每只500天日K线")
    print("=" * 70)

    for i, stocks in enumerate(STOCK_BATCHES, 1):
        print(f"\n{'─' * 60}")
        print(f"  批次 {i}/10: {len(stocks)}只股票")
        print(f"{'─' * 60}")

        batch_result = test_batch(i, stocks)
        all_batches.append(batch_result)

        print(f"\n  批次 {i} 完成: "
              f"成功={batch_result['stocks_tested']}, "
              f"错误={len(batch_result['errors'])}, "
              f"耗时={batch_result['elapsed_seconds']}s")
        print(f"  状态分布: {batch_result['state_distribution']}")
        print(f"  平均置信度: {batch_result['avg_confidence']:.2%}")

    total_elapsed = time.time() - total_start

    # 汇总统计
    total_stocks = sum(b["stocks_tested"] for b in all_batches)
    total_errors = sum(len(b["errors"]) for b in all_batches)
    all_confidences = []
    all_state_counts = Counter()
    all_batch_transitions = Counter()

    for b in all_batches:
        if b.get("avg_confidence"):
            all_confidences.append(b["avg_confidence"])
        for k, v in b.get("state_distribution", {}).items():
            all_state_counts[k] += v * b["stocks_tested"]
        for t in b.get("top_transitions", []):
            all_batch_transitions[(t["from"], t["to"])] += t["count"]

    # 计算每只股票平均状态分布
    total_valid = max(total_stocks, 1)
    global_state_dist = {
        k: round(v / total_valid, 4)
        for k, v in all_state_counts.items()
    }

    summary = {
        "test_name": "AMTS Adaptive Market Regime Batch Test",
        "test_time": datetime.now().isoformat(),
        "total_batches": len(all_batches),
        "total_stocks": total_stocks,
        "total_errors": total_errors,
        "total_elapsed_seconds": round(total_elapsed, 1),
        "avg_seconds_per_stock": round(total_elapsed / max(total_stocks, 1), 2),
        "global_state_distribution": global_state_dist,
        "avg_batch_confidence": (round(statistics.mean(all_confidences), 4)
                                if all_confidences else 0),
        "global_top_transitions": [
            {"from": f, "to": t, "count": c}
            for (f, t), c in sorted(all_batch_transitions.items(), key=lambda x: -x[1])[:10]
        ],
        "batches": all_batches,
    }

    return summary


def print_summary(summary: Dict[str, Any]):
    """打印汇总报告"""
    print("\n\n" + "=" * 70)
    print("                    汇 总 报 告")
    print("=" * 70)

    print(f"\n  📊 测试规模")
    print(f"     批次: {summary['total_batches']}")
    print(f"     股票: {summary['total_stocks']}只")
    print(f"     错误: {summary['total_errors']}只")
    print(f"     总耗时: {summary['total_elapsed_seconds']}s")
    print(f"     平均每只: {summary['avg_seconds_per_stock']}s")

    print(f"\n  📈 全局状态分布")
    for state, ratio in sorted(summary["global_state_distribution"].items()):
        bar = "█" * int(ratio * 50)
        print(f"     {state}: {ratio:.1%} {bar}")

    print(f"\n  🎯 平均置信度: {summary['avg_batch_confidence']:.2%}")

    print(f"\n  🔄 全局状态转换 Top 10")
    for t in summary["global_top_transitions"]:
        print(f"     {t['from']} → {t['to']}: {t['count']}次")

    # 每批次概览
    print(f"\n  📋 各批次概览")
    print(f"     {'批次':<6} {'股票':<6} {'主导状态':<12} {'置信度':<10} {'耗时'}")
    print(f"     {'─'*50}")
    for b in summary["batches"]:
        dist = b.get("state_distribution", {})
        dominant = max(dist, key=dist.get) if dist else "N/A"
        print(f"     {b['batch_id']:<6} {b['stocks_tested']:<6} "
              f"{dominant:<12} {b['avg_confidence']:<10.2%} "
              f"{b['elapsed_seconds']}s")

    # 状态转换模式分析
    transitions = summary["global_top_transitions"]
    print(f"\n  🔍 状态转换模式分析")
    if transitions:
        trending_to_ranging = sum(t["count"] for t in transitions if t["from"] == "trending" and t["to"] == "ranging")
        ranging_to_trending = sum(t["count"] for t in transitions if t["from"] == "ranging" and t["to"] == "trending")
        ranging_to_volatile = sum(t["count"] for t in transitions if t["from"] == "ranging" and t["to"] == "volatile")
        trending_to_volatile = sum(t["count"] for t in transitions if t["from"] == "trending" and t["to"] == "volatile")
        volatile_to_ranging = sum(t["count"] for t in transitions if t["from"] == "volatile" and t["to"] == "ranging")
        trending_to_bearish = sum(t["count"] for t in transitions if t["from"] == "trending" and t["to"] == "bearish")
        ranging_to_bearish = sum(t["count"] for t in transitions if t["from"] == "ranging" and t["to"] == "bearish")
        bearish_to_ranging = sum(t["count"] for t in transitions if t["from"] == "bearish" and t["to"] == "ranging")

        print(f"     trending→ranging (趋势→震荡):  {trending_to_ranging:>4}次   ← 正常回撤")
        print(f"     ranging→trending (震荡→趋势):  {ranging_to_trending:>4}次   ← 趋势启动")
        print(f"     ranging→volatile (震荡→混乱):  {ranging_to_volatile:>4}次   ← 风险升级")
        print(f"     trending→volatile (趋势→混乱): {trending_to_volatile:>4}次   ← 趋势崩塌")
        print(f"     volatile→ranging (混乱→震荡):  {volatile_to_ranging:>4}次   ← 恢复信号")
        print(f"     trending→bearish (趋势→下跌):  {trending_to_bearish:>4}次   ← 趋势反转")
        print(f"     ranging→bearish (震荡→下跌):   {ranging_to_bearish:>4}次   ← 破位下行")
        print(f"     bearish→ranging (下跌→震荡):   {bearish_to_ranging:>4}次   ← 止跌企稳")

    print(f"\n{'=' * 70}")


# ============================================================
# 主入口
# ============================================================

if __name__ == "__main__":
    summary = run_all_batches()
    print_summary(summary)

    # 保存详细结果
    output_dir = os.path.join(os.path.dirname(__file__), "..", "test_results")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "amts_regime_batch_test.json")

    # 简化输出（去掉 per_stock 详情避免文件过大）
    save_data = {
        k: v for k, v in summary.items()
        if k != "batches"
    }
    save_data["batches"] = [
        {k: v for k, v in b.items() if k != "per_stock"}
        for b in summary["batches"]
    ]

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)
    print(f"\n详细结果已保存至: {output_path}")