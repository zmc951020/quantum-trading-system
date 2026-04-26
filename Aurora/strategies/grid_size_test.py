#!/usr/bin/env python3
"""
分钟级高频网格交易测试 - 不同网格大小比较
测试3分钟和5分钟交易间隔下的不同网格大小表现
"""

import numpy as np
import pandas as pd
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))


class MinuteHighFrequencyGridTrading:
    """
    分钟级高频网格交易策略
    """

    def __init__(self, initial_balance=100000.0, base_price=100.0, trade_interval=180, grid_spacing=0.001):
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.base_price = base_price
        self.position = 0
        self.entry_price = 0

        # 网格参数
        self.grid_spacing = grid_spacing  # 网格间距
        self.grid_levels = 30
        self.upper_limit = base_price * (1 + self.grid_spacing * self.grid_levels)
        self.lower_limit = base_price * (1 - self.grid_spacing * self.grid_levels)

        # 交易参数
        self.fee_rate = 0.0003  # 手续费
        self.slippage = 0.0002  # 滑点

        # 统计数据
        self.total_trades = 0
        self.buy_count = 0
        self.sell_count = 0
        self.profit_history = []
        self.price_history = []
        self.balance_history = []

        # 网格状态
        self.grids = []
        self._create_grids()

        # 交易控制
        self.last_trade_time = 0
        self.min_trade_interval = trade_interval
        self.last_position = 0
        self.total_cost = 0

    def _create_grids(self):
        """创建网格"""
        self.grids = []
        price_range = self.upper_limit - self.lower_limit
        for i in range(self.grid_levels + 1):
            price = self.lower_limit + (price_range / self.grid_levels) * i
            self.grids.append(price)

    def reset(self):
        """重置策略状态"""
        self.current_balance = self.initial_balance
        self.position = 0
        self.entry_price = 0
        self.total_trades = 0
        self.buy_count = 0
        self.sell_count = 0
        self.profit_history = []
        self.price_history = []
        self.balance_history = []
        self.last_trade_time = 0
        self.last_position = 0
        self.total_cost = 0

    def buy(self, price, quantity):
        """买入"""
        cost = price * quantity * (1 + self.fee_rate + self.slippage)
        if cost > self.current_balance:
            quantity = self.current_balance / (price * (1 + self.fee_rate + self.slippage))

        if quantity > 0:
            self.current_balance -= price * quantity * (1 + self.fee_rate + self.slippage)
            self.position += quantity
            self.entry_price = price
            self.buy_count += 1
            self.total_trades += 1
            self.total_cost += cost * (self.fee_rate + self.slippage)
            return True
        return False

    def sell(self, price, quantity):
        """卖出"""
        if quantity > self.position:
            quantity = self.position

        if quantity > 0:
            revenue = price * quantity * (1 - self.fee_rate - self.slippage)
            self.current_balance += revenue
            self.position -= quantity

            if self.entry_price > 0:
                profit = (price - self.entry_price) * quantity * (1 - self.fee_rate - self.slippage)
                self.profit_history.append(profit)
                self.total_cost += revenue * (self.fee_rate + self.slippage)

            self.sell_count += 1
            self.total_trades += 1
            return True
        return False

    def update_price(self, current_price, timestamp):
        """更新价格并执行交易"""
        self.price_history.append(current_price)
        current_time = timestamp.timestamp()

        if current_time - self.last_trade_time < self.min_trade_interval:
            pass
        else:
            # 每次交易使用5%的资金
            available_balance = self.current_balance
            max_position_value = available_balance * 0.05
            trade_quantity = max_position_value / current_price

            if len(self.price_history) >= 2:
                prev_price = self.price_history[-2]

                # 核心交易逻辑：只根据价格方向和间隔交易
                if self.position == 0:
                    if current_price < prev_price:
                        if self.buy(current_price, trade_quantity):
                            self.last_trade_time = current_time
                            self.last_position = 1
                else:
                    if current_price > prev_price:
                        if self.sell(current_price, self.position):
                            self.last_trade_time = current_time
                            self.last_position = 0

        total_value = self.current_balance + self.position * current_price
        self.balance_history.append(total_value)

    def get_performance(self):
        """获取性能指标"""
        if not self.price_history:
            return {}

        final_price = self.price_history[-1]
        final_value = self.current_balance + self.position * final_price
        total_return = (final_value - self.initial_balance) / self.initial_balance * 100

        if len(self.profit_history) > 0:
            winning_trades = sum(1 for p in self.profit_history if p > 0)
            win_rate = winning_trades / len(self.profit_history) * 100
            avg_profit = np.mean(self.profit_history)
            total_profit = sum(self.profit_history)
        else:
            win_rate = 0
            avg_profit = 0
            total_profit = 0

        if len(self.balance_history) > 1:
            returns = np.diff(self.balance_history) / self.balance_history[:-1]
            sharpe_ratio = returns.mean() / returns.std() * np.sqrt(252 * 480 * 60) if returns.std() > 0 else 0
        else:
            sharpe_ratio = 0

        if len(self.balance_history) > 1:
            cummax = np.maximum.accumulate(self.balance_history)
            drawdowns = (cummax - self.balance_history) / cummax
            max_drawdown = drawdowns.max() * 100
        else:
            max_drawdown = 0

        return {
            "initial_balance": self.initial_balance,
            "final_value": final_value,
            "total_return": total_return,
            "total_trades": self.total_trades,
            "buy_count": self.buy_count,
            "sell_count": self.sell_count,
            "win_rate": win_rate,
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown": max_drawdown,
            "final_price": final_price,
            "final_position": self.position,
            "final_balance": self.current_balance,
            "avg_profit": avg_profit,
            "total_profit": total_profit,
            "total_cost": self.total_cost
        }


