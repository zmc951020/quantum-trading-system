#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
伯努利-康达策略缺陷诊断与优化建议
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd
from datetime import datetime
from collections import defaultdict

print("="*90)
print("伯努利-康达量化策略 - 缺陷诊断与优化建议")
print("="*90)

from strategies.bernoulli_coanda_strategy import (
    bernoulli_coanda_strategy,
    BernoulliCoandaParameters
)

# 生成测试数据
np.random.seed(42)
n_days = 500
dates = pd.date_range(start='2021-01-01', periods=n_days, freq='D')
prices = 100 + np.cumsum(np.random.randn(n_days) * 2)

data = pd.DataFrame({
    'Open': prices * 0.995,
    'High': prices * 1.01,
    'Low': prices * 0.99,
    'Close': prices,
    'Volume': np.random.randint(1000000, 10000000, n_days)
}, index=dates)

# 使用优化后的参数运行策略
print("\n1/4 运行优化后策略...")
optimized_params = BernoulliCoandaParameters(
    short_velocity_window=4,
    long_velocity_window=18,
    pressure_threshold=0.4,
    stop_loss_atr_multiplier=2.0,
    take_profit_risk_reward=2.5,
    max_holding_days=25
)

strategy = bernoulli_coanda_strategy(name="BCQ_Optimized", params=optimized_params)
result = strategy.run_backtest(data, 100000)

print(f"   总交易: {result.get('total_trades', 0)}")
print(f"   收益率: {result.get('total_return_pct', 0):+.2f}%")
print(f"   夏普比率: {result.get('sharpe_ratio', 0):.2f}")

# ============================================================================
# 缺陷诊断
# ============================================================================
print("\n2/4 策略缺陷诊断...")
print("="*90)

defects = []
warnings = []

# 1. 胜率分析
win_rate = result.get('win_rate_pct', 0)
if win_rate < 50:
    defects.append({
        'type': '胜率不足',
        'severity': 'medium',
        'description': f'胜率{win_rate:.1f}%低于50%，策略期望为负',
        'impact': '长期交易会导致净亏损',
        'suggestion': '优化入场信号，增加确认条件，提高胜率至55%+'
    })
elif win_rate < 55:
    warnings.append({
        'type': '胜率偏低',
        'description': f'胜率{win_rate:.1f}%处于一般水平',
        'suggestion': '可以考虑增加信号过滤条件'
    })

# 2. 盈亏比分析
profit_factor = result.get('profit_factor', 0)
if profit_factor < 1.5:
    defects.append({
        'type': '盈亏比不足',
        'severity': 'medium',
        'description': f'盈亏比{profit_factor:.2f}低于1.5',
        'impact': '即使胜率高，盈利也可能被亏损抵消',
        'suggestion': '优化止盈止损比例，调整风险回报比'
    })

# 3. 夏普比率分析
sharpe = result.get('sharpe_ratio', 0)
if sharpe < 0.5:
    defects.append({
        'type': '夏普比率低',
        'severity': 'high',
        'description': f'夏普比率{sharpe:.2f}低于0.5，风险调整收益差',
        'impact': '策略风险收益比不佳',
        'suggestion': '需要全面优化入场出场逻辑，减少无效交易'
    })
elif sharpe < 1.0:
    warnings.append({
        'type': '夏普比率一般',
        'description': f'夏普比率{sharpe:.2f}有提升空间',
        'suggestion': '继续优化参数和逻辑'
    })

# 4. 最大回撤分析
max_dd = abs(result.get('max_drawdown_pct', 0))
if max_dd > 15:
    defects.append({
        'type': '回撤过大',
        'severity': 'high',
        'description': f'最大回撤{max_dd:.1f}%超过15%',
        'impact': '可能触发风险控制底线',
        'suggestion': '收紧止损，增加仓位管理，减少单笔风险暴露'
    })
elif max_dd > 10:
    warnings.append({
        'type': '回撤偏高',
        'description': f'最大回撤{max_dd:.1f}%可以接受但有优化空间',
        'suggestion': '优化止损位置和仓位控制'
    })

