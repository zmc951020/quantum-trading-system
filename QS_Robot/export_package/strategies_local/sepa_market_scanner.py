#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SEPA 全市场选股扫描器（工程级）
================================
基于米勒维尼《股票魔法师》趋势模板8条 + RS评分 + VCP形态
每日收盘后运行，从全市场股票中筛选符合SEPA标准的候选股，按综合评分排序。

用法：
    python sepa_market_scanner.py                    # 默认扫描全部，输出Top 20
    python sepa_market_scanner.py --top 30           # 输出Top 30
    python sepa_market_scanner.py --min-rs 75         # RS最低75分
    python sepa_market_scanner.py --output csv        # 输出CSV文件
    python sepa_market_scanner.py --check-market     # 先检查大盘环境

输出：
    1. 控制台彩色表格
    2. results/sepa_scan_YYYYMMDD.csv 详细结果
    3. results/sepa_scan_YYYYMMDD.log 运行日志
"""

from __future__ import annotations

import os
import sys
import time
import json
import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import numpy as np
import pandas as pd

# 导入策略类，复用完整版VCP和买点检查（消除双副本）
from minervini_sepa_strategy import MinerviniSepaStrategy

# ============================================================
# 配置区（所有路径和参数集中管理）
# ============================================================

# 数据路径
DATA_DIR = Path(r"D:\Gupiao\升级vscode\QS_Robot\export_package\data\daily_data_ext")
OUTPUT_DIR = Path(r"D:\Gupiao\升级vscode\QS_Robot\export_package\strategies_local\results")

# 基准指数（沪深300，用于RS评分）
BENCHMARK_FILE = "000300_daily.csv"  # 如果没有就用akshare联网拉

# 趋势模板参数（对应书p.66）
TREND_PARAMS = {
    'ma_short': 20,
    'ma_mid': 50,
    'ma_long1': 150,
    'ma_long2': 200,
    'ma200_up_bars': 22,          # MA200向上至少1个月
    'pct_from_52w_low': 0.30,      # 距52周低点≥30%
    'pct_to_52w_high': 0.25,       # 距52周高点≤25%
    'rs_min_score': 70,            # RS评分最低70
}

# VCP参数（对应书p.157-163）
VCP_PARAMS = {
    'min_weeks': 5,                # 整理期≥5周≈25交易日
    'min_contractions': 2,          # 最少收缩次数
    'zigzag_pct': 0.05,             # zigzag转折阈值5%
    'vol_shrink_ratio': 0.7,        # 后一段均量/前一段<0.7
}

# 综合评分权重
SCORE_WEIGHTS = {
    'rs_score': 0.40,               # RS评分权重40%
    'near_pivot': 0.25,             # 距枢轴点距离权重25%
    'vcp_quality': 0.20,            # VCP质量权重20%
    'near_high': 0.15,              # 距52周高点权重15%
}

# ============================================================
# 日志配置
# ============================================================

def setup_logging(output_dir: Path) -> logging.Logger:
    """配置日志：同时输出到控制台和文件"""
    output_dir.mkdir(parents=True, exist_ok=True)
    log_file = output_dir / f"sepa_scan_{datetime.now().strftime('%Y%m%d')}.log"

    logger = logging.getLogger('SEPA_Scanner')
    logger.setLevel(logging.INFO)

    # 避免重复添加handler
    if logger.handlers:
        return logger

    # 文件handler
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))

    # 控制台handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter('%(message)s'))

    logger.addHandler(fh)
    logger.addHandler(ch)

    return logger


# ============================================================
# 数据加载模块
# ============================================================

def load_stock_data(csv_path: Path) -> Optional[pd.DataFrame]:
    """加载单只股票日线数据"""
    try:
        df = pd.read_csv(csv_path)
        if len(df) < 250:  # 至少需要250根K线（1年）
            return None

        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)
        return df
    except Exception as e:
        return None


def load_benchmark(logger: logging.Logger) -> Optional[pd.DataFrame]:
    """加载基准指数（沪深300）"""
    bench_path = DATA_DIR / BENCHMARK_FILE
    if bench_path.exists():
        logger.info(f"加载基准指数: {bench_path.name}")
        return load_stock_data(bench_path)

    # 没有本地文件就返回None，RS评分退化为个股动量
    logger.warning("⚠️ 未找到基准指数文件，RS评分将退化为个股动量模式")
    return None


# ============================================================
# 指标计算模块（向量化，高性能）
# ============================================================

def sma(data: np.ndarray, period: int) -> np.ndarray:
    """简单移动平均（向量化）"""
    result = np.full_like(data, np.nan)
    if len(data) < period:
        return result
    result[period-1:] = np.convolve(data, np.ones(period)/period, mode='valid')
    return result


def calc_trend_template(df: pd.DataFrame, params: dict) -> Tuple[bool, dict]:
    """
    趋势模板8条硬过滤（p.66）

    Returns:
        (是否全部通过, 详情字典)
    """
    close = df['close'].values
    high = df['high'].values
    low = df['low'].values
    n = len(close)

    need = params['ma_long2'] + 30
    if n < need:
        return False, {'error': f'数据不足{need}根，当前{n}根'}

    # 计算均线
    ma50 = sma(close, params['ma_mid'])
    ma150 = sma(close, params['ma_long1'])
    ma200 = sma(close, params['ma_long2'])

    current_price = close[-1]

    # 52周高低点
    lookback = min(250, n)
    high_52w = high[-lookback:].max()
    low_52w = low[-lookback:].min()

    # 8条检查
    checks = {}

    # 第1条：股价 > MA150 且 > MA200
    c1 = current_price > ma150[-1] and current_price > ma200[-1]
    checks['1_above_ma150_ma200'] = c1

    # 第2条：MA150 > MA200
    c2 = ma150[-1] > ma200[-1]
    checks['2_ma150_above_ma200'] = c2

    # 第3条：MA200已向上≥1个月
    up_bars = params['ma200_up_bars']
    c3 = ma200[-1] > ma200[-1 - up_bars]
    checks['3_ma200_rising_1m'] = c3

    # 第4条：MA50 > MA150 > MA200
    c4 = ma50[-1] > ma150[-1] > ma200[-1]
    checks['4_ma50_above_ma150_above_ma200'] = c4

    # 第5条：股价 > MA50
    c5 = current_price > ma50[-1]
    checks['5_above_ma50'] = c5

    # 第6条：较52周低点 ≥ 30%
    pct_from_low = (current_price - low_52w) / low_52w
    c6 = pct_from_low >= params['pct_from_52w_low']
    checks['6_above_52w_low_30pct'] = c6

    # 第7条：距52周高点 ≤ 25%
    pct_to_high = (high_52w - current_price) / high_52w
    c7 = pct_to_high <= params['pct_to_52w_high']
    checks['7_within_25pct_of_52w_high'] = c7

    all_pass = all(checks.values())

    details = {
        'price': current_price,
        'ma50': ma50[-1],
        'ma150': ma150[-1],
        'ma200': ma200[-1],
        'high_52w': high_52w,
        'low_52w': low_52w,
        'pct_from_low': pct_from_low,
        'pct_to_high': pct_to_high,
        'checks': checks,
    }

    return all_pass, details


def calc_rs_score(df: pd.DataFrame, benchmark_df: Optional[pd.DataFrame]) -> float:
    """
    RS相对强度评分（p.66 第8条）

    代理实现：
        60% × 近6个月超额收益 + 40% × 前6个月超额收益
        映射到0-99分
    """
    if len(df) < 200:
        return 50.0

    if benchmark_df is None:
        # 无基准时用个股自身动量
        close = df['close'].values
        n = len(close)
        ret_6m = (close[-1] - close[max(0, n-120)]) / close[max(0, n-120)]
        return max(0, min(99, 50 + ret_6m * 150))

    # 按日期对齐
    merged = pd.merge(
        df[['date', 'close']].rename(columns={'close': 'stock'}),
        benchmark_df[['date', 'close']].rename(columns={'close': 'bench'}),
        on='date', how='inner'
    )
    if len(merged) < 200:
        return 50.0

    stock = merged['stock'].values
    bench = merged['bench'].values
    n = len(stock)

    # 近6个月超额收益
    recent_start = max(0, n - 120)
    stock_recent = (stock[-1] - stock[recent_start]) / stock[recent_start]
    bench_recent = (bench[-1] - bench[recent_start]) / bench[recent_start]
    excess_recent = stock_recent - bench_recent

    # 前6个月超额收益
    prior_end = n - 120
    prior_start = max(0, n - 240)
    if prior_end > prior_start and stock[prior_start] > 0:
        stock_prior = (stock[prior_end] - stock[prior_start]) / stock[prior_start]
        bench_prior = (bench[prior_end] - bench[prior_start]) / bench[prior_start]
        excess_prior = stock_prior - bench_prior
    else:
        excess_prior = excess_recent

    # 加权 + 映射
    weighted_excess = 0.6 * excess_recent + 0.4 * excess_prior
    rs_score = 50.0 + weighted_excess * 150.0
    return max(0.0, min(99.0, rs_score))


def detect_vcp_full(df: pd.DataFrame) -> Tuple[bool, float, int, float]:
    """
    VCP波动收缩检测（完整版，复用策略类 MinerviniSepaStrategy.detect_vcp）

    消除双副本：扫描器与策略使用同一套 zigzag + 幅度递减 + 量萎缩算法。

    Returns:
        (是否命中VCP, 枢轴点价格, 收缩次数, 最后收缩幅度)
    """
    price = float(df['close'].iloc[-1])
    strategy = MinerviniSepaStrategy(base_price=price)
    return strategy.detect_vcp(df)


def check_breakout(df: pd.DataFrame, pivot_price: float) -> Tuple[bool, str]:
    """
    枢轴点突破买点检查（复用策略类 MinerviniSepaStrategy.check_pivot_breakout）

    检查项：
    1. 收盘价在枢轴点上方（允许0-2%浮动）
    2. 不追高（枢轴点上方>5%不买）
    3. 放量突破（量比≥2.5x）
    4. 涨停不追（A股T+1适配）

    Returns:
        (是否触发买点, 原因说明)
    """
    price = float(df['close'].iloc[-1])
    strategy = MinerviniSepaStrategy(base_price=price)
    return strategy.check_pivot_breakout(df, pivot_price)


def calc_composite_score(
    rs_score: float,
    price: float,
    pivot_price: float,
    high_52w: float,
    vcp_contractions: int,
    weights: dict
) -> float:
    """
    综合评分计算

    评分构成：
        RS评分（0-99）→ 归一化到0-100
        距枢轴点距离（越近越好）
        VCP收缩次数（越多越好）
        距52周高点距离（越近越好）
    """
    # 1. RS分（权重40%）
    score_rs = rs_score

    # 2. 距枢轴点距离分（权重25%）
    # 理想状态：价格在枢轴点附近（0-3%以内）
    if pivot_price > 0:
        dist_to_pivot = (price - pivot_price) / pivot_price
        # 在枢轴点下方：越近越好；上方：追高分递减
        if dist_to_pivot <= 0:
            # 在下方，距离越近分越高（0%距离=100分，-10%距离=50分）
            score_pivot = 100 + dist_to_pivot * 500  # dist是负数，所以+会变小
        else:
            # 在上方，超过5%直接低分
            score_pivot = 100 - dist_to_pivot * 1000
        score_pivot = max(0, min(100, score_pivot))
    else:
        score_pivot = 50

    # 3. VCP质量分（权重20%）
    # 2次收缩=60分，3次=80分，4次+=100分
    if vcp_contractions >= 4:
        score_vcp = 100
    elif vcp_contractions == 3:
        score_vcp = 80
    elif vcp_contractions == 2:
        score_vcp = 60
    else:
        score_vcp = 30

    # 4. 距52周高点分（权重15%）
    if high_52w > 0:
        pct_to_high = (high_52w - price) / high_52w
        # 距高点0%=100分，距25%=0分
        score_high = 100 - pct_to_high * 400
        score_high = max(0, min(100, score_high))
    else:
        score_high = 50

    # 加权综合
    total = (
        weights['rs_score'] * score_rs +
        weights['near_pivot'] * score_pivot +
        weights['vcp_quality'] * score_vcp +
        weights['near_high'] * score_high
    )

    return round(total, 2)


# ============================================================
# 大盘环境检查
# ============================================================

def check_market_environment(benchmark_df: Optional[pd.DataFrame], logger: logging.Logger) -> bool:
    """
    大盘环境检查（p.248：恶劣市场收紧或不开新仓）

    规则：指数在MA50之上才允许选股
    """
    if benchmark_df is None:
        logger.warning("⚠️ 无基准数据，跳过大盘环境检查")
        return True

    close = benchmark_df['close'].values
    if len(close) < 50:
        return True

    ma50 = sma(close, 50)
    current = close[-1]
    above_ma50 = current > ma50[-1]

    if above_ma50:
        logger.info(f"✅ 大盘环境良好：沪深300={current:.0f} > MA50={ma50[-1]:.0f}")
    else:
        logger.warning(f"⚠️ 大盘环境偏弱：沪深300={current:.0f} < MA50={ma50[-1]:.0f}")

    return above_ma50


# ============================================================
# 主扫描流程
# ============================================================

def scan_market(
    top_n: int = 20,
    min_rs: float = 70.0,
    check_market: bool = True,
    output_csv: bool = True,
    logger: logging.Logger = None
) -> List[dict]:
    """
    全市场SEPA选股扫描主流程

    Returns:
        排序后的候选股票列表
    """
    start_time = time.time()

    logger.info("=" * 70)
    logger.info("🚀 SEPA 全市场选股扫描启动")
    logger.info("=" * 70)
    logger.info(f"扫描日期: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    logger.info(f"数据目录: {DATA_DIR}")
    logger.info(f"输出Top: {top_n}")
    logger.info(f"RS最低分: {min_rs}")

    # 1. 加载基准
    bench_df = load_benchmark(logger)

    # 2. 大盘环境检查
    if check_market:
        market_ok = check_market_environment(bench_df, logger)
        if not market_ok:
            logger.warning("⚠️ 大盘环境偏弱，仍继续扫描但请注意风险")

    # 3. 遍历所有股票
    csv_files = list(DATA_DIR.glob("*_daily.csv"))
    # 排除基准指数本身
    csv_files = [f for f in csv_files if f.name != BENCHMARK_FILE]

    total_stocks = len(csv_files)
    logger.info(f"\n📊 开始扫描 {total_stocks} 只股票...")

    candidates = []
    passed_trend = 0
    passed_rs = 0
    errors = 0

    for i, csv_path in enumerate(csv_files, 1):
        symbol = csv_path.stem.replace('_daily', '')

        # 进度显示
        if i % 50 == 0 or i == total_stocks:
            logger.info(f"  进度: {i}/{total_stocks} ({i/total_stocks*100:.0f}%) "
                        f"| 趋势模板通过: {passed_trend} | RS通过: {passed_rs}")

        # 加载数据
        df = load_stock_data(csv_path)
        if df is None:
            errors += 1
            continue

        # 第1层：趋势模板8条
        trend_pass, trend_details = calc_trend_template(df, TREND_PARAMS)
        if not trend_pass:
            continue
        passed_trend += 1

        # 第2层：RS评分
        rs_score = calc_rs_score(df, bench_df)
        if rs_score < min_rs:
            continue
        passed_rs += 1

        # 第3层：VCP检测（完整版，复用策略类）
        is_vcp, pivot_price, vcp_count, last_pct = detect_vcp_full(df)

        # 第4层：买点检查（枢轴点突破确认）
        is_breakout, breakout_reason = check_breakout(df, pivot_price)

        # 计算综合评分
        composite = calc_composite_score(
            rs_score=rs_score,
            price=trend_details['price'],
            pivot_price=pivot_price,
            high_52w=trend_details['high_52w'],
            vcp_contractions=vcp_count,
            weights=SCORE_WEIGHTS
        )

        # 收集结果
        candidates.append({
            'symbol': symbol,
            'date': df['date'].iloc[-1].strftime('%Y-%m-%d'),
            'price': round(trend_details['price'], 2),
            'rs_score': round(rs_score, 1),
            'composite_score': composite,
            'pivot_price': round(pivot_price, 2),
            'vcp_count': vcp_count,
            'is_vcp': is_vcp,
            'is_breakout': is_breakout,
            'breakout_reason': breakout_reason,
            'pct_from_low': round(trend_details['pct_from_low'] * 100, 1),
            'pct_to_high': round(trend_details['pct_to_high'] * 100, 1),
            'ma50': round(trend_details['ma50'], 2),
            'ma150': round(trend_details['ma150'], 2),
            'ma200': round(trend_details['ma200'], 2),
        })

    # 4. 按综合评分排序
    candidates.sort(key=lambda x: x['composite_score'], reverse=True)

    # 5. 输出结果
    elapsed = time.time() - start_time
    logger.info("\n" + "=" * 70)
    logger.info(f"✅ 扫描完成！耗时 {elapsed:.1f} 秒")
    logger.info("=" * 70)
    logger.info(f"总扫描股票数: {total_stocks}")
    logger.info(f"数据错误: {errors}")
    logger.info(f"通过趋势模板: {passed_trend} ({passed_trend/total_stocks*100:.1f}%)")
    logger.info(f"通过RS筛选: {passed_rs} ({passed_rs/total_stocks*100:.1f}%)")
    logger.info(f"最终候选: {len(candidates)} 只")

    # 打印Top N
    top_list = candidates[:top_n]
    logger.info(f"\n{'='*70}")
    logger.info(f"🏆 Top {len(top_list)} SEPA候选股票")
    logger.info(f"{'='*70}")
    logger.info(f"{'排名':<4} {'代码':<8} {'现价':>8} {'RS分':>6} {'综合分':>7} "
                f"{'枢轴点':>8} {'VCP':>4} {'买点':>4} {'距高点':>7}")
    logger.info("-" * 78)

    for i, c in enumerate(top_list, 1):
        breakout_mark = '✅' if c.get('is_breakout', False) else '❌'
        logger.info(
            f"{i:<4} {c['symbol']:<8} {c['price']:>8.2f} {c['rs_score']:>6.1f} "
            f"{c['composite_score']:>7.2f} {c['pivot_price']:>8.2f} "
            f"{c['vcp_count']:>3}次 {breakout_mark:>4} {c['pct_to_high']:>6.1f}%"
        )

    # 6. 保存CSV
    if output_csv and candidates:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        csv_file = OUTPUT_DIR / f"sepa_scan_{datetime.now().strftime('%Y%m%d')}.csv"
        df_out = pd.DataFrame(candidates)
        df_out.to_csv(csv_file, index=False, encoding='utf-8-sig')
        logger.info(f"\n📁 详细结果已保存: {csv_file}")

    return candidates


# ============================================================
# 命令行入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='SEPA全市场选股扫描器')
    parser.add_argument('--top', type=int, default=20, help='输出Top N（默认20）')
    parser.add_argument('--min-rs', type=float, default=70.0, help='RS最低分（默认70）')
    parser.add_argument('--no-market-check', action='store_true', help='跳过大盘环境检查')
    parser.add_argument('--no-csv', action='store_true', help='不输出CSV文件')
    args = parser.parse_args()

    # 配置日志
    logger = setup_logging(OUTPUT_DIR)

    # 执行扫描
    scan_market(
        top_n=args.top,
        min_rs=args.min_rs,
        check_market=not args.no_market_check,
        output_csv=not args.no_csv,
        logger=logger
    )


if __name__ == '__main__':
    main()
