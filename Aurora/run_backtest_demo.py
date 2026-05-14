# -*- coding: utf-8 -*-
"""
AI智能体回测中心 - 测试运行脚本
"""

import sys
import os

# 添加当前目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auto_backtest.auto_backtest_system import get_backtest_system
from auto_backtest.strategy_discovery import get_strategy_discovery

def run_full_backtest_test():
    """运行完整的回测测试"""
    print("=" * 70)
    print("🤖 AI智能体回测中心 - 测试运行")
    print("=" * 70)

    # 获取回测系统
    backtest_system = get_backtest_system()
    
    # 获取策略发现系统
    discovery = get_strategy_discovery()

    print("\n📊 系统状态:")
    status = backtest_system.get_status()
    for key, value in status.items():
        print(f"  {key}: {value}")

    print("\n🔍 步骤1: 自动发现策略...")
    new_count = discovery.auto_register_to_backtest_system(backtest_system)
    print(f"   ✅ 发现 {new_count} 个新策略")

    print("\n🧪 步骤2: 一键回测所有策略...")
    results = backtest_system.run_all_backtests()
    
    print("\n📈 回测结果汇总:")
    summary = results['summary']
    print(f"   总策略数: {summary['total_strategies']}")
    print(f"   已测试: {summary['tested_strategies']}")
    print(f"   通过率: {summary['pass_rate'] * 100:.2f}%")

    print("\n📋 各策略回测详情:")
    for strategy_name, result in results['results'].items():
        print(f"\n   ┌─ {strategy_name}")
        print(f"   │  年化收益率: {result['annual_return'] * 100:.2f}%")
        print(f"   │  夏普比率: {result['sharpe_ratio']:.2f}")
        print(f"   │  最大回撤: {result['max_drawdown'] * 100:.2f}%")
        print(f"   │  胜率: {result['win_rate'] * 100:.2f}%")
        print(f"   │  交易次数: {result['total_trades']}")

    print("\n✅ 步骤3: 智能审核...")
    for strategy_name in results['results'].keys():
        report = backtest_system.audit_strategy(strategy_name)
        status = "通过" if report['approved'] else "未通过"
        print(f"\n   ┌─ {strategy_name}")
        print(f"   │  审核状态: {status}")
        print(f"   │  检查项:")
        for check_name, passed in report['checks'].items():
            check_status = "✓" if passed else "✗"
            print(f"   │    {check_status} {check_name}")
        if report['recommendations']:
            print(f"   │  建议:")
            for rec in report['recommendations']:
                print(f"   │    - {rec}")

    print("\n" + "=" * 70)
    print("✅ AI智能体回测中心测试完成！")
    print("=" * 70)

    return results

if __name__ == "__main__":
    run_full_backtest_test()
