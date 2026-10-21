#!/usr/bin/env python3
"""市场分类器：基于RandomForest的趋势/震荡/波动识别，可独立训练和持久化"""

import numpy as np
import pandas as pd
import pickle
import os
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

MARKET_TYPES = ['range_bound', 'trending_up', 'trending_down', 'volatile']


class MarketClassifier:
    """市场分类器：提取特征 + 训练RF模型 + 预测 + 持久化"""

    def __init__(self):
        self.classifier = RandomForestClassifier(n_estimators=100, random_state=42)
        self.scaler = StandardScaler()
        self.trained = False
        self.feature_data = []
        self.label_data = []

    def _extract_features(self, data: pd.Series) -> list:
        if len(data) < 20:
            return [0] * 16
        returns = data.pct_change().dropna()
        recent = data.iloc[-20:]
        features = [
            (data.iloc[-1] - data.iloc[-10]) / data.iloc[-10] if len(data) >= 10 else 0,
            (data.iloc[-1] - data.iloc[-20]) / data.iloc[-20] if len(data) >= 20 else 0,
            returns.std() * 100 if len(returns) > 1 else 0,
            (data.iloc[-1] - recent.min()) / (recent.max() - recent.min()) if recent.max() != recent.min() else 0.5,
            data.ewm(span=10).mean().iloc[-1] / data.ewm(span=60).mean().iloc[-1] - 1 if len(data) >= 60 else 0,
            data.rolling(20).mean().iloc[-1] / data.rolling(20).mean().iloc[-1] if len(data) >= 20 else 1,
            data.rolling(20).std().iloc[-1] / data.iloc[-1] if len(data) >= 20 and data.iloc[-1] != 0 else 0,
            data.diff().rolling(10).mean().iloc[-1] / data.iloc[-1] if len(data) >= 10 and data.iloc[-1] != 0 else 0,
        ]
        delta = data.diff()
        for period in [7, 14, 21]:
            if len(data) >= period + 1:
                gain = delta.iloc[-period:].clip(lower=0).mean()
                loss = (-delta.iloc[-period:].clip(upper=0)).mean()
                rsi = 100 - 100 / (1 + gain / loss) if loss != 0 else 100
                features.append(rsi)
            else:
                features.append(50)
        ema10 = data.ewm(span=10).mean().iloc[-1] if len(data) >= 10 else data.iloc[-1]
        ema20 = data.ewm(span=20).mean().iloc[-1] if len(data) >= 20 else data.iloc[-1]
        ema60 = data.ewm(span=60).mean().iloc[-1] if len(data) >= 60 else data.iloc[-1]
        features.append((ema10 - ema20) / data.iloc[-1] if data.iloc[-1] != 0 else 0)
        features.append((ema10 - ema60) / data.iloc[-1] if data.iloc[-1] != 0 else 0)
        features.append(data.iloc[-1] / data.rolling(20).max().iloc[-1] if len(data) >= 20 else 1)
        features.append(data.iloc[-1] / data.rolling(20).min().iloc[-1] if len(data) >= 20 else 1)
        return features

    def _label_market_type(self, data: pd.Series) -> str:
        if len(data) < 60:
            return 'range_bound'
        ema10 = data.ewm(span=10).mean().iloc[-1]
        ema60 = data.ewm(span=60).mean().iloc[-1]
        ema_ratio = (ema10 - ema60) / ema60
        volatility = data.pct_change().dropna().std() * 100
        if abs(ema_ratio) < 0.01:
            return 'volatile' if volatility > 2 else 'range_bound'
        elif ema_ratio > 0.02:
            return 'trending_up'
        elif ema_ratio < -0.02:
            return 'trending_down'
        else:
            return 'volatile' if volatility > 1.5 else 'range_bound'

    def detect_market_type(self, data: pd.Series) -> str:
        """检测当前市场类型"""
        if len(data) < 60:
            return 'range_bound'
        features = self._extract_features(data)
        true_label = self._label_market_type(data)
        self.feature_data.append(features)
        self.label_data.append(true_label)
        if len(self.feature_data) % 30 == 0:
            self.train_classifier(self.feature_data, self.label_data)
        if self.trained:
            try:
                features_scaled = self.scaler.transform([features])
                pred = self.classifier.predict(features_scaled)[0]
                return MARKET_TYPES[pred]
            except Exception:
                return true_label
        return true_label

    def train_classifier(self, features, labels):
        """训练RandomForest分类器"""
        if len(features) < 20:
            return
        y = [MARKET_TYPES.index(lbl) if lbl in MARKET_TYPES else 0 for lbl in labels]
        if len(set(y)) < 2:
            return
        X = self.scaler.fit_transform(features)
        self.classifier.fit(X, y)
        self.trained = True

    def predict_market(self, data: pd.Series) -> str:
        """预测市场类型（不收集训练数据）"""
        if len(data) < 20:
            return 'range_bound'
        features = self._extract_features(data)
        if not self.trained:
            return self._label_market_type(data)
        try:
            features_scaled = self.scaler.transform([features])
            return MARKET_TYPES[self.classifier.predict(features_scaled)[0]]
        except Exception:
            return self._label_market_type(data)

    def save_model(self, path: str):
        """保存模型到文件"""
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)
        with open(path, 'wb') as f:
            pickle.dump({
                'classifier': self.classifier,
                'scaler': self.scaler,
                'trained': self.trained,
                'feature_data': self.feature_data[-500:],
                'label_data': self.label_data[-500:],
            }, f)

    def load_model(self, path: str):
        """从文件加载模型"""
        if os.path.exists(path):
            with open(path, 'rb') as f:
                data = pickle.load(f)
                self.classifier = data.get('classifier', self.classifier)
                self.scaler = data.get('scaler', self.scaler)
                self.trained = data.get('trained', False)
                self.feature_data = data.get('feature_data', [])
                self.label_data = data.get('label_data', [])
            return True
        return False