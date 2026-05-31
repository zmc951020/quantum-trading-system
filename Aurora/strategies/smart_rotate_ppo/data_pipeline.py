#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能标的轮动策略 — 数据管线
=============================
负责：真实数据获取、模拟数据生成、特征工程、时序分割、数据泄露校验

两层设计：
- Stage 1: 合规模拟数据（快速跑通全链路）
- Stage 2: Aurora 四源真实数据对接（yfinance / akshare 自动降级）
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from strategies.smart_rotate_ppo.config import ETF_CODES, ETF_POOL, StrategyConfig

logger = logging.getLogger(__name__)


class DataPipeline:
    """
    数据管线：获取/生成 → 特征工程 → 时序分割 → 校验

    用法:
        pipeline = DataPipeline(cfg)
        df = pipeline.load_or_generate(use_real=True)  # 自动选择真实/模拟
        df = pipeline.build_features(df)
        train, val, test = pipeline.time_series_split(df)
    """

    def __init__(self, cfg: StrategyConfig):
        self.cfg = cfg
        self.N: int = cfg.N
        self.L: int = cfg.lookback

    # ========================================================================
    # 统一入口
    # ========================================================================
    def load_or_generate(self, use_real: Optional[bool] = None) -> pd.DataFrame:
        """
        根据配置自动选择真实数据或模拟数据

        Args:
            use_real: 覆盖配置。None 则使用 cfg.use_real_data

        Returns:
            包含原始价格列 (close_0~close_9) 和 date 的 DataFrame
        """
        if use_real is None:
            use_real = self.cfg.use_real_data

        if use_real:
            df = self.fetch_real_data()
            if df is not None and len(df) >= self.L + 30:
                logger.info(f"真实数据获取成功: {len(df)} 行, {df.index[0]} ~ {df.index[-1]}")
                return df
            logger.warning("真实数据获取失败或不足，回退到模拟数据")

        logger.info("使用模拟数据")
        return self.generate_synthetic_data()

    # ========================================================================
    # 真实数据获取（多源降级）
    # ========================================================================
    def fetch_real_data(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Optional[pd.DataFrame]:
        """
        从真实数据源获取10只ETF历史行情，自动降级

        降级链: yfinance → akshare → Aurora DataProvider → 返回 None 触发模拟回退

        Args:
            start_date: 起始日期，默认 cfg.data_start_date
            end_date: 截止日期，默认 cfg.data_end_date

        Returns:
            包含 close_0~close_9 + date 的 DataFrame，失败返回 None
        """
        start = start_date or self.cfg.data_start_date
        end = end_date or self.cfg.data_end_date

        # 构建 yfinance 代码映射
        yf_map = self._build_yfinance_code_map()

        # ── 尝试 1: yfinance ──
        try:
            df = self._fetch_yfinance(yf_map, start, end)
            if df is not None and len(df) > 0:
                logger.info(f"✅ 数据源 yfinance 成功: {len(df)} 行")
                return df
        except Exception as e:
            logger.warning(f"yfinance 获取失败: {e}")

        # ── 尝试 2: akshare ──
        try:
            df = self._fetch_akshare(start, end)
            if df is not None and len(df) > 0:
                logger.info(f"✅ 数据源 akshare 成功: {len(df)} 行")
                return df
        except Exception as e:
            logger.warning(f"akshare 获取失败: {e}")

        # ── 尝试 3: Aurora DataProvider ──
        try:
            df = self._fetch_aurora_provider(start, end)
            if df is not None and len(df) > 0:
                logger.info(f"✅ 数据源 Aurora DataProvider 成功: {len(df)} 行")
                return df
        except Exception as e:
            logger.warning(f"Aurora DataProvider 获取失败: {e}")

        return None

    def _build_yfinance_code_map(self) -> List[str]:
        """
        将 ETF 代码映射为 yfinance 格式

        ETF_POOL 中已包含 exchange 字段：
        - SH → .SS (如 510300.SS)
        - SZ → .SZ (如 159915.SZ)
        """
        codes = []
        for etf in ETF_POOL:
            code = etf["code"]
            exchange = etf.get("exchange", "SH")
            suffix = ".SS" if exchange == "SH" else ".SZ"
            codes.append(f"{code}{suffix}")
        return codes

    def _fetch_yfinance(
        self, tickers: List[str], start: str, end: str
    ) -> Optional[pd.DataFrame]:
        """使用 yfinance 批量获取历史数据"""
        import yfinance as yf
        logger.info(f"正在从 yfinance 获取 {len(tickers)} 只 ETF: {start} ~ {end}")

        data = yf.download(
            tickers=tickers,
            start=start,
            end=end,
            auto_adjust=True,       # 自动复权
            progress=False,
            group_by="ticker",
        )

        if data is None or data.empty:
            return None

        # 处理可能的多级列（当多 ticker 时 yfinance 返回 MultiIndex columns）
        return self._extract_close_prices(data, tickers)

    def _extract_close_prices(
        self, data: pd.DataFrame, tickers_order: List[str]
    ) -> pd.DataFrame:
        """从 yfinance 下载结果提取收盘价并标准化为 close_0~close_9"""
        df_out = pd.DataFrame()

        if isinstance(data.columns, pd.MultiIndex):
            # 多 ticker: columns = MultiIndex [(Close, ticker1), ...]
            for i, tk in enumerate(tickers_order):
                if (tk,) in data.columns or ("Close", tk) in data.columns or tk in data.columns:
                    try:
                        col = data[("Close", tk)] if ("Close", tk) in data.columns else data[tk]
                        df_out[f"close_{i}"] = col.astype(float)
                    except (KeyError, ValueError):
                        df_out[f"close_{i}"] = np.nan
        else:
            # 单 ticker 或单级列
            # 尝试匹配：Close, Adj Close
            close_cols = [c for c in data.columns if "Close" in str(c) or "close" in str(c).lower()]
            for i, tk in enumerate(tickers_order):
                # 在单级列中找对应的列
                matched = [c for c in close_cols if tk.replace(".SS", "").replace(".SZ", "") in str(c)]
                if matched:
                    df_out[f"close_{i}"] = data[matched[0]].astype(float)
                else:
                    df_out[f"close_{i}"] = np.nan

        # 日期处理
        if isinstance(data.index, pd.DatetimeIndex):
            df_out["date"] = data.index
        else:
            df_out["date"] = pd.to_datetime(data.index)

        # 前向填充缺失（非交易日），丢弃全 NaN 行
        df_out = df_out.ffill().dropna(subset=[f"close_{i}" for i in range(len(tickers_order))], how="all")
        df_out = df_out.reset_index(drop=True)

        # 基本数据质量校验
        n_tickers = len(tickers_order)
        min_valid_ratio = 0.5  # 至少 50% 的标的有数据
        valid_count = sum(1 for i in range(n_tickers)
                          if f"close_{i}" in df_out.columns and df_out[f"close_{i}"].notna().sum() > 10)
        if valid_count < n_tickers * min_valid_ratio:
            logger.warning(f"yfinance 数据质量不足: {valid_count}/{n_tickers} 标的有效")
            return None

        logger.info(f"yfinance 提取完成: {len(df_out)} 行, {valid_count}/{n_tickers} 标的")
        return df_out

    def _fetch_akshare(self, start: str, end: str) -> Optional[pd.DataFrame]:
        """使用 akshare 逐只获取 ETF 数据（批量构建避免 DataFrame 碎片化）"""
        import akshare as ak
        logger.info(f"正在从 akshare 获取 {len(ETF_POOL)} 只 ETF: {start} ~ {end}")

        columns_data: Dict[str, np.ndarray] = {}
        date_col: Optional[pd.Series] = None
        max_len: int = 0
        success_count = 0

        for i, etf in enumerate(ETF_POOL):
            code = etf["code"]
            name = etf["name"]
            col_name = f"close_{i}"
            try:
                df_etf = ak.fund_etf_hist_em(
                    symbol=code,
                    period="daily",
                    start_date=start.replace("-", ""),
                    end_date=end.replace("-", ""),
                    adjust="qfq",
                )
                if df_etf is not None and not df_etf.empty and "收盘" in df_etf.columns:
                    series = pd.to_numeric(df_etf["收盘"], errors="coerce").values
                    n = len(series)
                    if n > max_len:
                        max_len = n
                    columns_data[col_name] = series
                    if i == 0:
                        date_col = pd.to_datetime(df_etf["日期"])
                    success_count += 1
                    logger.debug(f"  ✅ {name}({code})")
                else:
                    logger.debug(f"  ⚠️ {name}({code}): 无数据")
            except Exception as e:
                logger.debug(f"  ❌ {name}({code}): {e}")

        if success_count < len(ETF_POOL) * 0.5:
            logger.warning(f"akshare 数据质量不足: {success_count}/{len(ETF_POOL)} 标的")
            return None

        # 批量构建 DataFrame：对齐各列长度，缺失列填 NaN
        aligned: Dict[str, np.ndarray] = {}
        for name, values in columns_data.items():
            if len(values) < max_len:
                padded = np.full(max_len, np.nan, dtype=np.float64)
                padded[-len(values):] = values  # 尾部对齐
                aligned[name] = padded
            else:
                aligned[name] = values

        # 未获取到的标的填全 NaN
        for i in range(len(ETF_POOL)):
            col_name = f"close_{i}"
            if col_name not in aligned:
                aligned[col_name] = np.full(max_len, np.nan, dtype=np.float64)

        # 统一构建 date 列
        if date_col is not None and len(date_col) < max_len:
            aligned_date = pd.Series([pd.NaT] * max_len)
            aligned_date.iloc[-len(date_col):] = date_col.values
            date_col = aligned_date
        elif date_col is None:
            date_col = pd.Series([pd.NaT] * max_len)

        df_out = pd.DataFrame(aligned)
        df_out["date"] = date_col.values
        df_out = df_out.ffill().reset_index(drop=True)

        logger.info(f"akshare 提取完成: {len(df_out)} 行, {success_count}/{len(ETF_POOL)} 标的")
        return df_out

    def _fetch_aurora_provider(self, start: str, end: str) -> Optional[pd.DataFrame]:
        """
        使用 Aurora 内置 DataProvider（多源数据管理器）

        通过 data_provider.fetch_from_source 调用 multi_data_source.get_historical
        """
        try:
            from data.data_provider import DataProvider
            dp = DataProvider()

            # 估算所需天数
            try:
                days_needed = max(
                    365,
                    (pd.Timestamp(end) - pd.Timestamp(start)).days + 30,
                )
            except Exception:
                days_needed = 3650  # 10年兜底

            all_data = {}
            dates = None

            for i, etf in enumerate(ETF_POOL):
                code = etf["code"]
                try:
                    df_single = dp.fetch_from_source(
                        symbol=code,
                        data_type="historical",
                        days=days_needed,
                    )
                    if df_single is not None and not df_single.empty and "close" in df_single.columns:
                        all_data[f"close_{i}"] = df_single["close"].astype(float)
                        if dates is None and isinstance(df_single.index, pd.DatetimeIndex):
                            dates = df_single.index
                    else:
                        all_data[f"close_{i}"] = np.nan
                except Exception as e:
                    logger.debug(f"  ⚠️ {code} Aurora获取失败: {e}")
                    all_data[f"close_{i}"] = np.nan

            if not all_data:
                return None

            df_out = pd.DataFrame(all_data)
            if dates is None:
                try:
                    df_out["date"] = pd.date_range(start=start, periods=len(df_out), freq="B")
                except Exception:
                    df_out["date"] = pd.date_range(start="2020-01-01", periods=len(df_out), freq="B")
            else:
                df_out["date"] = dates
            df_out = df_out.ffill()
            valid_mask = df_out[[c for c in all_data.keys()]].notna().any(axis=1)
            df_out = df_out[valid_mask].reset_index(drop=True)
            return df_out
        except ImportError:
            logger.debug("Aurora DataProvider 模块不可用")
            return None
        except Exception as e:
            logger.warning(f"Aurora DataProvider 异常: {e}")
            return None

    # ========================================================================
    # 模拟数据生成
    # ========================================================================
    def generate_synthetic_data(self) -> pd.DataFrame:
        """
        生成模拟行情数据

        Returns:
            DataFrame 含 close_0~close_9 + date，长度 cfg.synthetic_data_length
        """
        n = self.cfg.synthetic_data_length
        N = self.N
        rng = np.random.RandomState(self.cfg.random_seed)

        # 对数正态价格路径（10只ETF各自独立）
        mu = 0.0003  # 日均收益 3bp
        sigma = 0.015  # 日波动 1.5%
        shocks = rng.randn(n, N) * sigma + mu
        log_returns = np.cumsum(shocks, axis=0)
        prices = 10.0 * np.exp(log_returns)  # 起始价格 10 元

        # 构建 DataFrame
        cols = {f"close_{i}": prices[:, i] for i in range(N)}
        cols["date"] = pd.date_range(
            start=self.cfg.data_start_date,
            periods=n,
            freq="B",  # 交易日
        )
        df = pd.DataFrame(cols)

        # 质量校验
        self._validate_synthetic(df)
        logger.info(f"模拟数据生成完成: {len(df)} 行 × {N} 标的")
        return df

    def _validate_synthetic(self, df: pd.DataFrame) -> None:
        """模拟数据基本质量检查"""
        assert len(df) > 0, "数据为空"
        for i in range(self.N):
            col = f"close_{i}"
            assert col in df.columns, f"缺少列 {col}"
            assert df[col].notna().sum() > self.L, (
                f"{col} 有效数据不足: {df[col].notna().sum()} < {self.L}"
            )
            assert (df[col] > 0).all(), f"{col} 包含非正价格"

    # ========================================================================
    # 特征工程（dict 批量构建，零 DataFrame 碎片化）
    # ========================================================================
    def build_features(
        self, df: pd.DataFrame
    ) -> Tuple[pd.DataFrame, List[str], List[str]]:
        """
        从原始价格数据构建每标的16维技术指标

        使用 dict 批量收集所有新列，最后一次性 pd.concat，
        彻底消除 PerformanceWarning: DataFrame is highly fragmented。

        Args:
            df: 含 close_0~close_9 + date 的 DataFrame

        Returns:
            (df_features, feature_cols, return_cols):
        """
        new_cols: Dict[str, np.ndarray] = {}

        # ── 收益率列 ──
        return_cols: List[str] = []
        for i in range(self.N):
            col_name = f"return_{i}"
            new_cols[col_name] = df[f"close_{i}"].pct_change().fillna(0.0).values
            return_cols.append(col_name)

        # ── 每标的 16 维技术指标 ──
        feature_cols: List[str] = []
        for i in range(self.N):
            close = df[f"close_{i}"]
            close_vals = close.values
            ret_vals = new_cols[f"return_{i}"]
            prefix = f"f{i}_"

            # 1. 归一化价格 (MinMax 20日滚动)
            col = prefix + "norm_price"
            pmin = close.rolling(20, min_periods=5).min().values
            pmax = close.rolling(20, min_periods=5).max().values
            denom = pmax - pmin
            new_cols[col] = np.where(
                denom > 0, (close_vals - pmin) / (denom + 1e-8), 0.5
            )
            feature_cols.append(col)

            # 2. 收益率
            col = prefix + "return_1d"
            new_cols[col] = ret_vals
            feature_cols.append(col)

            # 3. RSI(14)
            col = prefix + "rsi_14"
            new_cols[col] = self._compute_rsi(close, 14).values
            feature_cols.append(col)

            # 4. MACD 柱
            col = prefix + "macd_hist"
            new_cols[col] = self._compute_macd_hist(close).values
            feature_cols.append(col)

            # 5. 布林带位置
            col = prefix + "bb_position"
            new_cols[col] = self._compute_bb_position(close, 20).values
            feature_cols.append(col)

            # 6. ATR(14)
            col = prefix + "atr_14"
            new_cols[col] = self._compute_atr_ratio(df, i, 14).values
            feature_cols.append(col)

            # 7. 成交量比（用价格波动代理）
            col = prefix + "volume_ratio"
            diff_vals = np.abs(np.diff(close_vals, prepend=close_vals[0]))
            vol_ma = pd.Series(diff_vals).rolling(20, min_periods=5).mean().values
            new_cols[col] = np.where(vol_ma > 0, diff_vals / (vol_ma + 1e-8), 1.0)
            feature_cols.append(col)

            # 8. 5日动量
            col = prefix + "momentum_5"
            new_cols[col] = close.pct_change(5).fillna(0.0).values
            feature_cols.append(col)

            # 9. 20日动量
            col = prefix + "momentum_20"
            new_cols[col] = close.pct_change(20).fillna(0.0).values
            feature_cols.append(col)

            # 10. 20日波动率
            col = prefix + "volatility_20"
            vol = pd.Series(ret_vals).rolling(20, min_periods=5).std().fillna(0.0).values
            new_cols[col] = vol
            feature_cols.append(col)

            # 11. 换手率代理
            col = prefix + "turnover_proxy"
            new_cols[col] = self._compute_turnover_proxy(close).values
            feature_cols.append(col)

            # 12. ADX(14)
            col = prefix + "adx_14"
            new_cols[col] = self._compute_adx(df, i, close, 14).values
            feature_cols.append(col)

            # 13. OBV 变化率
            col = prefix + "obv_change"
            new_cols[col] = self._compute_obv_change(close).values
            feature_cols.append(col)

            # 14. 威廉 %R
            col = prefix + "williams_r"
            new_cols[col] = self._compute_williams_r(close, 14).values
            feature_cols.append(col)

            # 15. CCI(20)
            col = prefix + "cci_20"
            new_cols[col] = self._compute_cci(close, 20).values
            feature_cols.append(col)

            # 16. MFI(14)（价格代理版）
            col = prefix + "mfi_14"
            new_cols[col] = self._compute_mfi_proxy(close, 14).values
            feature_cols.append(col)

        # ── 一次性拼接：保留 date 列 + 所有新特征 ──
        feature_df = pd.DataFrame(new_cols, index=df.index)
        # 保留非 close 的原始列（date），丢弃冗余的 close_*
        keep_cols = [c for c in df.columns if not c.startswith("close_")]
        result = pd.concat([df[keep_cols], feature_df], axis=1)

        # 丢弃 NaN（滚动窗口产生的）
        result = result.dropna(subset=feature_cols).reset_index(drop=True)

        logger.info(
            f"特征工程完成: {len(result)} 行 × {len(feature_cols)} 特征"
        )
        return result, feature_cols, return_cols

    # ========================================================================
    # 技术指标计算
    # ========================================================================
    @staticmethod
    def _compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(period, min_periods=period).mean()
        avg_loss = loss.rolling(period, min_periods=period).mean()
        rs = avg_gain / (avg_loss + 1e-8)
        return 100.0 - 100.0 / (1.0 + rs)

    @staticmethod
    def _compute_macd_hist(close: pd.Series) -> pd.Series:
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        return macd - signal

    @staticmethod
    def _compute_bb_position(close: pd.Series, period: int = 20) -> pd.Series:
        ma = close.rolling(period, min_periods=period).mean()
        std = close.rolling(period, min_periods=period).std()
        denom = 4.0 * std + 1e-8
        return (close - ma) / denom

    @staticmethod
    def _compute_atr_ratio(df: pd.DataFrame, asset_idx: int, period: int = 14) -> pd.Series:
        close = df[f"close_{asset_idx}"]
        high = close.rolling(2, min_periods=1).max()
        low = close.rolling(2, min_periods=1).min()
        tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(period, min_periods=period).mean()
        return atr / (close + 1e-8)

    @staticmethod
    def _compute_turnover_proxy(close: pd.Series) -> pd.Series:
        vol = close.diff().abs()
        vol_ma = vol.rolling(20, min_periods=5).mean()
        # 返回 pd.Series（保持与其他 _compute_* 方法一致），避免 ndarray→.values 报错
        return pd.Series(
            np.where(vol_ma > 0, vol / (vol_ma + 1e-8), 1.0),
            index=close.index,
        )

    @staticmethod
    def _compute_adx(df: pd.DataFrame, asset_idx: int, close: pd.Series, period: int = 14) -> pd.Series:
        """简化 ADX 计算（仅用价格）"""
        high = close.rolling(2, min_periods=1).max()
        low = close.rolling(2, min_periods=1).min()
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ], axis=1).max(axis=1)
        plus_dm = high.diff().clip(lower=0)
        minus_dm = (-low.diff()).clip(lower=0)
        atr = tr.rolling(period, min_periods=period).mean()
        plus_di = 100.0 * plus_dm.rolling(period, min_periods=period).mean() / (atr + 1e-8)
        minus_di = 100.0 * minus_dm.rolling(period, min_periods=period).mean() / (atr + 1e-8)
        dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-8)
        return dx.rolling(period, min_periods=period).mean()

    @staticmethod
    def _compute_obv_change(close: pd.Series) -> pd.Series:
        direction = np.sign(close.diff().fillna(0))
        obv = direction.cumsum()
        return obv.pct_change(5).fillna(0.0)

    @staticmethod
    def _compute_williams_r(close: pd.Series, period: int = 14) -> pd.Series:
        hh = close.rolling(period, min_periods=period).max()
        ll = close.rolling(period, min_periods=period).min()
        return -100.0 * (hh - close) / (hh - ll + 1e-8)

    @staticmethod
    def _compute_cci(close: pd.Series, period: int = 20) -> pd.Series:
        tp = close  # 无OHLC时用收盘价代理典型价格
        ma = tp.rolling(period, min_periods=period).mean()
        mad = tp.rolling(period, min_periods=period).apply(
            lambda x: np.mean(np.abs(x - np.mean(x))), raw=True
        )
        return (tp - ma) / (0.015 * mad + 1e-8)

    @staticmethod
    def _compute_mfi_proxy(close: pd.Series, period: int = 14) -> pd.Series:
        """MFI 代理版本（无成交量时的价格动量代理）"""
        tp = close
        tp_change = tp.diff()
        pos_flow = tp_change.clip(lower=0).rolling(period, min_periods=period).sum()
        neg_flow = (-tp_change.clip(upper=0)).rolling(period, min_periods=period).sum()
        mfr = pos_flow / (neg_flow + 1e-8)
        return 100.0 - 100.0 / (1.0 + mfr)

    # ========================================================================
    # 时序分割
    # ========================================================================
    def time_series_split(
        self, df: pd.DataFrame
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        时序分割（避免未来信息泄露）

        Returns:
            (train_df, val_df, test_df)
        """
        n = len(df)
        train_end = int(n * self.cfg.train_ratio)
        val_end = int(n * (self.cfg.train_ratio + self.cfg.val_ratio))

        train_df = df.iloc[:train_end].reset_index(drop=True)
        val_df = df.iloc[train_end:val_end].reset_index(drop=True)
        test_df = df.iloc[val_end:].reset_index(drop=True)

        # 防泄露校验
        if len(val_df) > 0 and len(train_df) > 0:
            assert train_df["date"].max() <= pd.Timestamp(val_df["date"].min()), (
                "数据泄露: 训练集与验证集时间重叠"
            )
        if len(test_df) > 0 and len(val_df) > 0:
            assert val_df["date"].max() <= pd.Timestamp(test_df["date"].min()), (
                "数据泄露: 验证集与测试集时间重叠"
            )

        logger.info(
            f"数据分割: 训练 {len(train_df)} | 验证 {len(val_df)} | 测试 {len(test_df)}"
        )
        return train_df, val_df, test_df

    # ========================================================================
    # 数据摘要
    # ========================================================================
    def summarize(self, df: pd.DataFrame, feature_cols: List[str]) -> dict:
        """快速数据摘要"""
        return {
            "rows": len(df),
            "features": len(feature_cols),
            "start_date": str(df["date"].min()) if "date" in df.columns else "N/A",
            "end_date": str(df["date"].max()) if "date" in df.columns else "N/A",
            "nan_ratio": round(df[feature_cols].isna().mean().mean(), 4),
            "price_range": {
                f"ETF_{i}": f"{df[f'close_{i}'].min():.2f} ~ {df[f'close_{i}'].max():.2f}"
                for i in range(self.N)
                if f"close_{i}" in df.columns
            },
        }