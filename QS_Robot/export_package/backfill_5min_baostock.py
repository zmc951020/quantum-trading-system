# -*- coding: utf-8 -*-
"""
backfill_5min_baostock.py — 5分钟K线历史回溯补数（2026-10-21）

背景：任务4「5分钟口径复核」需要 ≥6 个月 5 分钟数据。
现有 data_expansion_v1.py 用东财/新浪免费接口，历史深度受限
（东财只返回最近 ~1512 根，新浪更短），无法往前推。
实测 baostock（免费开源）支持 5 分钟历史回溯 16 个月+。

用法：
  python backfill_5min_baostock.py          # 补全 70 只，从 2025-06-01 拉至最新
  python backfill_5min_baostock.py --start 2025-01-01
"""
import argparse
import os
import sys
import time

import baostock as bs
import pandas as pd

MIN_DIR = r'D:\Gupiao\升级vscode\QS_Robot\export_package\data\minute_data_ext'
COLS = ['time', 'open', 'high', 'low', 'close', 'volume', 'amount', 'day']


def fetch(code: str, start: str, end: str) -> pd.DataFrame:
    bs_code = f'sh.{code}' if code.startswith('6') else f'sz.{code}'
    rs = bs.query_history_k_data_plus(
        bs_code, 'date,time,open,high,low,close,volume,amount',
        start_date=start, end_date=end, frequency='5', adjustflag='2'
    )
    rows = []
    while (rs.error_code == '0') and rs.next():
        rows.append(rs.get_row_data())
    if not rows:
        return pd.DataFrame(columns=COLS)
    df = pd.DataFrame(rows, columns=['date', 'time', 'open', 'high', 'low', 'close', 'volume', 'amount'])
    df['time'] = pd.to_datetime(df['time'], format='%Y%m%d%H%M%S%f').dt.strftime('%Y-%m-%d %H:%M:%S')
    df['day'] = df['date']
    df = df[COLS]
    for c in ['open', 'high', 'low', 'close', 'volume', 'amount']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    return df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', default='2025-06-01')
    parser.add_argument('--limit', type=int, default=0, help='只处理前 N 只（调试用）')
    args = parser.parse_args()

    codes = sorted(f.replace('_5min.csv', '') for f in os.listdir(MIN_DIR) if f.endswith('_5min.csv'))
    if args.limit > 0:
        codes = codes[:args.limit]
    print(f'共 {len(codes)} 只，回溯起点 {args.start}')

    lg = bs.login()
    print('baostock login:', lg.error_code, lg.error_msg)
    ok = fail = 0
    t0 = time.time()
    for i, code in enumerate(codes, 1):
        try:
            df = fetch(code, args.start, '2026-12-31')
            if df.empty:
                print(f'[{i}/{len(codes)}] {code}: 无数据')
                fail += 1
                continue
            # 覆盖写（baostock 前复权更完整，含现有缺口）
            out = os.path.join(MIN_DIR, f'{code}_5min.csv')
            df.to_csv(out, index=False)
            ok += 1
            if i % 10 == 0 or i == len(codes):
                span = f'{df["time"].iloc[0][:10]} ~ {df["time"].iloc[-1][:10]} ({len(df)}根)'
                print(f'[{i}/{len(codes)}] {code}: {span}  用时{time.time()-t0:.0f}s')
        except Exception as e:
            print(f'[{i}/{len(codes)}] {code}: 失败 {e}')
            fail += 1
    bs.logout()
    print(f'完成: 成功 {ok} / 失败 {fail}，总用时 {time.time()-t0:.0f}s')


if __name__ == '__main__':
    sys.exit(main())
