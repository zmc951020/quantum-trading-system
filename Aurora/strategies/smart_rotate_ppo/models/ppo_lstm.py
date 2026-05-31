#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能标的轮动策略 — LSTM-PPO 模型
===============================
基于 Stable-Baselines3 PPO + 自定义 LSTM 特征提取器

架构：
  输入: (batch, N * LOOKBACK * F) 展平向量
  → Reshape → (batch, LOOKBACK, N * F)
  → 2层双向 LSTM (hidden=128) → 取最后隐状态
  → Shared MLP [256, 128] → GELU
  → Actor Head + Critic Head
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, List, Optional, Type, Union

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from gymnasium import spaces
from stable_baselines3 import PPO
from stable_baselines3.common.policies import ActorCriticPolicy
from stable_baselines3.common.torch_layers import BaseFeaturesExtractor

logger = logging.getLogger(__name__)


class LSTMFeatureExtractor(BaseFeaturesExtractor):
    """
    时序特征提取器：将展平的观测向量 reshape 后送入 LSTM

    输入: (batch, N * LOOKBACK * F)
    输出: (batch, lstm_hidden * 2 * num_layers)
    """

    def __init__(
        self,
        observation_space: spaces.Box,
        n_assets: int = 10,
        lookback: int = 60,
        feature_dim: int = 90,
        lstm_hidden_size: int = 128,
        lstm_num_layers: int = 2,
        dropout: float = 0.1,
    ):
        self.n_assets = n_assets
        self.lookback = lookback
        self.feature_dim = feature_dim
        self.lstm_hidden_size = lstm_hidden_size
        self.lstm_num_layers = lstm_num_layers

        lstm_input_dim = n_assets * feature_dim
        output_dim = lstm_hidden_size * 2  # 双向LSTM最后隐状态 concat: hidden*2

        super().__init__(observation_space, features_dim=output_dim)

        self.lstm = nn.LSTM(
            input_size=lstm_input_dim,
            hidden_size=lstm_hidden_size,
            num_layers=lstm_num_layers,
            batch_first=True,
            dropout=dropout if lstm_num_layers > 1 else 0,
            bidirectional=True,
        )

        self.proj = nn.Sequential(
            nn.LayerNorm(output_dim),
            nn.Linear(output_dim, 256),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(256, output_dim),
        )

        logger.info(
            f"LSTM 特征提取器 | N={n_assets} L={lookback} F={feature_dim} "
            f"H={lstm_hidden_size} layers={lstm_num_layers} | out={output_dim}"
        )

    def forward(self, observations: torch.Tensor) -> torch.Tensor:
        batch_size = observations.shape[0]
        seq_len = self.lookback
        input_dim = self.n_assets * self.feature_dim
        expected_total = seq_len * input_dim

        if observations.shape[1] > expected_total:
            observations = observations[:, :expected_total]
        elif observations.shape[1] < expected_total:
            pad = torch.zeros(batch_size, expected_total - observations.shape[1],
                              device=observations.device)
            observations = torch.cat([observations, pad], dim=1)

        x = observations.view(batch_size, seq_len, input_dim)
        lstm_out, (hn, cn) = self.lstm(x)

        last_out = lstm_out[:, -1, :]
        mean_out = lstm_out.mean(dim=1)
        features = last_out + mean_out
        features = self.proj(features)
        return features


