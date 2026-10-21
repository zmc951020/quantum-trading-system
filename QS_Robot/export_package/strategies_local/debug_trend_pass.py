#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试：看看这些股票在历史上有没有满足过趋势模板8条
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

    # 逐bar检查趋势模板是否通过
    pass_count = 0
    pass_dates = []

    for i in range(250, len(df)):
        # 用截至第i根bar的数据检查
        df_slice = df.iloc[:i+1].copy()

        try:
            # 临时修改self.df为切片
            old_df = strategy.df
            strategy.df = df_slice

            trend_pass, details = strategy.passes_trend_template(df_slice)
            if trend_pass:
                pass_count += 1
                pass_dates.append(df['date'].iloc[i].date())

            # 恢复
            strategy.df = old_df
        except Exception as e:
            pass

    print(f"\n趋势模板通过次数: {pass_count}")
    if pass_dates:
        print(f"首次通过: {pass_dates[0]}")
        print(f"最后通过: {pass_dates[-1]}")
        print(f"最近5次: {pass_dates[-5:]}")
    else:
        print("⚠️ 从未通过趋势模板8条！")

    # 看看最新一天的具体情况
    print(f"\n--- 最新一天({df['date'].iloc[-1].date()})详情 ---")
    close = df['close'].values
    ma50 = pd.Series(close).rolling(50).mean().iloc[-1]
    ma150 = pd.Series(close).rolling(150).mean().iloc[-1]
    ma200 = pd.Series(close).rolling(200).mean().iloc[-1]
    print(f"当前价格: {close[-1]:.2f}")
    print(f"MA50: {ma50:.2f}")
    print(f"MA150: {ma150:.2f}")
    print(f"MA200: {ma200:.2f}")
    print(f"价格>MA150: {close[-1] > ma150}")
    print(f"价格>MA200: {close[-1] > ma200}")
    print(f"MA150>MA200: {ma150 > ma200}")
    print(f"MA50>MA150: {ma50 > ma150}")


if __name__ == '__main__':
    # 调试3只代表性股票
    debug_stock('001368')
    debug_stock('601857')
    debug_stock('000823')
