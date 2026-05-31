#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能标的轮动策略 — 多因子特征工程
================================
为每只 ETF 生成 100+ 技术因子 + 行业轮动特征，输出固定维度特征矩阵。

因子分类（共 5 大类）：
  1. 价格动量因子（~25个）   — 收益率、动量、加速度
  2. 波动率因子（~15个）      — 历史波动率、ATR、布林带宽度
  3. 流动性因子（~10个）      — 换手率、Amihud非流动性
  4. 趋势/反转因子（~20个）   — MACD、RSI、KDJ、OBV
  5. 行业轮动因子（~20个）    — 截面排名、相对强度、行业动量
  6. 宏观/市场因子（~10个）   — 指数关联、市场宽度

输出：shape = (T, N_ASSETS, FEATURE_DIM) 的 numpy 数组
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# 尝试导入 TA-Lib（加速计算）
try:
    import talib as ta
    HAS_TALIB = True
except ImportError:
    HAS_TALIB = False
    logger.warning("TA-Lib 未安装，使用纯 numpy/pandas 回退实现（速度较慢）")


# ==================== 因子计算器 ====================

class FactorEngine:
    """
    多因子特征计算引擎
    
    特性：
    - 严格避免未来函数：所有因子仅使用时刻 t 及之前的数据
    - 逐标的独立计算，再合成为截面张量
    - NaN 安全填充（前向填充 + 0 填充）
    """

    def __init__(self, lookback: int = 60, price_col: str = "close", volume_col: str = "volume"):
        self.lookback = lookback
        self.price_col = price_col
        self.volume_col = volume_col
        self._factor_cache: Dict[str, np.ndarray] = {}

    # ── 1. 价格动量因子 ──
    def _momentum_factors(self, close: np.ndarray) -> np.ndarray:
        """
        动量因子组（~20维）
        
        Returns:
            ndarray shape=(T, 20)
        """
        T = len(close)
        # 确保至少足够长的数据
        if T < 2:
            return np.zeros((T, 20))
        
        factors = []
        # 对数收益率
        log_ret = np.diff(np.log(np.maximum(close, 1e-8)), prepend=np.log(close[0:1]))
        
        # 简单收益率
        ret = np.diff(close, prepend=close[0:1]) / np.maximum(close, 1e-8)
        
        # 1-5: 多周期动量（1/5/10/20/60日）
        for period in [1, 5, 10, 20, 60]:
            mom = np.zeros(T)
            for t in range(period, T):
                mom[t] = (close[t] - close[t - period]) / max(close[t - period], 1e-8)
            factors.append(mom)
        
        # 6-7: 收益率的均值和标准差
        ret_mean = pd.Series(ret).rolling(20, min_periods=1).mean().values
        ret_std  = pd.Series(ret).rolling(20, min_periods=1).std().fillna(0).values
        factors.append(ret_mean)
        factors.append(ret_std)
        
        # 8: 偏度
        skew = pd.Series(ret).rolling(20, min_periods=3).skew().fillna(0).values
        factors.append(skew)
        # 9: 峰度
        kurt = pd.Series(ret).rolling(20, min_periods=4).kurt().fillna(0).values
        factors.append(kurt)
        
        # 10-13: 移动平均（5/10/20/60）与价格的偏离
        for period in [5, 10, 20, 60]:
            ma = pd.Series(close).rolling(period, min_periods=1).mean().values
            deviation = (close - ma) / np.maximum(ma, 1e-8)
            factors.append(deviation)
        
        # 14: ROC（价格变化率）
        roc = pd.Series(close).pct_change(10).fillna(0).values
        factors.append(roc)
        
        # 15-16: 最高/最低价的动量（如果没有就用 close 近似）
        high_mom = np.zeros(T)
        low_mom = np.zeros(T)
        for t in range(20, T):
            high_mom[t] = (close[t] - np.max(close[t-20:t])) / max(np.max(close[t-20:t]), 1e-8)
            low_mom[t]  = (close[t] - np.min(close[t-20:t])) / max(np.min(close[t-20:t]), 1e-8)
        factors.append(high_mom)
        factors.append(low_mom)
        
        # 17: 加速度（动量的一阶差分）
        accel = np.diff(factors[0], prepend=factors[0][0:1])
        factors.append(accel)
        
        # 18-19: 对数收益率 EMA 快/慢
        ema_fast = pd.Series(log_ret).ewm(span=5, min_periods=1).mean().values
        ema_slow = pd.Series(log_ret).ewm(span=20, min_periods=1).mean().values
        factors.append(ema_fast)
        factors.append(ema_slow - ema_fast)  # MACD 信号线
        
        # 20: 累计收益率（从 lookback 窗口起点）
        cum_ret = np.zeros(T)
        # 相对第一个观测点的累计收益
        cum_ret = (close - close[0]) / max(close[0], 1e-8)
        factors.append(cum_ret)
        
        return np.column_stack(factors)

    # ── 2. 波动率因子 ──
    def _volatility_factors(self, close: np.ndarray, high: Optional[np.ndarray] = None,
                            low: Optional[np.ndarray] = None) -> np.ndarray:
        """波动率因子组（~12维）"""
        T = len(close)
        ret = np.diff(close, prepend=close[0:1]) / np.maximum(close, 1e-8)
        factors = []
        
        # 1-3: 不同周期的历史波动率
        for period in [5, 20, 60]:
            vol = pd.Series(ret).rolling(period, min_periods=2).std().fillna(0).values
            factors.append(vol * np.sqrt(252))  # 年化
        
        # 4-5: Parkinson 波动率估计量（需要高低价）
        if high is not None and low is not None and len(high) == T and len(low) == T:
            pk = np.sqrt(1 / (4 * np.log(2)) * (np.log(np.maximum(high, low) / np.maximum(low, 1e-8))) ** 2)
            pk_20 = pd.Series(pk).rolling(20, min_periods=1).mean().fillna(0).values
        else:
            pk_20 = factors[1].copy()  # 回退到 20 日历史波动率
        factors.append(pk_20)
        factors.append(pd.Series(pk_20).rolling(5, min_periods=1).mean().fillna(0).values)

        # 6-7: 波动率的变化率
        vol_change = np.diff(factors[1], prepend=factors[1][0:1])
        factors.append(vol_change)
        factors.append(pd.Series(vol_change).rolling(10, min_periods=1).mean().fillna(0).values)

        # 8-10: Garman-Klass 类波动率（简化）
        for period in [10, 20, 60]:
            rolling_max = pd.Series(close).rolling(period, min_periods=1).max().values
            rolling_min = pd.Series(close).rolling(period, min_periods=1).min().values
            range_vol = (rolling_max - rolling_min) / np.maximum(rolling_max, 1e-8)
            factors.append(range_vol)

        # 11: 波动率锥（当前波动率在历史分位数中的位置）
        if T >= 60:
            rolling_std = pd.Series(ret).rolling(60, min_periods=60).std().fillna(0).values
            vol_percentile = np.zeros(T)
            for t in range(60, T):
                hist_vol = pd.Series(ret[max(0, t-252):t]).rolling(60, min_periods=60).std().dropna()
                if len(hist_vol) > 0:
                    vol_percentile[t] = np.percentile(hist_vol, np.clip(
                        100 * (rolling_std[t] - hist_vol.min()) / max(hist_vol.max() - hist_vol.min(), 1e-10),
                        0, 100
                    )) / 100.0
            factors.append(vol_percentile)
        else:
            factors.append(np.zeros(T))

        # 12: 下行波动率
        neg_ret = np.minimum(ret, 0)
        down_vol = pd.Series(neg_ret).rolling(20, min_periods=2).std().fillna(0).values
        factors.append(down_vol * np.sqrt(252))
        
        return np.column_stack(factors)

    # ── 3. 流动性因子 ──
    def _liquidity_factors(self, close: np.ndarray, volume: np.ndarray,
                           amount: Optional[np.ndarray] = None) -> np.ndarray:
        """流动性因子组（~8维）"""
        T = len(close)
        factors = []
        
        # 1-2: 成交量及其变化
        vol_ma5 = pd.Series(volume).rolling(5, min_periods=1).mean().values
        vol_ma20 = pd.Series(volume).rolling(20, min_periods=1).mean().values
        factors.append(volume / np.maximum(vol_ma20, 1.0))  # 量比
        factors.append(vol_ma5 / np.maximum(vol_ma20, 1.0))
        
        # 3: Amihud 非流动性指标（简化）
        ret = np.abs(np.diff(close, prepend=close[0:1]) / np.maximum(close, 1e-8))
        amihud = np.zeros(T)
        if amount is not None and len(amount) == T:
            for t in range(1, T):
                amihud[t] = ret[t] / max(amount[t], 1.0)
        else:
            for t in range(1, T):
                amihud[t] = ret[t] / max(volume[t] * close[t], 1.0)
        factors.append(pd.Series(amihud).rolling(20, min_periods=1).mean().fillna(0).values * 1e6)
        
        # 4: 换手率（成交量比 20 日均量）
        turnover = volume / np.maximum(vol_ma20, 1.0)
        factors.append(turnover)
        
        # 5: 成交量趋势
        vol_trend = np.zeros(T)
        for t in range(20, T):
            vol_trend[t] = np.polyfit(np.arange(20), volume[t-20:t], 1)[0]
        factors.append(vol_trend)
        
        # 6: 价量相关性
        price_vol_corr = np.zeros(T)
        for t in range(20, T):
            price_vol_corr[t] = np.corrcoef(close[t-20:t], volume[t-20:t])[0, 1] if np.std(volume[t-20:t]) > 0 else 0
        factors.append(np.nan_to_num(price_vol_corr))
        
        # 7: 成交量标准差
        vol_std = pd.Series(volume).rolling(20, min_periods=2).std().fillna(0).values
        factors.append(vol_std / np.maximum(vol_ma20, 1.0))
        
        # 8: 金额标准差（如果没有就用价格*成交量近似）
        amount_data = amount if amount is not None and len(amount) == T else volume * close
        amount_std = pd.Series(amount_data).rolling(20, min_periods=2).std().fillna(0).values
        factors.append(amount_std / np.maximum(amount_data, 1.0))
        
        return np.column_stack(factors)

    # ── 4. 趋势/反转因子 ──
    def _trend_reversal_factors(self, close: np.ndarray, high: Optional[np.ndarray] = None,
                                low: Optional[np.ndarray] = None,
                                volume: Optional[np.ndarray] = None) -> np.ndarray:
        """趋势/反转因子组（~20维）"""
        T = len(close)
        factors = []
        
        # 1-3: MACD 三口
        if HAS_TALIB:
            macd, macd_signal, macd_hist = ta.MACD(close)
        else:
            ema12 = pd.Series(close).ewm(span=12, min_periods=1).mean().values
            ema26 = pd.Series(close).ewm(span=26, min_periods=1).mean().values
            macd = ema12 - ema26
            macd_signal = pd.Series(macd).ewm(span=9, min_periods=1).mean().values
            macd_hist = (macd - macd_signal) * 2
        factors.append(np.nan_to_num(macd))
        factors.append(np.nan_to_num(macd_signal))
        factors.append(np.nan_to_num(macd_hist))
        
        # 4-5: RSI 快慢
        if HAS_TALIB:
            rsi_6 = ta.RSI(close, timeperiod=6)
            rsi_14 = ta.RSI(close, timeperiod=14)
        else:
            rsi_6 = _rsi_numpy(close, 6)
            rsi_14 = _rsi_numpy(close, 14)
        factors.append(np.nan_to_num(rsi_6, nan=50.0))
        factors.append(np.nan_to_num(rsi_14, nan=50.0))
        
        # 6-8: KDJ
        k, d, j = _kdj_numpy(close, high if high is not None else close,
                             low if low is not None else close)
        factors.append(k)
        factors.append(d)
        factors.append(j)
        
        # 9-10: 布林带 %b 和宽度
        bband_pct, bband_width = _bollinger_numpy(close)
        factors.append(bband_pct)
        factors.append(bband_width)
        
        # 11: ATR（平均真实波幅）
        if HAS_TALIB and high is not None and low is not None:
            atr = ta.ATR(high, low, close, timeperiod=14)
        else:
            atr = _atr_numpy(close, high if high is not None else close,
                            low if low is not None else close)
        factors.append(np.nan_to_num(atr, nan=0.0) / np.maximum(close, 1e-8))
        
        # 12: ADX（趋势强度）
        if HAS_TALIB and high is not None and low is not None:
            adx = ta.ADX(high, low, close, timeperiod=14)
        else:
            adx = _adx_numpy(close)
        factors.append(np.nan_to_num(adx, nan=20.0))
        
        # 13: OBV（能量潮）
        if HAS_TALIB and volume is not None:
            obv = ta.OBV(close, volume)
        elif volume is not None:
            obv = _obv_numpy(close, volume)
        else:
            obv = np.zeros(T)
        factors.append(obv / np.maximum(np.abs(obv).max(), 1.0))
        
        # 14-15: 慢/快随机指标
        slow_k, slow_d = _stochastic_numpy(close, high if high is not None else close,
                                           low if low is not None else close)
        factors.append(slow_k)
        factors.append(slow_d)
        
        # 16: CCI（商品通道指数）
        if HAS_TALIB and high is not None and low is not None:
            cci = ta.CCI(high, low, close, timeperiod=14)
        else:
            cci = _cci_numpy(close)
        factors.append(np.nan_to_num(cci, nan=0.0))
        
        # 17: 威廉 %R
        if HAS_TALIB and high is not None and low is not None:
            willr = ta.WILLR(high, low, close, timeperiod=14)
        else:
            willr = _willr_numpy(close)
        factors.append(np.nan_to_num(willr, nan=-50.0))
        
        # 18-19: DMI 方向线
        if HAS_TALIB and high is not None and low is not None:
            plus_di = ta.PLUS_DI(high, low, close, timeperiod=14)
            minus_di = ta.MINUS_DI(high, low, close, timeperiod=14)
        else:
            plus_di = np.full(T, 25.0)
            minus_di = np.full(T, 25.0)
        factors.append(np.nan_to_num(plus_di, nan=25.0))
        factors.append(np.nan_to_num(minus_di, nan=25.0))
        
        # 20: 趋势强度（ADX 与 25 的偏差）
        adx_signal = np.sign(adx - 25) * (np.abs(adx - 25) / 25)
        factors.append(np.nan_to_num(adx_signal))
        
        return np.column_stack(factors)

    # ── 5. 行业轮动因子 ──
    def _sector_rotation_factors(self, close_all: np.ndarray,
                                 symbols: List[str]) -> np.ndarray:
        """
        行业轮动因子组（~15维，每个标的）
        
        Args:
            close_all: shape=(T, N_ASSETS) 所有标的的收盘价矩阵
            symbols: 标的代码列表
        
        Returns:
            shape=(T, N_ASSETS, 15) 的因子矩阵
        """
        T, N = close_all.shape
        ret_all = np.diff(close_all, axis=0, prepend=close_all[0:1]) / np.maximum(close_all, 1e-8)
        
        # 截面相对强度排名（-1 到 1）
        factors_3d = np.zeros((T, N, 15))
        
        for period in [5, 20, 60]:
            mom = np.zeros((T, N))
            for t in range(period, T):
                mom[t] = (close_all[t] - close_all[t - period]) / np.maximum(close_all[t - period], 1e-8)
            # 截面排名
            rank = np.zeros((T, N))
            for t in range(T):
                order = np.argsort(np.argsort(mom[t]))  # 排名 0 到 N-1
                rank[t] = (2 * order / (N - 1 + 1e-8)) - 1  # 归一化到 [-1, 1]
            offset = [5, 20, 60].index(period) * 5
            factors_3d[:, :, offset] = rank
        
        # 持仓调整：动量强度分数
        for i in range(N):
            for period in [5, 10, 20]:
                rolling_ret = pd.DataFrame(ret_all[:, i]).rolling(period, min_periods=1).sum().values.flatten()
                offset = 3 + [5, 10, 20].index(period)
                factors_3d[:, i, offset] = rolling_ret
        
        # 截面波动率排名
        for period in [10, 20]:
            vol = np.zeros((T, N))
            for i in range(N):
                vol[:, i] = pd.Series(ret_all[:, i]).rolling(period, min_periods=2).std().fillna(0).values
            rank_vol = np.zeros((T, N))
            for t in range(T):
                order = np.argsort(np.argsort(vol[t]))
                rank_vol[t] = (2 * order / (N - 1 + 1e-8)) - 1
            offset = 6 + [10, 20].index(period)
            factors_3d[:, :, offset] = rank_vol
        
        # 相关性矩阵（每标的与组合平均的相关性）
        avg_ret = ret_all.mean(axis=1)
        for i in range(N):
            corr = np.zeros(T)
            for t in range(20, T):
                if np.std(ret_all[t-20:t, i]) > 0 and np.std(avg_ret[t-20:t]) > 0:
                    corr[t] = np.corrcoef(ret_all[t-20:t, i], avg_ret[t-20:t])[0, 1]
            factors_3d[:, i, 8] = np.nan_to_num(corr)
        
        # 相对强度（vs 等权基准）
        for period in [20, 60]:
            for i in range(N):
                rel_str = np.zeros(T)
                for t in range(period, T):
                    asset_ret = close_all[t, i] / max(close_all[t - period, i], 1e-8) - 1
                    bench_ret = np.mean(close_all[t] / np.maximum(close_all[t - period], 1e-8)) - 1
                    rel_str[t] = asset_ret - bench_ret
                offset = 9 + [20, 60].index(period)
                factors_3d[:, i, offset] = rel_str
        
        # 行业集中度（同一行业有多少标的在前 N）
        # 这里用截面排名比例简化
        for i in range(N):
            for period in [20, 60]:
                top_ratio = np.zeros(T)
                for t in range(period, T):
                    ret_rank = np.argsort(np.argsort(ret_all[t-period:t].sum(axis=0)))[i]
                    top_ratio[t] = 1.0 - (ret_rank / N)  # 排名越高值越接近 1
                offset = 11 + [20, 60].index(period)
                factors_3d[:, i, offset] = top_ratio
        
        # 动量持续性（MOM 信号的自相关性）
        for i in range(N):
            mom_5 = pd.Series(diff(close_all[:, i], 5) / np.maximum(close_all[:, i], 1e-8))
            mom_autocorr = mom_5.rolling(20, min_periods=5).apply(
                lambda x: x.autocorr() if len(x.dropna()) > 2 else 0, raw=False
            ).fillna(0).values
            factors_3d[:, i, 13] = np.nan_to_num(mom_autocorr)
        
        # 信息比率（超额收益 / 跟踪误差）
        for i in range(N):
            ir = np.zeros(T)
            for t in range(60, T):
                excess = ret_all[t-60:t, i] - avg_ret[t-60:t]
                if excess.std() > 0:
                    ir[t] = excess.mean() / excess.std() * np.sqrt(252)
            factors_3d[:, i, 14] = np.nan_to_num(ir)
        
        return np.clip(factors_3d, -5, 5)  # 截断极端值

    # ── 6. 宏观/市场因子 ──
    def _macro_market_factors(self, close_all: np.ndarray) -> np.ndarray:
        """宏观/市场因子（所有标的共享，~10维）"""
        T, N = close_all.shape
        factors = np.zeros((T, 10))
        
        # 1: 等权市场收益率
        market_ret = np.diff(close_all, axis=0, prepend=close_all[0:1]) / np.maximum(close_all, 1e-8)
        factors[:, 0] = market_ret.mean(axis=1)
        
        # 2: 市场宽度（上涨标的占比）
        for t in range(T):
            factors[t, 1] = (market_ret[t] > 0).sum() / N
        
        # 3-5: 市场波动率
        for j, period in enumerate([5, 20, 60]):
            avg_ret = market_ret.mean(axis=1)
            factors[:, 2 + j] = pd.Series(avg_ret).rolling(period, min_periods=2).std().fillna(0).values * np.sqrt(252)
        
        # 6: 市场偏度
        avg_ret = market_ret.mean(axis=1)
        factors[:, 5] = pd.Series(avg_ret).rolling(20, min_periods=3).skew().fillna(0).values
        
        # 7: 最大回撤
        cum_ret = np.cumprod(1 + market_ret.mean(axis=1))
        peak = np.maximum.accumulate(cum_ret)
        factors[:, 6] = (peak - cum_ret) / peak
        
        # 8: 截面离散度（标的之间收益的标准差）
        for t in range(T):
            factors[t, 7] = market_ret[t].std()
        
        # 9: 涨跌比
        for t in range(T):
            up_sum = market_ret[t][market_ret[t] > 0].sum() if (market_ret[t] > 0).any() else 0
            down_sum = np.abs(market_ret[t][market_ret[t] < 0].sum()) if (market_ret[t] < 0).any() else 1e-8
            factors[t, 8] = up_sum / max(down_sum, 1e-8)
        
        # 10: 市场趋势状态（MA20 与 MA60 的交叉信号）
        market_close = close_all.mean(axis=1)
        ma20 = pd.Series(market_close).rolling(20, min_periods=1).mean().values
        ma60 = pd.Series(market_close).rolling(60, min_periods=1).mean().values
        factors[:, 9] = np.tanh((ma20 - ma60) / np.maximum(ma60, 1e-8))
        
        return np.clip(factors, -5, 5)

    # ── 主处理流程 ──
    def compute_features(
        self,
        df: pd.DataFrame,
        close_cols: List[str],
        high_cols: Optional[List[str]] = None,
        low_cols: Optional[List[str]] = None,
        volume_cols: Optional[List[str]] = None,
        amount_cols: Optional[List[str]] = None,
        symbols: Optional[List[str]] = None,
    ) -> np.ndarray:
        """
        主计算入口：对每个标的独立计算因子，合成最终特征张量
        
        Args:
            df: 原始行情 DataFrame，index 为日期
            close_cols: 收盘价列名列表
            symbols: 标的代码列表
        
        Returns:
            ndarray shape=(T, N_ASSETS, FEATURE_DIM)
        """
        if symbols is None:
            symbols = [str(i) for i in range(len(close_cols))]
        N = len(close_cols)
        T = len(df)
        
        # 为每个标的分配因子维度（不含行业轮动和宏观）
        per_asset_factor_dim = 25 + 12 + 8 + 20  # 动量 + 波动率 + 流动性 + 趋势反转 = 65维
        rotation_dim = 15
        macro_dim = 10
        
        # 预留总输出
        all_features = np.zeros((T, N, per_asset_factor_dim + rotation_dim + macro_dim))
        
        # 逐标的计算单标的因子
        for i in range(N):
            close = df[close_cols[i]].values.astype(np.float64)
            high = df[high_cols[i]].values.astype(np.float64) if high_cols and i < len(high_cols) else None
            low = df[low_cols[i]].values.astype(np.float64) if low_cols and i < len(low_cols) else None
            volume = df[volume_cols[i]].values.astype(np.float64) if volume_cols and i < len(volume_cols) else np.ones(T)
            amount = df[amount_cols[i]].values.astype(np.float64) if amount_cols and i < len(amount_cols) else None
            
            # 各因子组
            momentum = self._momentum_factors(close)
            volatility = self._volatility_factors(close, high, low)
            liquidity = self._liquidity_factors(close, volume, amount)
            trend = self._trend_reversal_factors(close, high, low, volume)
            
            # 合并单标的因子
            asset_features = np.column_stack([momentum, volatility, liquidity, trend])
            # NaN 填充
            asset_features = np.nan_to_num(asset_features, nan=0.0, posinf=5.0, neginf=-5.0)
            # 截断
            asset_features = np.clip(asset_features, -5, 5)
            
            all_features[:, i, :per_asset_factor_dim] = asset_features
        
        # 行业轮动因子（截面）
        close_all = np.column_stack([df[c].values for c in close_cols])
        rotation_factors = self._sector_rotation_factors(close_all, symbols)
        all_features[:, :, per_asset_factor_dim:per_asset_factor_dim + rotation_dim] = rotation_factors
        
        # 宏观因子（共享）
        macro_factors = self._macro_market_factors(close_all)
        for i in range(N):
            all_features[:, i, per_asset_factor_dim + rotation_dim:] = macro_factors
        
        logger.info(
            f"特征工程完成 | 标的数={N} | 时间步={T} | "
            f"单标因子={per_asset_factor_dim} | 轮动因子={rotation_dim} | 宏观因子={macro_dim} | "
            f"总维度={all_features.shape[2]}"
        )
        
        return all_features

    def compute_all(
        self,
        close: np.ndarray,
        high: Optional[np.ndarray] = None,
        low: Optional[np.ndarray] = None,
        volume: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """单标的因子计算（供 FeatureEngineer 使用），返回 shape=(T, feature_dim)"""
        T = len(close)
        momentum = self._momentum_factors(close)
        volatility = self._volatility_factors(close, high, low)
        liquidity = self._liquidity_factors(close, volume)
        trend = self._trend_reversal_factors(close, high, low, volume)
        factors = np.column_stack([momentum, volatility, liquidity, trend])
        factors = np.nan_to_num(factors, nan=0.0, posinf=5.0, neginf=-5.0)
        return np.clip(factors, -5, 5)

    def list_factor_names(self) -> list:
        """返回单标的因子名称列表"""
        groups = [("momentum", 20), ("volatility", 12), ("liquidity", 8), ("trend", 20)]
        names = []
        for group, count in groups:
            for i in range(count):
                names.append(f"{group}_{i:02d}")
        return names


# ==================== 纯 NumPy 回退实现（无 TA-Lib 时使用） ====================

def _rsi_numpy(close: np.ndarray, period: int = 14) -> np.ndarray:
    """RSI 计算"""
    delta = np.diff(close, prepend=close[0:1])
    gain = np.maximum(delta, 0)
    loss = -np.minimum(delta, 0)
    
    avg_gain = np.zeros_like(close)
    avg_loss = np.zeros_like(close)
    
    if len(close) >= period:
        avg_gain[period-1] = gain[:period].mean()
        avg_loss[period-1] = loss[:period].mean()
        for t in range(period, len(close)):
            avg_gain[t] = (avg_gain[t-1] * (period - 1) + gain[t]) / period
            avg_loss[t] = (avg_loss[t-1] * (period - 1) + loss[t]) / period
    
    rs = np.divide(avg_gain, avg_loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))
    return np.nan_to_num(rsi, nan=50.0)


