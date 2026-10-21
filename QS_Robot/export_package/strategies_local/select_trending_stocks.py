#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从本地CSV数据里选出最近上升趋势的股票
"""

import os
import pandas as pd
import numpy as np

DATA_DIR = r'D:\Gupiao\升级vscode\QS_Robot\export_package\data\daily_data_ext'


def calc_recent_return(csv_path: str, days: int = 60) -> tuple:
    """计算最近days天的涨幅"""
    df = pd.read_csv(csv_path)
    if len(df) < days + 200:
        return None, 0

    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)

    # 最近days天的涨幅
    start_price = df['close'].iloc[-days]
    end_price = df['close'].iloc[-1]
    return_pct = (end_price - start_price) / start_price * 100

    return df, return_pct


def main():
    print("=" * 60)
    print("选出最近60天上升趋势的股票")
    print("=" * 60)

    stocks = []
    files = [f for f in os.listdir(DATA_DIR) if f.endswith('_daily.csv')]

    for f in files:
        csv_path = os.path.join(DATA_DIR, f)
        symbol = f.replace('_daily.csv', '')

        df, ret = calc_recent_return(csv_path, days=60)
        if df is None:
            continue

        # 同时检查：价格在MA200之上（上升趋势的基本条件）
        ma200 = df['close'].rolling(200).mean().iloc[-1]
        price_above_ma200 = df['close'].iloc[-1] > ma200

        stocks.append({
            'symbol': symbol,
            'return_60d': ret,
            'price_above_ma200': price_above_ma200,
            'current_price': df['close'].iloc[-1],
            'date_range': f"{df['date'].iloc[0].date()}~{df['date'].iloc[-1].date()}"
        })

    # 按涨幅排序
    stocks.sort(key=lambda x: x['return_60d'], reverse=True)

    print(f"\n总股票数: {len(stocks)}")

    # 选出涨幅前20，且价格在MA200之上的
    trending_stocks = [s for s in stocks if s['price_above_ma200']][:20]

    print(f"\n=== 最近60天上升趋势前20名（价格在MA200之上） ===")
    for i, s in enumerate(trending_stocks, 1):
        print(f"{i:2d}. {s['symbol']}: 60天涨幅 {s['return_60d']:+.1f}%, "
              f"价格 {s['current_price']:.2f}, 在MA200之上={s['price_above_ma200']}")

    # 保存到文件
    output_file = os.path.join(os.path.dirname(__file__), 'trending_stocks.txt')
    with open(output_file, 'w') as f:
        for s in trending_stocks:
            f.write(f"{s['symbol']}\n")

    print(f"\n股票列表已保存到: {output_file}")


if __name__ == '__main__':
    main()