class LSTMACPolicy(ActorCriticPolicy):
    """
    集成 LSTM 特征提取器的 Actor-Critic 策略
    """

    def __init__(
        self,
        observation_space: spaces.Box,
        action_space: spaces.Box,
        lr_schedule: Callable,
        net_arch: Optional[Union[List[int], Dict[str, List[int]]]] = None,
        activation_fn: Type[nn.Module] = nn.GELU,
        n_assets: int = 10,
        lookback: int = 60,
        feature_dim: int = 90,
        lstm_hidden_size: int = 128,
        lstm_num_layers: int = 2,
        *args,
        **kwargs,
    ):
        self.n_assets = n_assets
        self.lookback = lookback
        self.feature_dim = feature_dim

        kwargs["features_extractor_class"] = LSTMFeatureExtractor
        kwargs["features_extractor_kwargs"] = {
            "n_assets": n_assets,
            "lookback": lookback,
            "feature_dim": feature_dim,
            "lstm_hidden_size": lstm_hidden_size,
            "lstm_num_layers": lstm_num_layers,
        }

        if net_arch is None:
            net_arch = dict(pi=[256, 128], vf=[256, 128])

        super().__init__(
            observation_space=observation_space,
            action_space=action_space,
            lr_schedule=lr_schedule,
            net_arch=net_arch,
            activation_fn=activation_fn,
            *args,
            **kwargs,
        )

        # 重写 action_net: 输出 N 维 → Sigmoid（动作空间 [0,1]）
        action_dim = action_space.shape[0]
        latent_dim = 128  # MLP 最后层
        self.action_net = nn.Sequential(
            nn.Linear(latent_dim, action_dim),
            nn.Sigmoid(),
        )

        logger.info(f"LSTM-PPO 策略初始化 | N={n_assets} L={lookback} F={feature_dim}")

    def _predict(self, observation: torch.Tensor, deterministic: bool = False) -> torch.Tensor:
        features = self.extract_features(observation)
        latent_pi = self.mlp_extractor.forward_actor(features)
        action = self.action_net(latent_pi)  # Sigmoid → 已在 [0,1]
        return torch.clamp(action, 0.0, 1.0)

    def evaluate_actions(self, obs: torch.Tensor, actions: torch.Tensor):
        features = self.extract_features(obs)
        latent_pi = self.mlp_extractor.forward_actor(features)
        mean = self.action_net(latent_pi)

        log_std = self.log_std
        std = torch.exp(log_std)
        dist = torch.distributions.Normal(mean, std)

        log_prob = dist.log_prob(actions).sum(dim=-1)
        entropy = dist.entropy().sum(dim=-1)

        latent_vf = self.mlp_extractor.forward_critic(features)
        values = self.value_net(latent_vf)

        return values, log_prob, entropy

    @property
    def log_std(self) -> torch.Tensor:
        if not hasattr(self, "_log_std"):
            action_dim = self.action_space.shape[0]
            self._log_std = nn.Parameter(torch.ones(action_dim) * -0.5)
        return self._log_std


def create_lstm_ppo(
    env,
    learning_rate: float = 3e-4,
    n_steps: int = 2048,
    batch_size: int = 64,
    n_epochs: int = 10,
    gamma: float = 0.99,
    gae_lambda: float = 0.95,
    clip_range: float = 0.2,
    ent_coef: float = 0.01,
    vf_coef: float = 0.5,
    max_grad_norm: float = 0.5,
    device: str = "auto",
    tensorboard_log: Optional[str] = None,
    **kwargs,
) -> PPO:
    N = getattr(env, 'N', 10)
    L = getattr(env, 'lookback', 60)
    F = getattr(env, 'F', 90)

    policy_kwargs = {
        "n_assets": N,
        "lookback": L,
        "feature_dim": F,
        "lstm_hidden_size": 128,
        "lstm_num_layers": 2,
        "net_arch": dict(pi=[256, 128], vf=[256, 128]),
        "activation_fn": nn.GELU,
    }

    model = PPO(
        policy=LSTMACPolicy,
        env=env,
        learning_rate=learning_rate,
        n_steps=n_steps,
        batch_size=batch_size,
        n_epochs=n_epochs,
        gamma=gamma,
        gae_lambda=gae_lambda,
        clip_range=clip_range,
        ent_coef=ent_coef,
        vf_coef=vf_coef,
        max_grad_norm=max_grad_norm,
        normalize_advantage=True,
        policy_kwargs=policy_kwargs,
        verbose=1,
        device=device,
        tensorboard_log=tensorboard_log,
        **kwargs,
    )

    logger.info(f"LSTM-PPO 模型创建完成 | N={N} L={L} F={F} | device={device}")
    return model


__all__ = ["LSTMFeatureExtractor", "LSTMACPolicy", "create_lstm_ppo"]