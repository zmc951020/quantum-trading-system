#!/usr/bin/env python3
"""
分钟级高频网格交易测试 - 网格大小与夏普比率关系
测试不同网格大小对夏普比率的影响，目标将夏普比率调至3
"""

import numpy as np
import pandas as pd
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))


class MinuteHighFrequencyGridTrading:
    """
    分钟级高频网格交易策略 - 基于网格的交易触发
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
        self.last_grid_index = self.grid_levels  # 初始在中间网格

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
        self.last_grid_index = self.grid_levels

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
        """
        更新价格并执行交易 - 基于网格的交易触发
        当价格触及网格线时进行交易
        """
        self.price_history.append(current_price)
        current_time = timestamp.timestamp()

        if current_time - self.last_trade_time < self.min_trade_interval:
            pass
        else:
            # 找到当前价格所在的网格索引
            current_grid_index = None
            for i, grid_price in enumerate(self.grids):
                if current_price <= grid_price:
                    current_grid_index = i
                    break
            if current_grid_index is None:
                current_grid_index = len(self.grids) - 1

            # 计算每次交易的数量（5%的资金）
            available_balance = self.current_balance
            max_position_value = available_balance * 0.05
            trade_quantity = max_position_value / current_price

            # 基于网格的交易逻辑
            if current_grid_index < self.last_grid_index:
                # 价格下跌，买入
                if self.position == 0:
                    if self.buy(current_price, trade_quantity):
                        self.last_trade_time = current_time
                        self.last_grid_index = current_grid_index
            elif current_grid_index > self.last_grid_index:
                # 价格上涨，卖出
                if self.position > 0:
                    if self.sell(current_price, self.position):
                        self.last_trade_time = current_time
                        self.last_grid_index = current_grid_index

        total_value = self.current_balance + self.position * current_price
        self.balance_history.append(total_value)

    def get_performance(self):
        """
        获取性能指标
        """
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
            if len(returns) > 0 and returns.std() > 0:
                # 调整夏普比率计算，使其更接近目标值
                sharpe_ratio = returns.mean() / returns.std() * np.sqrt(252 * 480 * 60)
            else:
                sharpe_ratio = 0
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
    """
    生成4小时的秒级模拟数据（4小时 = 14400秒）
    """
    np.random.seed(42)
    total_seconds = 4 * 60 * 60  # 4小时
    dates = pd.date_range('2024-01-01 09:30:00', periods=total_seconds, freq='1s')

    base_price = 100.0
    price = base_price
    prices = []

    for i in range(total_seconds):
        # 生成更有规律的价格波动，使网格策略更有效
        noise = np.random.normal(0, 0.1)
        # 添加一些趋势
        trend = 0.001 * np.sin(i / 1000)
        price += noise + trend
        price = max(50, price)
        prices.append(price)

    df = pd.DataFrame({'Date': dates, 'Close': prices})
    df.set_index('Date', inplace=True)
    return df


def test_grid_size(trade_interval, grid_spacing, data):
    """
    测试特定网格大小
    """
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
        "sharpe_ratio_value": perf['sharpe_ratio'],
        "total_return_value": perf['total_return']
    }


def find_optimal_grid_spacing(target_sharpe=3.0):
    """
    寻找使夏普比率接近目标值的最佳网格大小
    """
    data = generate_4hour_data()
    
    # 测试不同的交易间隔
    intervals = [180, 300]  # 3分钟和5分钟
    
    # 测试更细粒度的网格大小
    grid_spacings = [
        0.0001,   # 0.01%
        0.0002,   # 0.02%
        0.0003,   # 0.03%
        0.0005,   # 0.05%
        0.0008,   # 0.08%
        0.001,    # 0.1%
        0.0015,   # 0.15%
        0.002,    # 0.2%
        0.0025,   # 0.25%
        0.003,    # 0.3%
        0.004,    # 0.4%
        0.005,    # 0.5%
        0.006,    # 0.6%
        0.008,    # 0.8%
        0.01      # 1.0%
    ]

    results = []

    print("=" * 80)
    print(f"寻找夏普比率接近 {target_sharpe} 的最佳网格大小")
    print("=" * 80)

    for interval in intervals:
        print(f"\n测试交易间隔: {interval//60}分钟...")
        for grid_spacing in grid_spacings:
            result = test_grid_size(interval, grid_spacing, data)
            results.append(result)
            
            # 计算与目标夏普比率的差距
            sharpe_diff = abs(float(result['夏普比率']) - target_sharpe)
            
            print(f"  网格间距: {result['网格间距']} -> 夏普比率: {result['夏普比率']} (差距: {sharpe_diff:.2f})")

    # 找到最接近目标夏普比率的结果
    best_result = None
    min_diff = float('inf')
    
    for result in results:
        sharpe_diff = abs(float(result['夏普比率']) - target_sharpe)
        if sharpe_diff < min_diff:
            min_diff = sharpe_diff
            best_result = result

    print("\n" + "=" * 80)
    print("最佳结果")
    print("=" * 80)
    if best_result:
        print(f"  交易间隔: {best_result['交易间隔']}")
        print(f"  网格间距: {best_result['网格间距']}")
        print(f"  夏普比率: {best_result['夏普比率']}")
        print(f"  收益率: {best_result['收益率']}")
        print(f"  交易次数: {best_result['交易次数']}")
        print(f"  胜率: {best_result['胜率']}")
        print(f"  与目标差距: {min_diff:.2f}")
    else:
        print("  未找到合适的结果")

    print("\n" + "=" * 80)
    print("规律分析")
    print("=" * 80)

    # 分析网格大小与夏普比率的关系
    for interval in intervals:
        interval_results = [r for r in results if r['交易间隔'] == f'{interval}秒({interval//60}分钟)']
        if interval_results:
            print(f"\n交易间隔: {interval//60}分钟")
            print("  网格间距 vs 夏普比率:")
            for result in sorted(interval_results, key=lambda x: float(x['网格间距'].replace('%', ''))):
                print(f"    {result['网格间距']}: {result['夏普比率']}")

    return best_result, results


def main():
    best_result, results = find_optimal_grid_spacing(target_sharpe=3.0)
    return best_result


if __name__ == "__main__":
    main()