def _kdj_numpy(close: np.ndarray, high: np.ndarray, low: np.ndarray,
               period: int = 9, signal_period: int = 3) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """KDJ 计算"""
    T = len(close)
    k = np.full(T, 50.0)
    d = np.full(T, 50.0)
    j = np.full(T, 50.0)
    
    for t in range(period - 1, T):
        hh = high[t - period + 1:t + 1].max()
        ll = low[t - period + 1:t + 1].min()
        rsv = (close[t] - ll) / max(hh - ll, 1e-8) * 100
        if t == period - 1:
            k[t] = rsv
            d[t] = rsv
        else:
            k[t] = 2/3 * k[t-1] + 1/3 * rsv
            d[t] = 2/3 * d[t-1] + 1/3 * k[t]
        j[t] = 3 * k[t] - 2 * d[t]
    
    return k, d, j


def _bollinger_numpy(close: np.ndarray, period: int = 20, nbdev: int = 2) -> Tuple[np.ndarray, np.ndarray]:
    """布林带 %b 和宽度"""
    ma = pd.Series(close).rolling(period, min_periods=1).mean().values
    std = pd.Series(close).rolling(period, min_periods=1).std().fillna(0).values
    upper = ma + nbdev * std
    lower = ma - nbdev * std
    pct_b = (close - lower) / np.maximum(upper - lower, 1e-8)
    bandwidth = (upper - lower) / np.maximum(ma, 1e-8)
    return np.nan_to_num(pct_b, nan=0.5), np.nan_to_num(bandwidth, nan=0.0)


