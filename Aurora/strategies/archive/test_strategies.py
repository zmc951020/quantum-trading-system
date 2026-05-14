#!/usr/bin/env python3
"""
策略性能测试脚本
测试优化后的HighReturnGridTrading和MLRangeGridTrading策略
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import sys
import os

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from high_return_grid import HighReturnGridTrading
from ml_range_grid import MLRangeGridTrading

class StrategyTester:
    """
    策略性能测试类
    """

    def __init__(self, data_file: str = None):
        """
        初始化测试类
        
        Args:
            data_file: 数据文件路径
        """
        self.data = self._load_data(data_file)
        self.results = {}

    def _load_data(self, data_file: str) -> pd.DataFrame:
        """
        加载测试数据
        
        Args:
            data_file: 数据文件路径
            
        Returns:
            价格数据
        """
        if data_file and os.path.exists(data_file):
            # 加载真实数据
            df = pd.read_csv(data_file)
            return df
        else:
            # 生成模拟数据
            return self._generate_simulated_data()

    def _generate_simulated_data(self, market_type='mixed') -> pd.DataFrame:
        """
        生成模拟价格数据（分钟级）
        
        Args:
            market_type: 市场类型 ('mixed', 'range_bound', 'trending_up')
            
        Returns:
            模拟价格数据（分钟级）
        """
        np.random.seed(42)
        
        # 生成分钟级数据（1天，480分钟）
        # 480条数据，用于快速测试高频交易
        dates = pd.date_range('2024-01-01', periods=480, freq='1min')
        base_price = 100.0
        
        # 生成带趋势和波动的价格
        price = base_price
        prices = []
        
        minutes_per_day = 480  # 每天480分钟交易时间
        trading_days = 365
        
        for i in range(len(dates)):
            day_index = i // minutes_per_day  # 当前是第几天
            minute_of_day = i % minutes_per_day  # 当天的第几分钟
            
            # 加入随机波动（每分钟波动更大）
            noise = np.random.normal(0, 0.3)
            
            if market_type == 'range_bound':
                # 横盘市场：价格在一定范围内波动
                daily_trend = 0.001 * np.sin(day_index / 5 + minute_of_day / 60)
                price += daily_trend + noise * 0.2
            elif market_type == 'trending_up':
                # 上涨市场：整体趋势向上
                daily_trend = 0.002 + 0.001 * np.sin(minute_of_day / 60)
                price += daily_trend + noise * 0.25
            else:  # mixed
                # 混合市场
                if day_index < 60:
                    # 横盘
                    price += 0.001 * np.sin(minute_of_day / 60) + noise * 0.15
                elif day_index < 120:
                    # 上涨
                    price += 0.003 + noise * 0.2
                elif day_index < 180:
                    # 横盘
                    price += 0.001 * np.sin(minute_of_day / 60) + noise * 0.15
                else:
                    # 下跌
                    price -= 0.002 + noise * 0.2
            
            prices.append(max(50, price))  # 确保价格不会太低
        
        df = pd.DataFrame({'Date': dates, 'Close': prices})
        df.set_index('Date', inplace=True)
        return df

    def test_strategy(self, strategy_name: str, strategy):
        """
        测试策略性能
        
        Args:
            strategy_name: 策略名称
            strategy: 策略实例
        """
        print(f"\n测试 {strategy_name} 策略")
        print("-" * 80)
        
        # 记录性能数据
        equity_history = []
        drawdown_history = []
        trades = []
        
        highest_equity = strategy.initial_balance
        max_drawdown = 0
        
        # 回测
        for i, price in enumerate(self.data['Close']):
            # 构建数据窗口
            data_window = self.data['Close'].iloc[max(0, i-100):i+1]
            
            # 更新价格
            result = strategy.update_price(price, data_window)
            
            # 计算当前权益
            current_price = price
            current_equity = strategy.balance if hasattr(strategy, 'balance') else strategy.current_balance
            current_position = strategy.position
            total_equity = current_equity + current_position * current_price
            equity_history.append(total_equity)
            
            # 计算回撤
            if total_equity > highest_equity:
                highest_equity = total_equity
            drawdown = (highest_equity - total_equity) / highest_equity
            drawdown_history.append(drawdown)
            if drawdown > max_drawdown:
                max_drawdown = drawdown
            
            # 记录交易
            if result.get('action') in ['buy', 'sell']:
                trades.append({
                    'date': self.data.index[i],
                    'action': result['action'],
                    'price': price,
                    'quantity': result.get('quantity', 0),
                    'balance': current_equity,
                    'position': current_position
                })
        
        # 获取策略性能
        performance = strategy.get_performance()
        
        # 计算额外指标
        returns = np.diff(equity_history) / equity_history[:-1]
        sharpe_ratio = np.mean(returns) / np.std(returns) if len(returns) > 0 else 0
        sortino_ratio = np.mean(returns) / np.std(returns[returns < 0]) if len(returns[returns < 0]) > 0 else 0
        
        # 保存结果
        self.results[strategy_name] = {
            'performance': performance,
            'equity_history': equity_history,
            'drawdown_history': drawdown_history,
            'trades': trades,
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sortino_ratio,
            'max_drawdown': max_drawdown
        }
        
        # 打印结果
        print(f"初始资金: {performance['initial_balance']:.2f}")
        final_balance = performance.get('total_value', performance.get('current_balance', 0))
        print(f"最终资金: {final_balance:.2f}")
        return_rate = performance.get('return', (final_balance - performance['initial_balance']) / performance['initial_balance'] * 100)
        print(f"总收益率: {return_rate:.2f}%")
        print(f"总交易次数: {performance.get('total_trades', 0)}")
        print(f"胜率: {performance.get('win_rate', 0):.2f}%")
        print(f"平均每笔收益: {performance.get('avg_profit_per_trade', 0):.2f}")
        print(f"总收益: {performance.get('total_profit', 0):.2f}")
        print(f"最大回撤: {performance.get('max_drawdown', max_drawdown * 100):.2f}%")
        print(f"夏普比率: {sharpe_ratio:.2f}")
        print(f"索提诺比率: {sortino_ratio:.2f}")
        if 'grid_adjustments' in performance:
            print(f"网格调整次数: {performance['grid_adjustments']}")
        if 'model_training_count' in performance:
            print(f"模型训练次数: {performance['model_training_count']}")
        print(f"交易次数: {len(trades)}")

    def plot_results(self):
        """
        绘制测试结果
        """
        plt.figure(figsize=(12, 8))
        
        # 绘制权益曲线
        plt.subplot(2, 1, 1)
        for strategy_name, result in self.results.items():
            plt.plot(result['equity_history'], label=strategy_name)
        plt.title('策略权益曲线')
        plt.xlabel('时间')
        plt.ylabel('权益')
        plt.legend()
        plt.grid(True)
        
        # 绘制回撤曲线
        plt.subplot(2, 1, 2)
        for strategy_name, result in self.results.items():
            plt.plot(result['drawdown_history'], label=strategy_name)
        plt.title('策略回撤曲线')
        plt.xlabel('时间')
        plt.ylabel('回撤')
        plt.legend()
        plt.grid(True)
        
        plt.tight_layout()
        plt.savefig('strategy_performance.png')
        print("\n性能图表已保存到 strategy_performance.png")

    def run_all_tests(self):
        """
        运行所有策略测试
        """
        # 测试不同市场环境
        market_types = ['range_bound', 'trending_up']
        
        for market_type in market_types:
            print(f"\n{market_type} 市场测试")
            print("=" * 80)
            
            # 生成对应市场的数据
            self.data = self._generate_simulated_data(market_type)
            self.results = {}
            
            # 测试HighReturnGridTrading策略
            hrgt = HighReturnGridTrading(initial_balance=100000.0, base_price=self.data['Close'].iloc[0])
            self.test_strategy('HighReturnGridTrading', hrgt)
            
            # 测试MLRangeGridTrading策略
            mlrgt = MLRangeGridTrading(base_price=self.data['Close'].iloc[0], initial_balance=100000.0)
            self.test_strategy('MLRangeGridTrading', mlrgt)
            
            # 绘制结果
            self.plot_results()
            
            # 打印综合比较
            print("\n" + "=" * 80)
            print(f"{market_type} 市场策略性能比较")
            print("=" * 80)
            
            for strategy_name, result in self.results.items():
                perf = result['performance']
                final_balance = perf.get('total_value', perf.get('current_balance', 0))
                return_rate = perf.get('return', (final_balance - perf['initial_balance']) / perf['initial_balance'] * 100)
                win_rate = perf.get('win_rate', 0)
                max_drawdown = perf.get('max_drawdown', result['max_drawdown'] * 100)
                
                print(f"{strategy_name}:")
                print(f"  收益率: {return_rate:.2f}%")
                print(f"  胜率: {win_rate:.2f}%")
                print(f"  最大回撤: {max_drawdown:.2f}%")
                print(f"  夏普比率: {result['sharpe_ratio']:.2f}")
                print(f"  索提诺比率: {result['sortino_ratio']:.2f}")
                print()

if __name__ == "__main__":
    # 运行测试
    tester = StrategyTester()
    tester.run_all_tests()
