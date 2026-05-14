import sys
import numpy as np
import pandas as pd
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from final_market_adaptive import FinalMarketAdaptiveGrid

def analyze_strategy():
    result = []
    result.append('=' * 70)
    result.append('策略深度分析报告')
    result.append('=' * 70)
    result.append('')
    
    np.random.seed(42)
    days = 300
    prices = pd.Series(100 + np.random.normal(0, 0.8, days).cumsum())
    prices = np.clip(prices, 95, 105)
    
    strategy = FinalMarketAdaptiveGrid(base_price=100, initial_balance=100000)
    
    for i, price in enumerate(prices):
        result_strat = strategy.update_price(price, prices[:i+1])
    
    final_price = prices.iloc[-1]
    total_assets = strategy.current_balance + strategy.position * final_price
    capital_utilization = (strategy.position * final_price) / total_assets * 100 if total_assets > 0 else 0
    win_rate = strategy.winning_trades / strategy.total_trades * 100 if strategy.total_trades > 0 else 0
    
    result.append('1. 机器学习模型训练情况:')
    result.append(f'   模型是否训练: {strategy.model_trained}')
    result.append(f'   训练次数: {strategy.model_training_count}')
    result.append(f'   模型数据量: {len(strategy.model_data)}')
    result.append(f'   反转数据量: {len(strategy.reversal_data)}')
    result.append(f'   网格间距数据量: {len(strategy.grid_spacing_data)}')
    result.append(f'   资金分配数据量: {len(strategy.fund_allocation_data)}')
    result.append('')
    
    result.append('2. 交易统计:')
    result.append(f'   总交易次数: {strategy.total_trades}')
    result.append(f'   盈利次数: {strategy.winning_trades}')
    result.append(f'   亏损次数: {strategy.losing_trades}')
    result.append(f'   胜率: {win_rate:.2f}%')
    avg_trade = (total_assets - 100000) / strategy.total_trades if strategy.total_trades > 0 else float('nan')
    result.append(f'   平均每笔交易收益: {avg_trade:.2f}')
    result.append('')
    
    result.append('3. 资金使用情况:')
    result.append(f'   初始资金: 100000')
    result.append(f'   最终资金: {strategy.current_balance:.2f}')
    result.append(f'   当前持仓: {strategy.position:.4f}')
    result.append(f'   持仓价值: {strategy.position * final_price:.2f}')
    result.append(f'   总资产: {total_assets:.2f}')
    result.append(f'   收益率: {(total_assets - 100000) / 100000 * 100:.2f}%')
    result.append(f'   资金使用率: {capital_utilization:.2f}%')
    result.append('')
    
    result.append('4. 当前参数配置:')
    result.append(f'   网格间距: {strategy.grid_spacing * 100:.4f}%')
    result.append(f'   最大持仓比例: {strategy.max_position_percentage * 100:.2f}%')
    result.append(f'   保留资金比例: {strategy.reserve_balance_percentage * 100:.2f}%')
    result.append(f'   止盈阈值: {strategy.take_profit_threshold * 100:.2f}%')
    result.append(f'   止损阈值: {strategy.stop_loss_threshold * 100:.2f}%')
    result.append(f'   网格层数: {strategy.grid_levels}')
    result.append('')
    
    result.append('5. 价格波动统计:')
    result.append(f'   价格均值: {prices.mean():.2f}')
    result.append(f'   价格标准差: {prices.std():.2f}')
    result.append(f'   价格波动率: {prices.pct_change().std() * 100:.4f}%')
    result.append(f'   价格范围: [{prices.min():.2f}, {prices.max():.2f}]')
    result.append('')
    
    result.append('=' * 70)
    result.append('问题诊断:')
    result.append('=' * 70)
    
    issues = []
    if strategy.total_trades < 50:
        issues.append('交易频率过低 - 网格间距可能过大或价格波动不足')
    if not strategy.model_trained:
        issues.append('机器学习模型未训练 - 需要100条以上数据')
    if strategy.model_trained and strategy.model_training_count < 5:
        issues.append('模型训练次数不足 - 可能影响预测准确性')
    if capital_utilization < 30:
        issues.append('资金使用率过低 - 可能是保留资金比例过高或策略保守')
    if win_rate < 50 and strategy.total_trades > 10:
        issues.append('胜率低于50% - 交易策略需要优化')
    if len(strategy.model_data) < 100:
        issues.append('训练数据不足 - 需要至少100条数据才能训练模型')
    
    if issues:
        for issue in issues:
            result.append(issue)
    else:
        result.append('未发现明显问题')
    
    result.append('')
    result.append('=' * 70)
    result.append('优化建议:')
    result.append('=' * 70)
    
    if strategy.grid_spacing > 0.003:
        result.append('1. 减小网格间距以增加交易频率')
    if strategy.reserve_balance_percentage > 0.15:
        result.append('2. 降低保留资金比例以提高资金使用率')
    if strategy.take_profit_threshold > 0.02:
        result.append('3. 降低止盈阈值以提高交易频率')
    if not strategy.model_trained:
        result.append('4. 增加训练数据量或降低训练门槛')
    result.append('')
    result.append('=' * 70)
    
    output = '\n'.join(result)
    with open('strategy_analysis_report.txt', 'w', encoding='utf-8') as f:
        f.write(output)
    print('Report written')

if __name__ == '__main__':
    analyze_strategy()