#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高斯过程预测器 - 不确定性量化与自适应核选择
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple, List
from sklearn.preprocessing import StandardScaler
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, Matern, WhiteKernel, ConstantKernel
import os
import warnings
from datetime import datetime

warnings.filterwarnings('ignore')


class AdaptiveGaussianProcess:
    """
    自适应高斯过程预测器
    - 多种核函数自动选择
    - 完整后验分布（均值 + 方差）
    - 不确定性量化用于风控
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.scaler = StandardScaler()
        self.models: Dict[str, GaussianProcessRegressor] = {}
        self.best_kernel_name: str = ''
        self.best_model: Optional[GaussianProcessRegressor] = None
        self.performance_history: List[Dict] = []
        self.is_trained = False
        self.model_dir = config.get('model_dir', './model_storage/gp/')
        os.makedirs(self.model_dir, exist_ok=True)

    def _build_kernels(self, n_features: int) -> Dict[str, object]:
        """构建候选核函数"""
        kernels = {
            'RBF': ConstantKernel(1.0) * RBF(length_scale=1.0) + WhiteKernel(noise_level=0.1),
            'Matern32': ConstantKernel(1.0) * Matern(length_scale=1.0, nu=1.5) + WhiteKernel(noise_level=0.1),
            'Matern52': ConstantKernel(1.0) * Matern(length_scale=1.0, nu=2.5) + WhiteKernel(noise_level=0.1),
            'RBF_Matern': ConstantKernel(1.0) * (RBF(length_scale=1.0) + Matern(length_scale=1.0, nu=1.5)) + WhiteKernel(noise_level=0.1)
        }
        return kernels

    def fit(self, df: pd.DataFrame, feature_cols: Optional[List[str]] = None,
            target_col: str = 'target', verbose: bool = True) -> 'AdaptiveGaussianProcess':
        """训练高斯过程模型"""
        if feature_cols is None:
            exclude = ['date', 'datetime', 'symbol', 'code']
            feature_cols = [c for c in df.columns if c not in exclude]
        if target_col in df.columns and target_col not in feature_cols:
            feature_cols = [target_col] + feature_cols

        X = df[feature_cols].values
        y = df[target_col].values if target_col in df.columns else np.zeros(len(df))

        X = np.nan_to_num(X, nan=0.0, posinf=1e6, neginf=-1e6)
        X_scaled = self.scaler.fit_transform(X)

        split = int(len(X_scaled) * 0.8)
        X_train, X_val = X_scaled[:split], X_scaled[split:]
        y_train, y_val = y[:split], y[split:]

        if len(X_train) > 1000:
            idx = np.random.choice(len(X_train), 1000, replace=False)
            X_train, y_train = X_train[idx], y_train[idx]

        kernels = self._build_kernels(X_train.shape[1])
        best_score = -float('inf')

        for name, kernel in kernels.items():
            try:
                gp = GaussianProcessRegressor(
                    kernel=kernel, alpha=1e-6, normalize_y=True,
                    n_restarts_optimizer=3, random_state=42
                )
                gp.fit(X_train, y_train)
                score = gp.score(X_val, y_val)
                self.models[name] = gp
                if verbose:
                    print(f"[GP] {name}: R²={score:.4f}")
                if score > best_score:
                    best_score = score
                    self.best_kernel_name = name
                    self.best_model = gp
            except Exception as e:
                if verbose:
                    print(f"[GP] {name} 训练失败: {e}")

        self.is_trained = len(self.models) > 0
        return self

    def predict(self, features: np.ndarray, return_std: bool = True) -> Tuple[np.ndarray, np.ndarray]:
        """预测（均值 + 不确定性）"""
        if not self.is_trained or self.best_model is None:
            return np.zeros(len(features)), np.ones(len(features))

        features = np.nan_to_num(features, nan=0.0)
        X_scaled = self.scaler.transform(features)
        mean, std = self.best_model.predict(X_scaled, return_std=True)
        return mean, std

    def predict_next(self, features: Dict[str, float]) -> Tuple[float, float, float]:
        """
        预测下一个值
        Returns:
            (均值, 标准差, 95%置信区间半宽)
        """
        X = np.array([[features.get(c, 0) for c in self.scaler.feature_names_in_]]) if hasattr(self.scaler, 'feature_names_in_') else np.array([list(features.values())])
        mean, std = self.predict(X, return_std=True)
        ci_half = 1.96 * std[0]
        return float(mean[0]), float(std[0]), float(ci_half)

    def save(self, path: Optional[str] = None):
        import joblib
        save_path = path or os.path.join(self.model_dir, 'gp_best.pkl')
        joblib.dump({
            'scaler': self.scaler, 'best_model': self.best_model,
            'best_kernel_name': self.best_kernel_name,
            'is_trained': self.is_trained
        }, save_path)

    @classmethod
    def load(cls, path: str) -> 'AdaptiveGaussianProcess':
        import joblib
        data = joblib.load(path)
        inst = cls()
        inst.scaler = data['scaler']
        inst.best_model = data['best_model']
        inst.best_kernel_name = data.get('best_kernel_name', '')
        inst.is_trained = data.get('is_trained', True)
        return inst