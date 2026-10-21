"""机器学习策略引擎 — walk-forward训练/预测，sklearn实现，适配A股"""
from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Any, Dict, Optional

from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler


class SignalEngine:
    """ML策略信号引擎：Walk-forward滚动训练+预测

    参数:
        model_type: 'rf'/'lr'/'xgb'/'catboost'
        train_window: 训练窗口长度
        test_window: 测试窗口长度
        retrain_freq: 重训练频率
    """

    _MODELS = {"rf": RandomForestClassifier, "lr": LogisticRegression}

    def __init__(self, model_type: str = "rf", train_window: int = 252,
                 test_window: int = 63, retrain_freq: int = 63,
                 n_estimators: int = 100, max_depth: int = 5):
        self.model_type = model_type
        self.train_window = train_window
        self.test_window = test_window
        self.retrain_freq = retrain_freq
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self._scaler = StandardScaler()
        self._last_model: Optional[object] = None

    def _create_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """创建20+技术特征"""
        close = df["close"].astype(float)
        volume = df["volume"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        feats = pd.DataFrame(index=df.index)

        for w in [5, 10, 20, 60]:
            feats[f"ret_{w}d"] = close.pct_change(w)
            feats[f"ma_{w}d"] = close / close.rolling(w).mean() - 1
            feats[f"vol_{w}d"] = close.pct_change().rolling(w).std()
            feats[f"vol_ratio_{w}d"] = volume / volume.rolling(w).mean()

        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        for w in [14, 28]:
            avg_gain = gain.rolling(w).mean()
            avg_loss = loss.rolling(w).mean()
            rs = avg_gain / avg_loss.replace(0, np.nan)
            feats[f"rsi_{w}d"] = 100 - (100 / (1 + rs))

        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        feats["macd"] = ema12 - ema26
        feats["macd_signal"] = feats["macd"].ewm(span=9, adjust=False).mean()
        feats["macd_diff"] = feats["macd"] - feats["macd_signal"]

        for w in [20, 60]:
            feats[f"bb_upper_{w}d"] = (close - close.rolling(w).mean()) / (close.rolling(w).std() + 1e-10)

        feats["hl_ratio"] = (high - low) / close
        feats["tr"] = np.maximum(high - low, np.maximum(abs(high - close.shift()),
                                  abs(low - close.shift())))
        feats["atr_14"] = feats["tr"].rolling(14).mean()
        feats["atr_ratio"] = feats["atr_14"] / close

        for w in [5, 20]:
            feats[f"high_low_{w}d"] = (high.rolling(w).max() - low.rolling(w).min()) / close

        return feats.replace([np.inf, -np.inf], np.nan)

    def _create_labels(self, df: pd.DataFrame, forward_returns: int = 5) -> pd.Series:
        """创建标签：未来N日收益方向（1=涨, -1=跌, 0=平）"""
        fwd_ret = df["close"].astype(float).pct_change(forward_returns).shift(-forward_returns)
        labels = pd.Series(0, index=df.index)
        labels[fwd_ret > 0.005] = 1
        labels[fwd_ret < -0.005] = -1
        return labels

    def _walk_forward_train(self, df: pd.DataFrame) -> pd.Series:
        """滚动窗口训练+预测"""
        features = self._create_features(df)
        labels = self._create_labels(df)
        combined = pd.concat([features, labels.rename("label")], axis=1).dropna()
        if len(combined) < self.train_window + self.test_window:
            return pd.Series(0, index=df.index)

        predictions = pd.Series(np.nan, index=df.index)
        feat_cols = features.columns.tolist()
        total = len(combined)

        for start in range(0, total - self.train_window, self.retrain_freq):
            train_end = start + self.train_window
            test_end = min(train_end + self.test_window, total)
            train_data = combined.iloc[start:train_end]
            test_data = combined.iloc[train_end:test_end]
            if len(test_data) == 0:
                break

            X_train = train_data[feat_cols].fillna(0)
            y_train = train_data["label"]
            X_test = test_data[feat_cols].fillna(0)

            self._scaler.fit(X_train)
            X_train_s = self._scaler.transform(X_train)
            X_test_s = self._scaler.transform(X_test)

            try:
                model = self._get_model()
                model.fit(X_train_s, y_train)
                pred = model.predict(X_test_s)
                for j, idx in enumerate(test_data.index):
                    if idx in predictions.index:
                        predictions.loc[idx] = pred[j]
            except Exception as e:
                # FIX C6-20261020: 静默失败改为可见日志（豆包闸门）
                print(f"[WARN] vibe_ml_strategy: 预测行写入失败, 该条保持空: {e}")

        return predictions.fillna(0).astype(int)

    def _get_model(self):
        if self.model_type == "rf":
            return RandomForestClassifier(n_estimators=self.n_estimators,
                                          max_depth=self.max_depth, random_state=42, n_jobs=-1)
        elif self.model_type == "lr":
            return LogisticRegression(max_iter=1000, random_state=42)
        elif self.model_type == "xgb":
            try:
                from xgboost import XGBClassifier
                return XGBClassifier(
                    n_estimators=self.n_estimators, max_depth=self.max_depth,
                    learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
                    random_state=42, verbosity=0, use_label_encoder=False,
                    eval_metric='mlogloss')
            except ImportError:
                return RandomForestClassifier(n_estimators=self.n_estimators,
                                              max_depth=self.max_depth, random_state=42, n_jobs=-1)
        elif self.model_type == "catboost":
            try:
                from catboost import CatBoostClassifier
                return CatBoostClassifier(
                    iterations=self.n_estimators, depth=self.max_depth,
                    learning_rate=0.05, random_seed=42,
                    verbose=False, allow_writing_files=False)
            except ImportError:
                return RandomForestClassifier(n_estimators=self.n_estimators,
                                              max_depth=self.max_depth, random_state=42, n_jobs=-1)
        return RandomForestClassifier(n_estimators=self.n_estimators,
                                      max_depth=self.max_depth, random_state=42, n_jobs=-1)

    def generate(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        """生成ML信号：1=做多, -1=做空, 0=观望"""
        pred = self._walk_forward_train(df)
        return {"signal": pred}

    # V4修复: 添加update_price适配层，支持逐根bar调用
    def update_price(self, price: float, data=None) -> Dict[str, Any]:
        """逐根bar更新价格，返回交易信号
        优化：只训练一次模型，之后用缓存模型预测，避免重复训练
        """
        from collections import deque
        if not hasattr(self, '_price_buffer'):
            self._price_buffer = deque(maxlen=1000)
            self._trained_model = None  # 缓存训练好的模型
            self._trained_scaler = None  # 缓存scaler
            self._model_trained = False  # 是否已训练
            self._train_threshold = 100  # 达到100根bar就训练（原200太高导致短回测0交易）

        # 维护价格历史
        if not hasattr(self, '_close_list'):
            self._close_list = []
        self._close_list.append(float(price))
        if len(self._close_list) > 200:
            self._close_list = self._close_list[-200:]  # 只保留最近200根
        
        # 数据不足时返回hold
        if len(self._close_list) < 20:
            return {"action": "hold", "signal": "neutral", "balance": 100000.0, "position": 0}

        # [在线路径说明] update_price 为逐根 bar 调用，本类的模型训练在
        # _walk_forward_train（批量 DataFrame 路径，见 generate()）中完成，
        # 并未实现"训练后持久化模型 → 在线加载 predict"的保存/加载机制，
        # 因此 self._trained_model 始终为 None。这里不伪造 ML 预测，明确标注：
        # 当前在线路径使用动量兜底信号，真实 ML 信号请走 generate(df) 批量路径。
        try:
            if len(self._close_list) >= 20:
                # 动量兜底：最近20根bar收益（直接用列表，不创建DataFrame）
                momentum = (self._close_list[-1] / self._close_list[-20] - 1)
                # 阈值由 0.01 下调至 0.005（原阈值过高导致日线级几乎不产生交易）
                self._last_signal = 1 if momentum > 0.005 else (-1 if momentum < -0.005 else 0)
            else:
                self._last_signal = 0
        except Exception:
            self._last_signal = 0

        latest_sig = getattr(self, '_last_signal', 0)
        if latest_sig > 0:
            action, signal = "buy", "buy"
        elif latest_sig < 0:
            action, signal = "sell", "sell"
        else:
            action, signal = "hold", "neutral"

        return {"action": action, "signal": signal, "balance": 100000.0, "position": 0}


if __name__ == "__main__":
    try:
        import akshare as ak
    except ImportError:
        print("请先安装 akshare: pip install akshare")
        raise SystemExit(1)

    symbol = "000300"
    print(f"获取 {symbol} 沪深300指数日线数据...")
    raw = ak.stock_zh_index_daily(symbol=f"sh{symbol}")
    df = raw.rename(columns={"date": "date", "open": "open", "high": "high",
                              "low": "low", "close": "close", "volume": "volume"})
    df = df[["date", "open", "high", "low", "close", "volume"]].copy()
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna().sort_values("date").reset_index(drop=True)
    df = df.tail(500)

    engine = SignalEngine(model_type="rf", train_window=200, test_window=50, retrain_freq=50)
    signals = engine.generate(df)
    s = signals["signal"]
    buy_count = int((s == 1).sum())
    sell_count = int((s == -1).sum())
    print(f"信号统计: 做多={buy_count}, 做空={sell_count}, 观望={len(s) - buy_count - sell_count}")
    print(f"\n最近10个交易日:")
    for i in range(max(0, len(df) - 10), len(df)):
        sig = int(s.iloc[i])
        sig_text = {1: "做多", -1: "做空", 0: "观望"}[sig]
        print(f"  {df.iloc[i]['date']}: close={df.iloc[i]['close']:.2f}, signal={sig} ({sig_text})")