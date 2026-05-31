#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自编码器异常检测器 - 市场异常/操纵/黑天鹅检测
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple, List
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.preprocessing import StandardScaler
import os
import warnings
from datetime import datetime

warnings.filterwarnings('ignore')


class AutoEncoderAnomaly(nn.Module):
    """自编码器 - 通过重构误差检测异常"""
    def __init__(self, n_features: int, hidden_dims: List[int] = [64, 32, 16]):
        super().__init__()
        dims = [n_features] + hidden_dims
        encoder_layers = []
        for i in range(len(dims) - 1):
            encoder_layers.extend([nn.Linear(dims[i], dims[i + 1]), nn.ReLU(), nn.BatchNorm1d(dims[i + 1])])
        self.encoder = nn.Sequential(*encoder_layers)

        decoder_layers = []
        for i in range(len(dims) - 1, 0, -1):
            decoder_layers.extend([nn.Linear(dims[i], dims[i - 1]), nn.ReLU() if i > 1 else nn.Identity()])
        self.decoder = nn.Sequential(*decoder_layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.decoder(self.encoder(x))

    def reconstruction_error(self, x: torch.Tensor) -> torch.Tensor:
        recon = self.forward(x)
        return ((x - recon) ** 2).mean(dim=1)


class AnomalyDetector:
    """异常检测器主类"""
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.scaler = StandardScaler()
        self.model: Optional[AutoEncoderAnomaly] = None
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.threshold: Optional[float] = None
        self.n_features = config.get('n_features', 20)
        self.hidden_dims = config.get('hidden_dims', [64, 32, 16])
        self.lr = config.get('lr', 1e-3)
        self.epochs = config.get('epochs', 50)
        self.batch_size = config.get('batch_size', 64)
        self.contamination = config.get('contamination', 0.05)
        self.is_trained = False
        self.model_dir = config.get('model_dir', './model_storage/anomaly/')
        os.makedirs(self.model_dir, exist_ok=True)

    def fit(self, df: pd.DataFrame, feature_cols: Optional[List[str]] = None, verbose: bool = True) -> 'AnomalyDetector':
        if feature_cols is None:
            exclude = ['date', 'datetime', 'symbol', 'code', 'target']
            feature_cols = [c for c in df.columns if c not in exclude]

        self.n_features = len(feature_cols)
        X = df[feature_cols].values.astype(np.float32)
        X = np.nan_to_num(X, nan=0.0)
        X_scaled = self.scaler.fit_transform(X)

        self.model = AutoEncoderAnomaly(self.n_features, self.hidden_dims).to(self.device)
        optimizer = optim.Adam(self.model.parameters(), lr=self.lr)
        criterion = nn.MSELoss()

        X_tensor = torch.FloatTensor(X_scaled).to(self.device)
        dataset = torch.utils.data.TensorDataset(X_tensor)
        loader = torch.utils.data.DataLoader(dataset, batch_size=self.batch_size, shuffle=True)

        for epoch in range(self.epochs):
            self.model.train()
            total_loss = 0
            for (batch,) in loader:
                optimizer.zero_grad()
                recon = self.model(batch)
                loss = criterion(recon, batch)
                loss.backward()
                optimizer.step()
                total_loss += loss.item()
            if verbose and epoch % max(1, self.epochs // 10) == 0:
                print(f"[AE] Epoch {epoch}: Loss={total_loss / len(loader):.6f}")

        # 计算阈值
        self.model.eval()
        with torch.no_grad():
            errors = self.model.reconstruction_error(X_tensor).cpu().numpy()
        self.threshold = np.percentile(errors, 100 * (1 - self.contamination))
        self.is_trained = True

        if verbose:
            print(f"[AE] 训练完成, 异常阈值={self.threshold:.6f}")
        return self

    def detect(self, features: Dict[str, float]) -> Tuple[bool, float, str]:
        """
        检测异常
        Returns:
            (是否异常, 异常分数, 异常等级)
        """
        if not self.is_trained:
            return False, 0.0, 'unknown'

        X = np.array([list(features.values())[:self.n_features]], dtype=np.float32)
        X = np.nan_to_num(X, nan=0.0)
        X_scaled = self.scaler.transform(X)
        X_tensor = torch.FloatTensor(X_scaled).to(self.device)

        self.model.eval()
        with torch.no_grad():
            error = float(self.model.reconstruction_error(X_tensor).cpu().numpy()[0])

        score = error / max(self.threshold, 1e-8)

        if score < 1.0:
            level = 'normal'
            is_anomaly = False
        elif score < 2.0:
            level = 'warning'
            is_anomaly = True
        elif score < 5.0:
            level = 'critical'
            is_anomaly = True
        else:
            level = 'black_swan'
            is_anomaly = True

        return is_anomaly, float(score), level

    def detect_batch(self, df: pd.DataFrame) -> pd.DataFrame:
        """批量异常检测"""
        if not self.is_trained:
            return df.assign(anomaly_score=0.0, anomaly_level='unknown')
        exclude = ['date', 'datetime', 'symbol', 'code', 'target']
        feature_cols = [c for c in df.columns if c not in exclude]
        X = df[feature_cols].values.astype(np.float32)
        X = np.nan_to_num(X, nan=0.0)
        X_scaled = self.scaler.transform(X)
        X_tensor = torch.FloatTensor(X_scaled).to(self.device)

        self.model.eval()
        with torch.no_grad():
            errors = self.model.reconstruction_error(X_tensor).cpu().numpy()

        scores = errors / max(self.threshold, 1e-8)
        result = df.copy()
        result['anomaly_score'] = scores
        result['anomaly_level'] = np.where(scores < 1, 'normal',
            np.where(scores < 2, 'warning', np.where(scores < 5, 'critical', 'black_swan')))
        return result

    def save(self, path: Optional[str] = None):
        save_path = path or os.path.join(self.model_dir, 'ae_detector.pt')
        torch.save({
            'model_state_dict': self.model.state_dict(),
            'scaler': self.scaler, 'threshold': self.threshold,
            'n_features': self.n_features, 'config': self.config
        }, save_path)

    @classmethod
    def load(cls, path: str) -> 'AnomalyDetector':
        ckpt = torch.load(path, map_location='cpu')
        inst = cls(config=ckpt.get('config', {}))
        inst.n_features = ckpt['n_features']
        inst.model = AutoEncoderAnomaly(inst.n_features, inst.hidden_dims)
        inst.model.load_state_dict(ckpt['model_state_dict'])
        inst.model.eval()
        inst.scaler = ckpt['scaler']
        inst.threshold = ckpt['threshold']
        inst.is_trained = True
        return inst