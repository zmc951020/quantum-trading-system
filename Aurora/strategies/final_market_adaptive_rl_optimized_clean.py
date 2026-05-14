#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件名: final_market_adaptive.py
描述: 基于PPO算法的自适应市场交易策略
作者: 量化交易策略专家
版本: 3.0
"""

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
from collections import deque, namedtuple
import random
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
    # 网络参数
    state_dim: int = 20  # 状态空间维度
    action_dim: int = 3  # 动作空间维度（买入、卖出、持有）
    hidden_dim: int = 256  # 隐藏层维度
    
    # PPO超参数
    lr_actor: float = 3e-4  # Actor学习率
    lr_critic: float = 1e-3  # Critic学习率
    gamma: float = 0.99  # 折扣因子
    gae_lambda: float = 0.95  # GAE参数
    clip_epsilon: float = 0.2  # PPO裁剪参数
    entropy_coef: float = 0.01  # 熵正则化系数
    value_loss_coef: float = 0.5  # 价值损失系数
    max_grad_norm: float = 0.5  # 梯度裁剪
    update_epochs: int = 10  # 每次更新轮数
    batch_size: int = 64  # 批次大小
    memory_size: int = 10000  # 经验回放大小
    
    # 训练参数
    target_kl: float = 0.01  # KL散度目标
    use_gae: bool = True  # 是否使用GAE
    normalize_advantage: bool = True  # 是否标准化优势

@dataclass
class TradingConfig:
    """交易配置"""
    # 交易参数
    initial_capital: float = 100000.0  # 初始资金
    max_position_size: float = 0.95  # 最大仓位比例
    min_position_size: float = 0.01  # 最小仓位比例
    trade_fee: float = 0.0003  # 交易手续费
    slippage: float = 0.0001  # 滑点
    
    # 止损止盈参数
    stop_loss_atr_multiplier: float = 2.0  # 止损ATR倍数
    take_profit_atr_multiplier: float = 4.0  # 止盈ATR倍数
    trailing_stop_activation: float = 0.02  # 追踪止损激活阈值
    trailing_stop_distance: float = 0.01  # 追踪止损距离
    
    # 频率控制
    min_trades_per_day: int = 50  # 最小每日交易次数
    max_trades_per_day: int = 200  # 最大每日交易次数
    min_hold_time: int = 5  # 最小持仓时间（分钟）
    
    # 风险管理
    max_drawdown: float = 0.15  # 最大回撤
    risk_per_trade: float = 0.02  # 每笔交易风险
    volatility_window: int = 20  # 波动率计算窗口

# ==================== PPO网络结构 ====================
class PPONetwork(nn.Module):
    """PPO网络：Actor-Critic架构"""
    
    def __init__(self, state_dim: int, action_dim: int, hidden_dim: int = 256):
        super(PPONetwork, self).__init__()
        
        # 共享特征提取层
        self.feature_layer = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.1),
            
            nn.Linear(hidden_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.1),
            
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.LayerNorm(hidden_dim // 2),
            nn.ReLU()
        )
        
        # Actor网络（策略网络）
        self.actor = nn.Sequential(
            nn.Linear(hidden_dim // 2, hidden_dim // 4),
            nn.ReLU(),
            nn.Linear(hidden_dim // 4, action_dim),
            nn.Softmax(dim=-1)
        )
        
        # Critic网络（价值网络）
        self.critic = nn.Sequential(
            nn.Linear(hidden_dim // 2, hidden_dim // 4),
            nn.ReLU(),
            nn.Linear(hidden_dim // 4, 1)
        )
        
        # 初始化权重
        self._init_weights()
        
    def _init_weights(self):
        """初始化网络权重"""
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.orthogonal_(module.weight, gain=np.sqrt(2))
                nn.init.constant_(module.bias, 0)
                
    def forward(self, state: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        前向传播
        Args:
            state: 状态张量
        Returns:
            action_probs: 动作概率分布
            state_value: 状态价值
        """
        features = self.feature_layer(state)
        action_probs = self.actor(features)
        state_value = self.critic(features)
        return action_probs, state_value
    
    def get_action(self, state: torch.Tensor, deterministic: bool = False) -> Tuple[int, torch.Tensor, torch.Tensor]:
        """
        获取动作
        Args:
            state: 状态张量
            deterministic: 是否确定性选择
        Returns:
            action: 选择的动作
            log_prob: 动作的对数概率
            state_value: 状态价值
        """
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
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
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
        
        # 经验回放缓冲区
        self.memory = deque(maxlen=config.memory_size)
        self.Transition = namedtuple('Transition', 
                                   ['state', 'action', 'reward', 'next_state', 'done', 'log_prob', 'value'])
        
        # 训练统计
        self.training_stats = {
            'episode_rewards': [],
            'episode_lengths': [],
            'actor_losses': [],
            'critic_losses': [],
            'entropy_losses': []
        }
        
        logger.info(f"PPO训练器初始化完成，使用设备: {self.device}")
        
    def store_transition(self, state, action, reward, next_state, done, log_prob, value):
        """存储经验"""
        transition = self.Transition(
            state=state,
            action=action,
            reward=reward,
            next_state=next_state,
            done=done,
            log_prob=log_prob,
            value=value
        )
        self.memory.append(transition)
        
    def compute_gae(self, rewards: List[float], values: List[torch.Tensor], dones: List[bool]) -> Tuple[List[torch.Tensor], List[torch.Tensor]]:
        """
        计算GAE（广义优势估计）
        Args:
            rewards: 奖励序列
            values: 价值序列
            dones: 终止标志序列
        Returns:
            advantages: 优势函数值
            returns: 折扣回报
        """
        advantages = []
        returns = []
        gae = 0
        
        values = [v.item() for v in values]
        
        for t in reversed(range(len(rewards))):
            if t == len(rewards) - 1:
                next_value = 0 if dones[t] else values[t]
            else:
                next_value = 0 if dones[t] else values[t + 1]
                
            delta = rewards[t] + self.config.gamma * next_value - values[t]
            gae = delta + self.config.gamma * self.config.gae_lambda * (1 - dones[t]) * gae
            
            advantages.insert(0, gae)
            returns.insert(0, gae + values[t])
            
        return advantages, returns
    
    def update(self) -> Dict[str, float]:
        """
        更新网络参数
        Returns:
            loss_dict: 损失字典
        """
        if len(self.memory) < self.config.batch_size:
            return {'actor_loss': 0, 'critic_loss': 0, 'entropy_loss': 0}
            
        # 准备训练数据
        batch = random.sample(self.memory, min(self.config.batch_size, len(self.memory)))
        
        states = torch.FloatTensor([t.state for t in batch]).to(self.device)
        actions = torch.LongTensor([t.action for t in batch]).to(self.device)
        rewards = [t.reward for t in batch]
        dones = [t.done for t in batch]
        old_log_probs = torch.FloatTensor([t.log_prob for t in batch]).to(self.device)
        old_values = [t.value for t in batch]
        
        # 计算GAE
        advantages, returns = self.compute_gae(rewards, old_values, dones)
        advantages = torch.FloatTensor(advantages).to(self.device)
        returns = torch.FloatTensor(returns).to(self.device)
        
        if self.config.normalize_advantage:
            advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)
            
        # PPO更新
        total_actor_loss = 0
        total_critic_loss = 0
        total_entropy_loss = 0
        
        for _ in range(self.config.update_epochs):
            # 前向传播
            action_probs, state_values = self.network(states)
            dist = torch.distributions.Categorical(action_probs)
            
            # 计算新对数概率
            new_log_probs = dist.log_prob(actions)
            entropy = dist.entropy().mean()
            
            # 计算比率
            ratio = torch.exp(new_log_probs - old_log_probs.detach())
            
            # PPO裁剪
            surr1 = ratio * advantages
            surr2 = torch.clamp(ratio, 1 - self.config.clip_epsilon, 1 + self.config.clip_epsilon) * advantages
            actor_loss = -torch.min(surr1, surr2).mean()
            
            # Critic损失
            value_pred = state_values.squeeze()
            critic_loss = F.mse_loss(value_pred, returns)
            
            # 总损失
            total_loss = (actor_loss + 
                         self.config.value_loss_coef * critic_loss - 
                         self.config.entropy_coef * entropy)
            
            # 反向传播
            self.optimizer.zero_grad()
            total_loss.backward()
            nn.utils.clip_grad_norm_(self.network.parameters(), self.config.max_grad_norm)
            self.optimizer.step()
            
            total_actor_loss += actor_loss.item()
            total_critic_loss += critic_loss.item()
            total_entropy_loss += entropy.item()
            
        # 记录训练统计
        avg_actor_loss = total_actor_loss / self.config.update_epochs
        avg_critic_loss = total_critic_loss / self.config.update_epochs
        avg_entropy_loss = total_entropy_loss / self.config.update_epochs
        
        self.training_stats['actor_losses'].append(avg_actor_loss)
        self.training_stats['critic_losses'].append(avg_critic_loss)
        self.training_stats['entropy_losses'].append(avg_entropy_loss)
        
        return {
            'actor_loss': avg_actor_loss,
            'critic_loss': avg_critic_loss,
            'entropy_loss': avg_entropy_loss
        }
    
    def save_model(self, path: str):
        """保存模型"""
        torch.save({
            'network_state_dict': self.network.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'training_stats': self.training_stats,
            'config': self.config
        }, path)
        logger.info(f"模型已保存到: {path}")
        
    def load_model(self, path: str):
        """加载模型"""
        if os.path.exists(path):
            checkpoint = torch.load(path, map_location=self.device)
            self.network.load_state_dict(checkpoint['network_state_dict'])
            self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
            self.training_stats = checkpoint['training_stats']
            logger.info(f"模型已从 {path} 加载")
            return True
        return False

