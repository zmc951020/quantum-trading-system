#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高斯隐马尔可夫模型 - Aurora量化策略核心模型
用于市场状态识别与交易信号生成
"""

import logging
import json
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class GaussianHMM:
    """高斯隐马尔可夫模型 - 市场状态推断"""

    def __init__(self, n_states: int = 3, random_state: int = 42):
        self.n_states = n_states
        self.random_state = random_state
        self.is_trained = False
        self._params: Dict[str, Any] = {
            "start_prob": [1.0 / n_states] * n_states,
            "trans_mat": [[1.0 / n_states] * n_states for _ in range(n_states)],
            "means": [[0.0] for _ in range(n_states)],
            "covars": [[1.0] for _ in range(n_states)],
        }
        self._state_labels = {0: "熊市", 1: "震荡", 2: "牛市"}

    def fit(self, observations: List[float], **kwargs) -> Dict[str, Any]:
        """训练HMM模型"""
        if not observations or len(observations) < 10:
            return {"status": "error", "message": "数据不足，至少需要10个观测值"}

        n = len(observations)
        if self.n_states > 3 and n < self.n_states * 5:
            self.n_states = min(3, n // 3)

        import random
        random.seed(self.random_state)

        # 简单初始化
        mean_val = sum(observations) / n
        sorted_obs = sorted(observations)

        for i in range(self.n_states):
            idx = int(n * i / self.n_states)
            self._params["means"][i] = [sorted_obs[min(idx, n - 1)]]
            self._params["covars"][i] = [max(0.01, abs(sorted_obs[idx]) * 0.1) if n > 1 else 1.0]

        # 转移矩阵初始化
        persistence = 0.7
        residual = (1.0 - persistence) / max(self.n_states - 1, 1)
        for i in range(self.n_states):
            for j in range(self.n_states):
                self._params["trans_mat"][i][j] = persistence if i == j else residual

        self.is_trained = True
        return {
            "status": "success",
            "n_states": self.n_states,
            "observations": n,
            "means": [round(m[0], 4) for m in self._params["means"]],
        }

    def predict_state(self, observation: float) -> Dict[str, Any]:
        """预测当前市场状态"""
        import math

        if not self.is_trained:
            return {"status": "error", "message": "模型未训练"}

        probs = []
        for i in range(self.n_states):
            mean = self._params["means"][i][0]
            covar = self._params["covars"][i][0]
            diff = observation - mean
            prob = math.exp(-0.5 * (diff * diff) / covar) / math.sqrt(2 * math.pi * covar)
            probs.append(prob)

        total = sum(probs)
        if total > 0:
            probs = [p / total for p in probs]

        best_state = probs.index(max(probs))

        return {
            "state": best_state,
            "state_label": self._state_labels.get(best_state, f"状态{best_state}"),
            "probabilities": [round(p, 4) for p in probs],
            "confidence": round(max(probs), 4),
        }

    def predict_sequence(self, observations: List[float]) -> Dict[str, Any]:
        """预测序列的市场状态"""
        if not self.is_trained:
            return {"status": "error", "message": "模型未训练"}

        states = []
        for obs in observations:
            result = self.predict_state(obs)
            states.append(result["state"])

        state_counts = {}
        for s in states:
            state_counts[s] = state_counts.get(s, 0) + 1

        return {
            "status": "success",
            "states_sequence": states,
            "state_counts": state_counts,
            "dominant_state": max(state_counts, key=state_counts.get) if state_counts else 0,
            "dominant_label": self._state_labels.get(
                max(state_counts, key=state_counts.get) if state_counts else 0,
                "未知",
            ),
        }

    def get_transition_matrix(self) -> List[List[float]]:
        """获取状态转移矩阵"""
        return [[round(v, 4) for v in row] for row in self._params["trans_mat"]]

    def save(self, filepath: str) -> None:
        """保存模型参数"""
        data = {
            "n_states": self.n_states,
            "is_trained": self.is_trained,
            "params": self._params,
            "state_labels": self._state_labels,
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info(f"HMM模型已保存至 {filepath}")

    def load(self, filepath: str) -> bool:
        """加载模型参数"""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.n_states = data["n_states"]
                self.is_trained = data["is_trained"]
                self._params = data["params"]
                self._state_labels = data.get("state_labels", self._state_labels)
            logger.info(f"HMM模型已从 {filepath} 加载")
            return True
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"加载失败: {e}")
            return False


class StateDrivenStrategy:
    """状态驱动策略 - 基于HMM状态生成交易信号"""

    def __init__(self, hmm_model: Optional[GaussianHMM] = None):
        self.hmm = hmm_model or GaussianHMM(n_states=3)
        self.current_state = 1  # 默认震荡
        self.position: Dict[str, Any] = {"side": "flat", "size": 0}
        self.trade_history: List[Dict[str, Any]] = []

    def on_data(self, price: float, volume: float, additional_features: Optional[List[float]] = None) -> Dict[str, Any]:
        """处理新数据点，生成交易信号"""
        if not self.hmm.is_trained:
            self.hmm.fit([price])  # 自动训练
            return {"signal": "hold", "reason": "模型初始化中"}

        features = [price]
        if additional_features:
            features.extend(additional_features)

        prediction = self.hmm.predict_state(sum(features) / len(features))
        new_state = prediction["state"]

        signal = "hold"
        reason = f"状态: {prediction['state_label']}"

        # 状态切换信号
        if new_state == 2 and self.current_state != 2:  # 进入牛市
            signal = "buy"
            reason = f"检测到牛市信号，置信度 {prediction['confidence']}"
        elif new_state == 0 and self.current_state != 0:  # 进入熊市
            signal = "sell"
            reason = f"检测到熊市信号，置信度 {prediction['confidence']}"
        elif new_state == 1:  # 震荡
            signal = "hold"

        self.current_state = new_state
        return {"signal": signal, "reason": reason, "state": prediction["state_label"], "confidence": prediction["confidence"]}


__all__ = ["GaussianHMM", "StateDrivenStrategy"]