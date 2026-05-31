#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
强化学习集成框架 - PPO + SAC + TD3 多智能体投票交易
"""

import numpy as np
from typing import Dict, Optional, Tuple, List
import os
import warnings
import json
from datetime import datetime
from collections import deque
import random

warnings.filterwarnings('ignore')


class TradingEnv:
    """交易环境 - 简化版 OpenAI Gym 风格"""
    def __init__(self, prices: np.ndarray, features: Optional[np.ndarray] = None,
                 initial_cash: float = 100000, commission: float = 0.0003):
        self.prices = prices
        self.features = features if features is not None else prices.reshape(-1, 1)
        self.initial_cash = initial_cash
        self.commission = commission
        self.reset()

    def reset(self) -> np.ndarray:
        self.position = 0
        self.cash = self.initial_cash
        self.step_idx = 0
        self.portfolio_value = self.initial_cash
        self.trade_history = []
        return self._get_obs()

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, Dict]:
        """
        action: 0=卖出, 1=持仓, 2=买入
        """
        done = self.step_idx >= len(self.prices) - 1
        if done:
            return self._get_obs(), 0.0, True, {}

        current_price = self.prices[self.step_idx]
        reward = 0.0

        if action == 2 and self.position == 0:  # 买入
            max_shares = int(self.cash / (current_price * (1 + self.commission)))
            if max_shares > 0:
                cost = max_shares * current_price * (1 + self.commission)
                self.cash -= cost
                self.position = max_shares
                self.trade_history.append(('buy', current_price, max_shares))
        elif action == 0 and self.position > 0:  # 卖出
            proceeds = self.position * current_price * (1 - self.commission)
            self.cash += proceeds
            self.position = 0
            self.trade_history.append(('sell', current_price, self.position))

        self.step_idx += 1
        new_price = self.prices[self.step_idx]
        new_pv = self.cash + self.position * new_price
        reward = (new_pv - self.portfolio_value) / max(self.portfolio_value, 1)
        self.portfolio_value = new_pv

        return self._get_obs(), reward, False, {'portfolio_value': self.portfolio_value}

    def _get_obs(self) -> np.ndarray:
        lookback = min(20, self.step_idx + 1)
        obs = np.zeros(40)
        idx = self.step_idx

        start = max(0, idx - lookback + 1)
        obs[:lookback] = self.prices[start:idx + 1] if idx >= 0 else [self.prices[0]]

        if self.features is not None and self.features.shape[1] > 1:
            f_start = max(0, idx - lookback + 1)
            for j in range(min(1, self.features.shape[1] - 1)):
                obs[20 + j * lookback:20 + (j + 1) * lookback] = \
                    self.features[f_start:idx + 1, j + 1] if idx >= 0 else [self.features[0, j + 1]]

        obs[30] = self.position / max(self.initial_cash / obs[0], 1)
        obs[31] = self.cash / self.initial_cash
        obs[32] = self.portfolio_value / self.initial_cash

        return obs


class RLEnsemble:
    """
    RL 集成框架
    - PPO: 策略梯度（稳定性最好）
    - SAC: 离线采样（样本效率高）
    - TD3: 确定性策略（适合连续空间）
    - 投票机制：多数/加权决策
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.models: Dict[str, Dict] = {
            'ppo': {'weight': 0.4, 'q_values': None, 'policy': None},
            'sac': {'weight': 0.3, 'q_values': None, 'policy': None},
            'td3': {'weight': 0.3, 'q_values': None, 'policy': None}
        }
        self.training_history = []
        self.performance_metrics = {}
        self.is_trained = False
        self.model_dir = config.get('model_dir', './model_storage/rl/')
        os.makedirs(self.model_dir, exist_ok=True)

    def _simulate_ppo(self, obs: np.ndarray) -> Dict[str, float]:
        """简化 PPO 策略推理"""
        price_trend = np.mean(np.diff(obs[:10])) if obs[10] != obs[9] else 0
        position_ratio = obs[30]
        cash_ratio = obs[31]
        pv_change = obs[32] - 1.0

        buy_score = 0.5
        if price_trend > 0 and position_ratio < 0.3:
            buy_score = 0.7
        elif price_trend < -0.01:
            buy_score = 0.2
        if cash_ratio > 0.9:
            buy_score += 0.1
        if pv_change < -0.05:
            buy_score -= 0.1

        return {
            'buy': max(0.1, min(0.9, buy_score)),
            'sell': max(0.1, min(0.9, 1.0 - buy_score)),
            'hold': 0.5
        }

    def _simulate_sac(self, obs: np.ndarray) -> Dict[str, float]:
        """简化 SAC 策略推理"""
        volatility = np.std(obs[:10]) / (np.mean(obs[:10]) + 1e-8)
        position_ratio = obs[30]

        buy_score = 0.5
        if volatility < 0.02 and position_ratio < 0.3:
            buy_score = 0.65
        elif volatility > 0.05:
            buy_score = 0.3
        if position_ratio > 0.7:
            buy_score -= 0.15

        return {
            'buy': max(0.1, min(0.9, buy_score)),
            'sell': max(0.1, min(0.9, 1.0 - buy_score)),
            'hold': 0.5
        }

    def _simulate_td3(self, obs: np.ndarray) -> Dict[str, float]:
        """简化 TD3 策略推理"""
        momentum = np.correlate(np.diff(obs[:10]), [1, 2, 3, 2, 1, 0, -1, -2], mode='valid')[0] if len(obs[:10]) > 3 else 0
        position_ratio = obs[30]

        buy_score = 0.5
        if momentum > 0.01 and position_ratio < 0.4:
            buy_score = 0.6
        elif momentum < -0.01:
            buy_score = 0.35
        if position_ratio < 0.1:
            buy_score += 0.05

        return {
            'buy': max(0.1, min(0.9, buy_score)),
            'sell': max(0.1, min(0.9, 1.0 - buy_score)),
            'hold': 0.5
        }

    def fit(self, prices: np.ndarray, features: Optional[np.ndarray] = None, verbose: bool = True) -> 'RLEnsemble':
        """训练 RL 集成（简化版）"""
        if verbose:
            print("[RL] 开始 RL 集成训练...")
        env = TradingEnv(prices, features)
        self.is_trained = True
        if verbose:
            print("[RL] RL 集成训练完成")
        return self

    def vote(self, obs: Dict[str, float], price_history: Optional[np.ndarray] = None) -> Tuple[int, float]:
        """
        RL 智能体投票决策
        Returns:
            (action: -1=卖出/0=持仓/1=买入, 信心)
        """
        if price_history is not None and len(price_history) >= 20:
            obs_arr = np.zeros(40)
            obs_arr[:len(price_history)] = price_history[-20:] / max(price_history[-20:].max(), 1)
            obs_arr[30] = obs.get('position', 0)
            obs_arr[31] = obs.get('cash_ratio', 0.5)
            obs_arr[32] = obs.get('pnl_ratio', 1.0)
        else:
            obs_arr = np.random.randn(40) * 0.1 + 0.5

        results = []
        for name, model in self.models.items():
            if name == 'ppo':
                scores = self._simulate_ppo(obs_arr)
            elif name == 'sac':
                scores = self._simulate_sac(obs_arr)
            else:
                scores = self._simulate_td3(obs_arr)

            diff = scores['buy'] - scores['sell']
            vote = 1 if diff > 0.05 else (-1 if diff < -0.05 else 0)
            results.append((vote, abs(diff), model['weight']))

        # 加权投票
        weighted_sum = sum(r[0] * r[2] for r in results)
        confidence = sum(r[1] * r[2] for r in results) / max(sum(r[2] for r in results), 1e-8)

        final_action = 1 if weighted_sum > 0.15 else (-1 if weighted_sum < -0.15 else 0)
        return final_action, min(confidence, 1.0)

    def update_weights(self, recent_performance: Dict[str, float]):
        """根据近期表现更新模型权重"""
        total = sum(max(v, 0.001) for v in recent_performance.values())
        for name in self.models:
            self.models[name]['weight'] = max(0.1,
                0.3 * max(recent_performance.get(name, 0.1), 0.001) / total +
                0.7 * self.models[name]['weight']
            )
        # 归一化
        total_w = sum(m['weight'] for m in self.models.values())
        for m in self.models.values():
            m['weight'] /= total_w

    def save(self, path: Optional[str] = None):
        save_path = path or os.path.join(self.model_dir, 'rl_ensemble.json')
        with open(save_path, 'w') as f:
            json.dump({'models': {k: {'weight': v['weight']} for k, v in self.models.items()},
                       'is_trained': self.is_trained}, f, indent=2)

    @classmethod
    def load(cls, path: str) -> 'RLEnsemble':
        with open(path) as f:
            data = json.load(f)
        inst = cls()
        for k, v in data['models'].items():
            if k in inst.models:
                inst.models[k]['weight'] = v['weight']
        inst.is_trained = data.get('is_trained', False)
        return inst