# ==================== 增强的强化学习交易代理 ====================
class EnhancedRLTrader:
    """增强的强化学习交易代理"""
    
    def __init__(self, ppo_config: PPOConfig, trading_config: TradingConfig):
        self.ppo_config = ppo_config
        self.trading_config = trading_config
        self.trainer = PPOTrainer(ppo_config)
        
        # 交易状态
        self.capital = trading_config.initial_capital
        self.position = 0  # 当前持仓量
        self.position_value = 0  # 持仓市值
        self.total_trades = 0
        self.daily_trades = 0
        self.current_day = None
        
        # 持仓记录
        self.holdings = []  # 持仓历史
        self.trade_history = []  # 交易历史
        
        # 技术指标缓存
        self.price_history = deque(maxlen=100)
        self.volume_history = deque(maxlen=100)
        self.atr = 0  # 平均真实波幅
        self.volatility = 0  # 波动率
        
        # 止损止盈
        self.stop_loss_price = 0
        self.take_profit_price = 0
        self.trailing_stop_price = 0
        self.entry_price = 0
        
        # 性能统计
        self.performance_stats = {
            'total_return': 0,
            'sharpe_ratio': 0,
            'max_drawdown': 0,
            'win_rate': 0,
            'avg_profit': 0,
            'avg_loss': 0
        }
        
        logger.info("增强的RL交易代理初始化完成")
        
    def _compute_state(self, market_data: Dict) -> np.ndarray:
        """
        计算状态向量
        Args:
            market_data: 市场数据字典
        Returns:
            state: 状态向量
        """
        state = np.zeros(self.ppo_config.state_dim)
        
        try:
            # 1. 价格特征（0-4）
            current_price = market_data.get('close', 0)
            if len(self.price_history) > 0:
                prev_price = self.price_history[-1]
                if prev_price > 0:
                    price_change = (current_price - prev_price) / prev_price
                    state[0] = np.clip(price_change, -0.1, 0.1)  # 即时价格变化
                
                # 平均价格变化
                price_changes = []
                for i in range(1, len(self.price_history)):
                    if self.price_history[i-1] > 0:
                        price_changes.append((self.price_history[i] - self.price_history[i-1]) / self.price_history[i-1])
                if price_changes:
                    state[1] = np.mean(price_changes)
                
                # 相对位置
                avg_price = np.mean(self.price_history)
                if avg_price > 0:
                    state[2] = np.clip((current_price / avg_price - 1), -0.5, 0.5)
                
            # 2. 技术指标（5-9）
            if len(self.price_history) >= 20:
                # RSI
                gains = []
                losses = []
                for i in range(1, min(15, len(self.price_history))):
                    change = self.price_history[-i] - self.price_history[-i-1]
                    if change > 0:
                        gains.append(change)
                    else:
                        losses.append(abs(change))
                avg_gain = np.mean(gains) if gains else 0
                avg_loss = np.mean(losses) if losses else 0
                rs = avg_gain / (avg_loss + 1e-10)
                rsi = 100 - (100 / (1 + rs))
                state[5] = rsi / 100  # 归一化RSI
                
                # 波动率
                returns = []
                for i in range(1, len(self.price_history)):
                    if self.price_history[i-1] > 0:
                        returns.append((self.price_history[i] - self.price_history[i-1]) / self.price_history[i-1])
                if returns:
                    state[6] = np.std(returns) * np.sqrt(252)  # 年化波动率
                
                # 趋势强度
                short_ma = np.mean(list(self.price_history)[-5:])
                long_ma = np.mean(list(self.price_history))
                if long_ma > 0:
                    state[7] = (short_ma - long_ma) / long_ma  # 趋势强度
                
            # 3. 持仓状态（10-14）
            state[10] = self.position / (self.capital + self.position_value + 1e-10)  # 仓位比例
            state[11] = self.capital / self.trading_config.initial_capital  # 资金比例
            state[12] = self.total_trades / 1000  # 累计交易次数
            
            # 4. 风险指标（15-19）
            state[15] = min(self.volatility, 0.5)  # 当前波动率
            state[16] = self.atr / current_price if current_price > 0 else 0  # 相对ATR
            state[17] = self.performance_stats.get('max_drawdown', 0)  # 最大回撤
            state[18] = self.performance_stats.get('sharpe_ratio', 0)  # 夏普比率
            state[19] = min(self.total_trades / max(1, self.daily_trades), 10)  # 交易频率
            
        except Exception as e:
            logger.error(f"计算状态向量时出错: {e}")
            
        # 处理NaN和Inf值
        state = np.nan_to_num(state, nan=0.0, posinf=1.0, neginf=-1.0)
        # 限制值范围
        state = np.clip(state, -10, 10)
        
        return state
    
    def _compute_reward(self, action: int, price: float, next_price: float) -> float:
        """
        计算奖励
        Args:
            action: 执行的动作
            price: 当前价格
            next_price: 下一时刻价格
        Returns:
            reward: 奖励值
        """
        reward = 0
        
        try:
            # 1. 即时利润
            if self.position > 0:
                profit = self.position * (next_price - price)
                reward += profit / self.trading_config.initial_capital * 100  # 归一化
            
            # 2. 交易成本惩罚
            if action != 1:  # 非持有动作
                trade_value = self.capital * self.trading_config.trade_fee
                reward -= trade_value / self.trading_config.initial_capital * 10
            
            # 3. 风险惩罚
            if self.volatility > 0.02:  # 高波动率惩罚
                reward -= self.volatility * 5
                
            # 4. 频率奖励
            if self.daily_trades < self.trading_config.min_trades_per_day:
                reward += 0.01  # 鼓励交易
            elif self.daily_trades > self.trading_config.max_trades_per_day:
                reward -= 0.02  # 惩罚过度交易
                
            # 5. 多样性奖励
            if len(self.trade_history) > 0:
                recent_actions = [t['action'] for t in self.trade_history[-10:]]
                if len(set(recent_actions)) >= 2:  # 动作多样性
                    reward += 0.005
                    
        except Exception as e:
            logger.error(f"计算奖励时出错: {e}")
            
        return reward
    
    def _update_stop_loss_take_profit(self, price: float):
        """更新止损止盈价格"""
        if self.position > 0:
            # 基于ATR的动态止损
            self.stop_loss_price = self.entry_price - self.atr * self.trading_config.stop_loss_atr_multiplier
            self.take_profit_price = self.entry_price + self.atr * self.trading_config.take_profit_atr_multiplier
            
            # 追踪止损
            if price > self.entry_price * (1 + self.trading_config.trailing_stop_activation):
                new_stop = price * (1 - self.trading_config.trailing_stop_distance)
                self.trailing_stop_price = max(self.trailing_stop_price, new_stop)
                
    def _check_stop_loss_take_profit(self, price: float) -> bool:
        """检查是否触发止损止盈"""
        if self.position <= 0:
            return False
            
        # 检查止损
        if price <= self.stop_loss_price or price <= self.trailing_stop_price:
            logger.info(f"触发止损: 当前价格 {price:.2f}, 止损价格 {self.stop_loss_price:.2f}")
            return True
            
        # 检查止盈
        if price >= self.take_profit_price:
            logger.info(f"触发止盈: 当前价格 {price:.2f}, 止盈价格 {self.take_profit_price:.2f}")
            return True
            
        return False
    
    def execute_trade(self, action: int, price: float, volume: int = 0) -> Dict:
        """
        执行交易
        Args:
            action: 0-卖出, 1-持有, 2-买入
            price: 交易价格
            volume: 交易量
        Returns:
            trade_result: 交易结果
        """
        trade_result = {
            'action': action,
            'price': price,
            'volume': 0,
            'value': 0,
            'fee': 0,
            'profit': 0,
            'success': False
        }
        
        try:
            if action == 2:  # 买入
                # 计算可买入数量
                available_capital = self.capital * (1 - self.trading_config.trade_fee)
                max_shares = int(available_capital / price)
                
                if max_shares > 0:
                    # 限制仓位
                    max_position_value = (self.capital + self.position_value) * self.trading_config.max_position_size
                    current_position_value = self.position * price
                    available_position_value = max_position_value - current_position_value
                    
                    buy_value = min(available_capital, available_position_value)
                    buy_shares = int(buy_value / price)
                    
                    if buy_shares > 0:
                        fee = buy_shares * price * self.trading_config.trade_fee
                        self.position += buy_shares
                        self.capital -= buy_shares * price + fee
                        self.position_value = self.position * price
                        self.entry_price = price
                        
                        trade_result['volume'] = buy_shares
                        trade_result['value'] = buy_shares * price
                        trade_result['fee'] = fee
                        trade_result['success'] = True
                        
                        logger.debug(f"买入 {buy_shares} 股，价格 {price:.2f}，费用 {fee:.2f}")
                        
            elif action == 0:  # 卖出
                if self.position > 0:
                    sell_shares = self.position
                    fee = sell_shares * price * self.trading_config.trade_fee
                    profit = sell_shares * (price - self.entry_price) - fee
                    
                    self.capital += sell_shares * price - fee
                    self.position = 0
                    self.position_value = 0
                    
                    trade_result['volume'] = sell_shares
                    trade_result['value'] = sell_shares * price
                    trade_result['fee'] = fee
                    trade_result['profit'] = profit
                    trade_result['success'] = True
                    
                    logger.debug(f"卖出 {sell_shares} 股，价格 {price:.2f}，利润 {profit:.2f}")
                    
            # 更新交易统计
            if trade_result['success']:
                self.total_trades += 1
                self.daily_trades += 1
                self.trade_history.append(trade_result)
                
        except Exception as e:
            logger.error(f"执行交易时出错: {e}")
            
        return trade_result
    
    def step(self, market_data: Dict) -> Tuple[int, float, Dict]:
        """
        执行一步交易
        Args:
            market_data: 市场数据
        Returns:
            action: 执行的动作
            reward: 获得的奖励
            info: 额外信息
        """
        # 更新市场数据
        price = market_data.get('close', 0)
        self.price_history.append(price)
        
        # 计算技术指标
        if len(self.price_history) >= 2:
            returns = []
            for i in range(1, len(self.price_history)):
                if self.price_history[i-1] > 0:
                    returns.append((self.price_history[i] - self.price_history[i-1]) / self.price_history[i-1])
            if returns:
                self.volatility = np.std(returns)
            else:
                self.volatility = 0
            
        # 获取状态（总是计算状态）
        state = self._compute_state(market_data)
        log_prob = torch.tensor(0.0)
        value = torch.tensor(0.0)
        
        # 检查止损止盈
        if self._check_stop_loss_take_profit(price):
            action = 0  # 强制卖出
        else:
            # PPO选择动作
            with torch.no_grad():
                state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.trainer.device)
                action, log_prob, value = self.trainer.network.get_action(state_tensor)
                
        # 执行交易
        trade_result = self.execute_trade(action, price)
        
        # 更新止损止盈
        if action == 2:  # 买入后更新
            self._update_stop_loss_take_profit(price)
            
        # 计算奖励
        next_price = market_data.get('next_close', price)
        reward = self._compute_reward(action, price, next_price)
        
        # 存储经验（仅在有有效状态时）
        if not np.any(np.isnan(state)):
            self.trainer.store_transition(state, action, reward, state, False, log_prob, value)
        
        # 更新性能统计
        self._update_performance_stats()
        
        info = {
            'capital': self.capital,
            'position': self.position,
            'position_value': self.position_value,
            'total_trades': self.total_trades,
            'daily_trades': self.daily_trades,
            'trade_result': trade_result
        }
        
        return action, reward, info
    
    def _update_performance_stats(self):
        """更新性能统计"""
        try:
            if len(self.trade_history) > 0:
                profits = [t.get('profit', 0) for t in self.trade_history if 'profit' in t]
                if profits:
                    winning_trades = [p for p in profits if p > 0]
                    losing_trades = [p for p in profits if p < 0]
                    
                    self.performance_stats['win_rate'] = len(winning_trades) / len(profits) if profits else 0
                    self.performance_stats['avg_profit'] = np.mean(winning_trades) if winning_trades else 0
                    self.performance_stats['avg_loss'] = np.mean(losing_trades) if losing_trades else 0
                    
                    # 计算夏普比率
                    if len(profits) > 1:
                        # 修复reshape问题
                        profit_array = np.array(profits)
                        if len(profit_array) >= 390:
                            # 只取完整天数的数据
                            num_days = len(profit_array) // 390
                            daily_profits = profit_array[:num_days * 390].reshape(num_days, 390).sum(axis=1)
                        else:
                            daily_profits = profit_array
                        
                        std_daily = np.std(daily_profits)
                        if std_daily > 0:
                            self.performance_stats['sharpe_ratio'] = np.mean(daily_profits) / std_daily * np.sqrt(252)
                        else:
                            self.performance_stats['sharpe_ratio'] = 0
                    
                    # 计算最大回撤
                    portfolio_values = [self.capital + self.position_value]
                    peak = np.maximum.accumulate(portfolio_values)
                    drawdown = (peak - portfolio_values) / (peak + 1e-10)
                    self.performance_stats['max_drawdown'] = np.max(drawdown)
                    
                    # 计算总收益
                    self.performance_stats['total_return'] = (self.capital + self.position_value - 
                                                              self.trading_config.initial_capital) / self.trading_config.initial_capital
        except Exception as e:
            logger.error(f"更新性能统计时出错: {e}")
    
    def train(self, episodes: int = 100):
        """训练代理"""
        logger.info(f"开始训练，共 {episodes} 个周期")
        
        for episode in range(episodes):
            # 更新网络
            losses = self.trainer.update()
            
            if (episode + 1) % 10 == 0:
                logger.info(f"周期 {episode + 1}/{episodes} - "
                           f"Actor损失: {losses['actor_loss']:.4f}, "
                           f"Critic损失: {losses['critic_loss']:.4f}, "
                           f"熵: {losses['entropy_loss']:.4f}")
                
                # 保存模型
                self.trainer.save_model(f'ppo_trading_model_episode_{episode + 1}.pth')
                
        logger.info("训练完成")
        
    def get_summary(self) -> Dict:
        """获取代理状态摘要"""
        return {
            'capital': self.capital,
            'position': self.position,
            'position_value': self.position_value,
            'total_trades': self.total_trades,
            'daily_trades': self.daily_trades,
            'performance_stats': self.performance_stats,
            'trade_history_length': len(self.trade_history)
        }

