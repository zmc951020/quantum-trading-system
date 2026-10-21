#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
魔法策略简单回测脚本
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
from minervini_sepa_strategy import MinerviniSepaStrategy

# 20只最近上升趋势股票（60天涨幅最大）
STOCKS = [
    '001368', '001326', '000993', '000823', '000011',
    '001216', '000530', '000560', '000995', '001318',
    '001211', '000635', '000607', '000526', '000710',
    '000626', '000498', '000731', '601857', '001228'
]

DATA_DIR = r'D:\Gupiao\升级vscode\QS_Robot\export_package\data\daily_data_ext'


def load_data(symbol: str) -> pd.DataFrame:
    """加载本地CSV数据"""
    csv_path = os.path.join(DATA_DIR, f'{symbol}_daily.csv')
    if not os.path.exists(csv_path):
        return None
    df = pd.read_csv(csv_path)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    return df


def backtest_stock(symbol: str) -> dict:
    """回测单只股票"""
    df = load_data(symbol)
    if df is None or len(df) < 250:
        return {'symbol': symbol, 'error': '数据不足'}

    # 初始化策略
    base_price = df['close'].iloc[0]
    strategy = MinerviniSepaStrategy(base_price=base_price, initial_balance=100000)

    # 注入数据（绕过load_data，直接用本地CSV）
    strategy.set_dataframe(df)

    # 交易记录
    trades = []
    position = 0  # 0=空仓, 1=持仓
    entry_price = 0

    # 逐bar回测（从第250根开始，因为MA200需要200根）
    for i in range(250, len(df)):
        row = df.iloc[i]
        current_price = row['close']

        # 更新策略
        result = strategy.update_price(current_price=current_price)
        action = result.get('action', 'hold')

        if action == 'buy' and position == 0:
            # 买入
            position = 1
            entry_price = current_price
            trades.append({
                'date': row['date'],
                'action': 'BUY',
                'price': current_price
            })
        elif action == 'sell' and position == 1:
            # 卖出
            position = 0
            exit_price = current_price
            trades.append({
                'date': row['date'],
                'action': 'SELL',
                'price': exit_price,
                'profit_pct': (exit_price - entry_price) / entry_price * 100
            })

    # 统计
    buy_trades = [t for t in trades if t['action'] == 'BUY']
    sell_trades = [t for t in trades if t['action'] == 'SELL']

    profits = [t.get('profit_pct', 0) for t in sell_trades]
    total_trades = len(sell_trades)
    win_trades = len([p for p in profits if p > 0])
    win_rate = win_trades / total_trades * 100 if total_trades > 0 else 0
    avg_profit = np.mean(profits) if profits else 0

    return {
        'symbol': symbol,
        'total_bars': len(df),
        'total_trades': total_trades,
        'win_rate': win_rate,
        'avg_profit': avg_profit,
        'trades': trades
    }


def main():
    print("=" * 60)
    print("魔法策略简单回测（20只长历史股）")
    print("=" * 60)

    results = []
    for symbol in STOCKS:
        print(f"回测 {symbol}...")
        result = backtest_stock(symbol)
        results.append(result)

    # 汇总
    print("\n" + "=" * 60)
    print("回测结果汇总")
    print("=" * 60)

    total_trades_all = 0
    total_win_trades = 0
    total_profits = []
    stocks_with_trades = 0

    for r in results:
        if 'error' in r:
            print(f"{r['symbol']}: {r['error']}")
            continue

        print(f"{r['symbol']}: {r['total_trades']}笔交易, 胜率{r['win_rate']:.1f}%, 平均{r['avg_profit']:.2f}%")
        total_trades_all += r['total_trades']
        total_win_trades += len([p for p in r.get('trades', []) if p['action'] == 'SELL' and p.get('profit_pct', 0) > 0])
        total_profits.extend([t.get('profit_pct', 0) for t in r.get('trades', []) if t['action'] == 'SELL'])
        if r['total_trades'] > 0:
            stocks_with_trades += 1

    print("\n" + "=" * 60)
    print(f"总股票数: {len(results)}")
    print(f"有交易的股票数: {stocks_with_trades}")
    print(f"总交易次数: {total_trades_all}")
    if total_trades_all > 0:
        print(f"总胜率: {total_win_trades / total_trades_all * 100:.1f}%")
        print(f"平均每笔收益: {np.mean(total_profits):.2f}%")
    print("=" * 60)


if __name__ == '__main__':
    main()
