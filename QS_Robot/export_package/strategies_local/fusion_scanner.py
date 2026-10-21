#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
魔法策略+公转自转融合扫描器
================================
流程：
1. 用SEPA趋势模板+VCP+RS筛选全市场强势股（选股）
2. 用公转自转决策引擎判断每只股票今天是否适合交易（择时）
3. 输出最终可交易候选名单

核心思想：
- SEPA负责"选什么股"（大方向，第二阶段强势股）
- 公转自转负责"什么时候买"（精确择时，避免追高/接飞刀）
"""

import sys
import os
import argparse

# 路径设置
QS_ROBOT_ROOT = r'D:\Gupiao\升级vscode\QS_Robot'
STRATEGIES_DIR = os.path.join(QS_ROBOT_ROOT, 'export_package', 'strategies_local')

sys.path.insert(0, QS_ROBOT_ROOT)
sys.path.insert(0, STRATEGIES_DIR)

import pandas as pd
from datetime import datetime

# 导入公转自转决策引擎
from core.decision_engine import DecisionEngine


def load_sepa_results():
    """读取最新的SEPA扫描结果CSV"""
    results_dir = os.path.join(STRATEGIES_DIR, 'results')
    
    # 找最新的sepa_scan_*.csv文件
    csv_files = [f for f in os.listdir(results_dir) if f.startswith('sepa_scan_') and f.endswith('.csv')]
    if not csv_files:
        print("错误：未找到SEPA扫描结果，请先运行sepa_market_scanner.py")
        return []
    
    csv_files.sort(reverse=True)
    latest_csv = os.path.join(results_dir, csv_files[0])
    
    print(f"读取SEPA扫描结果: {csv_files[0]}")
    df = pd.read_csv(latest_csv)
    
    # 转换为字典列表
    results = df.to_dict('records')
    return results


def attach_realtime_prices(sepa_results):
    """盘中模式：用免费实时行情(腾讯主源)刷新候选股票现价/涨跌幅"""
    try:
        sys.path.insert(0, QS_ROBOT_ROOT)
        from core.data_sources.realtime_adapter import RealtimeAdapter
    except Exception as e:
        print(f"  [实时] 适配器加载失败: {e}，跳过实时刷新")
        return sepa_results

    codes = [str(s['symbol']).zfill(6) for s in sepa_results]
    print(f"  [实时] 拉取 {len(codes)} 只候选股票实时快照...")
    a = RealtimeAdapter()
    qs = {}
    for i in range(0, len(codes), 40):
        qs.update(a.get_realtime_batch(codes[i:i + 40]))
        import time
        time.sleep(0.5)

    hit = 0
    for s in sepa_results:
        code = str(s['symbol']).zfill(6)
        q = qs.get(code)
        if q and q.get('price'):
            s['price'] = q['price']
            s['realtime_change_pct'] = q.get('change_pct')
            s['realtime_time'] = q.get('time')
            hit += 1
    print(f"  [实时] 刷新成功 {hit}/{len(sepa_results)}")
    return sepa_results


def run_fusion_scan(realtime: bool = False):
    """运行融合扫描（realtime=True 时用实时行情刷新现价）"""
    
    print("=" * 70)
    print("  魔法策略 + 公转自转 融合扫描器" + ("（盘中实时模式）" if realtime else ""))
    print("=" * 70)
    print(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # ===== 第一步：读取SEPA选股结果 =====
    print("【第一步】读取SEPA趋势模板扫描结果...")
    sepa_results = load_sepa_results()
    
    if not sepa_results:
        print("错误：无SEPA候选结果")
        return []
    
    print(f"读取完成：{len(sepa_results)}只候选股票")
    print()

    # 盘中模式：先刷新实时价格
    if realtime:
        sepa_results = attach_realtime_prices(sepa_results)
    
    # ===== 第二步：公转自转择时过滤 =====
    print("【第二步】公转自转决策引擎逐只过滤...")
    eng = DecisionEngine()
    
    fusion_results = []
    
    for i, stock in enumerate(sepa_results, 1):
        code = str(stock['symbol']).zfill(6)  # 补前导0，确保6位代码
        print(f"  ({i}/{len(sepa_results)}) 检查 {code}...", end=' ')
        
        # 调用公转自转决策引擎
        decision = eng.evaluate(code)
        
        if 'error' in decision:
            print(f"跳过（{decision['error']}）")
            stock['tradable'] = False
            stock['regime'] = 'N/A'
            stock['zone'] = 'N/A'
            stock['notrade_reason'] = decision['error']
            fusion_results.append(stock)
            continue
        
        tradable = decision.get('tradable', False)
        regime = decision.get('regime', 'N/A')
        zone = decision.get('zone', 'N/A')
        
        # 获取触发的NO_TRADE原因
        notrade = decision.get('notrade', {})
        triggered = [k for k, v in notrade.items() if v.get('triggered')]
        notrade_reason = ', '.join(triggered) if triggered else '无'
        
        stock['tradable'] = tradable
        stock['regime'] = regime
        stock['zone'] = zone
        stock['notrade_reason'] = notrade_reason
        
        status = "✅可交易" if tradable else "❌不可交易"
        print(f"{status} | regime={regime} zone={zone}")
        
        fusion_results.append(stock)
    
    print()
    
    # ===== 第三步：输出融合结果 =====
    print("=" * 70)
    print("  融合扫描结果")
    print("=" * 70)
    print()
    
    # 按SEPA综合评分排序
    fusion_results.sort(key=lambda x: x.get('composite_score', 0), reverse=True)
    
    # 统计
    tradable_count = sum(1 for s in fusion_results if s['tradable'])
    print(f"SEPA候选总数: {len(fusion_results)}")
    print(f"公转自转判定可交易: {tradable_count}")
    print(f"公转自转判定不可交易: {len(fusion_results) - tradable_count}")
    print()
    
    # 打印表格
    print(f"{'排名':<4} {'代码':<8} {'现价':<8} {'RS分':<6} {'SEPA分':<8} {'VCP':<5} {'regime':<8} {'zone':<6} {'可交易':<6} {'NO_TRADE原因'}")
    print("-" * 100)
    
    for i, stock in enumerate(fusion_results, 1):
        code = stock['symbol']
        price = stock.get('price', 0)
        rs = stock.get('rs_score', 0)
        sepa_score = stock.get('composite_score', 0)
        vcp = f"{stock.get('vcp_count', 0)}次"
        regime = stock.get('regime', 'N/A')
        zone = stock.get('zone', 'N/A')
        tradable = '✅' if stock.get('tradable', False) else '❌'
        reason = stock.get('notrade_reason', '')
        
        print(f"{i:<4} {code:<8} {price:<8.2f} {rs:<6.1f} {sepa_score:<8.2f} {vcp:<5} {regime:<8} {zone:<6} {tradable:<6} {reason}")
    
    print()
    
    # 输出可交易名单
    tradable_stocks = [s for s in fusion_results if s['tradable']]
    if tradable_stocks:
        print("=" * 70)
        print("  🏆 今日真正可交易的候选股票")
        print("=" * 70)
        for s in tradable_stocks:
            print(f"  ✅ {s['symbol']} | SEPA分={s.get('composite_score',0):.2f} | RS={s.get('rs_score',0):.1f} | VCP={s.get('vcp_count',0)}次")
    else:
        print("=" * 70)
        print("  ⚠️ 今日无可交易股票")
        print("  原因：所有SEPA候选都被公转自转决策引擎过滤")
        print("=" * 70)
    
    # 保存结果
    results_dir = os.path.join(STRATEGIES_DIR, 'results')
    os.makedirs(results_dir, exist_ok=True)
    
    date_str = datetime.now().strftime('%Y%m%d')
    csv_path = os.path.join(results_dir, f'fusion_scan_{date_str}.csv')
    
    df = pd.DataFrame(fusion_results)
    df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    
    print()
    print(f"📁 结果已保存: {csv_path}")
    
    return fusion_results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="魔法策略+公转自转融合扫描器")
    parser.add_argument('--realtime', action='store_true',
                        help='盘中实时模式：用免费实时行情刷新候选股票现价')
    args = parser.parse_args()
    run_fusion_scan(realtime=args.realtime)
