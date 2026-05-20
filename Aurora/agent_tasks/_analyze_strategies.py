"""
分析策略注册表中所有策略，挑选相对优良策略进行智能体优化
"""
import sys
sys.path.insert(0, r'd:\Gupiao\量化交易测试设备方案\攒机\最后评估01\DS-V3.2T量化交易专用工作站配置深度研判与采购决策报告02_files\攒机配置\Aurora')

from strategies.strategy_registry import STRATEGY_REGISTRY

print("=" * 80)
print("策略注册表完整分析")
print("=" * 80)

# 按评分排序
sorted_strategies = sorted(STRATEGY_REGISTRY.items(), key=lambda x: x[1].get("rating", 0), reverse=True)

print(f"\n{'策略名称':<35} {'评分':<8} {'类型':<12} {'状态':<10} {'文件':<30}")
print("-" * 95)

for name, info in sorted_strategies:
    rating = info.get("rating", 0)
    stype = info.get("type", "N/A")
    status = info.get("status", "N/A")
    file = info.get("file", "N/A")
    desc = info.get("description", "")
    cls = info.get("class", "")
    print(f"{name:<35} {rating:<8.4f} {stype:<12} {status:<10} {file:<30}")
    if desc:
        print(f"  └─ 描述: {desc}")
    if cls:
        print(f"  └─ 类: {cls}")

print("\n" + "=" * 80)
print("评分排名分析")
print("=" * 80)

# 评分区间
ratings = [info.get("rating", 0) for info in STRATEGY_REGISTRY.values()]
print(f"\n最高评分: {max(ratings):.4f}")
print(f"最低评分: {min(ratings):.4f}")
print(f"平均评分: {sum(ratings)/len(ratings):.4f}")
print(f"策略总数: {len(STRATEGY_REGISTRY)}")

# 分类统计
from collections import Counter
type_counts = Counter(info.get("type", "未知") for info in STRATEGY_REGISTRY.values())
print(f"\n策略类型分布:")
for t, c in type_counts.most_common():
    print(f"  {t}: {c}个")

# 挑选相对优良策略（评分前5，排除已优化的FourierRLStrategy）
print("\n" + "=" * 80)
print("推荐优化的相对优良策略（评分前5，排除已优化的FourierRLStrategy）")
print("=" * 80)

candidates = [(n, i) for n, i in sorted_strategies if n != "FourierRLStrategy" and i.get("status") == "tested"]
for i, (name, info) in enumerate(candidates[:5]):
    print(f"\n{i+1}. {name} (评分: {info.get('rating', 0):.4f})")
    print(f"   类型: {info.get('type', 'N/A')}")
    print(f"   文件: {info.get('file', 'N/A')}")
    print(f"   类: {info.get('class', 'N/A')}")
    print(f"   描述: {info.get('description', 'N/A')}")
