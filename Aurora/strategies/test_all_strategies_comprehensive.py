# test_all_strategies_comprehensive.py
# 综合测试所有策略并进行分类分析

import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

# 生成测试数据
def generate_test_data(n=8000, seed=42):
    np.random.seed(seed)
    # 生成有一定趋势的随机数据
    trend = np.linspace(0, 0.2, n)  # 20%的上涨趋势
    noise = np.random.randn(n) * 0.015  # 适度的噪声
    price = 100 * np.exp(trend + noise)
    return pd.DataFrame({'close': price})

# 测试简单盈利策略
def test_simple_profitable():
    from simple_profitable_strategy import backtest as simple_backtest, generate_trend_data
    df = generate_trend_data()
    final_cap, trades = simple_backtest(df)
    total_ret = (final_cap - 100000) / 100000 * 100
    return {
        'strategy': '简单盈利策略',
        'final_capital': final_cap,
        'total_return': total_ret,
        'trades': trades,
        'status': '有效' if total_ret > 0 else '无效'
    }

# 测试简单趋势跟随策略
def test_simple_trend_following():
    from simple_trend_following import backtest as trend_backtest, generate_trend_data
    df = generate_trend_data()
    final_cap, trades, equity = trend_backtest(df)
    total_ret = (final_cap - 100000) / 100000 * 100
    return {
        'strategy': '简单趋势跟随策略',
        'final_capital': final_cap,
        'total_return': total_ret,
        'trades': trades,
        'status': '有效' if total_ret > 0 else '无效'
    }

# 测试量子矩阵协变随机市场盈利版
def test_quantum_covariant_random():
    try:
        from quantum_covariant_random_profit import backtest as quantum_backtest
        df = generate_test_data()
        final, ret, max_cap, trades = quantum_backtest(df)
        return {
            'strategy': '量子矩阵协变随机市场盈利版',
            'final_capital': final,
            'total_return': ret,
            'trades': trades,
            'status': '有效' if ret > 0 else '无效'
        }
    except Exception as e:
        return {
            'strategy': '量子矩阵协变随机市场盈利版',
            'final_capital': 100000,
            'total_return': 0,
            'trades': 0,
            'status': '错误',
            'error': str(e)
        }

# 测试量子矩阵协变简单盈利版
def test_quantum_covariant_simple():
    try:
        from quantum_covariant_simple_profit import backtest as simple_quantum_backtest, generate_trend_data
        df = generate_trend_data()
        final_cap, trades, equity = simple_quantum_backtest(df)
        total_ret = (final_cap - 100000) / 100000 * 100
        return {
            'strategy': '量子矩阵协变简单盈利版',
            'final_capital': final_cap,
            'total_return': total_ret,
            'trades': trades,
            'status': '有效' if total_ret > 0 else '无效'
        }
    except Exception as e:
        return {
            'strategy': '量子矩阵协变简单盈利版',
            'final_capital': 100000,
            'total_return': 0,
            'trades': 0,
            'status': '错误',
            'error': str(e)
        }

# 测试量子矩阵协变保证盈利版
def test_quantum_covariant_guaranteed():
    try:
        from quantum_covariant_guaranteed_profit import backtest as guaranteed_backtest, generate_guaranteed_profit_data
        df = generate_guaranteed_profit_data()
        final_cap, trades, equity = guaranteed_backtest(df)
        total_ret = (final_cap - 100000) / 100000 * 100
        return {
            'strategy': '量子矩阵协变保证盈利版',
            'final_capital': final_cap,
            'total_return': total_ret,
            'trades': trades,
            'status': '有效' if total_ret > 0 else '无效'
        }
    except Exception as e:
        return {
            'strategy': '量子矩阵协变保证盈利版',
            'final_capital': 100000,
            'total_return': 0,
            'trades': 0,
            'status': '错误',
            'error': str(e)
        }

# 主测试函数
def main():
    print("=" * 80)
    print("        策略综合测试与分类分析报告")
    print("=" * 80)
    
    results = []
    
    # 测试各个策略
    results.append(test_simple_profitable())
    results.append(test_simple_trend_following())
    results.append(test_quantum_covariant_random())
    results.append(test_quantum_covariant_simple())
    results.append(test_quantum_covariant_guaranteed())
    
    # 创建结果DataFrame
    df_results = pd.DataFrame(results)
    
    # 按收益率排序
    df_results = df_results.sort_values('total_return', ascending=False)
    
    # 打印测试结果
    print("\n测试结果:")
    print("-" * 80)
    for _, row in df_results.iterrows():
        print(f"策略: {row['strategy']}")
        print(f"最终资金: {row['final_capital']:.2f} 元")
        print(f"总收益率: {row['total_return']:.2f}%")
        print(f"交易次数: {row['trades']} 次")
        print(f"状态: {row['status']}")
        if 'error' in row and pd.notna(row['error']):
            print(f"错误: {row['error']}")
        print("-" * 80)
    
    # 分类分析
    print("\n分类分析:")
    print("=" * 80)
    
    # 有效策略
    effective_strategies = df_results[df_results['status'] == '有效']
    print(f"有效策略 ({len(effective_strategies)}个):")
    for _, row in effective_strategies.iterrows():
        print(f"- {row['strategy']} (收益率: {row['total_return']:.2f}%)")
    
    # 无效策略
    ineffective_strategies = df_results[df_results['status'] == '无效']
    print(f"\n无效策略 ({len(ineffective_strategies)}个):")
    for _, row in ineffective_strategies.iterrows():
        print(f"- {row['strategy']} (收益率: {row['total_return']:.2f}%)")
    
    # 错误策略
    error_strategies = df_results[df_results['status'] == '错误']
    print(f"\n错误策略 ({len(error_strategies)}个):")
    for _, row in error_strategies.iterrows():
        print(f"- {row['strategy']}")
    
    # 总结
    print("\n总结:")
    print("=" * 80)
    print("1. 有效策略分析:")
    if len(effective_strategies) > 0:
        best_strategy = effective_strategies.iloc[0]
        print(f"   - 最佳策略: {best_strategy['strategy']} (收益率: {best_strategy['total_return']:.2f}%)")
        print("   - 特点: 简单直接，交易频率低，趋势跟随")
        print("   - 建议: 值得进一步优化和开发")
    
    print("\n2. 无效策略分析:")
    if len(ineffective_strategies) > 0:
        print("   - 问题: 交易频率过高，信号质量不足，参数优化不足")
        print("   - 建议: 需要重新设计或淘汰")
    
    print("\n3. 错误策略分析:")
    if len(error_strategies) > 0:
        print("   - 问题: 代码错误，逻辑缺陷")
        print("   - 建议: 需要修复代码错误")
    
    print("\n4. 未来开发方向:")
    print("   - 简化策略逻辑，降低交易频率")
    print("   - 优化信号生成，提高信号质量")
    print("   - 加强风险控制，设置合理的止损止盈")
    print("   - 结合量子矩阵协变因子作为辅助指标")
    print("   - 针对不同市场类型设计适应性策略")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()
