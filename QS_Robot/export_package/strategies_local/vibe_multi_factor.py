"""多因子选股引擎 — 因子标准化/缩尾/组合排名，纯pandas实现，适配A股"""
from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple


AVAILABLE_FACTORS = ["momentum", "volatility", "value", "quality", "size",
                     "turnover", "reversal", "liquidity"]


class SignalEngine:
    """多因子选股信号引擎

    参数:
        factors: 因子列表
        weighting: 'equal'/'ic' 加权方式
        top_quantile: 做多分位数阈值
        bottom_quantile: 做空分位数阈值
    """

    def __init__(self, factors: List[str] | None = None,
                 weighting: str = "equal", top_quantile: float = 0.2,
                 bottom_quantile: float = 0.8):
        self.factors = factors or AVAILABLE_FACTORS
        self.weighting = weighting
        self.top_quantile = top_quantile
        self.bottom_quantile = bottom_quantile
        self._factor_weights: Dict[str, float] = {}

    def _standardize(self, series: pd.Series) -> pd.Series:
        """Z-score标准化"""
        std = series.std()
        if std is None or std == 0:
            return pd.Series(0.0, index=series.index)
        return (series - series.mean()) / std

    def _winsorize(self, series: pd.Series, limits: Tuple[float, float] = (0.01, 0.99)) -> pd.Series:
        """极值缩尾"""
        lo, hi = series.quantile(limits[0]), series.quantile(limits[1])
        return series.clip(lo, hi)

    def _calc_factor_scores(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算各因子得分"""
        close = df["close"].astype(float)
        volume = df["volume"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        scores = pd.DataFrame(index=df.index)

        if "momentum" in self.factors:
            scores["momentum"] = close.pct_change(20)
        if "volatility" in self.factors:
            scores["volatility"] = -close.pct_change().rolling(20).std()
        if "value" in self.factors:
            scores["value"] = -close.pct_change(60)
        if "quality" in self.factors:
            ret_std = close.pct_change().rolling(20).std()
            ret_mean = close.pct_change().rolling(20).mean()
            scores["quality"] = ret_mean / (ret_std + 1e-10)
        if "size" in self.factors:
            atr = np.maximum(high - low, abs(high - close.shift()))
            scores["size"] = -(atr.rolling(14).mean() / close)
        if "turnover" in self.factors:
            volume_ratio = volume / volume.rolling(20).mean()
            scores["turnover"] = volume_ratio
        if "reversal" in self.factors:
            scores["reversal"] = -close.pct_change(5)
        if "liquidity" in self.factors:
            daily_ret = close.pct_change()
            amihud = (daily_ret.abs() / (volume + 1e-10)).rolling(20).mean()
            scores["liquidity"] = -amihud
        return scores

    def _calc_ic_weights(self, factor_scores: pd.DataFrame, close: pd.Series) -> pd.DataFrame:
        """计算因果 Rank IC 加权：每个时点只用已实现收益（无前视偏差）

        旧实现用"未来收益"（对收益序列做负向位移）并对全序列取 IC 均值，
        导致 t 时刻的信号用到了 t 之后的收益信息（前视）。新实现：
        - 因子分数在 t-1 及之前已知，对应收益用 t 当日及之前已实现数据；
        - 每个时点的权重 = 截至该时点的 expanding IC 均值，绝不含未来数据。
        返回 DataFrame：行=时点，列=因子，值=该时点使用的权重。
        """
        ret = close.pct_change()  # ret[t]: t 收盘后已实现的当日收益
        n = len(factor_scores)
        ic_frames = {}
        for col in factor_scores.columns:
            ics = pd.Series(np.nan, index=factor_scores.index)
            for i in range(21, n):
                # 因子窗口: [i-21, i-1) = t-20..t-1（时点 t-1 及之前已知）
                window = factor_scores[col].iloc[i - 21:i - 1]
                # 收益窗口: [i-20, i) = t-19..t（均已实现，不含未来）
                window_ret = ret.iloc[i - 20:i]
                if window.std() > 0 and window_ret.std() > 0:
                    ics.iloc[i] = window.rank().corr(window_ret.rank())
            ic_frames[col] = ics
        ic_df = pd.DataFrame(ic_frames)
        # 因果权重：expanding 均值（只用截至当前时点的 IC），按行归一化
        cum_ic = ic_df.expanding(min_periods=5).mean().abs()
        row_sum = cum_ic.sum(axis=1)
        weights = cum_ic.div(row_sum.replace(0, np.nan), axis=0)
        weights = weights.fillna(1.0 / ic_df.shape[1])  # 前期数据不足时等权
        return weights

    def _combine_factors(self, factor_scores: pd.DataFrame, close: pd.Series | None = None) -> pd.Series:
        """等权或 IC 加权组合因子得分（IC 权重为逐时点因果权重，无前视）"""
        clean = factor_scores.replace([np.inf, -np.inf], np.nan).dropna(how="all")
        processed = pd.DataFrame(index=clean.index)
        for col in clean.columns:
            processed[col] = self._standardize(self._winsorize(clean[col]))

        ncols = len(processed.columns)
        if ncols == 0:
            return pd.Series(0.0, index=processed.index)

        weights_df = None
        if self.weighting == "ic" and close is not None and len(processed) > 21:
            weights_df = self._calc_ic_weights(processed, close)

        result = pd.Series(0.0, index=processed.index)
        for col in processed.columns:
            w = weights_df[col] if weights_df is not None else 1.0 / ncols
            result += processed[col].fillna(0) * w

        if weights_df is not None:
            self._factor_weights = weights_df.iloc[-1].to_dict()
        else:
            self._factor_weights = {c: 1.0 / ncols for c in processed.columns}
        return result

    def _dynamic_quantile(self, close: pd.Series) -> float:
        """根据市场波动率动态调整top_quantile"""
        daily_ret = close.pct_change().dropna()
        if len(daily_ret) < 20:
            return self.top_quantile
        vol = daily_ret.rolling(20).std().iloc[-1]
        if pd.isna(vol):
            return self.top_quantile
        if vol > 0.02:
            return 0.10
        if vol >= 0.01:
            return 0.20
        return 0.30

    def generate(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        """多因子排名信号：1=前20%做多, -1=后20%做空, 0=中间"""
        close = df["close"].astype(float)
        scores = self._calc_factor_scores(df)
        combined = self._combine_factors(scores, close)
        signal = pd.Series(0, index=df.index)
        common_idx = combined.index.intersection(signal.index)
        if len(common_idx) < 10:
            return {"signal": signal}
        c = combined.loc[common_idx]
        top_q = self._dynamic_quantile(close)
        top_thresh = c.quantile(1 - top_q)
        bottom_thresh = c.quantile(self.bottom_quantile)
        if pd.notna(top_thresh):
            top_mask = c[c >= top_thresh].index
            signal.loc[top_mask] = 1
        if pd.notna(bottom_thresh):
            bottom_mask = c[c <= bottom_thresh].index
            signal.loc[bottom_mask] = -1
        return {"signal": signal}

    def get_param_space(self) -> Dict[str, list]:
        """返回因子权重搜索空间 + IC加权窗口 + 分位数阈值"""
        space = {}
        for f in AVAILABLE_FACTORS:
            space[f"weight_{f}"] = [round(x, 2) for x in np.arange(0.0, 0.51, 0.05)]
        space["ic_window"] = [10, 20, 30, 40, 50, 60]
        space["top_quantile"] = [round(x, 2) for x in np.arange(0.05, 0.41, 0.05)]
        space["bottom_quantile"] = [round(x, 2) for x in np.arange(0.60, 0.96, 0.05)]
        space["winsorize_lo"] = [0.0, 0.01, 0.02, 0.03, 0.05]
        space["winsorize_hi"] = [0.95, 0.97, 0.98, 0.99, 1.0]
        return space

    def get_adaptive_params(self, df: pd.DataFrame) -> Dict[str, float | int]:
        """根据市场状态动态调整因子权重和分位数阈值"""
        close = df["close"].astype(float)
        daily_ret = close.pct_change().dropna()
        if len(daily_ret) < 20:
            return {"top_quantile": self.top_quantile, "bottom_quantile": self.bottom_quantile,
                    "ic_window": 20, "weighting": self.weighting,
                    "winsorize_lo": 0.01, "winsorize_hi": 0.99}

        vol = daily_ret.rolling(20).std().iloc[-1]
        if pd.isna(vol):
            vol = daily_ret.std()

        trend = close.iloc[-1] / close.iloc[-20] - 1 if len(close) >= 20 else 0.0

        if vol > 0.03:
            return {"top_quantile": 0.10, "bottom_quantile": 0.90, "ic_window": 10,
                    "weighting": "ic", "winsorize_lo": 0.02, "winsorize_hi": 0.98}
        if vol > 0.02:
            return {"top_quantile": 0.15, "bottom_quantile": 0.85, "ic_window": 20,
                    "weighting": "ic" if abs(trend) > 0.05 else "equal",
                    "winsorize_lo": 0.01, "winsorize_hi": 0.99}
        if vol > 0.01:
            return {"top_quantile": 0.20, "bottom_quantile": 0.80, "ic_window": 30,
                    "weighting": "equal", "winsorize_lo": 0.01, "winsorize_hi": 0.99}
        return {"top_quantile": 0.30, "bottom_quantile": 0.70, "ic_window": 40,
                "weighting": "equal", "winsorize_lo": 0.0, "winsorize_hi": 1.0}

    def apply_adaptive_params(self, params: Dict[str, float | int]) -> None:
        """应用自适应参数到当前实例"""
        self.top_quantile = float(params.get("top_quantile", self.top_quantile))
        self.bottom_quantile = float(params.get("bottom_quantile", self.bottom_quantile))
        self.weighting = str(params.get("weighting", self.weighting))
        self.ic_window = int(params.get("ic_window", 20))
        self.winsorize_lo = float(params.get("winsorize_lo", 0.01))
        self.winsorize_hi = float(params.get("winsorize_hi", 0.99))


if __name__ == "__main__":
    import time
    try:
        import akshare as ak
    except ImportError:
        print("请先安装 akshare: pip install akshare")
        raise SystemExit(1)

    stocks = ["000001", "000002", "000333", "000651", "000858",
              "600036", "600519", "600887", "601318", "601888"]
    print(f"获取 {len(stocks)} 只A股日线数据...")

    all_dfs = {}
    for sym in stocks:
        for attempt in range(3):
            try:
                raw = ak.stock_zh_a_hist(symbol=sym, period="daily",
                                         start_date="20240101", end_date="20250801",
                                         adjust="qfq")
                raw = raw.rename(columns={"日期": "date", "开盘": "open",
                                          "收盘": "close", "最高": "high",
                                          "最低": "low", "成交量": "volume"})
                df = raw[["date", "open", "high", "low", "close", "volume"]].copy()
                for col in ["open", "high", "low", "close", "volume"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                df = df.dropna().sort_values("date").reset_index(drop=True)
                if len(df) >= 100:
                    all_dfs[sym] = df.tail(250)
                break
            except Exception as e:
                if attempt < 2:
                    time.sleep(2)
                else:
                    print(f"  {sym} 获取失败: {e}")

    # 降级：使用指数数据测试
    if len(all_dfs) < 3:
        print("个股API受限，降级使用指数数据测试...")
        indices = [("000300", "sh"), ("000905", "sh"), ("000016", "sh")]
        for code, prefix in indices:
            try:
                raw = ak.stock_zh_index_daily(symbol=f"{prefix}{code}")
                raw = raw.rename(columns={"date": "date", "open": "open",
                                          "high": "high", "low": "low",
                                          "close": "close", "volume": "volume"})
                df = raw[["date", "open", "high", "low", "close", "volume"]].copy()
                for col in ["open", "high", "low", "close", "volume"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                df = df.dropna().sort_values("date").reset_index(drop=True)
                all_dfs[f"指数{code}"] = df.tail(500)
                time.sleep(1)
            except Exception as e:
                print(f"  指数{code} 获取失败: {e}")

    print(f"成功获取 {len(all_dfs)} 只标的 data")

    if len(all_dfs) == 0:
        print("无法获取任何数据，退出")
        raise SystemExit(1)

    engine = SignalEngine(factors=["momentum", "volatility", "value", "quality", "size"],
                          weighting="equal", top_quantile=0.2, bottom_quantile=0.8)
    results = {}
    for sym, df in all_dfs.items():
        s = engine.generate(df)["signal"]
        last_sig = int(s.iloc[-1])
        sig_text = {1: "做多", -1: "做空", 0: "观望"}[last_sig]
        results[sym] = {"signal": last_sig, "text": sig_text,
                        "close": float(df.iloc[-1]["close"]),
                        "date": str(df.iloc[-1]["date"])}
        print(f"  {sym}: date={results[sym]['date']}, "
              f"close={results[sym]['close']:.2f}, signal={last_sig} ({sig_text})")

    buy_codes = [k for k, v in results.items() if v["signal"] == 1]
    sell_codes = [k for k, v in results.items() if v["signal"] == -1]
    print(f"\n做多标的: {buy_codes}")
    print(f"做空标的: {sell_codes}")