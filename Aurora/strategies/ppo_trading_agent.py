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
        
        logger.info("交易代理初始化完成")
    
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
            
            # 归一化
            state = np.clip(state, -1.0, 1.0)
            
        except Exception as e:
            logger.error(f"状态计算错误: {e}")
        
        return state
    
    def _compute_reward(self, price: float, next_price: float, action: int) -> float:
        """计算奖励"""
        reward = 0.0
        
        # 持仓收益
        if self.position > 0:
            profit = self.position * (next_price - price)
            reward += profit / self.config.initial_capital * 100.0
        
        # 简单的交易惩罚（鼓励适当的交易频率）
        if action != 1:  # 非持有
            reward -= 0.01
        
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
        
        # PPO选择动作
        with torch.no_grad():
            state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.trainer.device)
            action, log_prob, value = self.trainer.network.get_action(state_tensor)
        
        # 执行交易
        next_price = price * (1 + np.random.normal(0, 0.001))  # 简化的下一个价格预测
        
        if action == 2:  # 买入
            self._execute_buy(price)
            action_str = 'buy'
        elif action == 0:  # 卖出
            self._execute_sell(price)
            action_str = 'sell'
        else:
            action_str = 'hold'
        
        # 计算奖励
        reward = self._compute_reward(price, next_price, action)
        
        # 存储经验
        next_state = self._compute_state(next_price)
        self.trainer.store_transition(state, action, reward, next_state, False, log_prob, value)
        
        # 更新网络
        self.trainer.update()
        
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
