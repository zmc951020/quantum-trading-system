#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试魔法策略：看看为什么0交易
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
from minervini_sepa_strategy import MinerviniSepaStrategy

DATA_DIR = r'D:\Gupiao\升级vscode\QS_Robot\export_package\data\daily_data_ext'


def load_data(symbol: str) -> pd.DataFrame:
    csv_path = os.path.join(DATA_DIR, f'{symbol}_daily.csv')
    df = pd.read_csv(csv_path)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    return df


def debug_stock(symbol: str):
    print(f"\n{'='*60}")
    print(f"调试股票: {symbol}")
    print(f"{'='*60}")

    df = load_data(symbol)
    print(f"总K线数: {len(df)}")
    print(f"时间范围: {df['date'].iloc[0].date()} ~ {df['date'].iloc[-1].date()}")

    # 初始化策略
    base_price = df['close'].iloc[0]
    strategy = MinerviniSepaStrategy(base_price=base_price, initial_balance=100000)
    strategy.set_dataframe(df)

    # 检查趋势模板
    print(f"\n--- 检查趋势模板（最后一天） ---")
    try:
        trend_pass = strategy.passes_trend_template()
        print(f"趋势模板通过: {trend_pass}")
    except Exception as e:
        print(f"趋势模板检查出错: {e}")

    # 检查RS评分
    print(f"\n--- 检查RS评分 ---")
    try:
        rs = strategy.relative_rating(df, strategy.benchmark_df)
        print(f"RS评分: {rs:.1f}")
    except Exception as e:
        print(f"RS评分检查出错: {e}")

    # 检查VCP
    print(f"\n--- 检查VCP（波动收缩） ---")
    try:
        vcp_result = strategy.detect_vcp()
        print(f"VCP检测结果: {vcp_result}")
    except Exception as e:
        print(f"VCP检测出错: {e}")

    # 逐bar扫描，看看有没有任何一天接近条件
    print(f"\n--- 逐bar扫描（从第250根开始） ---")
    buy_count = 0
    sell_count = 0
    trend_pass_count = 0
    rs_pass_count = 0

    for i in range(250, len(df)):
        row = df.iloc[i]
        current_price = row['close']

        try:
            result = strategy.update_price(current_price=current_price)
            action = result.get('action', 'hold')
            reason = result.get('reason', '')

            if action == 'buy':
                buy_count += 1
                print(f"  买入信号: {row['date'].date()} @ {current_price:.2f}")
            elif action == 'sell':
                sell_count += 1
                print(f"  卖出信号: {row['date'].date()} @ {current_price:.2f}")

            # 每100根bar打印一次状态
            if i % 100 == 0:
                print(f"  bar {i}: {row['date'].date()}, action={action}, reason={reason[:50]}")

        except Exception as e:
            if i == 250:
                print(f"  第250根bar出错: {e}")

    print(f"\n--- 统计 ---")
    print(f"买入信号数: {buy_count}")
    print(f"卖出信号数: {sell_count}")


if __name__ == '__main__':
    # 调试第一只股票
    debug_stock('000009')
