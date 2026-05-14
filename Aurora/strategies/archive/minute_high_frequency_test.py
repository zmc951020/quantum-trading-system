#!/usr/bin/env python3
"""
分钟级高频交易测试
测试网格交易策略在分钟级数据上的表现
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

class MinuteHighFrequencyGridTrading:
    """
    分钟级高频网格交易策略
    优化版：提高交易频率和盈利能力
    """

    def __init__(self, initial_balance=100000.0, base_price=100.0):
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.base_price = base_price
        self.position = 0
        self.entry_price = 0

        # 网格参数 - 优化版
        self.grid_spacing = 0.001  # 0.1% 网格间距
        self.grid_levels = 30  # 30个网格
        self.upper_limit = base_price * (1 + self.grid_spacing * self.grid_levels)
        self.lower_limit = base_price * (1 - self.grid_spacing * self.grid_levels)

        # 交易参数
        self.fee_rate = 0.0003  # 手续费
        self.slippage = 0.0002  # 滑点
        self.min_profit_pct = self.fee_rate * 1.5 + self.slippage * 1.5  # 减小最小盈利要求，增加交易机会

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
        self.last_trade_time = 0  # 上次交易的时间戳
        self.min_trade_interval = 1  # 最小交易间隔（秒），进一步提高交易频率
        self.last_position = 0  # 上次持仓状态
        self.price_change_history = []  # 价格变化历史
        self.trade_count = 0  # 交易计数器

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
        self.last_trade_price = self.base_price

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
            self.last_trade_price = price
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

            self.sell_count += 1
            self.total_trades += 1
            self.last_trade_price = price
            return True
        return False

    def update_price(self, current_price, timestamp):
        """
        更新价格并执行交易
        核心逻辑：价格波动足够大时交易，实现高频交易
        """
        self.price_history.append(current_price)

        # 计算当前时间（秒）
        current_time = timestamp.timestamp()

        # 检查交易间隔
        if current_time - self.last_trade_time < self.min_trade_interval:
            # 交易间隔不足，跳过
            pass
        else:
            # 计算每次交易的数量（每次用2%的资金）
            available_balance = self.current_balance
            max_position_value = available_balance * 0.02  # 每次2%的资金，更小的资金比例，降低风险
            trade_quantity = max_position_value / current_price

            # 价格波动过滤：只有当价格波动足够大时才交易
            if len(self.price_history) >= 2:
                prev_price = self.price_history[-2]
                price_change_pct = abs(current_price - prev_price) / prev_price
                self.price_change_history.append(price_change_pct)
                
                # 只有当价格波动超过最小盈利百分比时才交易
                if price_change_pct >= self.min_profit_pct:
                    # 核心交易逻辑
                    if self.position == 0:
                        # 没有持仓，价格下跌时买入
                        if current_price < prev_price:
                            if self.buy(current_price, trade_quantity):
                                self.last_trade_time = current_time
                                self.last_position = 1
                                self.trade_count += 1
                    else:
                        # 有持仓，价格上涨时卖出
                        if current_price > prev_price:
                            # 确保卖出价格高于买入价格，保证盈利
                            if current_price > self.entry_price:
                                if self.sell(current_price, self.position):
                                    self.last_trade_time = current_time
                                    self.last_position = 0
                                    self.trade_count += 1

        # 记录余额
        total_value = self.current_balance + self.position * current_price
        self.balance_history.append(total_value)

    def get_performance(self):
        """获取性能指标"""
        if not self.price_history:
            return {}

        final_price = self.price_history[-1]
        final_value = self.current_balance + self.position * final_price
        total_return = (final_value - self.initial_balance) / self.initial_balance * 100

        # 计算胜率
        if len(self.profit_history) > 0:
            winning_trades = sum(1 for p in self.profit_history if p > 0)
            win_rate = winning_trades / len(self.profit_history) * 100
        else:
            win_rate = 0

        # 计算夏普比率（简化版）
        if len(self.balance_history) > 1:
            returns = np.diff(self.balance_history) / self.balance_history[:-1]
            sharpe_ratio = returns.mean() / returns.std() * np.sqrt(252 * 480) if returns.std() > 0 else 0
        else:
            sharpe_ratio = 0

        # 计算最大回撤
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
            "final_balance": self.current_balance
        }


def generate_minute_data(days=30, minutes_per_day=480):
    """
    生成秒级模拟数据
    每分钟生成60个数据点（每秒1个）
    """
    np.random.seed(42)
    total_minutes = days * minutes_per_day
    total_seconds = total_minutes * 60  # 每分钟60秒
    dates = pd.date_range('2024-01-01', periods=total_seconds, freq='1s')

    base_price = 100.0
    price = base_price
    prices = []

    for i in range(total_seconds):
        # 随机波动（每秒波动）
        noise = np.random.normal(0, 0.1)  # 增大波动，使价格更容易触发交易
        price += noise
        price = max(50, price)  # 确保价格不会太低
        prices.append(price)

    df = pd.DataFrame({'Date': dates, 'Close': prices})
    df.set_index('Date', inplace=True)
    return df


def test_high_frequency_trading():
    """测试高频网格交易策略"""
    print("=" * 80)
    print("分钟级高频网格交易测试")
    print("=" * 80)

    # 生成秒级数据
    data = generate_minute_data(days=1)  # 1天数据，减少数据量以提高运行速度
    print(f"\n数据量: {len(data)} 条秒级数据")
    print(f"数据周期: {data.index[0]} 到 {data.index[-1]}")

    # 初始化策略
    strategy = MinuteHighFrequencyGridTrading(
        initial_balance=100000.0,
        base_price=100.0
    )

    print(f"\n策略参数:")
    print(f"  网格间距: {strategy.grid_spacing * 100:.4f}%")
    print(f"  网格层数: {strategy.grid_levels}")
    print(f"  初始资金: {strategy.initial_balance:.2f}")

    # 运行策略
    print("\n运行策略...")
    for i, (date, row) in enumerate(data.iterrows()):
        current_price = row['Close']
        strategy.update_price(current_price, date)

        if (i + 1) % 5000 == 0:
            print(f"  已处理 {i+1}/{len(data)} 条数据...")

    # 获取性能
    perf = strategy.get_performance()

    print("\n" + "=" * 80)
    print("测试结果")
    print("=" * 80)
    print(f"初始资金: {perf['initial_balance']:.2f}")
    print(f"最终价值: {perf['final_value']:.2f}")
    print(f"总收益率: {perf['total_return']:.2f}%")
    print(f"总交易次数: {perf['total_trades']}")
    print(f"买入次数: {perf['buy_count']}")
    print(f"卖出次数: {perf['sell_count']}")
    print(f"胜率: {perf['win_rate']:.2f}%")
    print(f"夏普比率: {perf['sharpe_ratio']:.4f}")
    print(f"最大回撤: {perf['max_drawdown']:.2f}%")

    # 计算每分钟交易次数
    minutes = len(data)
    trades_per_minute = perf['total_trades'] / minutes
    print(f"\n平均每分钟交易次数: {trades_per_minute:.2f} 次/分钟")

    return perf


if __name__ == "__main__":
    result = test_high_frequency_trading()