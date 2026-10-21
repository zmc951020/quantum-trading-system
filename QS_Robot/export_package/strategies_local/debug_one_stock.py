#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试单只股票：看看为什么0交易
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


def main():
    # 选第一只股票调试
    symbol = '001368'
    print(f"调试股票: {symbol}")

    df = load_data(symbol)
    print(f"总K线数: {len(df)}")
    print(f"时间范围: {df['date'].iloc[0].date()} ~ {df['date'].iloc[-1].date()}")

    # 看看最近60天的价格
    print(f"\n最近60天价格:")
    for i in range(-10, 0):
        row = df.iloc[i]
        print(f"  {row['date'].date()}: {row['close']:.2f}")

    # 计算MA200
    ma200 = df['close'].rolling(200).mean()
    current_price = df['close'].iloc[-1]
    current_ma200 = ma200.iloc[-1]

    print(f"\n当前价格: {current_price:.2f}")
    print(f"MA200: {current_ma200:.2f}")
    print(f"价格在MA200之上: {current_price > current_ma200}")

    # 计算MA150
    ma150 = df['close'].rolling(150).mean()
    current_ma150 = ma150.iloc[-1]
    print(f"MA150: {current_ma150:.2f}")
    print(f"MA150在MA200之上: {current_ma150 > current_ma200}")

    # 初始化策略
    base_price = df['close'].iloc[0]
    strategy = MinerviniSepaStrategy(base_price=base_price, initial_balance=100000)
    strategy.set_dataframe(df)

    # 检查趋势模板
    print(f"\n--- 趋势模板检查 ---")
    try:
        trend_pass = strategy.passes_trend_template()
        print(f"趋势模板通过: {trend_pass}")
    except Exception as e:
        print(f"趋势模板检查出错: {e}")
        import traceback
        traceback.print_exc()

    # 逐bar扫描最后100根，看看action
    print(f"\n--- 最后100根bar的action ---")
    for i in range(len(df)-100, len(df)):
        row = df.iloc[i]
        current_price = row['close']

        try:
            result = strategy.update_price(current_price=current_price)
            action = result.get('action', 'hold')
            reason = result.get('reason', '')

            if action != 'hold' or i % 20 == 0:
                print(f"  {row['date'].date()}: action={action}, reason={reason[:60]}")
        except Exception as e:
            print(f"  {row['date'].date()}: 出错 {e}")


if __name__ == '__main__':
    main()
