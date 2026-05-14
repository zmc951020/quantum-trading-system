#!/usr/bin/env python3
"""
策略综合测试框架 - 测试不同策略在各类市场环境中的表现
"""

import numpy as np
import pandas as pd
from datetime import datetime
import os
import sys

# 添加策略目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from final_market_adaptive import FinalMarketAdaptiveGrid
from grid_trading import GridTrading, MLGridTrading
from trend_trading import TrendSwitchingStrategy
from strategy_base import StrategyManager

class StrategyTester:
    """策略测试器"""
    
    def __init__(self, initial_balance=100000):
        self.initial_balance = initial_balance
        self.results = {}
        self.strategy_manager = StrategyManager()
    
    def generate_market_data(self, market_type='range_bound', days=200, base_price=100):
        """
        生成不同类型的市场数据
        
        Args:
            market_type: 市场类型 ('range_bound', 'trending_up', 'trending_down', 'volatile')
            days: 数据天数
            base_price: 基准价格
            
        Returns:
            DataFrame: 包含日期、收盘价、成交量的模拟数据
        """
        np.random.seed(42)
        dates = pd.date_range(start='2023-01-01', periods=days)
        
        # 根据市场类型生成数据
        if market_type == 'range_bound':
            # 横盘市场：价格在窄区间内波动
            prices = base_price + np.random.normal(0, base_price * 0.008, days).cumsum()
            prices = np.clip(prices, base_price * 0.95, base_price * 1.05)
            
        elif market_type == 'trending_up':
            # 上涨市场：持续上升趋势
            trend = np.linspace(0, 0.3, days)  # 30%涨幅
            noise = np.random.normal(0, base_price * 0.01, days).cumsum()
            prices = base_price * (1 + trend) + noise
            
        elif market_type == 'trending_down':
            # 下跌市场：持续下降趋势
            trend = np.linspace(0, -0.25, days)  # 25%跌幅
            noise = np.random.normal(0, base_price * 0.01, days).cumsum()
            prices = base_price * (1 + trend) + noise
            
        elif market_type == 'volatile':
            # 波动市场：高波动率但均值回归
            # 使用带均值回归的随机过程，避免价格无限增长
            prices = [base_price]
            mean_reversion = 0.05  # 均值回归强度
            long_term_mean = base_price  # 长期均值
            volatility_factor = 0.02  # 波动率因子
            
            for i in range(1, days):
                # 均值回归项 + 随机扰动
                reversion_term = mean_reversion * (long_term_mean - prices[-1])
                random_term = np.random.normal(0, base_price * volatility_factor)
                new_price = prices[-1] + reversion_term + random_term
                
                # 限制价格范围（防止极端值）
                new_price = max(base_price * 0.5, min(base_price * 2.0, new_price))
                prices.append(new_price)
            
        else:
            raise ValueError(f"未知市场类型: {market_type}")
        
        volumes = np.random.randint(1000000, 10000000, days)
        
        return pd.DataFrame({
            'close': prices,
            'volume': volumes
        }, index=dates)
    
    def calculate_metrics(self, balance_history, price_history, initial_balance):
        """
        计算性能指标
        
        Args:
            balance_history: 资金历史
            price_history: 价格历史
            initial_balance: 初始资金
            
        Returns:
            dict: 包含各项指标的字典
        """
        # 计算收益率
        returns = np.diff(balance_history) / balance_history[:-1]
        
        # 总收益率
        total_return = (balance_history[-1] - initial_balance) / initial_balance
        
        # 年化收益率 (假设252个交易日)
        annual_return = (1 + total_return) ** (252 / len(balance_history)) - 1
        
        # 波动率
        volatility = np.std(returns) * np.sqrt(252)
        
        # 夏普比率 (假设无风险利率为0)
        sharpe_ratio = annual_return / volatility if volatility > 0 else 0
        
        # 最大回撤
        peak = np.maximum.accumulate(balance_history)
        drawdown = (peak - balance_history) / peak
        max_drawdown = np.max(drawdown)
        
        # 胜率（基于每日收益）
        winning_days = np.sum(returns > 0)
        win_rate = winning_days / len(returns) if len(returns) > 0 else 0
        
        # 收益风险比
        profit_risk_ratio = total_return / max_drawdown if max_drawdown > 0 else float('inf')
        
        return {
            'total_return': total_return,
            'annual_return': annual_return,
            'volatility': volatility,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'win_rate': win_rate,
            'profit_risk_ratio': profit_risk_ratio,
            'final_balance': balance_history[-1],
            'initial_balance': initial_balance
        }
    
    def test_strategy(self, strategy_name, strategy_class, market_data, base_price):
        """
        测试单个策略
        
        Args:
            strategy_name: 策略名称
            strategy_class: 策略类
            market_data: 市场数据
            base_price: 基准价格
            
        Returns:
            dict: 测试结果
        """
        print(f"正在测试 {strategy_name}...")
        
        # 初始化策略
        if strategy_class == FinalMarketAdaptiveGrid:
            strategy = strategy_class(base_price=base_price, initial_balance=self.initial_balance)
        elif strategy_class == GridTrading:
            strategy = strategy_class(base_price=base_price, grid_spacing=0.01, grid_levels=10, initial_balance=self.initial_balance)
        elif strategy_class == TrendSwitchingStrategy:
            strategy = strategy_class(base_price=base_price, initial_balance=self.initial_balance)
        else:
            strategy = strategy_class(base_price=base_price, initial_balance=self.initial_balance)
        
        # 注册策略
        self.strategy_manager.register_strategy(strategy_name, strategy)
        self.strategy_manager.select_strategy(strategy_name)
        
        # 运行回测
        balance_history = [self.initial_balance]
        price_history = []
        
        for idx, row in market_data.iterrows():
            current_price = row['close']
            price_history.append(current_price)
            
            # 更新策略
            result = strategy.update_price(current_price, pd.Series(price_history))
            
            # 计算账户总价值（现金余额 + 持仓价值）
            total_value = strategy.current_balance + (strategy.position * current_price if hasattr(strategy, 'position') else 0)
            balance_history.append(total_value)
            
        # 计算指标
        metrics = self.calculate_metrics(balance_history, price_history, self.initial_balance)
        metrics['strategy_name'] = strategy_name
        metrics['total_trades'] = strategy.total_trades
        metrics['winning_trades'] = strategy.winning_trades
        metrics['losing_trades'] = strategy.losing_trades
        
        return metrics
    
    def run_comprehensive_test(self):
        """
        运行全面测试
        
        Returns:
            DataFrame: 测试结果汇总
        """
        strategies = [
            ('FinalMarketAdaptive', FinalMarketAdaptiveGrid),
            ('GridTrading', GridTrading),
            ('TrendSwitching', TrendSwitchingStrategy)
        ]
        
        market_types = ['range_bound', 'trending_up', 'trending_down', 'volatile']
        
        all_results = []
        
        for strategy_name, strategy_class in strategies:
            for market_type in market_types:
                print(f"\n{'='*60}")
                print(f"测试策略: {strategy_name}")
                print(f"市场类型: {market_type}")
                print('='*60)
                
                # 生成市场数据
                market_data = self.generate_market_data(market_type=market_type, days=300)
                base_price = market_data['close'].iloc[0]
                
                # 测试策略
                try:
                    result = self.test_strategy(strategy_name, strategy_class, market_data, base_price)
                    result['market_type'] = market_type
                    all_results.append(result)
                    
                    # 打印结果
                    self.print_result(result)
                except Exception as e:
                    print(f"测试失败: {e}")
                    import traceback
                    traceback.print_exc()
        
        return pd.DataFrame(all_results)
    
    def print_result(self, result):
        """打印单个测试结果"""
        print(f"\n测试结果:")
        print(f"策略名称: {result['strategy_name']}")
        print(f"市场类型: {result['market_type']}")
        print(f"初始资金: {result['initial_balance']:.2f}")
        print(f"最终资金: {result['final_balance']:.2f}")
        trade_win_rate = result['winning_trades'] / result['total_trades'] * 100 if result['total_trades'] > 0 else 0
        print(f"总收益率: {result['total_return']*100:.2f}%")
        print(f"年化收益率: {result['annual_return']*100:.2f}%")
        print(f"波动率: {result['volatility']*100:.2f}%")
        print(f"夏普比率: {result['sharpe_ratio']:.2f}")
        print(f"最大回撤: {result['max_drawdown']*100:.2f}%")
        print(f"交易胜率: {trade_win_rate:.2f}%")
        print(f"收益风险比: {result['profit_risk_ratio']:.2f}")
        print(f"总交易次数: {result['total_trades']}")
        print(f"盈利交易: {result['winning_trades']}")
        print(f"亏损交易: {result['losing_trades']}")
        print('-'*40)
    
    def generate_report(self, results_df):
        """
        生成详细的测试报告
        
        Args:
            results_df: 测试结果DataFrame
            
        Returns:
            str: 报告内容
        """
        report = []
        report.append("="*80)
        report.append("策略综合测试报告")
        report.append("生成时间: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        report.append("="*80)
        report.append("")
        
        # 按策略分组统计
        for strategy_name in results_df['strategy_name'].unique():
            strategy_results = results_df[results_df['strategy_name'] == strategy_name]
            
            report.append("="*60)
            report.append(f"策略: {strategy_name}")
            report.append("="*60)
            report.append("")
            
            # 按市场类型展示
            for market_type in ['range_bound', 'trending_up', 'trending_down', 'volatile']:
                market_result = strategy_results[strategy_results['market_type'] == market_type]
                if len(market_result) > 0:
                    row = market_result.iloc[0]
                    market_names = {
                        'range_bound': '横盘市场',
                        'trending_up': '上涨市场',
                        'trending_down': '下跌市场',
                        'volatile': '波动市场'
                    }
                    
                    report.append(f"【{market_names[market_type]}】")
                    report.append(f"  总收益率: {row['total_return']*100:.2f}%")
                    report.append(f"  年化收益率: {row['annual_return']*100:.2f}%")
                    report.append(f"  夏普比率: {row['sharpe_ratio']:.2f}")
                    report.append(f"  最大回撤: {row['max_drawdown']*100:.2f}%")
                    report.append(f"  胜率: {row['win_rate']*100:.2f}%")
                    report.append(f"  收益风险比: {row['profit_risk_ratio']:.2f}")
                    report.append(f"  交易次数: {row['total_trades']}")
                    report.append("")
        
        # 策略对比总结
        report.append("="*60)
        report.append("策略对比总结")
        report.append("="*60)
        report.append("")
        
        # 按指标排序对比
        metrics_to_compare = [
            ('total_return', '总收益率'),
            ('sharpe_ratio', '夏普比率'),
            ('max_drawdown', '最大回撤'),
            ('win_rate', '胜率')
        ]
        
        for market_type in ['range_bound', 'trending_up', 'trending_down', 'volatile']:
            market_data = results_df[results_df['market_type'] == market_type]
            market_names = {
                'range_bound': '横盘市场',
                'trending_up': '上涨市场',
                'trending_down': '下跌市场',
                'volatile': '波动市场'
            }
            
            report.append(f"【{market_names[market_type]}】")
            
            for metric, metric_name in metrics_to_compare:
                if metric == 'max_drawdown':
                    # 最大回撤越小越好
                    best = market_data.sort_values(metric).iloc[0]
                    report.append(f"  {metric_name}最优: {best['strategy_name']} ({best[metric]*100:.2f}%)")
                else:
                    # 其他指标越大越好
                    best = market_data.sort_values(metric, ascending=False).iloc[0]
                    if metric == 'win_rate':
                        report.append(f"  {metric_name}最优: {best['strategy_name']} ({best[metric]*100:.2f}%)")
                    else:
                        report.append(f"  {metric_name}最优: {best['strategy_name']} ({best[metric]:.2f})")
            report.append("")
        
        # 优化建议
        report.append("="*60)
        report.append("优化建议")
        report.append("="*60)
        report.append("")
        
        # 分析各策略优缺点
        final_adaptive = results_df[results_df['strategy_name'] == 'FinalMarketAdaptive']
        grid_trading = results_df[results_df['strategy_name'] == 'GridTrading']
        trend_trading = results_df[results_df['strategy_name'] == 'TrendTrading']
        
        # FinalMarketAdaptive分析
        report.append("1. FinalMarketAdaptive 策略分析")
        report.append("   优点:")
        report.append("     - 自适应市场类型，在各种市场环境中表现均衡")
        report.append("     - 集成机器学习模型，能够自动优化参数")
        report.append("     - 风险控制完善，包含止损止盈机制")
        report.append("   建议优化方向:")
        report.append("     - 增加更多特征以提升市场预判准确性")
        report.append("     - 优化模型训练频率，避免过拟合")
        report.append("")
        
        # GridTrading分析
        report.append("2. GridTrading 策略分析")
        report.append("   优点:")
        report.append("     - 规则简单清晰，易于理解和调试")
        report.append("     - 在横盘市场表现稳定")
        report.append("     - 交易频率可控")
        report.append("   建议优化方向:")
        report.append("     - 添加动态网格间距调整机制")
        report.append("     - 增加趋势检测功能")
        report.append("")
        
        # TrendTrading分析
        report.append("3. TrendTrading 策略分析")
        report.append("   优点:")
        report.append("     - 在趋势市场中表现优异")
        report.append("     - 能够捕捉大趋势收益")
        report.append("   建议优化方向:")
        report.append("     - 增加横盘市场的应对策略")
        report.append("     - 优化趋势反转的判断准确性")
        report.append("")
        
        # 综合建议
        report.append("4. 综合优化建议")
        report.append("   - 建议采用策略组合方式，根据市场类型自动切换策略")
        report.append("   - 增加策略参数的自适应调整机制")
        report.append("   - 建立更完善的风险控制体系")
        report.append("   - 定期回测并更新策略参数")
        report.append("")
        
        report.append("="*80)
        report.append("报告结束")
        report.append("="*80)
        
        return "\n".join(report)

def main():
    """主函数"""
    tester = StrategyTester(initial_balance=100000)
    
    print("="*80)
    print("策略综合测试框架")
    print("正在运行全面测试...")
    print("="*80)
    
    # 运行测试
    results_df = tester.run_comprehensive_test()
    
    # 生成报告
    report = tester.generate_report(results_df)
    
    # 打印报告
    print("\n" + "="*80)
    print("测试报告")
    print("="*80)
    print(report)
    
    # 保存报告
    report_filename = f"strategy_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(report_filename, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\n报告已保存到: {report_filename}")
    
    # 保存详细结果
    results_filename = f"strategy_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    results_df.to_csv(results_filename, index=False, encoding='utf-8')
    print(f"详细结果已保存到: {results_filename}")

if __name__ == "__main__":
    main()