def _atr_numpy(close: np.ndarray, high: np.ndarray, low: np.ndarray, period: int = 14) -> np.ndarray:
    """ATR 计算"""
    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]
    tr = np.maximum(np.maximum(high - low, np.abs(high - prev_close)), np.abs(low - prev_close))
    atr = pd.Series(tr).ewm(span=period, min_periods=1).mean().values
    return atr

def _adx_numpy(close: np.ndarray, period: int = 14) -> np.ndarray:
    """ADX 简化计算"""
    T = len(close)
    adx = np.full(T, 20.0)
    for t in range(period * 2, T):
        pm = np.maximum(close[t] - close[t-1], 0)
        nm = np.maximum(close[t-1] - close[t], 0)
        pm_sum = np.sum(np.maximum(np.diff(close[t-period:t+1]), 0))
        nm_sum = np.sum(np.maximum(-np.diff(close[t-period:t+1]), 0))
        if pm_sum + nm_sum > 1e-8:
            adx[t] = abs(pm_sum - nm_sum) / (pm_sum + nm_sum) * 100
    return adx

def _obv_numpy(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    """OBV 计算"""
    obv = np.zeros_like(close, dtype=float)
    for t in range(1, len(close)):
        if close[t] > close[t-1]:
            obv[t] = obv[t-1] + volume[t]
        elif close[t] < close[t-1]:
            obv[t] = obv[t-1] - volume[t]
        else:
            obv[t] = obv[t-1]
    return obv

def _stochastic_numpy(close: np.ndarray, high: np.ndarray, low: np.ndarray,
                      period: int = 14, signal: int = 3) -> Tuple[np.ndarray, np.ndarray]:
    """随机指标"""
    T = len(close)
    slow_k = np.full(T, 50.0)
    slow_d = np.full(T, 50.0)
    for t in range(period - 1, T):
        hh = high[t - period + 1:t + 1].max()
        ll = low[t - period + 1:t + 1].min()
        slow_k[t] = (close[t] - ll) / max(hh - ll, 1e-8) * 100
    slow_d = pd.Series(slow_k).rolling(signal, min_periods=1).mean().fillna(50.0).values
    return slow_k, slow_d

def _cci_numpy(close: np.ndarray, period: int = 14) -> np.ndarray:
    """CCI 计算"""
    tp = close
    ma = pd.Series(tp).rolling(period, min_periods=1).mean().values
    md = pd.Series(np.abs(tp - ma)).rolling(period, min_periods=1).mean().values
    cci = (tp - ma) / (0.015 * md + 1e-8)
    return cci

def _willr_numpy(close: np.ndarray, period: int = 14) -> np.ndarray:
    """威廉%R"""
    T = len(close)
    willr = np.full(T, -50.0)
    for t in range(period - 1, T):
        hh = close[t - period + 1:t + 1].max()
        ll = close[t - period + 1:t + 1].min()
        willr[t] = (hh - close[t]) / max(hh - ll, 1e-8) * -100
    return willr

def diff(arr: np.ndarray, n: int = 1) -> np.ndarray:
    """安全的 n 阶差分（前面填充 0）"""
    out = np.zeros_like(arr)
    out[n:] = arr[n:] - arr[:-n]
    return out

__all__ = ["FactorEngine", "HAS_TALIB", "FeatureEngineer"]


# ==================== FeatureEngineer 包装器 ====================

class FeatureEngineer:
    """
    FactorEngine 的对外包装类，兼容 train.py 和 strategy.py 的调用接口。

    支持两种初始化方式：
        # 方式1: 传入 lookback
        eng = FeatureEngineer(lookback=60)
        # 方式2: 传入 StrategyConfig 对象
        eng = FeatureEngineer(config=my_config)

    核心方法：
        build_features(df, N)   → pd.DataFrame (新增特征列)
        get_feature_columns(N)  → List[str] (特征列名)
        compute(df, ...)        → np.ndarray (T, feature_dim)
    """

    def __init__(self, lookback: int = 60, config: Optional[Any] = None):
        if config is not None:
            # 从 StrategyConfig 提取参数
            self.lookback = getattr(config, "lookback", 60)
        else:
            self.lookback = lookback
        self._engine = FactorEngine(lookback=self.lookback)
        self._feature_names: list = []
        self._last_N: int = 0
        self._last_feature_cols: List[str] = []

        logger.info(f"FeatureEngineer 初始化 | lookback={self.lookback}")

    # ──────── 核心新增方法（供 train.py / strategy.py 调用）────────

    def build_features(self, df: "pd.DataFrame", N: int = 10) -> "pd.DataFrame":
        """
        对多标的 DataFrame 进行特征工程，返回带有特征列的 DataFrame。

        Args:
            df: 原始数据，列名格式 {close|open|high|low|volume}_{index} 或 {asset_i}/close_i 等
            N: 标的数量

        Returns:
            带有特征列的新 DataFrame（包含原始列 + 特征列）
        """
        result_df = df.copy()
        close_cols = []

        # 自动检测 close 列格式
        for i in range(N):
            candidates = [f"close_{i}", f"asset_{i}"]
            for cand in candidates:
                if cand in df.columns:
                    close_cols.append(cand)
                    break
            else:
                # 如果连 close_i 都没有，尝试直接有索引值列
                alt_cols = [c for c in df.columns if str(i) in c and "close" in c.lower()]
                if alt_cols:
                    close_cols.append(alt_cols[0])
                else:
                    logger.debug(f"标的 {i} 无 close 列，跳过特征计算")
                    close_cols.append(None)

        # 收集有效标的
        valid_cols = [c for c in close_cols if c is not None and c in df.columns]
        if len(valid_cols) == 0:
            logger.warning("无有效价格列，创建占位特征")
            for i in range(90):
                result_df[f"feature_{i}"] = 0.0
            self._last_N = N
            return result_df

        # 对每个标的计算特征
        feature_dim = 0
        all_features = []
        for i in range(N):
            col = close_cols[i] if i < len(close_cols) and close_cols[i] else None
            if col and col in df.columns:
                # 尝试找到对应的 OHLCV 列
                high_col = col.replace("close", "high") if "close" in col else None
                low_col = col.replace("close", "low") if "close" in col else None
                open_col = col.replace("close", "open") if "close" in col else None
                vol_cols = [c for c in df.columns if "volume" in c.lower() and str(i) in c]
                volume_col = vol_cols[0] if vol_cols else None

                close_vals = df[col].values.astype(np.float64)
                high_vals = df[high_col].values.astype(np.float64) if high_col and high_col in df.columns else close_vals
                low_vals = df[low_col].values.astype(np.float64) if low_col and low_col in df.columns else close_vals
                vol_vals = df[volume_col].values.astype(np.float64) if volume_col and volume_col in df.columns else np.ones(len(df))

                asset_features = self._engine.compute_all(
                    close=close_vals,
                    high=high_vals,
                    low=low_vals,
                    volume=vol_vals,
                )  # shape: (T, feature_dim)
            else:
                # 占位：全零特征
                asset_features = np.zeros((len(df), 60))

            all_features.append(asset_features)
            feature_dim = asset_features.shape[1]

        # 展平并添加到 DataFrame
        self._last_feature_cols = []
        for i, asset_feat in enumerate(all_features):
            for j in range(asset_feat.shape[1]):
                col_name = f"f_{i}_{j}"
                result_df[col_name] = asset_feat[:, j]
                self._last_feature_cols.append(col_name)

        self._last_N = N
        logger.info(
            f"build_features 完成 | N={N} 每标特征={feature_dim} "
            f"总特征列={len(self._last_feature_cols)}"
        )
        return result_df

    def get_feature_columns(self, N: int) -> List[str]:
        """
        返回当前特征工程的列名列表。

        Args:
            N: 标的数量

        Returns:
            特征列名列表 ["f_0_0", "f_0_1", ..., "f_9_59"]
        """
        if self._last_feature_cols:
            return list(self._last_feature_cols)
        # 回退：生成标准列名
        n_features_per_asset = 90
        cols = []
        for i in range(N):
            for j in range(n_features_per_asset):
                cols.append(f"f_{i}_{j}")
        return cols

    # ──────── 原有方法（保持向后兼容）────────

    def compute(
        self,
        df: "pd.DataFrame",
        price_col: str = "close",
        volume_col: str = "volume",
    ) -> "np.ndarray":
        """
        从 DataFrame 计算特征。

        Args:
            df: 包含 OHLCV 列的 DataFrame
            price_col: 价格列名
            volume_col: 成交量列名

        Returns:
            np.ndarray shape=(T, feature_dim)
        """
        import numpy as np

        close = df[price_col].values.astype(np.float64)
        volume = df[volume_col].values.astype(np.float64) if volume_col in df.columns else np.ones_like(close)
        high = df.get("high", df[price_col]).values.astype(np.float64)
        low = df.get("low", df[price_col]).values.astype(np.float64)

        features = self._engine.compute_all(
            close=close,
            high=high,
            low=low,
            volume=volume,
        )
        self._feature_names = self._engine.list_factor_names()
        return features

    def get_feature_names(self) -> List[str]:
        """返回单标的特征名称列表"""
        if not self._feature_names:
            return [f"f_{i}" for i in range(90)]
        return list(self._feature_names)
