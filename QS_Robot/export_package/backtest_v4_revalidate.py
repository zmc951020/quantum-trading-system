#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P0-B: V4.0 分层重验（统一底座 6 条热启动版）
==============================================
背景：V4.0 报告"热启动/通用信号无额外效果"基于 deep_optimizer_v16 旧版 3 条热启动
      （check_hot_start：放量>1.3x/站上MA60/止跌），与 unified_base_filter 的 6 条热启动无关。
      旧报告 B/C/D 三层中真正生效的只有底座一层（C/D 无额外过滤）。
本脚本用 UnifiedBaseFilter 的 6 条热启动在分钟级数据上重跑 B/C/D 分层，
检验 6 条热启动是否具有独立过滤效果（推翻或修正"热启动无用"结论）。

分层定义（对齐 unified_base_filter 真实链路）：
- A组：纯策略（无过滤）
- B组：+底座低位（check_low_position stars >= low_stars_min）
- C组：+低位 + 6条热启动（check_hot_start_6，min_hot_conditions 由 hot_strictness 决定）
- D组：完整 filter_one（低位 + 热启动 + 涨跌停 + 大盘 + 综合评分>=2）

数据：export_package/data/minute_data_ext/{code}_5min.csv（5分钟，48根/日）
用法：D:\\anaconda3\\python.exe export_package\\backtest_v4_revalidate.py
"""

import sys
import os
import numpy as np
import pandas as pd

sys.path.insert(0, r"D:\Gupiao\升级vscode\QS_Robot\export_package")
sys.path.insert(0, r"D:\Gupiao\升级vscode\QS_Robot")

from deep_optimizer_v16 import V14_FACTORIES, create_strategy_factory_v11
from tools.unified_base_filter import UnifiedBaseFilter

DATA_DIR = r"D:\Gupiao\升级vscode\QS_Robot\export_package\data\minute_data_ext"

# 重验统一底座配置（中档：低位星级>=2，热启动需 5/6 条）
LOW_STARS_MIN = 2
HOT_STRICTNESS = 0.5  # 中档 -> min_hot_conditions = 5


def load_minute_data(stock_code):
    file_path = os.path.join(DATA_DIR, f"{stock_code}_5min.csv")
    if not os.path.exists(file_path):
        return None
    return pd.read_csv(file_path)


class LayerGates:
    """按 unified_base_filter 真实链路实现的分层闸门（单只股票逐bar评估）"""

    def __init__(self, low_stars_min=2, hot_strictness=0.5):
        self.bf = UnifiedBaseFilter(low_stars_min=low_stars_min,
                                    hot_strictness=hot_strictness, n_stocks=20)
        # 预计算 min_hot_conditions（0.9->6, 0.5->5, 0.3->4）
        hs = hot_strictness
        self.min_hot = 6 if hs >= 0.8 else (5 if hs >= 0.5 else 4)

    def passed(self, layer, opens, highs, lows, closes, volumes, i):
        """layer: 0=不过滤 / 1=仅低位 / 2=低位+6热启 / 3=完整"""
        if layer == 0:
            return True
        # 1. 低位
        low_score, low_details, stars = self.bf.check_low_position(closes, highs, lows, i)
        if stars < self.bf.low_stars_min:
            return False
        if layer == 1:
            return True
        # 2. 6条热启动
        hot_score, hot_details, hot_conds, hot_vals = self.bf.check_hot_start_6(
            opens, highs, lows, closes, volumes, i)
        if hot_score < self.min_hot:
            return False
        if layer == 2:
            return True
        # 3. 完整 filter_one 剩余链：涨跌停+大盘+综合评分
        # （大盘/涨跌停在回测中难以逐bar取真实值，此处用中性环境+涨跌停+评分模拟，
        #   与 strategy_backtest 的 DEFAULT_MARKET_ENV 一致）
        limit_ok, _ = self.bf.check_limit(highs, lows, closes, i)
        if not limit_ok:
            return False
        composite = low_score + hot_score
        if composite < 2:
            return False
        return True


def backtest_layer(strategy_name, stock_code, layer, initial_balance=100000):
    df = load_minute_data(stock_code)
    if df is None:
        return None

    try:
        factory = create_strategy_factory_v11(strategy_name)
        strategy = factory()
    except Exception as e:
        return {'strategy': strategy_name, 'stock': stock_code,
                'layer': layer, 'error': str(e)[:50]}

    gates = LayerGates(LOW_STARS_MIN, HOT_STRICTNESS)

    balance = initial_balance
    position = 0
    entry_price = 0
    buy_count = 0
    sell_count = 0
    winning_trades = 0
    rejected_by_layer = 0

    closes = df['close'].values.astype(float)
    highs = df['high'].values.astype(float)
    lows = df['low'].values.astype(float)
    opens = df['open'].values.astype(float)
    volumes = df['volume'].values.astype(float) if 'volume' in df.columns else np.ones(len(closes)) * 1e6

    n = len(closes)
    for i in range(200, n):
        price = closes[i]
        try:
            if hasattr(strategy, 'update_price'):
                signal = strategy.update_price(price)
            else:
                signal = None

            if signal:
                action = signal.get('action', None)

                if action == 'buy' and position == 0:
                    if not gates.passed(layer, opens, highs, lows, closes, volumes, i):
                        rejected_by_layer += 1
                        continue
                    position = int(balance / price / 100) * 100
                    if position > 0:
                        entry_price = price
                        balance -= position * price
                        buy_count += 1

                elif action == 'sell' and position > 0:
                    balance += position * price
                    pnl_pct = (price - entry_price) / entry_price * 100
                    if pnl_pct > 0:
                        winning_trades += 1
                    sell_count += 1
                    position = 0
        except Exception:
            pass

    final_value = balance + position * closes[-1]
    total_return = (final_value - initial_balance) / initial_balance * 100
    win_rate = winning_trades / sell_count * 100 if sell_count > 0 else 0

    return {
        'strategy': strategy_name,
        'stock': stock_code,
        'layer': layer,
        'total_return': round(total_return, 2),
        'trades': buy_count,
        'win_rate': round(win_rate, 1),
        'rejected': rejected_by_layer,
    }


def main():
    test_strategies = ['high_return_grid', 'gyro_precession_strategy']
    test_stocks = ['000001', '000063', '000333', '600036', '601318']
    layer_names = {0: 'A纯策略', 1: 'B+底座', 2: 'C+6热启', 3: 'D完整'}

    print("=" * 72)
    print("P0-B V4.0 分层重验（统一底座 6 条热启动，hot_strictness=0.5 -> 需5/6条）")
    print("=" * 72)

    all_results = []
    for strat in test_strategies:
        for layer in [0, 1, 2, 3]:
            for stock in test_stocks:
                r = backtest_layer(strat, stock, layer)
                if r and 'error' not in r:
                    all_results.append(r)
                    print(f"  {strat} | {layer_names[layer]} | {stock}: "
                          f"{r['total_return']:+.2f}% ({r['trades']}次) 拒={r['rejected']}")

    print("\n" + "=" * 72)
    print("分层汇总（平均）")
    print("=" * 72)
    rows = []
    for strat in test_strategies:
        for layer in [0, 1, 2, 3]:
            rs = [r for r in all_results
                  if r['strategy'] == strat and r['layer'] == layer]
            if rs:
                avg_ret = np.mean([r['total_return'] for r in rs])
                avg_tr = np.mean([r['trades'] for r in rs])
                # 过滤比例相对 A 组
                a_rs = [r for r in all_results
                        if r['strategy'] == strat and r['layer'] == 0]
                a_tr = np.mean([r['trades'] for r in a_rs]) if a_rs else 0
                filt = (1 - avg_tr / a_tr) * 100 if a_tr > 0 else 0
                print(f"  {strat} | {layer_names[layer]:10s}: 收益{avg_ret:+.2f}% "
                      f"交易{avg_tr:.0f} 过滤{filt:.0f}%")
                rows.append({'strategy': strat, 'layer': layer,
                             'layer_name': layer_names[layer],
                             'avg_return': round(avg_ret, 2),
                             'avg_trades': round(avg_tr, 1),
                             'filter_pct': round(filt, 1)})

    df = pd.DataFrame(rows)
    out = r"D:\Gupiao\升级vscode\QS_Robot\results\p0b_v4_revalidate_layers_20261022.csv"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    df.to_csv(out, index=False, encoding='utf-8-sig')
    print(f"\n结果已保存: {out}")

    # 结论判定：C组相对B组的额外过滤/收益变化
    print("\n结论判定（6条热启动是否有独立效果）：")
    for strat in test_strategies:
        b_rs = [r for r in rows if r['strategy'] == strat and r['layer'] == 1]
        c_rs = [r for r in rows if r['strategy'] == strat and r['layer'] == 2]
        if b_rs and c_rs:
            d_filt = c_rs[0]['filter_pct'] - b_rs[0]['filter_pct']
            d_ret = c_rs[0]['avg_return'] - b_rs[0]['avg_return']
            print(f"  {strat}: C-B 额外过滤={d_filt:.1f}pp, 收益差={d_ret:+.2f}pp"
                  f" -> {'6条热启动有独立过滤效果' if d_filt > 1 else '6条热启动过滤效果弱'}")


if __name__ == '__main__':
    main()
