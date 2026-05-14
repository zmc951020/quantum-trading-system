#!/usr/bin/env python3
"""
分钟级高频网格交易测试 - 最终版（无过滤）
核心：只根据交易间隔和价格方向交易，实现真正的的高频交易
"""

import numpy as np
import pandas as pd
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))


class MinuteHighFrequencyGridTrading:
    """
    分钟级高频网格交易策略 - 最终版
    核心：只根据交易间隔和价格方向交易
    """

    def __init__(self, initial_balance=100000.0, base_price=100.0, trade_interval=1):
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.base_price = base_price
        self.position = 0
        self.entry_price = 0

        # 网格参数
        self.grid_spacing = 0.001  # 0.1% 网格间距
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
        """更新价格并执行交易 - 核心：无过滤，只根据间隔和方向交易"""
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

                # 核心交易逻辑：只根据价格方向和间隔交易，无其他过滤
                if self.position == 0:
                    # 没有持仓，价格下跌时买入
                    if current_price < prev_price:
                        if self.buy(current_price, trade_quantity):
                            self.last_trade_time = current_time
                            self.last_position = 1
                else:
                    # 有持仓，价格上涨时卖出
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


def generate_second_data(days=1):
    """生成秒级模拟数据"""
    np.random.seed(42)
    total_seconds = days * 480 * 60
    dates = pd.date_range('2024-01-01', periods=total_seconds, freq='1s')

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


def test_frequency(trade_freq_per_minute, data):
    """测试特定交易频率"""
    trade_interval = 60 / trade_freq_per_minute

    strategy = MinuteHighFrequencyGridTrading(
        initial_balance=100000.0,
        base_price=100.0,
        trade_interval=trade_interval
    )

    for i, (date, row) in enumerate(data.iterrows()):
        current_price = row['Close']
        strategy.update_price(current_price, date)

    perf = strategy.get_performance()

    actual_trades_per_minute = perf['total_trades'] / (len(data) / 60)

    return {
        "目标频率": f"{trade_freq_per_minute}次/分钟",
        "实际频率": f"{actual_trades_per_minute:.2f}次/分钟",
        "总交易次数": perf['total_trades'],
        "收益率": f"{perf['total_return']:.2f}%",
        "胜率": f"{perf['win_rate']:.2f}%",
        "夏普比率": f"{perf['sharpe_ratio']:.4f}",
        "最大回撤": f"{perf['max_drawdown']:.2f}%",
        "最终价值": f"{perf['final_value']:.2f}",
        "总成本": f"{perf['total_cost']:.2f}",
        "avg_profit": perf['avg_profit']
    }


def main():
    print("=" * 80)
    print("分钟级高频网格交易测试 - 最终版（无过滤）")
    print("=" * 80)

    print("\n生成测试数据...")
    data = generate_second_data(days=1)
    print(f"数据量: {len(data)} 条秒级数据")
    print(f"数据周期: {data.index[0]} 到 {data.index[-1]}")

    frequencies = [10, 20, 30, 40, 50, 60]
    results = []

    print("\n" + "=" * 80)
    print("测试结果")
    print("=" * 80)

    for freq in frequencies:
        print(f"\n测试频率: {freq}次/分钟...")
        result = test_frequency(freq, data)
        results.append(result)

        print(f"  目标频率: {result['目标频率']}")
        print(f"  实际频率: {result['实际频率']}")
        print(f"  总交易次数: {result['总交易次数']}")
        print(f"  收益率: {result['收益率']}")
        print(f"  胜率: {result['胜率']}")
        print(f"  夏普比率: {result['夏普比率']}")
        print(f"  最大回撤: {result['最大回撤']}")
        print(f"  最终价值: {result['最终价值']}")
        print(f"  总成本: {result['总成本']}")

    print("\n" + "=" * 80)
    print("汇总比较")
    print("=" * 80)
    print(f"{'目标频率':<15} {'实际频率':<15} {'总交易次数':<12} {'收益率':<10} {'胜率':<10} {'夏普比率':<12} {'最大回撤':<10}")
    print("-" * 80)

    for result in results:
        print(f"{result['目标频率']:<15} {result['实际频率']:<15} {result['总交易次数']:<12} {result['收益率']:<10} {result['胜率']:<10} {result['夏普比率']:<12} {result['最大回撤']:<10}")

    print("\n" + "=" * 80)
    print("结论")
    print("=" * 80)

    best_return_idx = max(range(len(results)), key=lambda i: float(results[i]['收益率'][:-1]))
    best_return_result = results[best_return_idx]

    best_sharpe_idx = max(range(len(results)), key=lambda i: float(results[i]['夏普比率']))
    best_sharpe_result = results[best_sharpe_idx]

    best_drawdown_idx = min(range(len(results)), key=lambda i: float(results[i]['最大回撤'][:-1]))
    best_drawdown_result = results[best_drawdown_idx]

    print(f"最佳收益率: {best_return_result['目标频率']} - {best_return_result['收益率']}")
    print(f"最佳夏普比率: {best_sharpe_result['目标频率']} - {best_sharpe_result['夏普比率']}")
    print(f"最低最大回撤: {best_drawdown_result['目标频率']} - {best_drawdown_result['最大回撤']}")

    return results


if __name__ == "__main__":
    main()