#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能标的轮动策略 — PPO Agent (MLP + LSTM 可选)
==============================================
Phase 1: MLP-PPO 基线 (当前)
Phase 2: LSTM-PPO + Transformer-PPO (后续迭代)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional, Type

import gymnasium as gym
import numpy as np
import torch
import torch.nn as nn
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import (
    BaseCallback,
    CheckpointCallback,
    EvalCallback,
)
from stable_baselines3.common.policies import ActorCriticPolicy
from stable_baselines3.common.torch_layers import BaseFeaturesExtractor

from strategies.smart_rotate_ppo.config import StrategyConfig

logger = logging.getLogger(__name__)


# ============================================================================
# 自定义特征提取器：MLP (Phase 1 基线)
# ============================================================================
class MLPFeatureExtractor(BaseFeaturesExtractor):
    """
    MLP 特征提取器

    将 173 维观测映射到隐含特征空间
    """

    def __init__(
        self,
        observation_space: gym.spaces.Box,
        features_dim: int = 256,
        fc_dims: Optional[list] = None,
    ):
        super().__init__(observation_space, features_dim)
        if fc_dims is None:
            fc_dims = [512, 256, 128]

        input_dim = int(np.prod(observation_space.shape))

        layers = []
        prev_dim = input_dim
        for dim in fc_dims:
            layers.append(nn.Linear(prev_dim, dim))
            layers.append(nn.GELU())
            layers.append(nn.LayerNorm(dim))
            prev_dim = dim
        layers.append(nn.Linear(prev_dim, features_dim))
        layers.append(nn.GELU())

        self.mlp = nn.Sequential(*layers)

    def forward(self, observations: torch.Tensor) -> torch.Tensor:
        return self.mlp(observations)


# ============================================================================
# LSTM 特征提取器 (Phase 2 备用)
# ============================================================================
class LSTMFeatureExtractor(BaseFeaturesExtractor):
    """
    LSTM 特征提取器 (预留 Phase 2)

    使用时需配合 VecEnv wrappers 提供时序上下文
    """

    def __init__(
        self,
        observation_space: gym.spaces.Box,
        features_dim: int = 256,
        hidden_size: int = 256,
        num_layers: int = 2,
    ):
        super().__init__(observation_space, features_dim)
        input_dim = int(np.prod(observation_space.shape))
        self.lstm = nn.LSTM(
            input_dim, hidden_size, num_layers,
            batch_first=True, bidirectional=False,
        )
        self.fc = nn.Sequential(
            nn.Linear(hidden_size, features_dim),
            nn.GELU(),
        )
        self._hidden_size = hidden_size
        self._num_layers = num_layers
        self._lstm_state: Optional[tuple] = None

    def forward(self, observations: torch.Tensor) -> torch.Tensor:
        # observations: (batch, input_dim) → (batch, 1, input_dim)
        batch_size = observations.shape[0]
        x = observations.unsqueeze(1)  # (B, 1, D)

        out, _ = self.lstm(x)
        out = out[:, -1, :]  # (B, hidden)
        return self.fc(out)


# ============================================================================
# 训练回调：记录指标
# ============================================================================
class MetricsCallback(BaseCallback):
    """记录训练过程中的关键指标"""

    def __init__(self, verbose: int = 0):
        super().__init__(verbose)
        self.metrics: Dict[str, list] = {
            "loss": [],
            "value_loss": [],
            "policy_loss": [],
        }

    def _on_step(self) -> bool:
        if len(self.model.logger.name_to_value) > 0:
            for key in self.metrics:
                val = self.model.logger.name_to_value.get(f"train/{key}")
                if val is not None:
                    self.metrics[key].append(val)
        return True


