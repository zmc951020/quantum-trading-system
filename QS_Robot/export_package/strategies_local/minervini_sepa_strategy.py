#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
米勒维尼 SEPA 趋势突破策略（内部代号：魔法策略）
====================================================
基于 Mark Minervini《股票魔法师》(SEPA = Specific Entry Point Analysis)
实现：趋势模板8条 + RS相对强度 + VCP波动收缩 + 枢轴点突破 + 3R保本止损

书籍页码引用（中文版电子工业出版社2015年译本）：
- 趋势模板8条: p.66
- 四阶段理论: p.52-64
- VCP波动收缩: p.157-163
- 枢轴点突破: p.174, p.178, p.183
- 深蹲与逆转恢复: p.183-185
- 风险数学/止损: p.222-224
- 3R保本规则: p.246
- 分批建仓/金字塔: p.246
- 持仓数量4-6只: p.249
- 恶劣市场收紧: p.248
- 卖出规则全集: 散见全书汇总

A股适配：
- T+1：当日买入次日才可卖，止损信号记录到次日执行
- 涨跌停：涨停板不追、跌停板不挂卖单（假设无法成交）
- 最小交易单位：100股整数倍
"""

from __future__ import annotations

import logging
from typing import Dict, Optional, Any, List, Tuple

import numpy as np
import pandas as pd

# 兼容包内导入和独立测试
try:
    from .strategy_base import StrategyBase
except ImportError:
    from strategy_base import StrategyBase

logger = logging.getLogger(__name__)


class MinerviniSepaStrategy(StrategyBase):
    """
    米勒维尼 SEPA 趋势突破策略

    选股漏斗（对应书里四层过滤 p.29）：
        全市场 → 趋势模板8条(p.66) → RS评分≥70 → VCP波动收缩 → 枢轴点放量突破

    核心哲学（p.156）：
        "我不想成为第一个跳上船的人；我要找的是势头已经起来、
         失败风险已经较低的股票。"
    """

    strategy_type = "minervini_sepa"

    # ========== 所有可调参数集中于此（无硬编码密钥）==========
    DEFAULT_PARAMS = {
        # --- 趋势模板8条 (p.66) ---
        'ma_short': 20,               # MA20：保本后动态跟踪止损线
        'ma_mid': 50,                 # MA50
        'ma_long1': 150,              # MA150
        'ma_long2': 200,              # MA200
        'ma200_up_bars': 22,          # MA200向上至少1个月≈22交易日
        'pct_from_52w_low': 0.30,     # 第6条：距52周低点≥30%
        'pct_to_52w_high': 0.25,      # 第7条：距52周高点≤25%
        'rs_min_score': 70,            # 第8条：RS评分≥70（IBD标准）

        # --- VCP波动收缩 (p.157-163) ---
        'vcp_min_weeks': 5,            # 整理期≥5周（p.66-67第二阶段回调5~26周）
        'vcp_min_contractions': 2,     # 最少收缩次数（p.159通常2~4次）
        'vcp_max_contractions': 6,     # 最多收缩次数（p.159有时达6次）
        'vcp_zigzag_pct': 0.05,        # zigzag转折阈值5%
        'vcp_vol_shrink_ratio': 0.7,   # 后一段均量/前一段均量<0.7
        'vcp_last_vol_ratio': 0.9,     # 最后收缩段量<50日均量×0.9（p.181）

        # --- 枢轴点突破 (p.174, p.183) ---
        'pivot_drift_tol': 0.02,       # 枢轴点上方允许0-2%浮动
        'pivot_chase_limit': 0.05,    # 枢轴点上方>5%绝不追高
        'breakout_vol_mult': 2.5,      # 突破日量≥50日均量×2.5（书里300-400%）

        # --- 风险引擎 (p.222-248) ---
        'risk_per_trade': 0.005,        # 单笔总风险=总资金×0.5%（p.246）
        'stop_loss_pct': 0.075,        # 初始止损7.5%（p.240：成功投资均收益15%的一半）
        'bear_stop_loss_pct': 0.055,    # 恶劣市场止损5.5%（p.248收紧到5-6%）
        'max_loss_pct': 0.10,          # 最大亏损线10%硬性上限（p.222）

        # --- 3R保本规则 (p.246) ---
        'breakeven_r_mult': 3.0,        # 浮盈≥3R移止损至成本价
        'trailing_ma_period': 20,       # 保本后用MA20动态跟踪（p.186成功突围守MA20）

        # --- 分批建仓 (p.246) ---
        'first_trade_ratio': 0.5,       # 首次建仓1/2计划仓位
        'add_confirm_days': 3,          # 收盘站稳枢轴点上方3天后加仓

        # --- 大盘环境过滤 (p.248) ---
        'benchmark_symbol': '000300',   # 沪深300指数
        'market_filter_on': True,        # 指数<MA200时不开新仓

        # --- A股交易规则适配 ---
        'lot_size': 100,                # 最小交易单位100股
        'limit_pct': 0.099,             # 涨跌停幅度近似10%（主板）
        't1_settlement': True,          # T+1结算：当日买入次日才可卖

        # --- 持仓管理 (p.249) ---
        'max_positions': 6,             # 最多同时持仓6只（p.249通常4-6只）
        'max_exposure': 0.8,            # 总敞口上限80%
    }

    def __init__(self, base_price: float, initial_balance: float = 100000, **params):
        """
        初始化策略

        Args:
            base_price: 基准价格（当前股价）
            initial_balance: 初始资金
            **params: 覆盖DEFAULT_PARAMS中的任意参数
        """
        super().__init__(base_price, initial_balance)

        # 合并参数：默认值 → 构造参数覆盖
        self.params = {**self.DEFAULT_PARAMS, **params}

        # 数据容器（坑1：必须自己load_data拉OHLCV，不能依赖update_price的close Series）
        self.df: Optional[pd.DataFrame] = None
        self.benchmark_df: Optional[pd.DataFrame] = None
        self.symbol: str = params.get('symbol', 'UNKNOWN')

        # 持仓状态机
        self.entry_price: float = 0.0        # 首次建仓价
        self.add_price: float = 0.0          # 加仓价
        self.stop_loss: float = 0.0          # 当前止损价
        self.position_size: int = 0          # 持仓股数
        self.target_position: int = 0        # 计划总仓位（股数）
        self.buy_date: Optional[pd.Timestamp] = None  # 买入日期（T+1判断）
        self.is_first_trade: bool = True     # 是否仍为首仓阶段
        self.days_above_pivot: int = 0       # 收盘站稳枢轴点上方天数
        self.pivot_price: float = 0.0        # 本次交易的枢轴点价格
        self.breakeven_triggered: bool = False  # 是否已触发3R保本

        # 市场环境标记
        self.bear_market: bool = False

        # 交易信号日志（回测复盘用）
        self.signal_log: List[Dict[str, Any]] = []

        # RS评分缓存（由relative_rating()写入，passes_trend_template读取）
        self._current_rs: float = 50.0

    # ============================================================
    # 数据加载（坑1解决方案：主动拉OHLCV历史）
    # ============================================================
    def load_data(self, symbol: str, days: int = 600) -> bool:
        """
        主动拉取日线OHLCV历史数据

        优先从本地CSV读取，本地没有再用data_bus联网拉取。
        出错时抛出异常（fail-close），不静默失效。

        Args:
            symbol: 股票代码
            days: 自然日历史长度（实际返回交易日约days×0.7）

        Returns:
            是否加载成功
        """
        self.symbol = symbol

        # 第一步：先尝试从本地CSV读取
        local_df = self._load_local_csv(symbol, days)
        if local_df is not None and len(local_df) > 0:
            self.df = local_df
            logger.info(f"[{self.strategy_name}] 从本地CSV加载 {symbol} 数据 {len(self.df)} 根K线")
        else:
            # 第二步：本地没有，用data_bus联网拉取
            try:
                from core.data_bus import get_data_bus
                bus = get_data_bus()
                kline = bus.get_kline(symbol, period="daily", days=days)
                self.df = self._kline_to_df(kline)
                if self.df is None or len(self.df) == 0:
                    raise ValueError(f"data_bus返回空数据: {symbol}")
                logger.info(f"[{self.strategy_name}] 从data_bus加载 {symbol} 数据 {len(self.df)} 根K线")
            except Exception as e:
                logger.error(f"[{self.strategy_name}] 加载 {symbol} 数据失败: {e}")
                self.df = None
                self.benchmark_df = None
                raise  # fail-close: 抛出异常，不静默失效

        # 加载基准指数（沪深300）
        benchmark = self.params.get('benchmark_symbol', '000300')
        local_bench_df = self._load_local_csv(benchmark, days)
        if local_bench_df is not None and len(local_bench_df) > 0:
            self.benchmark_df = local_bench_df
            logger.info(f"[{self.strategy_name}] 从本地CSV加载基准 {benchmark} 数据 {len(self.benchmark_df)} 根")
        else:
            try:
                from core.data_bus import get_data_bus
                bus = get_data_bus()
                kline_bench = bus.get_kline(benchmark, period="daily", days=days)
                self.benchmark_df = self._kline_to_df(kline_bench)
                if self.benchmark_df is None or len(self.benchmark_df) == 0:
                    raise ValueError(f"data_bus返回基准空数据: {benchmark}")
                logger.info(f"[{self.strategy_name}] 从data_bus加载基准 {benchmark} 数据 {len(self.benchmark_df)} 根")
            except Exception as e:
                logger.error(f"[{self.strategy_name}] 加载基准 {benchmark} 数据失败: {e}")
                self.benchmark_df = None
                raise  # fail-close

        return True

    def _load_local_csv(self, symbol: str, days: int = 600) -> Optional[pd.DataFrame]:
        """
        从本地CSV加载日线数据

        Args:
            symbol: 股票代码
            days: 需要的天数

        Returns:
            DataFrame或None
        """
        import os
        data_dir = r'D:\Gupiao\升级vscode\QS_Robot\export_package\data\daily_data_ext'
        csv_path = os.path.join(data_dir, f'{symbol}_daily.csv')

        if not os.path.exists(csv_path):
            return None

        try:
            df = pd.read_csv(csv_path)
            # 标准化列名
            col_map = {
                'date': 'date', 'Date': 'date',
                'open': 'open', 'Open': 'open',
                'high': 'high', 'High': 'high',
                'low': 'low', 'Low': 'low',
                'close': 'close', 'Close': 'close',
                'volume': 'volume', 'Volume': 'volume',
            }
            df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date').reset_index(drop=True)

            # 只取最近days天的数据
            if len(df) > days:
                df = df.tail(days).reset_index(drop=True)

            return df
        except Exception as e:
            logger.warning(f"[{self.strategy_name}] 读取本地CSV失败 {csv_path}: {e}")
            return None

    def set_dataframe(self, df: pd.DataFrame, benchmark_df: Optional[pd.DataFrame] = None):
        """
        直接注入DataFrame（回测框架/单元测试用，绕过data_bus）

        Args:
            df: 个股OHLCV DataFrame，需含 columns: date/open/high/low/close/volume
            benchmark_df: 基准指数DataFrame（同结构）
        """
        self.df = df.copy()
        if benchmark_df is not None:
            self.benchmark_df = benchmark_df.copy()

    @staticmethod
    def _kline_to_df(kline: dict) -> Optional[pd.DataFrame]:
        """将data_bus返回的dict转为标准DataFrame"""
        if not kline or 'closes' not in kline:
            return None
        df = pd.DataFrame({
            'date': kline.get('dates', []),
            'open': kline.get('opens', []),
            'high': kline.get('highs', []),
            'low': kline.get('lows', []),
            'close': kline.get('closes', []),
            'volume': kline.get('volumes', []),
        })
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)
        return df

    # ============================================================
    # 模块1：趋势模板8条过滤函数 passes_trend_template(df)
    # ============================================================
    def passes_trend_template(self, df: pd.DataFrame) -> Tuple[bool, Dict[str, Tuple[bool, str]]]:
        """
        趋势模板8条硬性过滤（p.66，核心中的核心）

        8条必须全部满足，对应书里原文：
        1. 股价处在150日均线和200日均线上方
        2. 150日均线处在200日均线上方（MA150 > MA200）
        3. 200日均线至少已上涨1个月（p.66：大多数已涨4-5个月更好）
        4. 50日均线高于150日均线，且高于200日均线（MA50>MA150>MA200）
        5. 当前股价高于50日均线
        6. 股价比最近一年(52周)最低价至少高30%
        7. 股价处在最近一年最高价的25%以内（距高点≤25%）
        8. 相对强度RS评分不低于70

        统计佐证（p.66）：明星股飙升前，99%股价高于MA200，96%高于MA50。

        Returns:
            (是否全部通过, {每条: (布尔通过, 原因说明)})
        """
        result: Dict[str, Tuple[bool, str]] = {}
        n = len(df)
        need = self.params['ma_long2'] + 5  # MA200需要200根+余量

        if n < need:
            return False, {'error': (False, f'数据不足{need}根K线，当前{n}根')}

        close = df['close'].values
        ma50 = self._sma(close, self.params['ma_mid'])
        ma150 = self._sma(close, self.params['ma_long1'])
        ma200 = self._sma(close, self.params['ma_long2'])

        current_price = close[-1]

        # 52周高低点（约250个交易日）
        lookback = min(250, n)
        high_52w = df['high'].tail(lookback).max()
        low_52w = df['low'].tail(lookback).min()

        # 第1条：股价 > MA150 且 > MA200
        c1 = current_price > ma150[-1] and current_price > ma200[-1]
        result['1_above_ma150_ma200'] = (
            c1, f'price={current_price:.2f}, MA150={ma150[-1]:.2f}, MA200={ma200[-1]:.2f}'
        )

        # 第2条：MA150 > MA200
        c2 = ma150[-1] > ma200[-1]
        result['2_ma150_above_ma200'] = (
            c2, f'MA150={ma150[-1]:.2f} > MA200={ma200[-1]:.2f}'
        )

        # 第3条：MA200已向上≥1个月（比较当前MA200与22个交易日前）
        up_bars = self.params['ma200_up_bars']
        c3 = ma200[-1] > ma200[-1 - up_bars]
        result['3_ma200_rising_1m'] = (
            c3, f'MA200 now={ma200[-1]:.2f}, {up_bars}bars前={ma200[-1-up_bars]:.2f}'
        )

        # 第4条：MA50 > MA150 > MA200（多头排列）
        c4 = ma50[-1] > ma150[-1] > ma200[-1]
        result['4_ma50_above_ma150_above_ma200'] = (
            c4, f'MA50={ma50[-1]:.2f}, MA150={ma150[-1]:.2f}, MA200={ma200[-1]:.2f}'
        )

        # 第5条：股价 > MA50
        c5 = current_price > ma50[-1]
        result['5_above_ma50'] = (
            c5, f'price={current_price:.2f} > MA50={ma50[-1]:.2f}'
        )

        # 第6条：较52周低点 ≥ 30%
        pct_from_low = (current_price - low_52w) / low_52w
        c6 = pct_from_low >= self.params['pct_from_52w_low']
        result['6_above_52w_low_30pct'] = (c6, f'距低点涨幅={pct_from_low:.1%}')

        # 第7条：距52周高点 ≤ 25%
        pct_to_high = (high_52w - current_price) / high_52w
        c7 = pct_to_high <= self.params['pct_to_52w_high']
        result['7_within_25pct_of_52w_high'] = (c7, f'距高点回撤={pct_to_high:.1%}')

        # 第8条：RS评分 ≥ 70（由relative_rating()预先计算写入self._current_rs）
        c8 = self._current_rs >= self.params['rs_min_score']
        result['8_rs_score_70'] = (c8, f'RS={self._current_rs:.0f} (阈值{self.params["rs_min_score"]})')

        all_pass = all(v[0] for v in result.values())
        return all_pass, result

    # ============================================================
    # 模块2：RS相对强度评分（IBD RS Rating的工程代理实现）
    # ============================================================
    def relative_rating(self, df: pd.DataFrame, benchmark_df: Optional[pd.DataFrame]) -> float:
        """
        RS相对强度评分（p.66 趋势模板第8条）

        IBD原版RS Rating：个股过去12个月涨幅在全市场所有股票中的百分位排名
        （0-99，99表示过去一年表现最好）。IBD数据在A股不可得，
        这里用可工程化的代理实现：

        代理方法：
            60%权重 × 最近6个月(约120交易日)超额收益
          + 40%权重 × 前6个月(120~240交易日前)超额收益
          → 加权超额收益映射到0-99分

        超额收益 = 个股区间涨幅 - 同期基准(沪深300)涨幅

        映射校准（经验值）：
            超额0% → 50分（与基准持平）
            超额+10% → 约65分（显著跑赢）
            超额+30% → 99分（极端强势）
            超额-20% → 0分（极端弱势）

        注意：这是"超额收益强度分"，不是全市场截面排名。
        完整的IBD RS需要每日全市场股票涨幅排名，单票策略内无法独立计算。
        若框架有全市场选股器，可将此分数替换为真实截面百分位。

        Args:
            df: 个股OHLCV DataFrame
            benchmark_df: 基准指数DataFrame

        Returns:
            RS评分 0-99
        """
        if df is None or len(df) < 200:
            self._current_rs = 50.0
            return 50.0

        if benchmark_df is None or len(benchmark_df) < 200:
            # 无基准数据时，退化为个股自身动量评分
            close = df['close'].values
            n = len(close)
            ret_6m = (close[-1] - close[max(0, n-120)]) / close[max(0, n-120)]
            # 年化动量映射
            self._current_rs = max(0, min(99, 50 + ret_6m * 150))
            return self._current_rs

        # 按日期对齐个股与基准
        merged = pd.merge(
            df[['date', 'close']].rename(columns={'close': 'stock'}),
            benchmark_df[['date', 'close']].rename(columns={'close': 'bench'}),
            on='date', how='inner'
        )
        if len(merged) < 200:
            self._current_rs = 50.0
            return 50.0

        stock = merged['stock'].values
        bench = merged['bench'].values
        n = len(stock)

        # 最近6个月（约120交易日）超额收益
        recent_end = n - 1
        recent_start = max(0, n - 120)
        stock_recent = (stock[recent_end] - stock[recent_start]) / stock[recent_start]
        bench_recent = (bench[recent_end] - bench[recent_start]) / bench[recent_start]
        excess_recent = stock_recent - bench_recent

        # 前6个月（120~240交易日前）超额收益
        prior_end = n - 120
        prior_start = max(0, n - 240)
        if prior_end > prior_start and stock[prior_start] > 0:
            stock_prior = (stock[prior_end] - stock[prior_start]) / stock[prior_start]
            bench_prior = (bench[prior_end] - bench[prior_start]) / bench[prior_start]
            excess_prior = stock_prior - bench_prior
        else:
            excess_prior = excess_recent

        # 加权：近期权重60%，远期40%（近期更重要）
        weighted_excess = 0.6 * excess_recent + 0.4 * excess_prior

        # 映射到0-99分位
        rs_score = 50.0 + weighted_excess * 150.0
        rs_score = max(0.0, min(99.0, rs_score))

        self._current_rs = rs_score
        return rs_score

    # ============================================================
    # 模块3：VCP波动收缩检测器 detect_vcp(df)
    # ============================================================
    def detect_vcp(self, df: pd.DataFrame) -> Tuple[bool, float, int, float]:
        """
        VCP波动收缩检测（p.157-163）

        Minervini称之为"投资圣经里最重要的词"。
        定义：在稳固期(base/整理期)，价格波动从左到右不断收窄，
        同时成交量同步萎缩。这反映了供给被清除（卖压枯竭）。

        书里典型数字链（p.159）：
            从高点下跌25% → 反弹 → 再跌15% → 再跌8%
            经典VCP：25%纠正到10%，再到5%（p.160）

        本算法实现步骤：
        1. 取最近一段整理窗口（≥5周≈25交易日，多留30根余量）
        2. 用Zigzag指标识别窗口内峰谷交替序列
        3. 枢轴点 = 整理期内最高高点
        4. 从枢轴点左侧回溯，收集所有H→L下跌段
        5. 验证：收缩次数2-6次、幅度逐次递减、成交量逐次萎缩、
           最后收缩段量<50日均量×0.9

        Returns:
            (是否命中VCP, 枢轴点价格, 收缩次数, 最后收缩幅度)
        """
        n = len(df)
        min_bars = self.params['vcp_min_weeks'] * 5  # 5周≈25交易日

        # 取整理窗口（最近 min_bars+30 根，多留余量给zigzag）
        window = df.tail(min_bars + 30).copy()
        if len(window) < min_bars:
            return False, 0.0, 0, 0.0

        highs = window['high'].values
        lows = window['low'].values
        vols = window['volume'].values

        # Step 1: Zigzag识别峰谷转折点
        zigzag_pct = self.params['vcp_zigzag_pct']
        pivots = self._zigzag(highs, lows, zigzag_pct)

        if len(pivots) < 3:
            return False, 0.0, 0, 0.0

        # Step 2: 枢轴点 = 整理期内最高高点
        high_pivots = [p for p in pivots if p[2] == 'H']
        if not high_pivots:
            return False, 0.0, 0, 0.0
        pivot_idx, pivot_price, _ = max(high_pivots, key=lambda x: x[1])

        # Step 3: 收集枢轴点左侧的 H→L 收缩段
        before_pivot = [p for p in pivots if p[0] <= pivot_idx]

        contractions: List[Tuple[float, float]] = []  # [(跌幅%, 该段均量)]
        for i in range(len(before_pivot) - 1):
            p1 = before_pivot[i]      # 高点
            p2 = before_pivot[i + 1]  # 后续低点
            if p1[2] == 'H' and p2[2] == 'L':
                pct_decline = (p1[1] - p2[1]) / p1[1]
                # 这段下跌的均量
                lo_idx = min(p1[0], p2[0])
                hi_idx = max(p1[0], p2[0])
                if hi_idx > lo_idx:
                    seg_vol = float(np.mean(vols[lo_idx:hi_idx + 1]))
                else:
                    seg_vol = float(vols[p1[0]])
                contractions.append((pct_decline, seg_vol))

        n_contr = len(contractions)

        # Step 4: 检查收缩次数范围（p.159：通常2~4次，有时达6次）
        if (n_contr < self.params['vcp_min_contractions'] or
                n_contr > self.params['vcp_max_contractions']):
            return False, pivot_price, n_contr, 0.0

        # Step 5: 检查幅度逐次递减（每次跌幅应小于前一次，允许10%误差）
        pcts = [c[0] for c in contractions]
        amplitude_decreasing = all(
            pcts[i] > pcts[i + 1] * 0.9 for i in range(len(pcts) - 1)
        )
        if not amplitude_decreasing:
            return False, pivot_price, n_contr, pcts[-1] if pcts else 0.0

        # Step 6: 检查成交量逐次萎缩（后一段均量/前一段 < 0.7）
        vols_seg = [c[1] for c in contractions]
        vol_shrink = all(
            vols_seg[i + 1] / max(vols_seg[i], 1e-9) < self.params['vcp_vol_shrink_ratio']
            for i in range(len(vols_seg) - 1)
        )

        # Step 7: 最后收缩段成交量 < 50日均量×0.9（p.181：被榨干）
        vol50 = df['volume'].tail(50).mean()
        last_vol = vols_seg[-1] if vols_seg else float(vols[-1])
        last_vol_ok = last_vol < vol50 * self.params['vcp_last_vol_ratio']

        hit = vol_shrink and last_vol_ok
        last_pct = pcts[-1] if pcts else 0.0

        return hit, pivot_price, n_contr, last_pct

    @staticmethod
    def _zigzag(highs: np.ndarray, lows: np.ndarray,
                threshold_pct: float = 0.05) -> List[Tuple[int, float, str]]:
        """
        Zigzag指标：识别显著的峰谷转折点

        从起始点开始追踪趋势方向，价格反向波动超过threshold_pct
        才确认前一个转折点，过滤微小噪音。

        Args:
            highs: 最高价数组
            lows: 最低价数组
            threshold_pct: 转折阈值（5%表示反向波动5%才确认转折）

        Returns:
            [(idx, price, type='H'/'L'), ...] 按时间顺序
        """
        n = len(highs)
        if n < 10:
            return []

        pivots: List[Tuple[int, float, str]] = []
        trend: Optional[str] = None  # None / 'up' / 'down'

        extreme_idx = 0
        extreme_price = float(highs[0])

        for i in range(1, n):
            if trend is None:
                # 未定方向：先判定初始趋势
                if highs[i] > extreme_price * (1 + threshold_pct):
                    trend = 'up'
                    extreme_idx = i
                    extreme_price = float(highs[i])
                elif lows[i] < extreme_price * (1 - threshold_pct):
                    trend = 'down'
                    extreme_idx = i
                    extreme_price = float(lows[i])

            elif trend == 'up':
                # 上升趋势中：持续更新最高点
                if highs[i] > extreme_price:
                    extreme_idx = i
                    extreme_price = float(highs[i])
                # 从最高点回撤超过阈值 → 确认高点，反转为下降趋势
                elif lows[i] < extreme_price * (1 - threshold_pct):
                    pivots.append((extreme_idx, extreme_price, 'H'))
                    trend = 'down'
                    extreme_idx = i
                    extreme_price = float(lows[i])

            elif trend == 'down':
                # 下降趋势中：持续更新最低点
                if lows[i] < extreme_price:
                    extreme_idx = i
                    extreme_price = float(lows[i])
                # 从最低点反弹超过阈值 → 确认低点，反转为上升趋势
                elif highs[i] > extreme_price * (1 + threshold_pct):
                    pivots.append((extreme_idx, extreme_price, 'L'))
                    trend = 'up'
                    extreme_idx = i
                    extreme_price = float(highs[i])

        return pivots

    # ============================================================
    # 模块4：枢轴点突破入场 check_pivot_breakout(df, pivot_price)
    # ============================================================
    def check_pivot_breakout(self, df: pd.DataFrame, pivot_price: float) -> Tuple[bool, str]:
        """
        枢轴点突破入场检查（p.174, p.178, p.183）

        枢轴点定义（p.178）：
            股票完成稳固期、准备开始下一次上涨的位置。
            利弗莫尔称之为"最后的阻力线"。

        突破日条件：
        1. 当日收盘价 > pivot_price（允许0-2%浮动）
        2. 绝不在枢轴点上方>5%追高
        3. 当日成交量 ≥ 50日均量×2.5
           （书里p.183：正常日100万股的股票，半天成交50万股，
            推断全天放量300-400%）
        4. 涨停板不追（A股T+1适配：涨停买入次日可能低开）

        为什么要等突破不能提前买（p.183）：
            "股票能突破转折点是非常危险的假设。
             如果转折点很难突破，你最终竹篮打水一场空。
             让股票自己证明可以打破转折点的禁锢吧。"

        Returns:
            (是否触发买入, 原因说明)
        """
        if pivot_price <= 0 or len(df) < 50:
            return False, '枢轴点无效或数据不足50根'

        today_close = float(df['close'].iloc[-1])
        today_vol = float(df['volume'].iloc[-1])
        vol50 = float(df['volume'].tail(50).mean())

        # 条件1：收盘价在枢轴点上方（允许0-2%浮动）
        drift_pct = (today_close - pivot_price) / pivot_price
        if drift_pct < -self.params['pivot_drift_tol']:
            return False, f'价格在枢轴点下方{drift_pct:.1%}，未突破'
        if drift_pct > self.params['pivot_chase_limit']:
            return False, (
                f'价格在枢轴点上方{drift_pct:.1%}，'
                f'超过追高上限{self.params["pivot_chase_limit"]:.0%}'
            )

        # 条件2：成交量显著放大
        vol_ratio = today_vol / max(vol50, 1e-9)
        if vol_ratio < self.params['breakout_vol_mult']:
            return False, (
                f'量比{vol_ratio:.1f}x < {self.params["breakout_vol_mult"]}x，'
                f'放量不足'
            )

        # 条件3：涨停板不追（A股适配）
        if len(df) >= 2:
            prev_close = float(df['close'].iloc[-2])
            if prev_close > 0 and today_close >= prev_close * (1 + self.params['limit_pct']):
                return False, '当日涨停，不追高（A股T+1适配）'

        return True, (
            f'枢轴点突破！drift={drift_pct:.1%}, '
            f'vol_ratio={vol_ratio:.1f}x'
        )

    # ============================================================
    # 模块5：风险引擎 compute_position_size()
    # ============================================================
    def compute_position_size(self, entry_price: float, stop_loss_price: float) -> int:
        """
        计算仓位股数（p.246 风险预算）

        公式：
            单笔总风险 = 总资金 × 0.5%
            股数 = (总资金 × 0.005) / (入场价 - 初始止损价)

        示例（100万资金，8%止损）：
            风险金额 = 1,000,000 × 0.005 = 5,000元
            每股风险 = 50 - 46 = 4元（买50元，止损46元）
            股数 = 5,000 / 4 = 1,250股 → 向下取整1200股（100股整数倍）
            实际占用资金 = 1200 × 50 = 60,000元（占总资金6%）

        A股适配：向下取整到100股整数倍。

        Args:
            entry_price: 入场价
            stop_loss_price: 初始止损价

        Returns:
            计划持仓股数（100股整数倍）
        """
        if entry_price <= 0 or stop_loss_price <= 0:
            return 0

        risk_amount = self.current_balance * self.params['risk_per_trade']
        risk_per_share = entry_price - stop_loss_price

        if risk_per_share <= 0:
            return 0

        raw_shares = risk_amount / risk_per_share
        lot = self.params['lot_size']
        shares = int(raw_shares // lot) * lot

        # 总敞口检查：不超过总资金的max_exposure
        max_cost = self.current_balance * self.params['max_exposure']
        if shares * entry_price > max_cost:
            shares = int(max_cost / entry_price // lot) * lot

        return max(shares, 0)

    def compute_initial_stop(self, entry_price: float, recent_low: float) -> float:
        """
        计算初始止损价（p.222-248）

        规则：
        - 正常市场：买入价 - 7.5%
          （p.240第一法则：止损不超过历史成功投资平均收益的一半；
            若平均收益15%，止损应在7.5%以内）
        - 恶劣市场：买入价 - 5.5%
          （p.248：平常7-8%，恶劣市场收紧到5-6%）
        - 同时不跌破近期整理低点（取较高者，更紧的止损）
        - 硬性上限：最大亏损不超过10%（p.222：挽回损失所需收益率表）

        Args:
            entry_price: 买入价
            recent_low: 近期整理期最低点

        Returns:
            止损价
        """
        stop_pct = (self.params['bear_stop_loss_pct'] if self.bear_market
                    else self.params['stop_loss_pct'])
        stop_by_pct = entry_price * (1 - stop_pct)

        # 不跌破近期整理低点（取较高者=更紧止损）
        stop = max(stop_by_pct, recent_low * 0.99)

        # 硬性上限：最大亏损不超过10%（p.222）
        max_stop = entry_price * (1 - self.params['max_loss_pct'])
        stop = max(stop, max_stop)

        return stop

    # ============================================================
    # 模块6：3R保本规则 update_stop()
    # ============================================================
    def update_stop(self, current_price: float, df: pd.DataFrame) -> Tuple[float, str]:
        """
        更新止损价（p.246 3R保本规则）

        书里原文（p.246）：
            "当股价已经升高到我可容忍风险的3倍位置时，
             我会把止损线提高到至少盈亏平衡。"

        数值例子（p.246）：
            买入价$50，止损$47.50（风险5%），每股风险$2.50（=1R）
            当股价升到$57.50（=3R位置），止损移到$50（成本价）
            之后被止损卖出，至少保留初始资本，不赚不亏。

        本实现：
        1. R = 入场价 - 初始止损价
        2. 浮盈 ≥ 3R → 止损上移至成本价（breakeven_triggered=True）
        3. 保本后 → 用MA20作为动态跟踪止损（p.186：成功突围应守在MA20上方）
           收盘价跌破MA20即离场。

        Args:
            current_price: 当前价
            df: OHLCV DataFrame

        Returns:
            (新止损价, 状态说明)
        """
        if self.entry_price <= 0:
            return self.stop_loss, '无持仓'

        R = self.entry_price - self.stop_loss  # 初始风险R
        if R <= 0:
            return self.stop_loss, '止损逻辑异常（R≤0）'

        # Phase 1: 未触发保本前，检查是否达到3R
        if not self.breakeven_triggered:
            target_3r = self.entry_price + self.params['breakeven_r_mult'] * R
            if current_price >= target_3r:
                self.stop_loss = self.entry_price  # 移到成本价
                self.breakeven_triggered = True
                return (self.stop_loss,
                        f'3R触发！价格{current_price:.2f}≥{target_3r:.2f}，'
                        f'止损移至成本价{self.entry_price:.2f}')
            distance = target_3r - current_price
            return (self.stop_loss,
                    f'持有中，浮盈{(current_price/self.entry_price-1):.1%}，'
                    f'距3R保本还差{distance:.2f}')

        # Phase 2: 已保本，用MA20动态跟踪止损
        ma_period = self.params['trailing_ma_period']
        if len(df) >= ma_period:
            ma_trailing = float(df['close'].tail(ma_period).mean())
            # 跟踪止损只上移不下移（取较高者）
            if ma_trailing > self.stop_loss:
                self.stop_loss = ma_trailing
                return (self.stop_loss,
                        f'MA{ma_period}跟踪止损上移至{ma_trailing:.2f}')

        return self.stop_loss, f'保本持有中，止损{self.stop_loss:.2f}'

    # ============================================================
    # 模块7：分批建仓 check_add_position()
    # ============================================================
    def check_add_position(self, df: pd.DataFrame, pivot_price: float) -> Tuple[bool, str]:
        """
        检查是否加仓（p.246 分批建仓/金字塔加仓）

        书里规则：
        - 首次建仓1/2计划仓位
        - 突破确认后加至满仓（收盘站稳枢轴点上方2-3天，或回调不破枢轴点）
        - "永远不要相信初始价格，除非你的仓位已经让你盈利"（p.246）
        - "我只会在给我带来利润的股票上面增加仓位"
        - 绝不摊低成本（p.244："摊低成本是业余的、自我毁灭的行为"）

        本实现：
        - 首仓 = target_position × 50%
        - 收盘价连续≥3天站在枢轴点上方 → 加仓至满仓
        - 加仓时更新平均成本（只在盈利头寸上加仓）

        Returns:
            (是否加仓, 原因)
        """
        if self.position_size <= 0:
            return False, '无持仓'

        if not self.is_first_trade:
            return False, '已是满仓状态'

        today_close = float(df['close'].iloc[-1])

        # 加仓前提：当前价在枢轴点上方（盈利才加仓，不摊低）
        if today_close < pivot_price:
            self.days_above_pivot = 0
            return False, (f'价格{today_close:.2f} < 枢轴点{pivot_price:.2f}，'
                           f'不摊低成本，不加仓')

        # 累计站稳天数
        self.days_above_pivot += 1

        if self.days_above_pivot >= self.params['add_confirm_days']:
            return True, (f'已站稳枢轴点{self.days_above_pivot}天'
                          f'(阈值{self.params["add_confirm_days"]}天)，加仓至满仓')

        return False, (f'站稳枢轴点{self.days_above_pivot}/'
                       f'{self.params["add_confirm_days"]}天')

    # ============================================================
    # 模块8：大盘环境过滤 check_market_regime()
    # ============================================================
    def check_market_regime(self, benchmark_df: Optional[pd.DataFrame]) -> bool:
        """
        大盘环境过滤（p.248 恶劣市场应对）

        用基准指数（沪深300）自身是否在MA200上方作为开关：
        - 指数在MA200上方 → 牛市环境，正常开仓，止损7.5%
        - 指数在MA200下方 → 熊市环境，不开新仓，已有持仓收紧止损到5.5%

        书里原文（p.248）：
            "恶劣市场环境：缩紧止损线（7-8%→5-6%），
             小利润落袋为安（15-20%→10-12%），
             削减杠杆，减小风险敞口。"

        金融股预警规律（p.71）：
            "金融股会为即将到来的问题做出预警。"

        Returns:
            是否允许开新仓
        """
        if not self.params['market_filter_on']:
            self.bear_market = False
            return True

        if benchmark_df is None or len(benchmark_df) < self.params['ma_long2']:
            return True  # 基准数据不足，默认允许

        bench_close = benchmark_df['close'].values
        ma200 = self._sma(bench_close, self.params['ma_long2'])

        if np.isnan(ma200[-1]):
            return True

        current_bench = float(bench_close[-1])
        bench_ma200 = float(ma200[-1])

        if current_bench < bench_ma200:
            self.bear_market = True
            return False   # 熊市不开新仓
        else:
            self.bear_market = False
            return True    # 牛市正常开仓

    # ============================================================
    # 主接口：update_price（每根K线调用）
    # ============================================================
    def update_price(self, current_price: float,
                     data: Optional[pd.Series] = None) -> Dict[str, Any]:
        """
        每根K线调用：根据当前价格执行交易决策

        注意（坑1，盘点报告2.4节）：
            data参数只有截至当前的close Series。
            VCP/枢轴点/MA200/ATR等全部使用self.df
            （由load_data()或set_dataframe()预加载的完整OHLCV）。

        决策流程：
            1. 更新最新收盘价到self.df
            2. 若有持仓 → _manage_position()（止损/保本/跟踪/加仓）
            3. 若空仓 → _check_entry()（趋势模板→RS→VCP→枢轴突破→大盘过滤）

        Returns:
            交易动作字典 {action, price, shares, reason, ...}
        """
        self.last_price = current_price

        if self.df is None or len(self.df) < 250:
            return {'action': 'hold', 'reason': 'OHLCV数据未加载(需≥250根)',
                    'balance': self.current_balance}

        # 将最新收盘价写入预加载DataFrame的最后一行
        self.df.loc[self.df.index[-1], 'close'] = current_price

        # ---------- 持仓中：管理已有仓位 ----------
        if self.position_size > 0:
            return self._manage_position(current_price)

        # ---------- 空仓：寻找入场机会 ----------
        return self._check_entry(current_price)

    def _manage_position(self, current_price: float) -> Dict[str, Any]:
        """管理已有持仓：T+1检查→跌停检查→止损更新→止损触发→加仓检查"""
        df = self.df

        # A股T+1：当日买入次日才可卖
        today = df['date'].iloc[-1] if 'date' in df.columns else None
        if (self.params['t1_settlement'] and self.buy_date is not None
                and today is not None and hasattr(today, 'date')):
            if self.buy_date.date() == today.date():
                return {'action': 'hold', 'reason': 'T+1：当日买入次日才可卖',
                        'balance': self.current_balance,
                        'position': self.position_size}

        # 跌停板不挂卖单（A股适配：假设无法成交）
        if len(df) >= 2:
            prev_close = float(df['close'].iloc[-2])
            if prev_close > 0 and current_price <= prev_close * (1 - self.params['limit_pct']):
                return {'action': 'hold', 'reason': '跌停板，卖单假设无法成交',
                        'balance': self.current_balance,
                        'position': self.position_size}

        # 更新止损（3R保本 + MA20动态跟踪）
        new_stop, stop_status = self.update_stop(current_price, df)

        # 检查止损是否被触发
        if current_price <= self.stop_loss:
            return self._execute_sell(current_price,
                                      f'止损触发：价格{current_price:.2f}≤止损{self.stop_loss:.2f}',
                                      'stop_loss')

        # 检查是否满足加仓条件
        should_add, add_reason = self.check_add_position(df, self.pivot_price)
        if should_add and self.is_first_trade:
            return self._execute_add(current_price)

        return {'action': 'hold', 'reason': stop_status,
                'balance': self.current_balance,
                'position': self.position_size,
                'stop_loss': self.stop_loss}

    def _check_entry(self, current_price: float) -> Dict[str, Any]:
        """空仓时按选股漏斗检查入场条件"""
        df = self.df

        # 第0层：大盘环境过滤（指数<MA200不开新仓）
        market_ok = self.check_market_regime(self.benchmark_df)
        if not market_ok:
            return {'action': 'hold',
                    'reason': '熊市环境：沪深300<MA200，不开新仓(p.248)',
                    'balance': self.current_balance}

        # 第1层：RS评分
        rs = self.relative_rating(df, self.benchmark_df)

        # 第2层：趋势模板8条
        template_ok, template_detail = self.passes_trend_template(df)
        if not template_ok:
            failed = [k for k, v in template_detail.items()
                      if isinstance(v, tuple) and not v[0]]
            return {'action': 'hold',
                    'reason': f'趋势模板未通过: {failed}',
                    'balance': self.current_balance}

        # 第3层：VCP波动收缩检测
        vcp_hit, pivot, n_contr, last_pct = self.detect_vcp(df)
        if not vcp_hit:
            return {'action': 'hold',
                    'reason': f'VCP未命中（收缩{n_contr}次，最后幅度{last_pct:.1%}）',
                    'balance': self.current_balance}

        # 第4层：枢轴点放量突破
        breakout, breakout_reason = self.check_pivot_breakout(df, pivot)
        if not breakout:
            return {'action': 'hold', 'reason': breakout_reason,
                    'balance': self.current_balance}

        # 全部通过 → 执行首仓买入
        self.pivot_price = pivot
        return self._execute_buy(current_price, pivot, n_contr)

    # ============================================================
    # 交易执行
    # ============================================================
    def _execute_buy(self, price: float, pivot: float, n_contr: int) -> Dict[str, Any]:
        """执行首仓买入（1/2计划仓位）"""
        recent_low = float(self.df['low'].tail(25).min())

        # 计算初始止损
        stop = self.compute_initial_stop(price, recent_low)

        # 计算计划总仓位股数
        total_shares = self.compute_position_size(price, stop)
        if total_shares <= 0:
            return {'action': 'hold', 'reason': '风险计算后仓位为0',
                    'balance': self.current_balance}

        # 首仓 = 1/2计划仓位
        lot = self.params['lot_size']
        first_shares = int(total_shares * self.params['first_trade_ratio'] // lot) * lot

        cost = first_shares * price
        if cost > self.current_balance:
            return {'action': 'hold', 'reason': f'资金不足(需{cost:.0f})',
                    'balance': self.current_balance}

        # 更新持仓状态
        self.current_balance -= cost
        self.position_size = first_shares
        self.entry_price = price
        self.stop_loss = stop
        self.target_position = total_shares
        self.is_first_trade = True
        self.days_above_pivot = 0
        self.breakeven_triggered = False
        self.buy_date = (self.df['date'].iloc[-1]
                         if 'date' in self.df.columns else None)
        self.total_trades += 1

        msg = (f'买入{first_shares}股@{price:.2f}, 止损{stop:.2f}, '
               f'VCP {n_contr}次收缩, 枢轴{pivot:.2f}')
        self.signal_log.append({
            'date': str(self.buy_date), 'action': 'buy',
            'price': price, 'shares': first_shares,
            'stop_loss': stop, 'pivot': pivot
        })
        logger.info(f'[{self.strategy_name}] {msg}')

        return {'action': 'buy', 'price': price, 'shares': first_shares,
                'stop_loss': stop, 'reason': msg,
                'balance': self.current_balance,
                'position': self.position_size}

    def _execute_add(self, price: float) -> Dict[str, Any]:
        """执行加仓（从1/2加至满仓，只在盈利头寸上加仓）"""
        add_shares = self.target_position - self.position_size
        lot = self.params['lot_size']
        add_shares = int(add_shares // lot) * lot

        if add_shares <= 0:
            self.is_first_trade = False
            return {'action': 'hold', 'reason': '已是满仓',
                    'balance': self.current_balance,
                    'position': self.position_size}

        cost = add_shares * price
        if cost > self.current_balance:
            add_shares = int(self.current_balance / price // lot) * lot
            cost = add_shares * price

        if add_shares <= 0:
            return {'action': 'hold', 'reason': '加仓资金不足',
                    'balance': self.current_balance,
                    'position': self.position_size}

        # 更新平均成本（只在盈利头寸上加仓，不摊低成本）
        total_shares = self.position_size + add_shares
        self.entry_price = ((self.entry_price * self.position_size +
                            price * add_shares) / total_shares)

        self.current_balance -= cost
        self.position_size = total_shares
        self.add_price = price
        self.is_first_trade = False

        self.signal_log.append({
            'date': str(self.df['date'].iloc[-1]), 'action': 'add',
            'price': price, 'shares': add_shares
        })

        return {'action': 'add', 'price': price, 'shares': add_shares,
                'reason': f'加仓{add_shares}股，总持仓{self.position_size}股，'
                          f'均价{self.entry_price:.2f}',
                'balance': self.current_balance,
                'position': self.position_size}

    def _execute_sell(self, price: float, reason: str,
                      sell_type: str) -> Dict[str, Any]:
        """执行卖出（止损/止盈）"""
        proceeds = self.position_size * price
        self.current_balance += proceeds

        # 计算单笔盈亏
        pnl = (price - self.entry_price) * self.position_size
        if pnl > 0:
            self.winning_trades += 1
        else:
            self.losing_trades += 1
        self.profit_history.append(pnl)

        self.signal_log.append({
            'date': str(self.df['date'].iloc[-1]), 'action': 'sell',
            'price': price, 'shares': self.position_size,
            'pnl': pnl, 'sell_type': sell_type
        })

        sold_shares = self.position_size
        logger.info(f'[{self.strategy_name}] 卖出{sold_shares}股@{price:.2f}, '
                    f'PnL={pnl:.2f}, {reason}')

        # 重置持仓状态机
        self.position_size = 0
        self.entry_price = 0.0
        self.add_price = 0.0
        self.stop_loss = 0.0
        self.target_position = 0
        self.is_first_trade = True
        self.days_above_pivot = 0
        self.breakeven_triggered = False
        self.pivot_price = 0.0
        self.buy_date = None

        return {'action': 'sell', 'price': price, 'shares': sold_shares,
                'reason': reason, 'sell_type': sell_type, 'pnl': pnl,
                'balance': self.current_balance, 'position': 0}

    # ============================================================
    # 性能统计 get_performance()
    # ============================================================
    def get_performance(self) -> Dict[str, float]:
        """返回策略性能指标（基类要求实现）"""
        total = self.total_trades
        win_rate = (self.winning_trades / total * 100) if total > 0 else 0.0

        total_pnl = sum(self.profit_history) if self.profit_history else 0.0
        wins = [p for p in self.profit_history if p > 0]
        losses = [p for p in self.profit_history if p < 0]

        avg_win = float(np.mean(wins)) if wins else 0.0
        avg_loss = float(np.mean(losses)) if losses else 0.0
        profit_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0.0

        return {
            'total_trades': float(total),
            'winning_trades': float(self.winning_trades),
            'losing_trades': float(self.losing_trades),
            'win_rate_pct': round(win_rate, 2),
            'current_balance': round(self.current_balance, 2),
            'position': float(self.position_size),
            'entry_price': self.entry_price,
            'stop_loss': self.stop_loss,
            'total_pnl': round(total_pnl, 2),
            'avg_win': round(avg_win, 2),
            'avg_loss': round(avg_loss, 2),
            'profit_loss_ratio': round(profit_loss_ratio, 2),
            'bear_market': 1.0 if self.bear_market else 0.0,
        }

    # ============================================================
    # 框架接口
    # ============================================================
    def get_risk_params(self) -> dict:
        """返回风险参数（供框架调用）"""
        return {
            'stop_loss': self.params['stop_loss_pct'],
            'take_profit': 0.20,
            'max_position': self.params['max_exposure'],
            'risk_per_trade': self.params['risk_per_trade'],
        }

    def get_param_space(self) -> dict:
        """返回参数搜索空间（供Optuna/网格搜索）"""
        return {
            'stop_loss_pct': [0.05, 0.06, 0.07, 0.075, 0.08, 0.10],
            'risk_per_trade': [0.003, 0.005, 0.008, 0.01],
            'breakout_vol_mult': [1.5, 2.0, 2.5, 3.0, 3.5, 4.0],
            'rs_min_score': [60, 70, 75, 80],
            'breakeven_r_mult': [2.0, 2.5, 3.0, 3.5],
            'vcp_min_weeks': [4, 5, 6, 8],
            'vcp_zigzag_pct': [0.03, 0.05, 0.07, 0.10],
        }

    def validate_params(self) -> bool:
        """参数合法性校验"""
        if self.params['risk_per_trade'] > 0.02:
            logger.error('单笔风险超过2%过高（书里p.246建议0.5%）')
            return False
        if self.params['stop_loss_pct'] > self.params['max_loss_pct']:
            logger.error('初始止损超过10%硬性上限（p.222）')
            return False
        if self.params['lot_size'] != 100:
            logger.warning('A股最小交易单位应为100股')
        return True

    # ============================================================
    # 辅助方法
    # ============================================================
    @staticmethod
    def _sma(data: np.ndarray, period: int) -> np.ndarray:
        """
        简单移动平均（自实现，不依赖外部指标库，保持文件自包含）

        Args:
            data: 收盘价数组
            period: 周期

        Returns:
            SMA数组（前period-1个为NaN）
        """
        n = len(data)
        result = np.full(n, np.nan)
        if n < period:
            return result
        cumsum = np.cumsum(data, dtype=float)
        result[period - 1:] = (
            (cumsum[period - 1:] -
             np.concatenate([[0.0], cumsum[:-period]])) / period
        )
        return result
