#!/usr/bin/env python3
"""
基于HMM的市场状态识别器
"""

import numpy as np
from scipy import stats
import pandas as pd

HMM_AVAILABLE = False
HMM_IMPL = None

try:
    from hmmlearn import hmm
    HMM_AVAILABLE = True
except ImportError:
    print("hmmlearn not available, trying pure Python implementation")

    try:
        from gaussian_hmm import GaussianHMM as PureGaussianHMM

        class PureHMMWrapper:
            """纯Python HMM包装器，适配hmmlearn接口"""

            def __init__(self, n_components=3, covariance_type="full", n_iter=1000, random_state=42):
                self.n_components = n_components
                self.covariance_type = covariance_type
                self.n_iter = n_iter
                self.random_state = random_state
                self.model = PureGaussianHMM(n_states=n_components, n_iter=n_iter)

            def fit(self, X):
                self.model.fit(X)
                return self

            def predict(self, X):
                return self.model.predict(X)

        HMM_IMPL = PureHMMWrapper
        HMM_AVAILABLE = True
        print("Using pure Python GaussianHMM implementation")
    except ImportError as e:
        print(f"Pure Python HMM not available: {e}")
        print("Using heuristic method only")


class MarketRegimeDetector:
    """
    基于HMM的市场状态识别
    识别三种状态：
    - 0: 低波动趋势市（最佳交易环境）
    - 1: 高波动震荡市（降低仓位）
    - 2: 危机模式（只平仓）
    """

    def __init__(self, n_regimes=3, lookback=100):
        """
        初始化市场状态识别器

        Args:
            n_regimes: 状态数量
            lookback: 回顾窗口大小
        """
        self.n_regimes = n_regimes
        self.lookback = lookback
        self.model = None
        self.regime_labels = {
            0: 'TRENDING_LOW_VOL',
            1: 'CHOPPY_HIGH_VOL',
            2: 'CRISIS_MODE'
        }
        self.regime_history = []
        self.state_mapping = {0: 0, 1: 1, 2: 2}

    def fit(self, returns, volumes):
        """
        训练HMM模型

        Args:
            returns: 收益率序列
            volumes: 成交量序列

        Returns:
            self: 实例本身
        """
        if HMM_AVAILABLE:
            features = self._engineer_features(returns, volumes)

            if features.shape[0] < self.n_regimes:
                print("Not enough data for HMM training, using heuristic method")
                return self

            try:
                impl_class = HMM_IMPL if HMM_IMPL else hmm.GaussianHMM
                self.model = impl_class(
                    n_components=self.n_regimes,
                    covariance_type="full",
                    n_iter=1000,
                    random_state=42
                )
                self.model.fit(features)

                state_volatilities = []
                for state in range(self.n_regimes):
                    state_mask = self.model.predict(features) == state
                    if np.any(state_mask):
                        state_vol = np.std(returns[state_mask])
                        state_volatilities.append((state, state_vol))

                state_volatilities.sort(key=lambda x: x[1])

                if self.n_regimes == 3:
                    self.state_mapping = {
                        state_volatilities[0][0]: 0,
                        state_volatilities[1][0]: 1,
                        state_volatilities[2][0]: 2
                    }
            except Exception as e:
                print(f"HMM training failed: {e}, using heuristic method")
                self.model = None

        return self

    def predict_regime(self, returns, volumes):
        """
        预测当前市场状态

        Args:
            returns: 收益率序列
            volumes: 成交量序列

        Returns:
            int: 市场状态
        """
        if not HMM_AVAILABLE or self.model is None:
            regime = self._heuristic_regime(returns)
        else:
            try:
                features = self._engineer_features(returns, volumes)
                if features.shape[0] < self.n_regimes:
                    regime = self._heuristic_regime(returns)
                else:
                    raw_state = self.model.predict(features[-1:])[0]
                    regime = self.state_mapping.get(raw_state, 1)
            except Exception as e:
                print(f"Regime prediction failed: {e}")
                regime = self._heuristic_regime(returns)

        self.regime_history.append(regime)
        if len(self.regime_history) > 100:
            self.regime_history.pop(0)

        return regime

    def get_regime_confidence(self):
        """
        获取当前状态识别置信度

        Returns:
            float: 置信度
        """
        if len(self.regime_history) < 10:
            return 0.5

        recent_states = self.regime_history[-10:]
        stability = len(set(recent_states)) / len(recent_states)

        return 1.0 - stability

    def _engineer_features(self, returns, volumes):
        """
        构建HMM特征
        """
        features = []

        min_len = max(self.lookback, 30)
        if len(returns) < min_len:
            return np.zeros((1, 7))

        for i in range(self.lookback, len(returns)):
            window_ret = returns[i-self.lookback:i]

            vol = np.std(window_ret) if len(window_ret) > 0 else 0
            vol_ratio = vol / np.std(returns[:i]) if i > 0 and np.std(returns[:i]) > 1e-10 else 1.0

            if len(window_ret) > 1:
                trend = np.polyfit(np.arange(len(window_ret)), window_ret, 1)[0]
                skew = stats.skew(window_ret) if len(window_ret) > 2 else 0
                kurt = stats.kurtosis(window_ret) if len(window_ret) > 3 else 0
                autocorr = np.corrcoef(window_ret[:-1], window_ret[1:])[0, 1] if len(window_ret) > 1 else 0
            else:
                trend = 0
                skew = 0
                kurt = 0
                autocorr = 0

            if volumes is not None and len(volumes) > i:
                vol_window = volumes[i-self.lookback:i]
                vol_change = (vol_window[-1] / np.mean(vol_window) - 1) if np.mean(vol_window) > 0 else 0
            else:
                vol_change = 0

            features.append([vol, vol_ratio, trend, skew, kurt, autocorr, vol_change])

        return np.array(features) if features else np.zeros((1, 7))

    def _heuristic_regime(self, returns):
        """
        启发式状态判断
        """
        if len(returns) < 20:
            return 1

        recent_vol = np.std(returns[-20:])
        long_vol = np.std(returns[-100:]) if len(returns) >= 100 else recent_vol

        vol_ratio = recent_vol / long_vol if long_vol > 1e-10 else 1.0

        if vol_ratio > 2.0:
            return 2
        elif vol_ratio > 1.3:
            return 1
        else:
            hurst = self._calculate_hurst(returns[-100:]) if len(returns) >= 100 else 0.5
            if hurst > 0.6:
                return 0
            else:
                return 1

    def _calculate_hurst(self, ts):
        """
        计算Hurst指数
        """
        if len(ts) < 10:
            return 0.5

        lags = range(2, min(20, len(ts)//2))
        if len(list(lags)) < 2:
            return 0.5

        tau = []
        for lag in lags:
            if len(ts) > lag:
                std_val = np.std(ts[lag:] - ts[:-lag])
                if std_val > 1e-10:
                    tau.append(std_val)

        if len(tau) < 2:
            return 0.5

        try:
            poly = np.polyfit(np.log(list(lags)), np.log(tau), 1)
            return max(0, min(1, poly[0] * 2.0))
        except:
            return 0.5