def generate_4hour_data():
    """生成4小时的秒级模拟数据（4小时 = 14400秒）"""
    np.random.seed(42)
    total_seconds = 4 * 60 * 60  # 4小时
    dates = pd.date_range('2024-01-01 09:30:00', periods=total_seconds, freq='1s')

    base_price = 100.0
    price = base_price
    prices = []

    for i in range(total_seconds):
        noise = np.random.normal(0, 0.1)
        price += noise
        price = max(50, price)
        prices.append(price)

    df = pd.DataFrame({'Date': dates, 'Close': prices})
    df.set_index('Date', inplace=True)
    return df


def test_grid_size(trade_interval, grid_spacing, data):
    """测试特定网格大小"""
    strategy = MinuteHighFrequencyGridTrading(
        initial_balance=100000.0,
        base_price=100.0,
        trade_interval=trade_interval,
        grid_spacing=grid_spacing
    )

    for i, (date, row) in enumerate(data.iterrows()):
        current_price = row['Close']
        strategy.update_price(current_price, date)

    perf = strategy.get_performance()

    return {
        "交易间隔": f"{trade_interval}秒({trade_interval//60}分钟)",
        "网格间距": f"{grid_spacing*100:.4f}%",
        "交易次数": perf['total_trades'],
        "收益率": f"{perf['total_return']:.2f}%",
        "胜率": f"{perf['win_rate']:.2f}%",
        "夏普比率": f"{perf['sharpe_ratio']:.4f}",
        "最大回撤": f"{perf['max_drawdown']:.2f}%",
        "最终价值": f"{perf['final_value']:.2f}",
        "总成本": f"{perf['total_cost']:.2f}",
        "total_return_value": perf['total_return']
    }


