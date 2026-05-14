import numpy as np
import pandas as pd
import sys
import os
import datetime

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from final_market_adaptive import FinalMarketAdaptiveGrid

class MinuteTradingTester:
    def __init__(self, initial_balance=100000, base_price=100):
        self.initial_balance = initial_balance
        self.base_price = base_price
        self.results = []

    def generate_minute_data(self, days=30, base_price=100, volatility=0.001):
        minutes_per_day = 390
        total_minutes = days * minutes_per_day
        
        np.random.seed(42)
        
        start_date = datetime.datetime(2024, 1, 1)
        time_index = pd.date_range(start=start_date, periods=total_minutes, freq='T')
        
        prices = [base_price]
        for i in range(1, total_minutes):
            reversion = 0.001 * (base_price - prices[-1])
            random_shock = np.random.normal(0, base_price * volatility)
            new_price = prices[-1] + reversion + random_shock
            new_price = max(base_price * 0.9, min(base_price * 1.1, new_price))
            prices.append(new_price)
        
        return pd.Series(prices, index=time_index)

    def generate_trending_minute_data(self, days=30, base_price=100, trend_direction=1):
        minutes_per_day = 390
        total_minutes = days * minutes_per_day
        
        np.random.seed(42)
        
        start_date = datetime.datetime(2024, 1, 1)
        time_index = pd.date_range(start=start_date, periods=total_minutes, freq='T')
        
        daily_trend = 0.005 * trend_direction
        
        prices = [base_price]
        for i in range(1, total_minutes):
            day_of_period = i // minutes_per_day
            trend_component = daily_trend * day_of_period
            reversion = 0.001 * (base_price * (1 + trend_component) - prices[-1])
            random_shock = np.random.normal(0, base_price * 0.001)
            new_price = prices[-1] + reversion + random_shock
            prices.append(new_price)
        
        return pd.Series(prices, index=time_index)

    def test_minute_strategy(self, price_data, market_type='range_bound'):
        strategy = FinalMarketAdaptiveGrid(base_price=self.base_price, initial_balance=self.initial_balance)
        
        for i, (timestamp, price) in enumerate(price_data.items()):
            data_window = price_data.iloc[:i+1]
            strategy.update_price(price, data_window)
        
        final_price = price_data.iloc[-1]
        total_assets = strategy.current_balance + strategy.position * final_price
        capital_utilization = (strategy.position * final_price) / total_assets * 100 if total_assets > 0 else 0
        win_rate = strategy.winning_trades / strategy.total_trades * 100 if strategy.total_trades > 0 else 0
        
        returns = np.array(strategy.balance_history)
        if len(returns) > 1:
            returns_pct = np.diff(returns) / returns[:-1]
            n_days = int(len(price_data) / 390)
            if n_days > 0 and len(returns_pct) >= n_days:
                daily_returns = []
                for i in range(n_days):
                    start_idx = i * 390
                    end_idx = min((i + 1) * 390, len(returns_pct))
                    if start_idx < end_idx:
                        daily_returns.append(returns_pct[start_idx:end_idx].sum())
                daily_returns = np.array(daily_returns)
            else:
                daily_returns = np.array([returns_pct.sum()])
        else:
            daily_returns = np.array([0])
        
        daily_returns = daily_returns[daily_returns != 0]
        
        annual_return = (total_assets - self.initial_balance) / self.initial_balance * (365 / (len(price_data) / 390))
        volatility = daily_returns.std() * np.sqrt(252) if len(daily_returns) > 0 else 0
        sharpe_ratio = annual_return / volatility if volatility > 0 else 0
        
        peak = np.maximum.accumulate(strategy.balance_history)
        drawdown = (peak - strategy.balance_history) / peak
        max_drawdown = np.max(drawdown)
        
        return {
            'market_type': market_type,
            'total_minutes': len(price_data),
            'total_days': len(price_data) / 390,
            'initial_balance': self.initial_balance,
            'final_balance': strategy.current_balance,
            'final_position': strategy.position,
            'final_price': final_price,
            'total_assets': total_assets,
            'total_return': (total_assets - self.initial_balance) / self.initial_balance,
            'annual_return': annual_return,
            'volatility': volatility,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'total_trades': strategy.total_trades,
            'winning_trades': strategy.winning_trades,
            'losing_trades': strategy.losing_trades,
            'win_rate': win_rate,
            'capital_utilization': capital_utilization,
            'avg_trades_per_day': strategy.total_trades / (len(price_data) / 390),
            'accumulation_fund': strategy.accumulation_fund
        }

    def run_comprehensive_minute_test(self):
        print('=' * 80)
        print('分钟级交易策略测试')
        print('=' * 80)
        print()
        
        results = []
        
        print('测试横盘市场...')
        range_data = self.generate_minute_data(days=5, base_price=100, volatility=0.0015)
        range_result = self.test_minute_strategy(range_data, 'range_bound')
        results.append(range_result)
        self.print_result(range_result)
        
        print('测试上涨市场...')
        up_data = self.generate_trending_minute_data(days=5, base_price=100, trend_direction=1)
        up_result = self.test_minute_strategy(up_data, 'trending_up')
        results.append(up_result)
        self.print_result(up_result)
        
        print('测试下跌市场...')
        down_data = self.generate_trending_minute_data(days=5, base_price=100, trend_direction=-1)
        down_result = self.test_minute_strategy(down_data, 'trending_down')
        results.append(down_result)
        self.print_result(down_result)
        
        print('测试波动市场...')
        vol_data = self.generate_minute_data(days=5, base_price=100, volatility=0.003)
        vol_result = self.test_minute_strategy(vol_data, 'volatile')
        results.append(vol_result)
        self.print_result(vol_result)
        
        self.generate_report(results)
        
        return results

    def print_result(self, result):
        print(f"\n{'='*60}")
        print(f"市场类型: {result['market_type']}")
        print(f"测试周期: {result['total_days']:.1f}天 ({result['total_minutes']}分钟)")
        print(f"初始资金: {result['initial_balance']:.2f}")
        print(f"最终资金: {result['final_balance']:.2f}")
        print(f"最终持仓: {result['final_position']:.4f}")
        print(f"持仓价值: {result['final_position'] * result['final_price']:.2f}")
        print(f"总资产: {result['total_assets']:.2f}")
        print(f"总收益率: {result['total_return'] * 100:.2f}%")
        print(f"年化收益率: {result['annual_return'] * 100:.2f}%")
        print(f"波动率: {result['volatility'] * 100:.2f}%")
        print(f"夏普比率: {result['sharpe_ratio']:.2f}")
        print(f"最大回撤: {result['max_drawdown'] * 100:.2f}%")
        print(f"总交易次数: {result['total_trades']}")
        print(f"盈利交易: {result['winning_trades']}")
        print(f"亏损交易: {result['losing_trades']}")
        print(f"胜率: {result['win_rate']:.2f}%")
        print(f"日均交易次数: {result['avg_trades_per_day']:.2f}")
        print(f"资金使用率: {result['capital_utilization']:.2f}%")
        print(f"风险储备金: {result['accumulation_fund']:.2f}")
        print('='*60)

    def generate_report(self, results):
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        report_filename = f'minute_trading_report_{timestamp}.txt'
        
        with open(report_filename, 'w', encoding='utf-8') as f:
            f.write('=' * 80 + '\n')
            f.write('分钟级交易策略测试报告\n')
            f.write('=' * 80 + '\n')
            f.write(f'生成时间: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
            f.write('\n')
            
            for result in results:
                f.write('=' * 60 + '\n')
                f.write(f"【{result['market_type']}】\n")
                f.write('=' * 60 + '\n')
                f.write(f"测试周期: {result['total_days']:.1f}天 ({result['total_minutes']}分钟)\n")
                f.write(f"总收益率: {result['total_return'] * 100:.2f}%\n")
                f.write(f"年化收益率: {result['annual_return'] * 100:.2f}%\n")
                f.write(f"夏普比率: {result['sharpe_ratio']:.2f}\n")
                f.write(f"最大回撤: {result['max_drawdown'] * 100:.2f}%\n")
                f.write(f"总交易次数: {result['total_trades']}\n")
                f.write(f"日均交易次数: {result['avg_trades_per_day']:.2f}\n")
                f.write(f"胜率: {result['win_rate']:.2f}%\n")
                f.write(f"资金使用率: {result['capital_utilization']:.2f}%\n")
                f.write(f"风险储备金: {result['accumulation_fund']:.2f}\n")
                f.write('\n')
            
            f.write('=' * 80 + '\n')
            f.write('策略分析与建议\n')
            f.write('=' * 80 + '\n')
            
            avg_sharpe = np.mean([r['sharpe_ratio'] for r in results])
            avg_return = np.mean([r['total_return'] for r in results])
            avg_trades = np.mean([r['avg_trades_per_day'] for r in results])
            
            f.write(f"平均夏普比率: {avg_sharpe:.2f}\n")
            f.write(f"平均收益率: {avg_return * 100:.2f}%\n")
            f.write(f"平均日均交易: {avg_trades:.2f}次\n")
            f.write('\n')
            
            f.write('建议:\n')
            if avg_sharpe < 0.5:
                f.write('- 夏普比率较低，建议优化风险调整收益\n')
            if avg_trades < 50:
                f.write('- 交易频率较低，建议调整网格间距\n')
            if any(r['capital_utilization'] < 50 for r in results):
                f.write('- 资金使用率较低，建议调整资金分配策略\n')
            
            f.write('=' * 80 + '\n')
        
        print(f"\n报告已保存至: {report_filename}")

if __name__ == '__main__':
    tester = MinuteTradingTester(initial_balance=100000, base_price=100)
    tester.run_comprehensive_minute_test()
