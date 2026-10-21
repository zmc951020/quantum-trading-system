#!/usr/bin/env python3
"""
基于PPO的量化交易策略 - 简化测试版本
"""
import random
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
from collections import deque, namedtuple
import logging
import pickle
import os
from typing import Tuple, List, Dict, Optional
from dataclasses import dataclass
from enum import Enum

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== 配置类 ====================
@dataclass
class PPOConfig:
    """PPO算法配置"""
    state_dim: int = 20
    action_dim: int = 3  # 0:sell, 1:hold, 2:buy
    hidden_dim: int = 64
    lr_actor: float = 3e-4
    lr_critic: float = 1e-3
    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_epsilon: float = 0.2
    entropy_coef: float = 0.01
    value_loss_coef: float = 0.5
    max_grad_norm: float = 0.5
    update_epochs: int = 10
    batch_size: int = 32
    memory_size: int = 1000

@dataclass
class TradingConfig:
    """交易配置"""
    initial_capital: float = 100000.0
    max_position_size: float = 0.8
    trade_fee: float = 0.0001

# ==================== PPO网络 ====================
class PPONetwork(nn.Module):
    """PPO网络：Actor-Critic架构"""
    
    def __init__(self, state_dim: int, action_dim: int, hidden_dim: int = 64):
        super(PPONetwork, self).__init__()
        
        # 共享特征层
        self.feature_layer = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU()
        )
        
        # Actor网络
        self.actor = nn.Sequential(
            nn.Linear(hidden_dim // 2, action_dim),
            nn.Softmax(dim=-1)
        )
        
        # Critic网络
        self.critic = nn.Linear(hidden_dim // 2, 1)
        
        # 初始化权重
        self._init_weights()
        
    def _init_weights(self):
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.normal_(module.weight, std=0.1)
                nn.init.constant_(module.bias, 0.0)
    
    def forward(self, state: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        features = self.feature_layer(state)
        action_probs = self.actor(features)
        state_value = self.critic(features)
        return action_probs, state_value
    
    def get_action(self, state: torch.Tensor, deterministic: bool = False):
        action_probs, state_value = self.forward(state)
        
        if deterministic:
            action = torch.argmax(action_probs, dim=-1)
        else:
            dist = torch.distributions.Categorical(action_probs)
            action = dist.sample()
        
        log_prob = torch.log(action_probs.gather(1, action.unsqueeze(1))).squeeze()
        return action.item(), log_prob, state_value

# ==================== PPO训练器 ====================
class PPOTrainer:
    """PPO算法训练器"""
    
    def __init__(self, config: PPOConfig):
        self.config = config
        self.device = torch.device("cpu")
        
        # 初始化网络
        self.network = PPONetwork(
            state_dim=config.state_dim,
            action_dim=config.action_dim,
            hidden_dim=config.hidden_dim
        ).to(self.device)
        
        # 优化器
        self.optimizer = optim.Adam([
            {'params': self.network.actor.parameters(), 'lr': config.lr_actor},
            {'params': self.network.critic.parameters(), 'lr': config.lr_critic}
        ])
        
        # 经验回放
        self.memory = deque(maxlen=config.memory_size)
        self.Transition = namedtuple('Transition', 
                                     ['state', 'action', 'reward', 'next_state', 'done', 'log_prob', 'value'])
    
    def store_transition(self, state, action, reward, next_state, done, log_prob, value):
        self.memory.append(self.Transition(
            state=state, action=action, reward=reward,
            next_state=next_state, done=done, log_prob=log_prob, value=value
        ))
    
    def update(self) -> Dict:
        if len(self.memory) < self.config.batch_size:
            return {}
        
        # 采样
        batch = random.sample(self.memory, min(self.config.batch_size, len(self.memory)))
        
        states = torch.FloatTensor([t.state for t in batch]).to(self.device)
        actions = torch.LongTensor([t.action for t in batch]).to(self.device)
        rewards = torch.FloatTensor([t.reward for t in batch]).to(self.device)
        old_log_probs = torch.FloatTensor([t.log_prob for t in batch]).to(self.device)
        
        # 计算优势（简化版）
        advantages = rewards - rewards.mean()
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)
        
        # PPO更新
        actor_loss_total = 0
        critic_loss_total = 0
        
        for _ in range(self.config.update_epochs):
            action_probs, state_values = self.network(states)
            dist = torch.distributions.Categorical(action_probs)
            
            new_log_probs = dist.log_prob(actions)
            ratio = torch.exp(new_log_probs - old_log_probs.detach())
            
            # Actor损失
            surr1 = ratio * advantages.detach()
            surr2 = torch.clamp(ratio, 1 - self.config.clip_epsilon, 1 + self.config.clip_epsilon) * advantages.detach()
            actor_loss = -torch.min(surr1, surr2).mean()
            
            # Critic损失
            critic_loss = F.mse_loss(state_values.squeeze(), rewards.detach())
            
            # 更新
            total_loss = actor_loss + self.config.value_loss_coef * critic_loss
            
            self.optimizer.zero_grad()
            total_loss.backward()
            nn.utils.clip_grad_norm_(self.network.parameters(), self.config.max_grad_norm)
            self.optimizer.step()
            
            actor_loss_total += actor_loss.item()
            critic_loss_total += critic_loss.item()
        
        return {
            'actor_loss': actor_loss_total / self.config.update_epochs,
            'critic_loss': critic_loss_total / self.config.update_epochs
        }

    def update_episode(self, transitions: list) -> Dict:
        """②-2 根因修复（迭代5）：标准 PPO 批量更新。
        旧 update() 缺陷：advantages = rewards - rewards.mean()（非 GAE）、
        critic 学单步奖励而非累积回报、熵正则从未生效、随机采样破坏轨迹顺序。
        本方法：① 按 episode 顺序组织（调用方保证 transitions 时间连续）；
        ② GAE 优势估计（critic 参与）；③ critic 学累积回报 returns；
        ④ 熵正则生效（entropy_coef）；⑤ mini-batch 多轮更新。"""
        n = len(transitions)
        if n < self.config.batch_size:
            return {}
        states = torch.FloatTensor([t[0] for t in transitions]).to(self.device)
        actions = torch.LongTensor([t[1] for t in transitions]).to(self.device)
        rewards = torch.FloatTensor([t[2] for t in transitions]).to(self.device)
        next_states = torch.FloatTensor([t[3] for t in transitions]).to(self.device)
        dones = torch.FloatTensor([1.0 if t[4] else 0.0 for t in transitions]).to(self.device)
        old_log_probs = torch.FloatTensor([t[5] for t in transitions]).to(self.device)

        # GAE 优势估计（标准公式）
        with torch.no_grad():
            _, values = self.network(states)
            _, next_values = self.network(next_states)
            values = values.squeeze()
            next_values = next_values.squeeze()
            deltas = rewards + self.config.gamma * next_values * (1 - dones) - values
            advantages = torch.zeros_like(deltas)
            gae = 0.0
            for t in reversed(range(n)):
                gae = deltas[t] + self.config.gamma * self.config.gae_lambda * (1 - dones[t]) * gae
                advantages[t] = gae
            returns = advantages + values  # critic 学习目标：累积回报

        actor_loss_total = critic_loss_total = 0.0
        for _ in range(self.config.update_epochs):
            idx = torch.randperm(n)[:self.config.batch_size]
            b_states, b_actions = states[idx], actions[idx]
            b_adv, b_ret = advantages[idx], returns[idx]
            b_old = old_log_probs[idx]

            action_probs, state_values = self.network(b_states)
            dist = torch.distributions.Categorical(action_probs)
            new_log_probs = dist.log_prob(b_actions)
            entropy = dist.entropy().mean()
            ratio = torch.exp(new_log_probs - b_old.detach())

            # 标准化优势（批内）
            b_adv = (b_adv - b_adv.mean()) / (b_adv.std() + 1e-8)

            surr1 = ratio * b_adv.detach()
            surr2 = torch.clamp(ratio, 1 - self.config.clip_epsilon,
                                1 + self.config.clip_epsilon) * b_adv.detach()
            actor_loss = -torch.min(surr1, surr2).mean()
            # 熵正则（②-2 根因修复：防止策略坍缩到单一动作）
            actor_loss = actor_loss - self.config.entropy_coef * entropy
            critic_loss = F.mse_loss(state_values.squeeze(), b_ret.detach())

            total_loss = actor_loss + self.config.value_loss_coef * critic_loss
            self.optimizer.zero_grad()
            total_loss.backward()
            nn.utils.clip_grad_norm_(self.network.parameters(), self.config.max_grad_norm)
            self.optimizer.step()

            actor_loss_total += actor_loss.item()
            critic_loss_total += critic_loss.item()

        return {'actor_loss': actor_loss_total / self.config.update_epochs,
                'critic_loss': critic_loss_total / self.config.update_epochs}

# ==================== 交易代理 ====================
class TradingAgent:
    """简化的交易代理"""
    
    def __init__(self, initial_capital: float = 100000.0):
        self.config = TradingConfig(initial_capital=initial_capital)
        self.ppo_config = PPOConfig()
        self.trainer = PPOTrainer(self.ppo_config)
        
        # 账户状态
        self.capital = self.config.initial_capital
        self.position = 0.0  # 持仓数量
        self.position_value = 0.0
        self.entry_price = 0.0
        
        # 历史记录
        self.price_history = deque(maxlen=100)
        self.trade_history = []
        self.balance_history = [self.capital]
        
        # 统计
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0

        # 预训练标记（FIX T4-20261020 审计说明）：
        # 本类当前不加载任何离线训练权重（工程内无 checkpoint 文件、环境缺 torch），
        # 默认未训练。未训练时在线路径强制 hold 是安全设计，不允许用未收敛网络随机开仓。
        # 接通训练/加载管线（需先有训练产物）属后续增强，不在本轮 bug 修复范围。
        self.is_trained = False
        self._hold_reason = 'not_trained_no_weights'  # 审计可见：恒 hold 的原因

        logger.info("交易代理初始化完成")

    def load_weights(self, path: str):
        """FIX T5b-20261020 训练管线：加载训练权重，启用真实交易能力。
        权重由 core\\train_ml_strategies.py 训练产生（weights\\ppo_network.pt）。"""
        import os as _os
        if not _os.path.exists(path):
            raise FileNotFoundError(f'权重文件不存在: {path}')
        state = torch.load(path, map_location='cpu')
        self.trainer.network.load_state_dict(state)
        self.is_trained = True
        self._hold_reason = 'trained'
        logger.info(f"已加载训练权重 {path}，交易能力启用")
    
    def _compute_state(self, price: float) -> np.ndarray:
        """计算状态向量"""
        state = np.zeros(self.ppo_config.state_dim)
        
        try:
            # 价格特征
            if len(self.price_history) > 0:
                prev_price = self.price_history[-1]
                state[0] = (price - prev_price) / prev_price if prev_price > 0 else 0.0
                
                if len(self.price_history) >= 5:
                    returns = [
                        (self.price_history[i] - self.price_history[i-1]) / self.price_history[i-1]
                        for i in range(1, len(self.price_history))
                    ]
                    state[1] = np.mean(returns) if returns else 0.0
                    state[2] = np.std(returns) if returns else 0.0
            
            # 持仓状态
            total_value = self.capital + self.position_value
            state[3] = self.position_value / total_value if total_value > 0 else 0.0
            state[4] = self.capital / total_value if total_value > 0 else 0.0

            # ②-2 迭代2：增强技术特征（利用 state_dim=20 的空槽 5-19，网络架构不变）
            hist = list(self.price_history)  # deque 不支持切片，先转 list
            if len(hist) >= 21:
                # 动量
                state[5] = (price - hist[-6]) / hist[-6] if hist[-6] > 0 else 0.0      # 5-bar 动量
                state[6] = (price - hist[-21]) / hist[-21] if hist[-21] > 0 else 0.0   # 20-bar 动量
                # 均线偏离
                ma20 = float(np.mean(hist[-20:]))
                state[7] = (price - ma20) / ma20 if ma20 > 0 else 0.0                 # vs MA20
                if len(hist) >= 61:
                    ma60 = float(np.mean(hist[-60:]))
                    state[8] = (price - ma60) / ma60 if ma60 > 0 else 0.0             # vs MA60
                    # 波动率比：近期/长期
                    r = np.diff(hist[-61:]) / hist[-61:-1]  # 60 个收益率（差分61-1）
                    std_short = float(np.std(r[-5:])) if len(r) >= 5 else 0.0
                    std_long = float(np.std(r))
                    state[9] = (std_short / std_long - 1.0) if std_long > 1e-9 else 0.0
                    # 60-bar 区间位置（0=区间低点，1=区间高点）
                    lo, hi = float(np.min(hist[-60:])), float(np.max(hist[-60:]))
                    state[10] = (price - lo) / (hi - lo) if hi > lo else 0.0
                    state[11] = (hi - price) / (hi - lo) if hi > lo else 0.0

            # 归一化
            state = np.clip(state, -1.0, 1.0)
            
        except Exception as e:
            logger.error(f"状态计算错误: {e}")
        
        return state
    
    def _compute_reward(self, price: float, next_price: float, action: int) -> float:
        """计算奖励（FIX T5b-20261020 训练管线配套）：
        原实现卖出无实现收益奖励、交易惩罚仅 0.01 → 训练数据全为上涨股时
        PPO 收敛到「全 buy 不卖」。修复：① 卖出按 entry_price 给实现收益
        奖励（买卖对称）；② 交易惩罚放大到 0.5，抑制无意义开仓。"""
        reward = 0.0

        # 持仓收益
        if self.position > 0:
            profit = self.position * (next_price - price)
            reward += profit / self.config.initial_capital * 100.0

        # 买卖对称信号 + 交易惩罚（FIX T5b；②-2 迭代1：惩罚 0.5 -> 0.05）
        # 0.5 惩罚 >> 持仓收益(缩放100后每bar约0.05-0.3) -> PPO 学"最优=不动"。
        # 降到 0.05 使交易惩罚与持仓收益同量级，鼓励产生真实交易后再看质量。
        # ②-2 迭代4：空卖漏洞——position=0 时的 sell 动作不产生真实成交，
        #   原奖励仍给 0.05 轻罚，导致 PPO 学「只喊卖不真卖」。
        #   修复：空卖加重罚 0.5；只有真实卖出（有持仓）才给实现收益奖励。
        if action == 2:  # 买入：支付成本
            reward -= 0.05
        elif action == 0:  # 卖出
            if self.position > 0 and self.entry_price > 0:  # 真实卖出
                realized = (price - self.entry_price) / self.entry_price
                reward += realized * 100.0
                reward -= 0.05
            else:  # 空卖：无意义动作，重罚
                reward -= 0.5

        return reward
    
    def update(self, price: float) -> str:
        """
        主更新函数
        Args:
            price: 当前价格
        Returns:
            action: 执行的动作
        """
        self.price_history.append(price)
        
        # 更新持仓市值
        self.position_value = self.position * price
        
        # 获取状态
        state = self._compute_state(price)

        # ============================================================
        # 在线推理路径（逐bar调用）——修复随机 next_price 致命 bug
        # ------------------------------------------------------------
        # 原代码 L282: next_price = price * (1 + np.random.normal(0, 0.001))
        # 问题：在线逐bar交易中，"下一个价格"是未来数据，用随机数冒充会导致：
        #   1) _compute_reward 拿到的 reward 是噪声
        #   2) next_state 由噪声价格推出，也是噪声
        #   3) store_transition 把 (state, action, noisy_reward, noisy_next_state)
        #      灌入经验池，trainer.update() 每bar都拿噪声做梯度下降，
        #      PPO 网络在学噪声，ML 训练完全无效。
        # 修复原则：
        #   * 在线路径只做"动作推理"，不做"经验存储 + 网络更新"——
        #     reward/next_state/store_transition/update 全部跳过；
        #   * 若未加载预训练权重（self.is_trained=False），强制 hold，
        #     不允许未收敛网络随机买卖；
        #   * 若已加载预训练权重，用 deterministic=True 做贪心推理，
        #     仍不做在线训练（在线训练会引入分布外样本、破坏已学策略）。
        # ============================================================
        if not self.is_trained:
            # 未预训练：以 hold 为主，不执行买/卖，也不做任何经验存储或网络更新
            action_str = 'hold'
        else:
            # 已预训练：仅做动作推理（no_grad + deterministic），不做在线训练
            with torch.no_grad():
                state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.trainer.device)
                action, _, _ = self.trainer.network.get_action(state_tensor, deterministic=True)

            if action == 2:  # 买入
                self._execute_buy(price)
                action_str = 'buy'
            elif action == 0:  # 卖出
                self._execute_sell(price)
                action_str = 'sell'
            else:
                action_str = 'hold'

        # 记录余额
        self.balance_history.append(self.capital + self.position_value)

        return action_str
    
    def _execute_buy(self, price: float):
        """执行买入"""
        if self.capital > price * 10:  # 至少可以买10股
            available_capital = self.capital * self.config.max_position_size
            shares = int(available_capital / price)
            
            if shares > 0:
                cost = shares * price
                fee = cost * self.config.trade_fee
                
                self.capital -= (cost + fee)
                self.position += shares
                self.entry_price = price
                
                self.total_trades += 1
                self.trade_history.append({
                    'type': 'buy',
                    'price': price,
                    'shares': shares,
                    'cost': cost,
                    'fee': fee
                })
    
    def _execute_sell(self, price: float):
        """执行卖出"""
        if self.position > 0:
            proceeds = self.position * price
            fee = proceeds * self.config.trade_fee
            profit = proceeds - fee - self.position * self.entry_price
            
            self.capital += (proceeds - fee)
            
            if profit > 0:
                self.winning_trades += 1
            else:
                self.losing_trades += 1
            
            self.trade_history.append({
                'type': 'sell',
                'price': price,
                'shares': self.position,
                'proceeds': proceeds,
                'fee': fee,
                'profit': profit
            })
            
            self.position = 0
            self.position_value = 0
            self.total_trades += 1
    
    def get_performance(self) -> Dict:
        """获取性能指标"""
        total_value = self.capital + self.position_value
        total_return = (total_value - self.config.initial_capital) / self.config.initial_capital
        
        # 计算夏普比率
        if len(self.balance_history) > 10:
            returns = np.diff(self.balance_history) / self.balance_history[:-1]
            daily_returns = np.array(returns).reshape(-1, min(390, len(returns))).sum(axis=1)
            if len(daily_returns) > 0:
                mean_return = np.mean(daily_returns)
                std_return = np.std(daily_returns)
                sharpe_ratio = mean_return / std_return * np.sqrt(252) if std_return > 0 else 0
            else:
                sharpe_ratio = 0
        else:
            sharpe_ratio = 0
        
        # 计算最大回撤
        if len(self.balance_history) > 1:
            peak = np.maximum.accumulate(self.balance_history)
            drawdown = (peak - self.balance_history) / peak
            max_drawdown = np.max(drawdown)
        else:
            max_drawdown = 0
        
        win_rate = self.winning_trades / self.total_trades if self.total_trades > 0 else 0
        
        return {
            'total_value': total_value,
            'capital': self.capital,
            'position_value': self.position_value,
            'total_return': total_return,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'total_trades': self.total_trades,
            'win_rate': win_rate
        }

    def get_param_space(self) -> dict:
        """获取PPO参数搜索空间"""
        return {
            'state_dim': {'type': 'choice', 'values': [10, 20, 30, 40], 'default': 20},
            'hidden_dim': {'type': 'choice', 'values': [32, 64, 128, 256], 'default': 64},
            'lr_actor': {'type': 'log_uniform', 'min': 1e-5, 'max': 1e-2, 'default': 3e-4},
            'lr_critic': {'type': 'log_uniform', 'min': 1e-5, 'max': 1e-2, 'default': 1e-3},
            'gamma': {'type': 'uniform', 'min': 0.90, 'max': 0.999, 'default': 0.99},
        }

    def get_adaptive_params(self, volatility: float) -> dict:
        """根据市场波动调整探索率"""
        if volatility > 0.02:
            exploration = 0.25
        elif volatility > 0.01:
            exploration = 0.15
        else:
            exploration = 0.10
        return {
            'lr_actor': self.ppo_config.lr_actor * (1.2 if volatility > 0.015 else 0.8),
            'lr_critic': self.ppo_config.lr_critic * (1.2 if volatility > 0.015 else 0.8),
            'gamma': 0.95 if volatility > 0.02 else 0.99,
            'exploration_rate': exploration,
        }

    def apply_adaptive_params(self, params: dict):
        """应用自适应参数"""
        if 'lr_actor' in params:
            self.ppo_config.lr_actor = params['lr_actor']
            for pg in self.trainer.optimizer.param_groups:
                if 'actor' in str(pg.get('params', [])):
                    pg['lr'] = params['lr_actor']
        if 'lr_critic' in params:
            self.ppo_config.lr_critic = params['lr_critic']
        if 'gamma' in params:
            self.ppo_config.gamma = params['gamma']
        if 'state_dim' in params:
            self.ppo_config.state_dim = params['state_dim']
        if 'hidden_dim' in params:
            self.ppo_config.hidden_dim = params['hidden_dim']

    def update_price(self, current_price: float, data=None) -> dict:
        """FIX T5-20261020 协议接口：逐bar驱动。
        复用 update() 决策（未预训练强制 hold、已预训练贪心推理），
        输出加载器可识别的标准信号 dict。"""
        action = self.update(float(current_price))
        return {'action': action, 'price': current_price,
                'balance': self.capital + self.position_value,
                'position': self.position, 'signal': action}

# ==================== 测试 ====================
def test_trading_agent():
    """测试交易代理"""
    print("=" * 80)
    print("PPO量化交易策略测试")
    print("=" * 80)
    
    # 市场类型配置
    market_configs = {
        'range_bound': {'mean': 0, 'std': 0.001},
        'trending_up': {'mean': 0.0005, 'std': 0.001},
        'trending_down': {'mean': -0.0005, 'std': 0.001},
        'volatile': {'mean': 0, 'std': 0.002}
    }
    
    results = []
    
    for market_name, config in market_configs.items():
        print(f"\n测试市场: {market_name}")
        print("-" * 80)
        
        # 创建代理
        agent = TradingAgent(initial_capital=100000.0)
        
        # 生成测试数据（30天，每天390分钟）
        np.random.seed(42)
        num_periods = 30 * 390
        base_price = 100.0
        
        returns = np.random.normal(config['mean'], config['std'], num_periods)
        prices = base_price * np.cumprod(1 + returns)
        
        # 运行策略
        for i, price in enumerate(prices):
            agent.update(price)
            
            if (i + 1) % 3900 == 0:  # 每10天输出一次
                perf = agent.get_performance()
                print(f"  进度 {i+1}/{num_periods}, 价值 {perf['total_value']:.0f}, 收益率 {perf['total_return']:.2%}")
        
        # 获取最终性能
        perf = agent.get_performance()
        results.append({
            '市场类型': market_name,
            '最终价值': perf['total_value'],
            '收益率': perf['total_return'],
            '夏普比率': perf['sharpe_ratio'],
            '最大回撤': perf['max_drawdown'],
            '交易次数': perf['total_trades'],
            '胜率': perf['win_rate'],
            '日均交易': perf['total_trades'] / 30
        })
        
        print(f"  最终价值: {perf['total_value']:.0f}")
        print(f"  收益率: {perf['total_return']:.2%}")
        print(f"  夏普比率: {perf['sharpe_ratio']:.2f}")
        print(f"  最大回撤: {perf['max_drawdown']:.2%}")
        print(f"  交易次数: {perf['total_trades']}")
        print(f"  胜率: {perf['win_rate']:.2%}")
    
    # 输出汇总
    print("\n" + "=" * 80)
    print("测试结果汇总")
    print("=" * 80)
    df = pd.DataFrame(results)
    print(df.to_string(formatters={
        '最终价值': '{:,.0f}'.format,
        '收益率': '{:.2%}'.format,
        '夏普比率': '{:.2f}'.format,
        '最大回撤': '{:.2%}'.format,
        '胜率': '{:.2%}'.format,
        '日均交易': '{:.1f}'.format
    }))
    
    df.to_csv('ppo_trading_results.csv', index=False, encoding='utf-8-sig')
    print("\n✓ 结果已保存到 ppo_trading_results.csv")

if __name__ == "__main__":
    test_trading_agent()