# ==================== 最终市场自适应网格交易策略 ====================
class FinalMarketAdaptiveGrid:
    """最终市场自适应网格交易策略"""
    
    def __init__(self, base_price: float, initial_balance: float = 100000, enable_rl: bool = True):
        # 基础参数
        self.base_price = base_price
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.enable_rl = enable_rl
        
        # 网格参数
        self.grid_spacing = 0.004  # 网格间距
        self.grid_levels = 20  # 网格层数
        self.max_position_percentage = 0.8  # 最大持仓比例
        self.reserve_balance_percentage = 0.2  # 保留资金比例
        
        # 止损止盈参数
        self.take_profit_threshold = 0.025  # 止盈阈值
        self.stop_loss_threshold = 0.008  # 止损阈值
        
        # 交易统计
        self.total_trades = 0
        self.winning_trades = 0
        self.current_position = 0
        
        # 价格历史
        self.price_history = []
        self.balance_history = [initial_balance]
        
        # 强化学习代理
        if self.enable_rl:
            ppo_config = PPOConfig()
            trading_config = TradingConfig(initial_capital=initial_balance)
            self.rl_agent = EnhancedRLTrader(ppo_config, trading_config)
            
        logger.info("最终市场自适应网格交易策略初始化完成")
        
    def update_price(self, price: float) -> str:
        """
        更新价格并执行交易
        Args:
            price: 当前价格
        Returns:
            action: 执行的动作 ('buy', 'sell', 'hold')
        """
        self.price_history.append(price)
        
        action = 'hold'
        
        if self.enable_rl:
            # 使用强化学习代理
            market_data = {
                'close': price,
                'next_close': price * (1 + np.random.normal(0, 0.001))  # 预测下一个价格
            }
            
            rl_action, reward, info = self.rl_agent.step(market_data)
            
            # 映射RL动作
            if rl_action == 0:
                action = 'sell'
            elif rl_action == 2:
                action = 'buy'
            else:
                action = 'hold'
                
            # 更新交易统计
            if action in ['buy', 'sell']:
                self.total_trades += 1
                
        return action
    
    def get_performance(self) -> Dict:
        """获取策略性能指标"""
        if self.enable_rl:
            return self.rl_agent.get_summary()
        else:
            return {
                'total_trades': self.total_trades,
                'winning_trades': self.winning_trades,
                'current_balance': self.current_balance,
                'total_return': (self.current_balance - self.initial_balance) / self.initial_balance
            }

# ==================== 测试函数 ====================
def test_strategy():
    """测试策略"""
    print("=" * 80)
    print("PPO强化学习交易策略测试")
    print("=" * 80)
    
    # 创建策略
    strategy = FinalMarketAdaptiveGrid(base_price=100, initial_balance=100000, enable_rl=True)
    
    # 生成测试数据
    np.random.seed(42)
    prices = 100 * np.cumprod(1 + np.random.normal(0, 0.001, 1000))
    
    # 运行策略
    for price in prices:
        action = strategy.update_price(price)
    
    # 获取结果
    performance = strategy.get_performance()
    print(f"\n测试结果:")
    print(f"最终资金: {performance['capital']:.2f}")
    print(f"总交易次数: {performance['total_trades']}")
    print(f"总收益: {performance['performance_stats']['total_return']:.2%}")
    print(f"夏普比率: {performance['performance_stats']['sharpe_ratio']:.2f}")
    print(f"最大回撤: {performance['performance_stats']['max_drawdown']:.2%}")
    print(f"胜率: {performance['performance_stats']['win_rate']:.2%}")

if __name__ == "__main__":
    test_strategy()