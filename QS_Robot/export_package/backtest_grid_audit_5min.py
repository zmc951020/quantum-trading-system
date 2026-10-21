#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backtest_grid_audit_5min.py — 5分钟口径复核（2026-10-21）
对象：final_market_adaptive（日线口径 -2.70%，待 5 分钟复核裁决）
       high_return_grid（5 分钟是网格主场，交叉验证）
口径：5 分钟 K 线、T+1（同日买入当日不可卖）、双边成本 0.1%、降频 20（=生产加载器行为）
用法：D:\\anaconda3\\python.exe export_package\\backtest_grid_audit_5min.py --codes 601398,600519 --strategies final_market_adaptive,high_return_grid
"""
import os
import sys
import argparse
import numpy as np
import pandas as pd

QS_ROOT = r'D:\Gupiao\升级vscode\QS_Robot'
STRATEGIES = os.path.join(QS_ROOT, 'export_package', 'strategies_local')
DATA_DIR = os.path.join(QS_ROOT, 'export_package', 'data', 'minute_data_ext')
FEE = 0.0005
INIT = 100000.0
AUDIT = [
    ('final_market_adaptive', 'final_market_adaptive', 'FinalMarketAdaptiveGrid', True),
    ('high_return_grid',      'high_return_grid',      'HighReturnGridTrading',   False),
    ('adaptive_range_grid',   'adaptive_range_grid',   'AdaptiveRangeGridTrading', True),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--codes', default='601398,600519,000858,000651')
    ap.add_argument('--strategies', default=None)
    args = ap.parse_args()
    codes = [c.strip().zfill(6) for c in args.codes.split(',') if c.strip()]
    audit = AUDIT if not args.strategies else [x for x in AUDIT if x[0] in args.strategies.split(',')]
    for d in (STRATEGIES, QS_ROOT):
        if d not in sys.path:
            sys.path.insert(0, d)
    print('=== 5分钟口径复核（降频20=生产行为）===')
    rows = []
    for code in codes:
        p = os.path.join(DATA_DIR, f'{code}_5min.csv')
        if not os.path.exists(p):
            continue
        df = pd.read_csv(p)
        for c in ('open', 'high', 'low', 'close', 'volume'):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce')
        df = df.dropna(subset=['close']).reset_index(drop=True)
        # 按 day 分组做 T+1：同一 day 内买入当日不可卖
        if 'day' in df.columns:
            df['_day'] = df['day']
        for name, mod, cls, nb in audit:
            m = __import__(mod)
            C = getattr(m, cls)
            base = float(df['close'].iloc[0]) if nb else None
            s = C(base_price=base, initial_balance=INIT) if nb else C(initial_balance=INIT)
            # 审计隔离：重定向策略内置参数持久化到临时目录，避免复核过程改写生产 optimized_params.pkl
            audit_dir = os.path.join(QS_ROOT, 'export_package', 'strategy_params_audit_tmp')
            if hasattr(s, 'persist_dir'):
                s.persist_dir = audit_dir
                s.persist_file = os.path.join(audit_dir, 'optimized_params.pkl')
                s.persist_history_file = os.path.join(audit_dir, 'training_history.json')
            cash = INIT; pos = 0.0; entry = 0.0; trades = buys = sells = wins = errs = 0
            n = len(df)
            num = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and c != '_day']
            last_day = None
            can_sell = True
            for i in range(20, n, 20):
                row = df.iloc[:i + 1][num]
                price = float(row['close'].iloc[-1])
                day = df['_day'].iloc[i] if '_day' in df.columns else None
                if day != last_day:
                    can_sell = True  # 新的一天解锁
                    last_day = day
                try:
                    r = s.update_price(price, data=row.copy())
                except Exception:
                    errs += 1
                    r = None
                if not isinstance(r, dict):
                    continue
                act = r.get('action') or r.get('signal') or ''
                if act in ('buy', 'BUY', 2) and cash > price * 1.01:
                    sh = int((cash * 0.8) / price)
                    if sh > 0:
                        cash -= sh * price * (1 + FEE); pos += sh; entry = price
                        trades += 1; buys += 1; can_sell = False
                elif act in ('sell', 'SELL', 0) and pos > 0 and can_sell:
                    cash += pos * price * (1 - FEE)
                    if price > entry: wins += 1
                    pos = 0.0; trades += 1; sells += 1; can_sell = True
            if pos > 0:
                cash += pos * float(df['close'].iloc[-1]) * (1 - FEE)
            ret = (cash - INIT) / INIT
            bench = float(df['close'].iloc[-1]) / float(df['close'].iloc[20]) - 1
            rows.append((name, code, ret, bench, trades, wins, errs))
            wr = wins / sells * 100 if sells else 0
            print(f"[{name}] {code}: 收益{ret*100:7.2f}% vs 基准{bench*100:7.2f}% "
                  f"交易{trades}(买{buys}/卖{sells}) 胜率{wr:.0f}% 异常{errs}")
    print('\n=== 汇总 ===')
    for name in dict.fromkeys(x[0] for x in rows):
        rr = [x for x in rows if x[0] == name]
        m = {k: np.mean([x[k] for x in rr]) for k in (2, 3, 4)}
        errs = sum(x[6] for x in rr)
        print(f"{name:24s}: 平均收益{m[2]*100:7.2f}% vs 基准{m[3]*100:7.2f}% | 交易{m[4]:.1f} 异常{errs}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