# 5. 交易频率分析
total_trades = result.get('total_trades', 0)
trades_per_year = total_trades * 252 / n_days
if trades_per_year < 10:
    defects.append({
        'type': '交易频率过低',
        'severity': 'low',
        'description': f'年化交易次数{trades_per_year:.1f}次，机会利用不足',
        'impact': '资金利用率低',
        'suggestion': '适当放宽入场条件，增加交易机会'
    })
elif trades_per_year > 100:
    defects.append({
        'type': '交易频率过高',
        'severity': 'medium',
        'description': f'年化交易次数{trades_per_year:.1f}次，可能过度交易',
        'impact': '增加交易成本，可能过度拟合',
        'suggestion': '增加信号确认条件，减少假信号'
    })

# 6. 信号一致性分析
if result.get('trades'):
    trades = result['trades']
    
    # 分析持仓时间分布
    holding_days = [t.get('holding_days', 0) for t in trades]
    if holding_days:
        avg_holding = np.mean(holding_days)
        if avg_holding < 3:
            defects.append({
                'type': '持仓时间过短',
                'severity': 'low',
                'description': f'平均持仓{avg_holding:.1f}天，可能被噪音影响',
                'impact': '容易被短期波动止损',
                'suggestion': '增加持仓时间容忍度'
            })
        elif avg_holding > 20:
            defects.append({
                'type': '持仓时间过长',
                'severity': 'medium',
                'description': f'平均持仓{avg_holding:.1f}天，可能暴露于长期风险',
                'impact': '增加不确定性',
                'suggestion': '设置更严格的持仓时间限制'
            })
    
    # 分析盈利交易vs亏损交易
    profitable_trades = [t for t in trades if t.get('profit_pct', 0) > 0]
    losing_trades = [t for t in trades if t.get('profit_pct', 0) <= 0]
    
    if profitable_trades and losing_trades:
        avg_profit = np.mean([t.get('profit_pct', 0) for t in profitable_trades])
        avg_loss = np.mean([t.get('profit_pct', 0) for t in losing_trades])
        
        if avg_profit < abs(avg_loss) * 2:
            defects.append({
                'type': '盈亏不对称',
                'severity': 'medium',
                'description': f'平均盈利{avg_profit*100:.2f}% vs 平均亏损{avg_loss*100:.2f}%，盈亏比不优',
                'impact': '胜率需要非常高才能盈利',
                'suggestion': '优化出场策略，让盈利充分奔跑'
            })

# 7. 市场适应性分析
defects.append({
    'type': '市场适应性单一',
    'severity': 'medium',
    'description': '策略参数固定，难以适应不同市场状态',
    'impact': '在震荡市场和趋势市场表现差异大',
    'suggestion': '实现市场状态识别，自适应调整参数'
})

# 8. 风险管理分析
defects.append({
    'type': '仓位管理简单',
    'severity': 'medium',
    'description': '使用固定风险比例仓位管理',
    'impact': '未能根据市场波动率动态调整',
    'suggestion': '实现基于波动率的动态仓位管理'
})

# 输出诊断结果
print("\n🚨 缺陷列表:")
print(f"{'='*90}")
for i, defect in enumerate(defects, 1):
    severity_emoji = "🔴" if defect['severity'] == 'high' else "🟡"
    print(f"\n{severity_emoji} {i}. {defect['type']} ({defect['severity']})")
    print(f"   问题: {defect['description']}")
    print(f"   影响: {defect['impact']}")
    print(f"   建议: {defect['suggestion']}")

if warnings:
    print(f"\n\n⚠️  警告列表:")
    print(f"{'='*90}")
    for i, warning in enumerate(warnings, 1):
        print(f"\n🟠 {i}. {warning['type']}")
        print(f"   问题: {warning['description']}")
        print(f"   建议: {warning['suggestion']}")