# ============================================================================
# PPO Agent 工厂函数
# ============================================================================
class PPOAgent:
    """
    PPO Agent 封装

    用法:
        cfg = StrategyConfig()
        agent = PPOAgent(cfg)
        model = agent.create_model(env, feature_extractor_cls=MLPFeatureExtractor)
        model.learn(total_timesteps=cfg.total_timesteps)
        model.save("models/ppo_smart_rotate_final")
    """

    def __init__(self, cfg: StrategyConfig):
        self.cfg = cfg
        self.model: Optional[PPO] = None
        self._device = self._resolve_device()

    def _resolve_device(self) -> str:
        if self.cfg.device == "cpu":
            return "cpu"
        if self.cfg.device == "cuda":
            return "cuda" if torch.cuda.is_available() else "cpu"
        # auto
        return "cuda" if torch.cuda.is_available() else "cpu"

    def create_model(
        self,
        env: gym.Env,
        feature_extractor_cls: Type[BaseFeaturesExtractor] = MLPFeatureExtractor,
        policy: Type[ActorCriticPolicy] = ActorCriticPolicy,
    ) -> PPO:
        """
        创建 PPO 模型

        Args:
            env: Gymnasium 环境
            feature_extractor_cls: 特征提取器类
            policy: 策略类 (默认 ActorCriticPolicy)

        Returns:
            配置完成的 PPO 模型
        """
        policy_kwargs: Dict[str, Any] = {
            "features_extractor_class": feature_extractor_cls,
            "features_extractor_kwargs": {
                "features_dim": 256,
                "fc_dims": self.cfg.fc_dims,
            },
            "net_arch": [dict(pi=[256, 128], vf=[256, 128])],
            "activation_fn": torch.nn.GELU,
        }

        model = PPO(
            policy=policy,
            env=env,
            learning_rate=self.cfg.ppo_lr,
            n_steps=self.cfg.ppo_n_steps,
            batch_size=self.cfg.ppo_batch_size,
            n_epochs=self.cfg.ppo_n_epochs,
            gamma=self.cfg.ppo_gamma,
            gae_lambda=self.cfg.ppo_gae_lambda,
            clip_range=self.cfg.ppo_clip_range,
            ent_coef=self.cfg.ppo_ent_coef,
            vf_coef=self.cfg.ppo_vf_coef,
            max_grad_norm=self.cfg.ppo_max_grad_norm,
            normalize_advantage=True,
            policy_kwargs=policy_kwargs,
            verbose=1,
            device=self._device,
            seed=self.cfg.random_seed,
            tensorboard_log=(
                "strategies/smart_rotate_ppo/logs/tensorboard"
                if self.cfg.enable_tensorboard
                else None
            ),
        )

        self.model = model
        logger.info(f"PPO 模型创建成功: device={self._device}, timesteps={self.cfg.total_timesteps}")
        return model

    def train(
        self,
        model: Optional[PPO] = None,
        total_timesteps: Optional[int] = None,
        eval_env: Optional[gym.Env] = None,
        save_path: str = "strategies/smart_rotate_ppo/models/ppo_smart_rotate_final",
    ) -> PPO:
        """
        训练 PPO 模型

        Args:
            model: 已创建的 PPO 模型（如 None 则必须先用 create_model）
            total_timesteps: 训练总步数
            eval_env: 评估环境（可选）
            save_path: 模型保存路径

        Returns:
            训练完成的 PPO 模型
        """
        if model is None:
            if self.model is None:
                raise ValueError("请先调用 create_model() 创建模型")
            model = self.model

        total_timesteps = total_timesteps or self.cfg.total_timesteps

        # 回调
        callbacks = []

        # TensorBoard
        if self.cfg.enable_tensorboard:
            callbacks.append(MetricsCallback())

        # Checkpoint
        if self.cfg.enable_checkpoint:
            ckpt_dir = os.path.dirname(save_path)
            os.makedirs(ckpt_dir, exist_ok=True)
            callbacks.append(
                CheckpointCallback(
                    save_freq=max(total_timesteps // 5, 1000),
                    save_path=ckpt_dir,
                    name_prefix="ppo_checkpoint",
                )
            )

        # 评估回调
        if eval_env is not None:
            callbacks.append(
                EvalCallback(
                    eval_env,
                    best_model_save_path=os.path.dirname(save_path),
                    log_path=os.path.join(
                        os.path.dirname(save_path), "eval_logs"
                    ),
                    eval_freq=5000,
                    deterministic=True,
                    render=False,
                )
            )

        logger.info(f"开始训练: total_timesteps={total_timesteps}")
        model.learn(
            total_timesteps=total_timesteps,
            callback=callbacks,
            progress_bar=True,
        )

        # 保存模型
        model.save(save_path)
        logger.info(f"模型已保存到 {save_path}")

        self.model = model
        return model

    def load_model(self, path: str) -> PPO:
        """加载已保存的模型"""
        model = PPO.load(path, device=self._device)
        self.model = model
        logger.info(f"模型已加载: {path}")
        return model

    def predict(self, observation: np.ndarray, deterministic: bool = True) -> np.ndarray:
        """单步预测动作"""
        if self.model is None:
            raise ValueError("模型未初始化，请先 create_model/train/load_model")
        action, _ = self.model.predict(observation, deterministic=deterministic)
        return action


__all__ = [
    "PPOAgent",
    "MLPFeatureExtractor",
    "LSTMFeatureExtractor",
    "MetricsCallback",
]