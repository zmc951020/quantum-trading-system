#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试：看看趋势模板具体哪几条没通过
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

    # 初始化策略
    base_price = df['close'].iloc[0]
    strategy = MinerviniSepaStrategy(base_price=base_price, initial_balance=100000)
    strategy.set_dataframe(df)

    # 检查最新一天的趋势模板
    trend_pass, details = strategy.passes_trend_template(df)
    print(f"\n趋势模板通过: {trend_pass}")
    print("\n各条详情:")
    for k, (passed, reason) in details.items():
        status = "✅" if passed else "❌"
        print(f"  {status} {k}: {reason}")

    # 看看最近100天里，有没有哪一天通过了趋势模板
    print(f"\n--- 最近100天趋势模板通过情况 ---")
    pass_days = 0
    for i in range(max(250, len(df)-100), len(df)):
        df_slice = df.iloc[:i+1].copy()
        try:
            # 需要先设置RS评分
            strategy.relative_rating(df_slice, None)  # 无基准，用个股动量
            passed, _ = strategy.passes_trend_template(df_slice)
            if passed:
                pass_days += 1
                if pass_days <= 3:
                    print(f"  ✅ {df['date'].iloc[i].date()}: 通过")
        except Exception as e:
            pass

    print(f"\n最近100天通过天数: {pass_days}")


if __name__ == '__main__':
    debug_stock('000823')