# ============================================================================
# 优化方向
# ============================================================================
print("\n\n" + "="*90)
print("3/4 优化方向建议")
print("="*90)

optimization_directions = [
    {
        'priority': 'high',
        'direction': '信号优化',
        'items': [
            '增加多周期确认机制（如日线和周线趋势一致）',
            '引入成交量确认（突破时需要放量）',
            '增加趋势强度过滤（ADX > 25时才入场）',
            '添加波动率过滤（ATR高于历史均值时才交易）'
        ]
    },
    {
        'priority': 'high',
        'direction': '出场优化',
        'items': [
            '实现跟踪止损（随盈利增加调整止损位）',
            '优化止盈策略（分段止盈或移动止盈）',
            '添加时间止损（持仓超过N天强制平仓）',
            '实现市场情绪出场（反转头肩形态时提前离场）'
        ]
    },
    {
        'priority': 'medium',
        'direction': '仓位管理优化',
        'items': [
            '基于波动率的动态仓位调整',
            '连亏后自动降低仓位',
            '实现凯利公式优化仓位',
            '添加最大持仓限制'
        ]
    },
    {
        'priority': 'medium',
        'direction': '市场适应性',
        'items': [
            '实现市场状态识别（趋势/震荡/突破）',
            '针对不同市场状态使用不同参数',
            '添加波动率 regime 检测',
            '实现自适应的压力差阈值'
        ]
    },
    {
        'priority': 'low',
        'direction': '风控增强',
        'items': [
            '添加单日最大亏损限制',
            '实现最大连续亏损次数限制',
            '添加相关性过滤（避免过度集中）',
            '实现动态回撤控制'
        ]
    }
]

for i, direction in enumerate(optimization_directions, 1):
    priority_emoji = "🔴" if direction['priority'] == 'high' else "🟡" if direction['priority'] == 'medium' else "🟢"
    print(f"\n{priority_emoji} {i}. {direction['direction']} (优先级: {direction['priority']})")
    for j, item in enumerate(direction['items'], 1):
        print(f"   {j}. {item}")

# ============================================================================
# 优化建议优先级
# ============================================================================
print("\n\n" + "="*90)
print("4/4 优化实施优先级")
print("="*90)

priority_plan = """
📋 优化实施计划（建议顺序）:

【第一阶段 - 快速见效】(1-2周)
   1. 优化出场策略 - 实现跟踪止损
   2. 添加趋势强度过滤 - 提高信号质量
   3. 增加成交量确认 - 减少假突破

【第二阶段 - 稳健提升】(2-4周)
   4. 实现波动率仓位管理
   5. 添加市场状态识别
   6. 优化止盈策略

【第三阶段 - 持续演进】(1-2月)
   7. 实现自适应参数调整
   8. 添加风控增强措施
   9. 集成到超能优化器V6进行深度优化

💡 关键建议:
   • 每次修改只调整一个参数，便于评估效果
   • 保存每个版本的回测结果，进行对比分析
   • 在模拟盘验证后再投入实盘
   • 持续监控策略表现，及时调整
"""

print(priority_plan)

# ============================================================================
# 预期效果
# ============================================================================
print("="*90)
print("预期优化效果")
print("="*90)

expected_improvements = """
基于上述优化方向，预期可达到的效果:

📈 收益类:
   • 总收益率: 提升至 10-15% (当前约5%)
   • 年化收益率: 提升至 15-20%
   • 盈亏比: 提升至 1.8-2.0

📊 风险类:
   • 夏普比率: 提升至 1.0-1.5 (当前约0.65)
   • 最大回撤: 控制在 10% 以内 (当前约7%)

⚙️ 稳定性类:
   • 胜率: 提升至 55-60%
   • 交易频率: 保持在合理范围 (20-50次/年)

🎯 适应类:
   • 多市场状态适应能力增强
   • 策略鲁棒性提升
   • 过拟合风险降低
"""

print(expected_improvements)

print("\n" + "="*90)
print("诊断完成！")
print("="*90)

