#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模型矩阵控制器 - 统一调度所有 ML/DL/RL 模型
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple, List, Any
import os
import json
import warnings
from datetime import datetime, timedelta
from dataclasses import dataclass, field

warnings.filterwarnings('ignore')


@dataclass
class ModelSignal:
    """模型信号"""
    model_name: str
    direction: int  # -1/0/1
    confidence: float  # 0-1
    predicted_return: float
    uncertainty: float
    timestamp: str
    metadata: Dict = field(default_factory=dict)


class ModelController:
    """
    模型矩阵控制器
    ===============
    统一调度 7 大 ML 模型：
    1. DeepEnsemble (XGBoost/LightGBM/CatBoost)
    2. MambaTS (状态空间)
    3. TFT (Temporal Fusion Transformer)
    4. RLEnsemble (PPO+SAC+TD3)
    5. GaussianProcess (不确定性量化)
    6. AnomalyDetector (异常检测)
    7. Shepherd Optimizer (策略优化)
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.models: Dict[str, Any] = {}
        self.model_status: Dict[str, str] = {}
        self.model_weights: Dict[str, float] = {}
        self.signal_history: List[ModelSignal] = []
        self.ensemble_mode = config.get('ensemble_mode', 'weighted_vote')
        self.confidence_threshold = config.get('confidence_threshold', 0.5)
        self.anomaly_freeze = config.get('anomaly_freeze', True)
        self.controller_dir = config.get('controller_dir', './model_storage/controller/')
        os.makedirs(self.controller_dir, exist_ok=True)

    def register_model(self, name: str, model: Any, weight: float = 1.0):
        """注册模型"""
        self.models[name] = model
        self.model_status[name] = 'registered'
        self.model_weights[name] = weight

    def load_all_models(self):
        """尝试加载所有已训练模型（无需训练时直接使用）"""
        model_files = {
            'deep_ensemble': ('./model_storage/ensemble/deep_ensemble.pkl', 'DeepEnsembleLearner'),
            'mamba': ('./model_storage/mamba/mamba_final.pt', 'MambaTrainer'),
            'tft': ('./model_storage/tft/tft_final.pt', 'TFTTrainer'),
            'rl': ('./model_storage/rl/rl_ensemble.json', 'RLEnsemble'),
            'gp': ('./model_storage/gp/gp_best.pkl', 'AdaptiveGaussianProcess'),
            'anomaly': ('./model_storage/anomaly/ae_detector.pt', 'AnomalyDetector'),
        }

        for name, (path, cls_name) in model_files.items():
            if os.path.exists(path):
                self.model_status[name] = 'loaded'
            else:
                self.model_status[name] = 'not_trained'

    def get_consensus_signal(self, features: Dict[str, float],
                             history_df: Optional[pd.DataFrame] = None,
                             price_history: Optional[np.ndarray] = None) -> Dict[str, Any]:
        """
        获取所有模型的共识信号
        Returns:
            {
                'direction': -1/0/1,
                'confidence': 0-1,
                'predicted_return': float,
                'uncertainty': float,
                'signals': [...],
                'anomaly': {...},
                'recommendation': str
            }
        """
        signals: List[ModelSignal] = []
        now = datetime.now().isoformat()

        # 1. DeepEnsemble 预测
        if 'deep_ensemble' in self.models and self.model_status.get('deep_ensemble') in ('loaded', 'trained'):
            try:
                ensemble = self.models['deep_ensemble']
                if hasattr(ensemble, 'predict'):
                    pred, unc = ensemble.predict(pd.DataFrame([features]), return_uncertainty=True)
                    direction = 1 if pred[0] > 0.001 else (-1 if pred[0] < -0.001 else 0)
                    signals.append(ModelSignal('deep_ensemble', direction, min(abs(float(pred[0])), 1.0),
                                               float(pred[0]), float(unc), now))
            except Exception as e:
                print(f"[Controller] DeepEnsemble 预测失败: {e}")

        # 2. MambaTS 预测
        if 'mamba' in self.models and history_df is not None:
            try:
                mamba = self.models['mamba']
                pred, unc = mamba.predict_next(features, history_df)
                direction = 1 if pred > 0.001 else (-1 if pred < -0.001 else 0)
                signals.append(ModelSignal('mamba_ts', direction, min(abs(pred), 1.0), pred, unc, now))
            except Exception as e:
                print(f"[Controller] MambaTS 预测失败: {e}")

        # 3. TFT 预测
        if 'tft' in self.models and history_df is not None:
            try:
                tft = self.models['tft']
                pred, unc = tft.predict_next(features, history_df)
                direction = 1 if pred > 0.001 else (-1 if pred < -0.001 else 0)
                signals.append(ModelSignal('tft', direction, min(abs(pred), 1.0), pred, unc, now))
            except Exception as e:
                print(f"[Controller] TFT 预测失败: {e}")

        # 4. RL 集成投票
        if 'rl' in self.models:
            try:
                rl_ens = self.models['rl']
                action, confidence = rl_ens.vote(features, price_history)
                signals.append(ModelSignal('rl_ensemble', action, confidence, 0.0, 1.0 - confidence, now))
            except Exception as e:
                print(f"[Controller] RL 投票失败: {e}")

        # 5. 高斯过程预测
        if 'gp' in self.models:
            try:
                gp = self.models['gp']
                mean, std, ci = gp.predict_next(features)
                direction = 1 if mean > 0.001 else (-1 if mean < -0.001 else 0)
                confidence = 1.0 - min(std / (abs(mean) + 1e-8), 1.0)
                signals.append(ModelSignal('gaussian_process', direction, confidence, mean, std, now))
            except Exception as e:
                print(f"[Controller] GaussianProcess 预测失败: {e}")

        # 6. 异常检测
        anomaly_result = {'is_anomaly': False, 'score': 0.0, 'level': 'unknown'}
        if 'anomaly' in self.models:
            try:
                detector = self.models['anomaly']
                is_anomaly, score, level = detector.detect(features)
                anomaly_result = {'is_anomaly': is_anomaly, 'score': score, 'level': level}
            except Exception as e:
                print(f"[Controller] 异常检测失败: {e}")

        # 共识聚合
        if not signals:
            return {
                'direction': 0, 'confidence': 0.0, 'predicted_return': 0.0,
                'uncertainty': 1.0, 'signals': [], 'anomaly': anomaly_result,
                'recommendation': '无可用模型信号'
            }

        # 加权投票
        directions = [s.direction for s in signals]
        confidences = [s.confidence * self.model_weights.get(s.model_name, 1.0) for s in signals]

        total_weight = sum(confidences) + 1e-8
        weighted_direction = sum(d * c for d, c in zip(directions, confidences)) / total_weight
        avg_confidence = sum(confidences) / len(confidences)
        avg_pred = np.mean([s.predicted_return for s in signals])
        avg_unc = np.mean([s.uncertainty for s in signals])

        # 最终方向
        if abs(weighted_direction) < 0.15:
            final_direction = 0
        else:
            final_direction = 1 if weighted_direction > 0 else -1

        # 异常冻结
        recommendation = '观望'
        if anomaly_result['is_anomaly'] and self.anomaly_freeze and anomaly_result['level'] in ('critical', 'black_swan'):
            final_direction = 0
            recommendation = f"市场异常({anomaly_result['level']})，冻结交易"
        elif final_direction == 1 and avg_confidence >= self.confidence_threshold:
            recommendation = '买入'
        elif final_direction == -1 and avg_confidence >= self.confidence_threshold:
            recommendation = '卖出'
        else:
            recommendation = '观望'

        return {
            'direction': final_direction,
            'confidence': float(avg_confidence),
            'predicted_return': float(avg_pred),
            'uncertainty': float(avg_unc),
            'signals': [{'model': s.model_name, 'direction': s.direction,
                         'confidence': s.confidence, 'pred_return': s.predicted_return} for s in signals],
            'anomaly': anomaly_result,
            'recommendation': recommendation,
            'models_available': len(signals),
            'total_models': len(self.models)
        }

    def update_weights_from_performance(self, performance_metrics: Dict[str, float]):
        """根据策略表现更新模型权重"""
        for name, metric in performance_metrics.items():
            if name in self.model_weights:
                alpha = self.config.get('weight_smoothing', 0.3)
                self.model_weights[name] = (1 - alpha) * self.model_weights[name] + alpha * metric
        # 归一化
        total = sum(self.model_weights.values())
        if total > 0:
            self.model_weights = {k: v / total for k, v in self.model_weights.items()}

    def get_status_report(self) -> Dict[str, Any]:
        """获取模型矩阵状态报告"""
        return {
            'total_models': len(self.models),
            'loaded_models': sum(1 for s in self.model_status.values() if s == 'loaded'),
            'trained_models': sum(1 for s in self.model_status.values() if s in ('loaded', 'trained')),
            'untrained_models': sum(1 for s in self.model_status.values() if s == 'not_trained'),
            'model_status': self.model_status.copy(),
            'model_weights': self.model_weights.copy(),
            'ensemble_mode': self.ensemble_mode,
            'recent_signals': len(self.signal_history),
            'active_recommendation': self.signal_history[-1].__dict__ if self.signal_history else None
        }

    def save(self, path: Optional[str] = None):
        save_path = path or os.path.join(self.controller_dir, 'controller_state.json')
        state = {
            'model_status': self.model_status,
            'model_weights': self.model_weights,
            'config': self.config,
            'signal_count': len(self.signal_history)
        }
        with open(save_path, 'w') as f:
            json.dump(state, f, indent=2, default=str)

    @classmethod
    def load(cls, path: str) -> 'ModelController':
        with open(path) as f:
            data = json.load(f)
        inst = cls(config=data.get('config', {}))
        inst.model_status = data.get('model_status', {})
        inst.model_weights = data.get('model_weights', {})
        return inst