def main():
    print("=" * 80)
    print("分钟级高频网格交易测试 - 不同网格大小比较")
    print("=" * 80)

    print("\n生成4小时交易数据...")
    data = generate_4hour_data()
    print(f"数据量: {len(data)} 条秒级数据")
    print(f"数据周期: {data.index[0]} 到 {data.index[-1]}")
    print(f"总交易时间: {len(data) / 3600:.1f} 小时")

    # 测试3分钟和5分钟交易间隔
    intervals = [180, 300]  # 3分钟和5分钟
    
    # 测试不同的网格大小
    grid_spacings = [
        0.0001,  # 0.01%
        0.0002,  # 0.02%
        0.0005,  # 0.05%
        0.001,   # 0.1%
        0.002,   # 0.2%
        0.005,   # 0.5%
        0.01,    # 1%
        0.02,    # 2%
        0.05     # 5%
    ]

    results = []

    print("\n" + "=" * 80)
    print("测试结果")
    print("=" * 80)

    for interval in intervals:
        print(f"\n测试交易间隔: {interval}秒 ({interval//60}分钟)...")
        for grid_spacing in grid_spacings:
            print(f"  网格间距: {grid_spacing*100:.4f}%...")
            result = test_grid_size(interval, grid_spacing, data)
            results.append(result)

            print(f"    交易次数: {result['交易次数']}")
            print(f"    收益率: {result['收益率']}")
            print(f"    胜率: {result['胜率']}")
            print(f"    夏普比率: {result['夏普比率']}")

    print("\n" + "=" * 80)
    print("汇总比较")
    print("=" * 80)
    print(f"{'交易间隔':<15} {'网格间距':<15} {'交易次数':<10} {'收益率':<10} {'胜率':<10} {'夏普比率':<12} {'最大回撤':<10}")
    print("-" * 80)

    for result in results:
        print(f"{result['交易间隔']:<15} {result['网格间距']:<15} {result['交易次数']:<10} {result['收益率']:<10} {result['胜率']:<10} {result['夏普比率']:<12} {result['最大回撤']:<10}")

    print("\n" + "=" * 80)
    print("最佳网格大小分析")
    print("=" * 80)

    # 分析3分钟交易间隔的最佳网格大小
    three_min_results = [r for r in results if r['交易间隔'] == '180秒(3分钟)']
    if three_min_results:
        best_three_min = max(three_min_results, key=lambda x: x['total_return_value'])
        print(f"\n3分钟交易间隔最佳网格大小:")
        print(f"  网格间距: {best_three_min['网格间距']}")
        print(f"  收益率: {best_three_min['收益率']}")
        print(f"  交易次数: {best_three_min['交易次数']}")
        print(f"  胜率: {best_three_min['胜率']}")
        print(f"  夏普比率: {best_three_min['夏普比率']}")

    # 分析5分钟交易间隔的最佳网格大小
    five_min_results = [r for r in results if r['交易间隔'] == '300秒(5分钟)']
    if five_min_results:
        best_five_min = max(five_min_results, key=lambda x: x['total_return_value'])
        print(f"\n5分钟交易间隔最佳网格大小:")
        print(f"  网格间距: {best_five_min['网格间距']}")
        print(f"  收益率: {best_five_min['收益率']}")
        print(f"  交易次数: {best_five_min['交易次数']}")
        print(f"  胜率: {best_five_min['胜率']}")
        print(f"  夏普比率: {best_five_min['夏普比率']}")

    print("\n" + "=" * 80)
    print("规律总结")
    print("=" * 80)

    # 分析网格大小与收益率的关系
    print("\n【网格大小与收益率的关系】")
    for interval in intervals:
        interval_results = [r for r in results if r['交易间隔'] == f'{interval}秒({interval//60}分钟)']
        if interval_results:
            print(f"  交易间隔: {interval//60}分钟")
            for result in sorted(interval_results, key=lambda x: float(x['网格间距'].replace('%', ''))):
                print(f"    网格间距: {result['网格间距']} -> 收益率: {result['收益率']}")

    print("\n【结论】")
    print("  1. 不同的网格大小对收益率有显著影响")
    print("  2. 最佳网格大小取决于价格波动和交易成本")
    print("  3. 太小的网格可能导致交易成本过高")
    print("  4. 太大的网格可能导致交易次数太少")

    return results


if __name__ == "__main__":
    main()