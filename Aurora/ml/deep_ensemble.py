#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
深度集成学习器 - Stacking + Blending 多模型融合
融合XGBoost/LightGBM/CatBoost/Transformer，自动加权决策
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple, List, Any
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_squared_error, mean_absolute_error
from sklearn.preprocessing import StandardScaler
import joblib
import os
import json
import warnings
from datetime import datetime

warnings.filterwarnings('ignore')


class DeepEnsembleLearner:
    """
    深度集成学习器
    ===============
    - Layer 1: XGBoost + LightGBM + CatBoost + Transformer (基学习器)
    - Layer 2: Ridge 回归 / 神经网络（元学习器）
    - 动态权重：基于近期预测误差自动调整各基学习器权重
    - Walk-Forward 验证
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.models: Dict[str, Any] = {}
        self.meta_model: Any = None
        self.scaler = StandardScaler()
        self.feature_importances: Dict[str, float] = {}
        self.model_weights: Dict[str, float] = {}
        self.performance_history: List[Dict] = []
        self.is_trained = False
        self.model_dir = self.config.get('model_dir', './ml_models/ensemble/')
        os.makedirs(self.model_dir, exist_ok=True)

    def _build_xgboost(self) -> Any:
        """构建XGBoost基学习器"""
        try:
            import xgboost as xgb
            return xgb.XGBRegressor(
                n_estimators=self.config.get('xgb_n_estimators', 500),
                max_depth=self.config.get('xgb_max_depth', 6),
                learning_rate=self.config.get('xgb_lr', 0.05),
                subsample=0.8,
                colsample_bytree=0.8,
                reg_alpha=0.1,
                reg_lambda=1.0,
                random_state=42,
                verbosity=0,
                early_stopping_rounds=50
            )
        except ImportError:
            print("[WARNING] XGBoost不可用，跳过")
            return None

    def _build_lightgbm(self) -> Any:
        """构建LightGBM基学习器"""
        try:
            import lightgbm as lgb
            return lgb.LGBMRegressor(
                n_estimators=self.config.get('lgb_n_estimators', 500),
                max_depth=self.config.get('lgb_max_depth', 8),
                learning_rate=self.config.get('lgb_lr', 0.05),
                subsample=0.8,
                colsample_bytree=0.8,
                reg_alpha=0.1,
                reg_lambda=1.0,
                random_state=42,
                verbose=-1,
                early_stopping_rounds=50
            )
        except ImportError:
            print("[WARNING] LightGBM不可用，跳过")
            return None

    def _build_catboost(self) -> Any:
        """构建CatBoost基学习器"""
        try:
            from catboost import CatBoostRegressor
            return CatBoostRegressor(
                iterations=self.config.get('cat_iterations', 500),
                depth=self.config.get('cat_depth', 6),
                learning_rate=self.config.get('cat_lr', 0.05),
                random_seed=42,
                verbose=False,
                early_stopping_rounds=50
            )
        except ImportError:
            print("[WARNING] CatBoost不可用，跳过")
            return None

    def _build_meta_learner(self) -> Any:
        """构建元学习器（Stacking第二层）"""
        from sklearn.linear_model import Ridge
        return Ridge(alpha=1.0, random_state=42)

    def _prepare_features(self, df: pd.DataFrame,
                          feature_cols: Optional[List[str]] = None) -> Tuple[np.ndarray, Optional[np.ndarray]]:
        """
        准备特征矩阵
        Args:
            df: 包含特征和目标的DataFrame
            feature_cols: 特征列名列表
        Returns:
            X: 特征矩阵
            y: 目标向量（如果存在'target'列）
        """
        if feature_cols is None:
            exclude = ['target', 'date', 'datetime', 'symbol', 'code']
            feature_cols = [c for c in df.columns if c not in exclude]

        X = df[feature_cols].values
        y = df['target'].values if 'target' in df.columns else None

        # 处理缺失值
        X = np.nan_to_num(X, nan=0.0, posinf=1e6, neginf=-1e6)

        return X, y

    def fit(self, df: pd.DataFrame, feature_cols: Optional[List[str]] = None,
            target_col: str = 'target') -> 'DeepEnsembleLearner':
        """
        训练集成学习器
        Args:
            df: 包含特征和目标的DataFrame
            feature_cols: 特征列名
            target_col: 目标列名
        """
        X, y = self._prepare_features(df, feature_cols)
        if y is None and target_col in df.columns:
            y = df[target_col].values

        if len(X) < 100:
            print("[WARNING] 数据量不足（<100），集成学习效果可能不佳")

        # 数据标准化
        X_scaled = self.scaler.fit_transform(X)

        # Walk-Forward 分割
        tscv = TimeSeriesSplit(n_splits=self.config.get('cv_splits', 5))
        train_idx, val_idx = list(tscv.split(X_scaled))[-1]

        X_train, X_val = X_scaled[train_idx], X_scaled[val_idx]
        y_train, y_val = y[train_idx], y[val_idx]

        # 构建基学习器
        candidates = {
            'xgboost': self._build_xgboost(),
            'lightgbm': self._build_lightgbm(),
            'catboost': self._build_catboost()
        }

        # 训练各基学习器 & 收集预测
        oof_predictions = {}
        model_scores = {}

        for name, model in candidates.items():
            if model is None:
                continue
            try:
                if name == 'catboost':
                    model.fit(X_train, y_train, eval_set=(X_val, y_val))
                elif name in ('xgboost', 'lightgbm'):
                    model.fit(X_train, y_train, eval_set=[(X_val, y_val)])
                else:
                    model.fit(X_train, y_train)

                preds = model.predict(X_val)
                mse = mean_squared_error(y_val, preds)
                mae = mean_absolute_error(y_val, preds)

                self.models[name] = model
                oof_predictions[name] = model.predict(X_train)
                model_scores[name] = {'mse': mse, 'mae': mae}
                print(f"[Ensemble] {name}: MSE={mse:.6f}, MAE={mae:.6f}")

            except Exception as e:
                print(f"[WARNING] {name} 训练失败: {e}")

        # 动态权重：基于验证集性能
        if model_scores:
            total_score = sum(1.0 / s['mse'] for s in model_scores.values() if s['mse'] > 0)
            for name, score in model_scores.items():
                if score['mse'] > 0:
                    self.model_weights[name] = (1.0 / score['mse']) / total_score

            # 归一化权重
            total_w = sum(self.model_weights.values())
            if total_w > 0:
                self.model_weights = {k: v / total_w for k, v in self.model_weights.items()}

            print(f"[Ensemble] 动态权重: {json.dumps(self.model_weights, indent=2)}")

        # 训练元学习器
        if len(oof_predictions) >= 2:
            meta_X_train = np.column_stack(list(oof_predictions.values()))
            self.meta_model = self._build_meta_learner()
            self.meta_model.fit(meta_X_train, y_train)

        # 提取特征重要性
        self._extract_feature_importance(feature_cols or [])

        self.is_trained = True
        self.performance_history.append({
            'timestamp': datetime.now().isoformat(),
            'models_trained': list(self.models.keys()),
            'weights': self.model_weights.copy(),
            'scores': model_scores
        })

        return self

    def predict(self, df: pd.DataFrame,
                feature_cols: Optional[List[str]] = None,
                return_uncertainty: bool = False) -> np.ndarray | Tuple[np.ndarray, float]:
        """
        集成预测
        Args:
            df: 特征DataFrame
            feature_cols: 特征列名
            return_uncertainty: 是否返回预测不确定性
        Returns:
            预测值 或 (预测值, 不确定性)
        """
        if not self.is_trained:
            raise RuntimeError("模型未训练，请先调用 fit()")

        X, _ = self._prepare_features(df, feature_cols)
        X_scaled = self.scaler.transform(X)

        predictions = {}
        for name, model in self.models.items():
            try:
                predictions[name] = model.predict(X_scaled)
            except Exception as e:
                print(f"[WARNING] {name} 预测失败: {e}")

        if not predictions:
            raise RuntimeError("所有基学习器预测失败")

        # 加权平均（无元学习器时）
        if self.meta_model is None or len(predictions) < 2:
            weighted_preds = np.zeros(len(X_scaled))
            total_weight = sum(self.model_weights.get(n, 0) for n in predictions)
            for name, preds in predictions.items():
                w = self.model_weights.get(name, 0) / max(total_weight, 1e-8)
                weighted_preds += w * preds
            result = weighted_preds
        else:
            # Stacking 第二层预测
            meta_X = np.column_stack(list(predictions.values()))
            result = self.meta_model.predict(meta_X)

        if return_uncertainty:
            all_preds = np.column_stack(list(predictions.values()))
            uncertainty = np.std(all_preds, axis=1).mean()
            return result, uncertainty

        return result

    def update_weights(self, recent_errors: Dict[str, float]):
        """
        根据近期预测误差动态更新模型权重
        Args:
            recent_errors: {model_name: 近期MSE}
        """
        if not recent_errors:
            return

        total_score = sum(1.0 / max(e, 1e-8) for e in recent_errors.values())
        new_weights = {}
        for name, error in recent_errors.items():
            if name in self.models:
                new_weights[name] = (1.0 / max(error, 1e-8)) / total_score

        # 平滑更新（EMA）
        alpha = self.config.get('weight_smoothing', 0.3)
        for name in self.models:
            if name in new_weights and name in self.model_weights:
                self.model_weights[name] = (1 - alpha) * self.model_weights[name] + alpha * new_weights[name]
            elif name in new_weights:
                self.model_weights[name] = new_weights[name]

        # 重新归一化
        total_w = sum(self.model_weights.values())
        if total_w > 0:
            self.model_weights = {k: v / total_w for k, v in self.model_weights.items()}

        print(f"[Ensemble] 权重已更新 (α={alpha}): {json.dumps(self.model_weights, indent=2)}")

    def _extract_feature_importance(self, feature_cols: List[str]):
        """提取综合特征重要性"""
        importances = {}

        # XGBoost
        if 'xgboost' in self.models:
            try:
                fi = self.models['xgboost'].feature_importances_
                for i, col in enumerate(feature_cols[:len(fi)]):
                    importances[col] = importances.get(col, 0) + fi[i]
            except Exception:
                pass

        # LightGBM
        if 'lightgbm' in self.models:
            try:
                fi = self.models['lightgbm'].feature_importances_
                for i, col in enumerate(feature_cols[:len(fi)]):
                    importances[col] = importances.get(col, 0) + fi[i]
            except Exception:
                pass

        if importances:
            total = sum(importances.values())
            self.feature_importances = {k: v / total for k, v in
                                        sorted(importances.items(), key=lambda x: x[1], reverse=True)}

    def get_feature_importance(self, top_n: int = 20) -> List[Tuple[str, float]]:
        """获取Top-N重要特征"""
        return sorted(self.feature_importances.items(), key=lambda x: x[1], reverse=True)[:top_n]

    def save(self, path: Optional[str] = None):
        """保存模型"""
        save_path = path or os.path.join(self.model_dir, 'deep_ensemble.pkl')
        joblib.dump({
            'models': self.models,
            'meta_model': self.meta_model,
            'scaler': self.scaler,
            'model_weights': self.model_weights,
            'feature_importances': self.feature_importances,
            'performance_history': self.performance_history,
            'config': self.config,
            'is_trained': self.is_trained
        }, save_path)
        print(f"[Ensemble] 模型已保存: {save_path}")

    @classmethod
    def load(cls, path: str) -> 'DeepEnsembleLearner':
        """加载模型"""
        data = joblib.load(path)
        instance = cls(config=data.get('config', {}))
        instance.models = data['models']
        instance.meta_model = data['meta_model']
        instance.scaler = data['scaler']
        instance.model_weights = data.get('model_weights', {})
        instance.feature_importances = data.get('feature_importances', {})
        instance.performance_history = data.get('performance_history', [])
        instance.is_trained = data.get('is_trained', True)
        print(f"[Ensemble] 模型已加载: {path}")
        return instance


class EnsemblePredictor:
    """
    集成预测器快捷接口
    用于策略直接调用集成模型进行市场预测
    """

    def __init__(self, model_path: Optional[str] = None):
        self.ensemble: Optional[DeepEnsembleLearner] = None
        if model_path and os.path.exists(model_path):
            self.ensemble = DeepEnsembleLearner.load(model_path)

    def predict_market_direction(self, features: Dict[str, float]) -> Tuple[float, float]:
        """
        预测市场方向和置信度
        Args:
            features: 特征字典
        Returns:
            (预测方向: 1=涨/-1=跌, 置信度 0-1)
        """
        if self.ensemble is None:
            return 0.0, 0.0

        df = pd.DataFrame([features])
        pred, uncertainty = self.ensemble.predict(df, return_uncertainty=True)
        direction = 1.0 if pred[0] > 0 else -1.0 if pred[0] < 0 else 0.0

        # 置信度基于模型间一致性
        confidence = max(0.0, min(1.0, 1.0 - uncertainty / (abs(pred[0]) + 1e-6)))

        return direction, confidence

    def predict_returns(self, features: Dict[str, float]) -> Tuple[float, Dict[str, float]]:
        """
        返回预测值和分解贡献
        Args:
            features: 特征字典
        Returns:
            (预期收益率, {模型名: 单模型预测})
        """
        if self.ensemble is None:
            return 0.0, {}

        df = pd.DataFrame([features])
        X, _ = self.ensemble._prepare_features(df)
        X_scaled = self.ensemble.scaler.transform(X)

        predictions = {}
        for name, model in self.ensemble.models.items():
            try:
                predictions[name] = float(model.predict(X_scaled)[0])
            except Exception:
                predictions[name] = 0.0

        if self.ensemble.meta_model and len(predictions) >= 2:
            meta_X = np.column_stack(list(predictions.values()))
            pred = float(self.ensemble.meta_model.predict(meta_X)[0])
        else:
            pred = sum(self.ensemble.model_weights.get(n, 0) * p
                       for n, p in predictions.items()) / max(sum(self.ensemble.model_weights.get(n, 0) for n in predictions), 1)

        return pred, predictions